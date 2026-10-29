"""日足データの取得（GitHub Actions 上で実行。通信するのはこのツールだけ）。

Yahoo Finance のチャート API（公開・無料・非公式）から日足を取り、分割・配当調整済みの
OHLC を CSV に保存する。調整は 調整後終値 ÷ 終値 の比率を始値・高値・安値にも掛ける。
認証情報は使わない。取得に失敗した銘柄は記録して続行する（ランナー側で data_missing として扱う）。

制約（レポートに明記すること）：無料・非公式データのため欠損や遅延があり得る。上場廃止銘柄は含まれない。
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import pathlib
import sys
import time
import urllib.parse
import urllib.request

URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range={range}&interval=1d&events=div%2Csplit"
HEADERS = {"User-Agent": "Mozilla/5.0 (paper-trading research; contact: repository owner)"}


def fetch(symbol: str, rng: str) -> list[dict]:
    url = URL.format(symbol=urllib.parse.quote(symbol), range=rng)
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.load(resp)
    result = data["chart"]["result"][0]
    offset = int(result["meta"].get("gmtoffset", 0))
    ts = result.get("timestamp") or []
    q = result["indicators"]["quote"][0]
    adj = (result["indicators"].get("adjclose") or [{}])[0].get("adjclose") or q["close"]
    rows = []
    for i, t in enumerate(ts):
        o, h, l, c, a = q["open"][i], q["high"][i], q["low"][i], q["close"][i], adj[i]
        if None in (o, h, l, c, a) or c <= 0:
            continue
        f = a / c
        day = dt.datetime.fromtimestamp(t + offset, dt.timezone.utc).date()
        rows.append({"date": day.isoformat(), "open": f"{o * f:.6f}", "high": f"{h * f:.6f}",
                     "low": f"{l * f:.6f}", "close": f"{a:.6f}"})
    # 同じ日付が複数あれば最後を採用
    dedup = {r["date"]: r for r in rows}
    return [dedup[d] for d in sorted(dedup)]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True, type=pathlib.Path)
    ap.add_argument("--out", required=True, type=pathlib.Path)
    ap.add_argument("--range", default="2y")
    a = ap.parse_args()
    cfg = json.loads(a.config.read_text(encoding="utf-8"))
    a.out.mkdir(parents=True, exist_ok=True)
    targets = [(u["symbol"], u["symbol"]) for u in cfg["universe"]] + [("USDJPY", "JPY=X")]
    failed = []
    for name, yahoo in targets:
        try:
            rows = fetch(yahoo, a.range)
            if not rows:
                raise ValueError("データが空")
            with (a.out / f"{name}.csv").open("w", newline="", encoding="utf-8") as fh:
                w = csv.DictWriter(fh, fieldnames=["date", "open", "high", "low", "close"])
                w.writeheader()
                w.writerows(rows)
            print(f"{name}: {len(rows)} 行（{rows[0]['date']} 〜 {rows[-1]['date']}）")
        except Exception as exc:  # noqa: BLE001 - 取得失敗は記録して続行
            failed.append(name)
            print(f"::warning::{name} の取得に失敗: {type(exc).__name__}: {exc}")
        time.sleep(1)
    if len(failed) == len(targets):
        print("::error::すべての銘柄で取得に失敗しました")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
