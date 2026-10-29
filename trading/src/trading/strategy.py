"""売買ルール（ベースライン：トレンドフォロー、買いのみ）。

**これは検証の出発点として事前に決めた単純なルールで、利益が出ることを示したものではない。**
過去データ検証（〜11/6）の結果で採否を決める。パラメータは config/paper.json に固定し、
結果を見て変えた場合はその旨を記録する。

判定はその日の終値までのデータだけを使い、注文は翌営業日の始値で約定する（先読みなし）。

- 新規：終値 > 200日移動平均 かつ 終値が直近20日の最高値以上（ブレイクアウト）
- 損切り幅：20日 ATR × 2（約定価格からの幅、現地通貨）
- 手仕舞い：終値 < 50日移動平均（翌始値で売り）。損切りはブローカー側で日中に執行
- 株数：1 トレードのリスク予算（円）÷ 損切り幅（円換算、為替の不利分込み）。上限・現金でさらに制限
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from trading.broker import Bar


@dataclass(frozen=True)
class StrategyParams:
    trend_window: int = 200
    breakout_window: int = 20
    exit_window: int = 50
    atr_window: int = 20
    atr_multiple: Decimal = Decimal(2)


@dataclass(frozen=True)
class Signal:
    action: str  # "enter" / "exit"
    stop_distance: Decimal | None = None
    note: str = ""


def sma(values: list[Decimal], n: int) -> Decimal:
    if n <= 0 or len(values) < n:
        raise ValueError("データ不足")
    return sum(values[-n:], Decimal(0)) / n


def atr(bars: list[Bar], n: int) -> Decimal:
    if len(bars) < n + 1:
        raise ValueError("データ不足")
    trs = []
    for prev, cur in zip(bars[-n - 1 : -1], bars[-n:]):
        trs.append(max(cur.high - cur.low, abs(cur.high - prev.close), abs(cur.low - prev.close)))
    return sum(trs, Decimal(0)) / n


def required_history(p: StrategyParams) -> int:
    return max(p.trend_window, p.breakout_window, p.exit_window, p.atr_window + 1)


def evaluate(history: list[Bar], holding: bool, p: StrategyParams = StrategyParams()) -> Signal | None:
    """history はその日を最後とする日足（古い順）。holding は保有中かどうか。"""
    if len(history) < required_history(p):
        return None
    closes = [b.close for b in history]
    close = closes[-1]
    if holding:
        if close < sma(closes, p.exit_window):
            return Signal("exit", note=f"終値 {close} < {p.exit_window}日平均")
        return None
    if close > sma(closes, p.trend_window) and close >= max(closes[-p.breakout_window :]):
        dist = atr(history, p.atr_window) * p.atr_multiple
        if dist > 0:
            return Signal("enter", stop_distance=dist, note=f"{p.breakout_window}日高値ブレイク・{p.trend_window}日平均の上")
    return None
