"""損失管理：注文がリスク上限を守っているかを判定する（ペーパートレード専用）。

上限（初期値は模擬資金 5 万円に対する割合）:
- 1 トレードの最大損失（エントリーから損切りまでの損失額）: 資金の 2%
- 1 日の最大確定損失: 資金の 5%（到達したらその日の新規注文を拒否）
- 1 銘柄あたりの最大ポジション金額: 資金の 50%

金額は Decimal で扱い、float の丸め誤差で判定がぶれないようにする。
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from trading.safety import assert_paper_mode


@dataclass(frozen=True)
class RiskLimits:
    capital_jpy: int = 50_000
    max_loss_per_trade_pct: Decimal = Decimal("0.02")
    max_daily_loss_pct: Decimal = Decimal("0.05")
    max_position_pct: Decimal = Decimal("0.50")


@dataclass(frozen=True)
class Order:
    """新規エントリーの注文。side は "buy"（買い）または "sell"（空売り）。"""

    symbol: str
    side: str
    quantity: int
    price: Decimal
    stop_price: Decimal


@dataclass(frozen=True)
class Decision:
    accepted: bool
    reason: str = ""


class RiskManager:
    def __init__(self, limits: RiskLimits | None = None) -> None:
        self.limits = limits or RiskLimits()
        capital = Decimal(self.limits.capital_jpy)
        self.max_loss_per_trade = capital * self.limits.max_loss_per_trade_pct
        self.max_daily_loss = capital * self.limits.max_daily_loss_pct
        self.max_position_value = capital * self.limits.max_position_pct
        self._positions: dict[str, Decimal] = {}
        self._daily_realized_pnl = Decimal(0)

    # --- 状態の更新 -------------------------------------------------
    def record_fill(self, order: Order) -> None:
        """約定（模擬）を記録し、銘柄ごとのポジション金額に加算する。"""
        value = order.price * order.quantity
        self._positions[order.symbol] = self._positions.get(order.symbol, Decimal(0)) + value

    def record_realized_pnl(self, pnl: Decimal) -> None:
        self._daily_realized_pnl += Decimal(pnl)

    def start_new_day(self) -> None:
        self._daily_realized_pnl = Decimal(0)

    # --- 判定 -------------------------------------------------------
    def check(self, order: Order) -> Decision:
        assert_paper_mode()

        invalid = self._validate(order)
        if invalid:
            return Decision(False, invalid)

        if -self._daily_realized_pnl >= self.max_daily_loss:
            return Decision(False, f"1日の損失上限 {self.max_daily_loss} 円に達しているため新規注文不可")

        loss = abs(order.price - order.stop_price) * order.quantity
        if loss > self.max_loss_per_trade:
            return Decision(False, f"1トレードの想定損失 {loss} 円が上限 {self.max_loss_per_trade} 円を超過")

        position = self._positions.get(order.symbol, Decimal(0)) + order.price * order.quantity
        if position > self.max_position_value:
            return Decision(
                False, f"{order.symbol} のポジション {position} 円が上限 {self.max_position_value} 円を超過"
            )

        return Decision(True)

    @staticmethod
    def _validate(order: Order) -> str:
        if order.side not in ("buy", "sell"):
            return f"不明な売買区分: {order.side!r}"
        if order.quantity <= 0:
            return "数量は 1 以上"
        if order.price <= 0 or order.stop_price <= 0:
            return "価格・損切り価格は正の値"
        if order.side == "buy" and order.stop_price >= order.price:
            return "買いの損切り価格はエントリー価格より下"
        if order.side == "sell" and order.stop_price <= order.price:
            return "空売りの損切り価格はエントリー価格より上"
        return ""
