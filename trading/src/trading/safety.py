"""安全ガード：このシステムは実資金取引を一切行わない。

発注処理は必ず `assert_paper_mode()` を通す。環境変数などで「ライブ」を
指定されても、ここで例外を投げて止める。ライブ取引を可能にする設定は存在しない。
"""

from __future__ import annotations

import os

PAPER = "paper"


class LiveTradingForbiddenError(RuntimeError):
    """実資金取引が要求されたときに投げる。"""


def trading_mode() -> str:
    """現在のモード。未設定なら paper。paper 以外の値はすべて拒否する。"""
    mode = os.environ.get("TRADING_MODE", PAPER).strip().lower()
    if mode != PAPER:
        raise LiveTradingForbiddenError(
            f"TRADING_MODE={mode!r} は許可されていません。このシステムはペーパートレード専用です。"
        )
    return mode


def assert_paper_mode() -> None:
    """発注の直前に必ず呼ぶ。"""
    trading_mode()
