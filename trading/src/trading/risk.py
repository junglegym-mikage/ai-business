"""損失管理：注文がリスク上限を守っているかを判定する（ペーパートレード専用）。

上限（初期値は模擬資金 5 万円に対する割合）:
- 1 トレードの最大損失（エントリーから損切りまでの損失額）: 資金の 2%
- 1 日の最大損失: 資金の 5%
  「その日の確定損益（手数料込み）＋ 保有ポジションの含み損益」で判定する。
  含み損益は取得時からの累計で数える（前日からの持ち越し分も含む＝保守的な扱い）。
  到達したらその日の新規・買い増し注文を拒否する（決済・縮小注文は許可）。
- 1 銘柄あたりの最大ポジション金額（約定後の想定）: 資金の 50%

1 トレードの損失は「約定後のポジション全体」で判定する。買い増しのときは、
新しい注文の損切り価格をポジション全体の損切り価格として扱い、
（平均取得価格 − 損切り価格）× 保有数量 が上限以内かを見る。

ポジションは銘柄ごとに「符号付き数量（買い＝正、空売り＝負）」と平均取得価格で持つ。
決済で数量が減り、確定損益が自動で日次損益に加算される。
ポジションを反転させる注文（買い 10 株保有中に売り 20 株など）は受け付けない。

日次の区切りは `start_new_day(日付)` に取引日を渡して行う。
同じ日・過去の日を渡してもリセットしない（呼び間違いで損失がゼロに戻るのを防ぐ）。

金額は Decimal で扱い、NaN・無限大などの不正値は拒否する。
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from decimal import Decimal

from trading.safety import assert_paper_mode

ZERO = Decimal(0)


def _finite_positive(value: Decimal) -> bool:
    return isinstance(value, Decimal) and value.is_finite() and value > 0


@dataclass(frozen=True)
class RiskLimits:
    capital_jpy: int = 50_000
    max_loss_per_trade_pct: Decimal = Decimal("0.02")
    max_daily_loss_pct: Decimal = Decimal("0.05")
    max_position_pct: Decimal = Decimal("0.50")

    def __post_init__(self) -> None:
        if not isinstance(self.capital_jpy, int) or self.capital_jpy <= 0:
            raise ValueError("capital_jpy は正の整数")
        for name in ("max_loss_per_trade_pct", "max_daily_loss_pct", "max_position_pct"):
            v = getattr(self, name)
            if not _finite_positive(v) or v > 1:
                raise ValueError(f"{name} は 0 より大きく 1 以下の Decimal")


@dataclass(frozen=True)
class Order:
    """注文。side は "buy" または "sell"。

    新規・買い増し（ポジションを増やす注文）には stop_price（損切り価格）が必須。
    決済・縮小注文では stop_price は不要（None）。
    """

    symbol: str
    side: str
    quantity: int
    price: Decimal
    stop_price: Decimal | None = None

    @property
    def signed_quantity(self) -> int:
        return self.quantity if self.side == "buy" else -self.quantity


@dataclass(frozen=True)
class Decision:
    accepted: bool
    reason: str = ""


@dataclass
class Position:
    quantity: int = 0  # 買い＝正、空売り＝負
    avg_price: Decimal = ZERO
    mark_price: Decimal = ZERO  # 含み損益の評価に使う直近価格
    stop_price: Decimal | None = None  # ポジション全体の損切り価格

    @property
    def unrealized_pnl(self) -> Decimal:
        if self.quantity == 0:
            return ZERO
        return (self.mark_price - self.avg_price) * self.quantity


class RiskManager:
    def __init__(self, limits: RiskLimits | None = None, trading_day: dt.date | None = None) -> None:
        self.limits = limits or RiskLimits()
        capital = Decimal(self.limits.capital_jpy)
        self.max_loss_per_trade = capital * self.limits.max_loss_per_trade_pct
        self.max_daily_loss = capital * self.limits.max_daily_loss_pct
        self.max_position_value = capital * self.limits.max_position_pct
        self.trading_day = trading_day or dt.date.today()
        self._positions: dict[str, Position] = {}
        self._daily_realized_pnl = ZERO

    # --- 参照 -------------------------------------------------------
    def position(self, symbol: str) -> Position:
        return self._positions.get(symbol, Position())

    @property
    def daily_realized_pnl(self) -> Decimal:
        return self._daily_realized_pnl

    @property
    def unrealized_pnl(self) -> Decimal:
        return sum((p.unrealized_pnl for p in self._positions.values()), ZERO)

    @property
    def daily_pnl(self) -> Decimal:
        """日次損失の判定に使う損益（確定＋含み）。"""
        return self._daily_realized_pnl + self.unrealized_pnl

    # --- 状態の更新 -------------------------------------------------
    def record_fill(self, order: Order) -> Decimal:
        """模擬約定を反映し、この約定で確定した損益を返す。

        check() で許可された注文だけを渡すこと。反転注文は例外にする。
        """
        invalid = self._validate_basic(order)
        if invalid:
            raise ValueError(invalid)
        pos = self._positions.setdefault(order.symbol, Position())
        delta = order.signed_quantity
        new_qty = pos.quantity + delta
        realized = ZERO

        if pos.quantity == 0 or (pos.quantity > 0) == (delta > 0):
            # 新規・買い増し：平均取得価格を更新
            total = pos.avg_price * abs(pos.quantity) + order.price * abs(delta)
            pos.avg_price = total / abs(new_qty)
            pos.stop_price = order.stop_price
        else:
            if abs(delta) > abs(pos.quantity):
                raise ValueError("ポジションを反転させる注文は受け付けない")
            # 決済・縮小：確定損益を計算
            closed = abs(delta)
            direction = 1 if pos.quantity > 0 else -1
            realized = (order.price - pos.avg_price) * closed * direction
            self._daily_realized_pnl += realized
            if new_qty == 0:
                pos.avg_price = ZERO

        pos.quantity = new_qty
        pos.mark_price = order.price
        if new_qty == 0:
            del self._positions[order.symbol]
        return realized

    def record_cost(self, amount: Decimal) -> None:
        """手数料・スリッページなどのコスト（正の値）を日次確定損益から差し引く。"""
        if not isinstance(amount, Decimal) or not amount.is_finite() or amount < 0:
            raise ValueError("コストは 0 以上の Decimal")
        self._daily_realized_pnl -= amount

    def update_mark(self, symbol: str, price: Decimal) -> None:
        """保有銘柄の評価価格を更新する（含み損益の計算用）。"""
        if not _finite_positive(price):
            raise ValueError("評価価格は正の Decimal")
        if symbol in self._positions:
            self._positions[symbol].mark_price = price

    def start_new_day(self, day: dt.date) -> bool:
        """取引日が進んだときだけ日次確定損益をリセットする。リセットしたら True。"""
        if day <= self.trading_day:
            return False
        self.trading_day = day
        self._daily_realized_pnl = ZERO
        return True

    # --- 判定 -------------------------------------------------------
    def check(self, order: Order) -> Decision:
        assert_paper_mode()

        invalid = self._validate_basic(order)
        if invalid:
            return Decision(False, invalid)

        pos = self.position(order.symbol)
        delta = order.signed_quantity
        new_qty = pos.quantity + delta
        reducing = pos.quantity != 0 and (pos.quantity > 0) != (delta > 0)

        if reducing:
            if abs(delta) > abs(pos.quantity):
                return Decision(False, "ポジションを反転させる注文は受け付けない（決済と新規に分ける）")
            return Decision(True, "決済・縮小注文")

        # ここから新規・買い増し
        stop_error = self._validate_stop(order)
        if stop_error:
            return Decision(False, stop_error)

        if -self.daily_pnl >= self.max_daily_loss:
            return Decision(False, f"1日の損失（確定＋含み）が上限 {self.max_daily_loss} 円に達しているため新規注文不可")

        loss = self.position_loss_at_stop(pos, order)
        if loss > self.max_loss_per_trade:
            return Decision(
                False, f"1トレードの想定損失（約定後のポジション全体）{loss} 円が上限 {self.max_loss_per_trade} 円を超過"
            )

        exposure = abs(new_qty) * order.price
        if exposure > self.max_position_value:
            return Decision(
                False, f"{order.symbol} の約定後ポジション {exposure} 円が上限 {self.max_position_value} 円を超過"
            )

        return Decision(True)

    @staticmethod
    def position_loss_at_stop(pos: Position, order: Order) -> Decimal:
        """新規・買い増しが約定した後、損切り価格で全量決済したときの損失（0 以上）。"""
        new_qty = pos.quantity + order.signed_quantity
        total = pos.avg_price * abs(pos.quantity) + order.price * order.quantity
        new_avg = total / abs(new_qty)
        loss = (new_avg - order.stop_price) * new_qty  # 買い: 正の数量, 空売り: 負の数量
        return max(loss, ZERO)

    @staticmethod
    def _validate_basic(order: Order) -> str:
        if not isinstance(order.symbol, str) or not order.symbol.strip():
            return "銘柄コードが空"
        if order.side not in ("buy", "sell"):
            return f"不明な売買区分: {order.side!r}"
        if not isinstance(order.quantity, int) or isinstance(order.quantity, bool) or order.quantity <= 0:
            return "数量は 1 以上の整数"
        if not _finite_positive(order.price):
            return "価格は正の有限な Decimal"
        return ""

    @staticmethod
    def _validate_stop(order: Order) -> str:
        if order.stop_price is None:
            return "新規・買い増し注文には損切り価格が必要"
        if not _finite_positive(order.stop_price):
            return "損切り価格は正の有限な Decimal"
        if order.side == "buy" and order.stop_price >= order.price:
            return "買いの損切り価格はエントリー価格より下"
        if order.side == "sell" and order.stop_price <= order.price:
            return "空売りの損切り価格はエントリー価格より上"
        return ""
