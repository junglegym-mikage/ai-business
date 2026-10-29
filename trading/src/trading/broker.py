"""ペーパートレード実行エンジン（模擬ブローカー）。

**注文の唯一の入口は `PaperBroker.submit()`。** ここで必ず
`assert_paper_mode()` → 停止状態の確認 → 重複注文の確認 → 損切りが設定できるか →
`RiskManager.check()` を通す。実際の証券会社には一切接続しない。

約定ルール（先読みをしないため）:
- 注文はその日の終値を見て出し、「次の営業日の始値」で約定する（`process_bar()` が処理）。
- 保有中の損切りは、日中の安値（空売りは高値）が損切り価格に届いたら損切り価格で約定。
  ただし始値の時点で損切り価格を飛び越えていたら（窓開け）、始値で約定する。
- 約定価格にはスリッページ（不利な方向）を加え、約定代金に手数料率を掛けたコストを日次損益から引く。
- 米国株は円換算して RiskManager に渡す。損切りの円換算には為替の不利な変動幅（fx_buffer）を見込む。

停止（halt）条件：日次損失上限に 2 営業日連続で到達／損失管理ルール違反（窓開けで 1 トレード上限を超過など）。
停止中は新規・買い増しを受け付けない（決済は受け付ける）。解除はオーナーが `resume()` で行う。
"""

from __future__ import annotations

import datetime as dt
from dataclasses import asdict, dataclass, field
from decimal import ROUND_DOWN, Decimal

from trading.risk import Order, RiskLimits, RiskManager
from trading.safety import assert_paper_mode

ZERO = Decimal(0)


@dataclass(frozen=True)
class Bar:
    date: dt.date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal


@dataclass(frozen=True)
class Instrument:
    symbol: str
    currency: str = "JPY"  # "JPY" または "USD"


@dataclass
class PendingOrder:
    client_id: str
    symbol: str
    side: str  # buy / sell
    quantity: int
    stop_distance: Decimal | None  # 新規・買い増しのみ：約定価格から損切りまでの幅（現地通貨）
    reason: str = ""


@dataclass
class StopOrder:
    side: str  # 決済方向（買い保有なら sell）
    quantity: int
    stop_price: Decimal  # 現地通貨


@dataclass
class Event:
    date: str
    kind: str
    symbol: str = ""
    detail: str = ""


@dataclass
class BrokerConfig:
    slippage_rate: Decimal = Decimal("0.0005")  # 片道 0.05%
    fx_buffer: Decimal = Decimal("0.03")  # 為替の不利な変動を 3% 見込む
    stop_orders_available: bool = True  # False = 損切り注文を置けない状況の模擬


class PaperBroker:
    def __init__(
        self,
        instruments: list[Instrument],
        limits: RiskLimits | None = None,
        config: BrokerConfig | None = None,
        start_day: dt.date | None = None,
    ) -> None:
        self.instruments = {i.symbol: i for i in instruments}
        self.limits = limits or RiskLimits()
        self.config = config or BrokerConfig()
        self.risk = RiskManager(self.limits, trading_day=start_day or dt.date(2000, 1, 1))
        self.cash = Decimal(self.limits.capital_jpy)
        self.pending: list[PendingOrder] = []
        self.stops: dict[str, StopOrder] = {}
        self.seen_client_ids: set[str] = set()
        self.events: list[Event] = []
        self.trades: list[dict] = []
        self.halted: str = ""
        self.limit_hit_streak = 0
        self.last_date: dt.date | None = None

    # ------------------------------------------------------------------ 入口
    def submit(self, order: PendingOrder, fx: Decimal = Decimal(1)) -> tuple[bool, str]:
        """注文を受け付ける唯一の入口。受け付けたら次の始値で約定する。"""
        assert_paper_mode()
        if order.symbol not in self.instruments:
            return self._reject(order, "未登録の銘柄")
        if order.client_id in self.seen_client_ids:
            return self._reject(order, "重複注文（同じ client_id）")
        pos = self.risk.position(order.symbol)
        signed = order.quantity if order.side == "buy" else -order.quantity
        increasing = pos.quantity == 0 or (pos.quantity > 0) == (signed > 0)
        if increasing:
            if self.halted:
                return self._reject(order, f"停止中のため新規不可: {self.halted}")
            if not self.config.stop_orders_available:
                return self._reject(order, "損切り注文を設定できないため新規不可")
            if order.stop_distance is None or order.stop_distance <= 0:
                return self._reject(order, "損切り幅がない新規注文は不可")
        self.seen_client_ids.add(order.client_id)
        self.pending.append(order)
        self._event("accepted", order.symbol, f"{order.side} {order.quantity} ({order.reason})")
        return True, ""

    def resume(self) -> None:
        """停止を解除する（オーナーの判断でのみ呼ぶ）。"""
        self.halted = ""
        self.limit_hit_streak = 0

    # ------------------------------------------------------------- 日次処理
    def process_day(self, day: dt.date, bars: dict[str, Bar], fx: Decimal) -> None:
        """1 営業日分の足を処理する：①日付更新 ②始値で待機注文を約定 ③損切り判定 ④評価更新 ⑤停止判定。"""
        assert_paper_mode()
        if self.last_date is not None and day <= self.last_date:
            raise ValueError(f"日付が進んでいない: {day} <= {self.last_date}")
        if self.last_date is not None:
            self._close_day(self.last_date)
        self.risk.start_new_day(day)
        self.last_date = day

        orders, self.pending = self.pending, []
        for order in orders:
            bar = bars.get(order.symbol)
            if bar is None:
                self.pending.append(order)  # その銘柄の足がない日（休場など）は持ち越す
                continue
            self._fill_at_open(day, order, bar, fx)

        for symbol, stop in list(self.stops.items()):
            bar = bars.get(symbol)
            if bar is not None:
                self._check_stop(day, symbol, stop, bar, fx)

        for symbol, bar in bars.items():
            if self.risk.position(symbol).quantity:
                self.risk.update_mark(symbol, self._jpy(symbol, bar.close, fx))


    def _close_day(self, day: dt.date) -> None:
        """前営業日の損益を確定させ、日次上限の連続到達を数える（次の日の処理の最初に呼ぶ）。"""
        if -self.risk.daily_pnl >= self.risk.max_daily_loss:
            self.limit_hit_streak += 1
            self._event("daily_limit_hit", detail=f"日次損益 {self.risk.daily_pnl}", day=day)
            if self.limit_hit_streak >= 2 and not self.halted:
                self._halt(day, "日次損失上限に2営業日連続で到達")
        else:
            self.limit_hit_streak = 0

    # ------------------------------------------------------------- 内部処理
    def _fill_at_open(self, day: dt.date, order: PendingOrder, bar: Bar, fx: Decimal) -> None:
        slip = self.config.slippage_rate
        price = bar.open * (1 + slip) if order.side == "buy" else bar.open * (1 - slip)
        pos = self.risk.position(order.symbol)
        signed = order.quantity if order.side == "buy" else -order.quantity
        increasing = pos.quantity == 0 or (pos.quantity > 0) == (signed > 0)

        stop_local = None
        stop_jpy = None
        if increasing:
            if self.halted:
                return self._event("cancelled", order.symbol, f"停止中のため取消: {self.halted}", day)
            if not self.config.stop_orders_available:
                return self._event("cancelled", order.symbol, "損切り注文を設定できないため取消", day)
            dist = order.stop_distance
            stop_local = price - dist if order.side == "buy" else price + dist
            if stop_local <= 0:
                return self._event("cancelled", order.symbol, "損切り価格が0以下", day)
            stop_jpy = self._stop_jpy(order.symbol, stop_local, fx, order.side)

        price_jpy = self._jpy(order.symbol, price, fx)
        notional = price_jpy * order.quantity
        if order.side == "buy" and increasing and notional + self._cost(notional) > self.cash:
            return self._event("cancelled", order.symbol, f"現金不足（必要 {notional:.0f} 円）", day)

        risk_order = Order(order.symbol, order.side, order.quantity, price_jpy, stop_jpy)
        decision = self.risk.check(risk_order)
        if not decision.accepted:
            return self._event("cancelled", order.symbol, f"約定時のリスク判定で拒否: {decision.reason}", day)

        realized = self.risk.record_fill(risk_order)
        cost = self._cost(notional)
        self.risk.record_cost(cost)
        self.cash += -notional - cost if order.side == "buy" else notional - cost
        self._event("filled", order.symbol, f"{order.side} {order.quantity} @ {price:.4f} ({order.reason})", day)
        self._log_trade(day, order.symbol, order.side, order.quantity, price, price_jpy, cost, realized, order.reason)

        new_qty = self.risk.position(order.symbol).quantity
        if new_qty == 0:
            self.stops.pop(order.symbol, None)
        elif increasing:
            self.stops[order.symbol] = StopOrder("sell" if new_qty > 0 else "buy", abs(new_qty), stop_local)
        else:
            self.stops[order.symbol].quantity = abs(new_qty)

    def _check_stop(self, day: dt.date, symbol: str, stop: StopOrder, bar: Bar, fx: Decimal) -> None:
        long = stop.side == "sell"
        hit = bar.low <= stop.stop_price if long else bar.high >= stop.stop_price
        if not hit:
            return
        gapped = bar.open <= stop.stop_price if long else bar.open >= stop.stop_price
        base = bar.open if gapped else stop.stop_price
        slip = self.config.slippage_rate
        price = base * (1 - slip) if long else base * (1 + slip)
        price_jpy = self._jpy(symbol, price, fx)
        pos = self.risk.position(symbol)
        trade_loss = (pos.avg_price - price_jpy) * pos.quantity  # 買い: 正の数量
        risk_order = Order(symbol, stop.side, stop.quantity, price_jpy)
        realized = self.risk.record_fill(risk_order)
        notional = price_jpy * stop.quantity
        cost = self._cost(notional)
        self.risk.record_cost(cost)
        self.cash += notional - cost if long else -notional - cost
        del self.stops[symbol]
        kind = "stop_gap" if gapped else "stop"
        self._event(kind, symbol, f"{stop.side} {stop.quantity} @ {price:.4f}", day)
        self._log_trade(day, symbol, stop.side, stop.quantity, price, price_jpy, cost, realized, kind)
        total_loss = trade_loss + cost
        if total_loss > self.risk.max_loss_per_trade:
            self._event("rule_violation", symbol, f"損切りの実損失 {total_loss:.0f} 円が上限超過（{kind}）", day)
            self._halt(day, f"{symbol} の実損失が1トレード上限を超過")

    def _stop_jpy(self, symbol: str, stop_local: Decimal, fx: Decimal, side: str) -> Decimal:
        """リスク判定用の損切り価格（円）。スリッページと為替の不利な変動を見込んで、より不利な側に置く。"""
        slip = self.config.slippage_rate
        stop = stop_local * (1 - slip) if side == "buy" else stop_local * (1 + slip)
        if self.instruments[symbol].currency == "JPY":
            return stop
        b = self.config.fx_buffer
        adverse = fx * (1 - b) if side == "buy" else fx * (1 + b)
        return stop * adverse

    def _jpy(self, symbol: str, price: Decimal, fx: Decimal) -> Decimal:
        return price if self.instruments[symbol].currency == "JPY" else price * fx

    def _cost(self, notional_jpy: Decimal) -> Decimal:
        return (notional_jpy * self.limits.est_cost_rate).quantize(Decimal("0.01"))

    def _halt(self, day: dt.date, reason: str) -> None:
        self.halted = reason
        self._event("halted", detail=reason, day=day)

    def _reject(self, order: PendingOrder, reason: str) -> tuple[bool, str]:
        self._event("rejected", order.symbol, reason)
        return False, reason

    def _event(self, kind: str, symbol: str = "", detail: str = "", day: dt.date | None = None) -> None:
        d = day or self.last_date
        self.events.append(Event(str(d) if d else "", kind, symbol, detail))

    def _log_trade(self, day, symbol, side, qty, price, price_jpy, cost, realized, reason) -> None:
        self.trades.append(
            {
                "date": str(day), "symbol": symbol, "side": side, "quantity": qty,
                "price": str(price.quantize(Decimal("0.0001"))), "price_jpy": str(price_jpy.quantize(Decimal("0.01"))),
                "cost_jpy": str(cost), "realized_jpy": str(realized.quantize(Decimal("0.01"))), "reason": reason,
            }
        )

    # ------------------------------------------------------------ 参照
    @property
    def equity(self) -> Decimal:
        """現金＋保有ポジションの評価額（円）。"""
        value = ZERO
        for sym in self.instruments:
            p = self.risk.position(sym)
            if p.quantity > 0:
                value += p.mark_price * p.quantity
            elif p.quantity < 0:
                value -= p.mark_price * -p.quantity
        return self.cash + value

    # ----------------------------------------------------- 保存と復元
    def to_dict(self) -> dict:
        return {
            "version": 1,
            "cash": str(self.cash),
            "trading_day": str(self.risk.trading_day),
            "last_date": str(self.last_date) if self.last_date else None,
            "daily_realized_pnl": str(self.risk.daily_realized_pnl),
            "positions": {
                s: {"quantity": p.quantity, "avg_price": str(p.avg_price), "mark_price": str(p.mark_price),
                    "stop_price": None if p.stop_price is None else str(p.stop_price)}
                for s in self.instruments if (p := self.risk.position(s)).quantity
            },
            "stops": {s: {"side": o.side, "quantity": o.quantity, "stop_price": str(o.stop_price)} for s, o in self.stops.items()},
            "pending": [
                {**asdict(o), "stop_distance": None if o.stop_distance is None else str(o.stop_distance)} for o in self.pending
            ],
            "seen_client_ids": sorted(self.seen_client_ids),
            "halted": self.halted,
            "limit_hit_streak": self.limit_hit_streak,
            "events": [asdict(e) for e in self.events],
            "trades": self.trades,
        }

    @classmethod
    def from_dict(
        cls, data: dict, instruments: list[Instrument], limits: RiskLimits | None = None, config: BrokerConfig | None = None
    ) -> "PaperBroker":
        if data.get("version") != 1:
            raise ValueError("未対応の状態ファイル")
        b = cls(instruments, limits, config, start_day=dt.date.fromisoformat(data["trading_day"]))
        b.cash = Decimal(data["cash"])
        b.last_date = dt.date.fromisoformat(data["last_date"]) if data["last_date"] else None
        b.risk.restore(
            positions={
                s: (v["quantity"], Decimal(v["avg_price"]), Decimal(v["mark_price"]),
                    None if v["stop_price"] is None else Decimal(v["stop_price"]))
                for s, v in data["positions"].items()
            },
            daily_realized_pnl=Decimal(data["daily_realized_pnl"]),
        )
        b.stops = {s: StopOrder(v["side"], v["quantity"], Decimal(v["stop_price"])) for s, v in data["stops"].items()}
        b.pending = [
            PendingOrder(**{**o, "stop_distance": None if o["stop_distance"] is None else Decimal(o["stop_distance"])})
            for o in data["pending"]
        ]
        b.seen_client_ids = set(data["seen_client_ids"])
        b.halted = data["halted"]
        b.limit_hit_streak = data["limit_hit_streak"]
        b.events = [Event(**e) for e in data["events"]]
        b.trades = list(data["trades"])
        return b


def size_position(risk_budget_jpy: Decimal, stop_distance_jpy: Decimal, price_jpy: Decimal, cap_jpy: Decimal) -> int:
    """損切り幅とリスク予算から株数を決める（切り捨て）。0 なら発注しない。"""
    if stop_distance_jpy <= 0 or price_jpy <= 0:
        return 0
    by_risk = (risk_budget_jpy / stop_distance_jpy).to_integral_value(rounding=ROUND_DOWN)
    by_cap = (cap_jpy / price_jpy).to_integral_value(rounding=ROUND_DOWN)
    return int(max(min(by_risk, by_cap), 0))


__all__ = ["Bar", "BrokerConfig", "Event", "Instrument", "PaperBroker", "PendingOrder", "StopOrder", "size_position", "field"]
