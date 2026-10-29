"""日足データの取得（GitHub Actions 上で実行。通信するのはこのツールだけ）。

Yahoo Finance のチャート API（公開・無料・非公式）から日足を取り、OHLC と配当・分割調整済み終値（adj_close）を
CSV に保存する。Yahoo の OHLC は**分割調整済み（配当は未調整）**で、分割があると過去の値も遡って書き換わる。
そのため分割イベントを別ファイル（<銘柄>.splits.csv）に保存し、ランナーは保有銘柄に分割があれば凍結する。
約定には OHLC、売買判定には調整済み（adj_close）を使う。
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


def fetch(symbol: str, rng: str) -> tuple[list[dict], list[dict]]:
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
        day = dt.datetime.fromtimestamp(t + offset, dt.timezone.utc).date()
        rows.append({"date": day.isoformat(), "open": f"{o:.6f}", "high": f"{h:.6f}",
                     "low": f"{l:.6f}", "close": f"{c:.6f}", "adj_close": f"{a:.6f}"})
    # 同じ日付が複数あれば最後を採用
    dedup = {r["date"]: r for r in rows}
    splits = []
    for ev in ((result.get("events") or {}).get("splits") or {}).values():
        day = dt.datetime.fromtimestamp(int(ev["date"]) + offset, dt.timezone.utc).date()
        splits.append({"date": day.isoformat(), "numerator": ev.get("numerator"), "denominator": ev.get("denominator")})
    splits.sort(key=lambda r: r["date"])
    return [dedup[d] for d in sorted(dedup)], splits


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
            rows, splits = fetch(yahoo, a.range)
            if not rows:
                raise ValueError("データが空")
            with (a.out / f"{name}.splits.csv").open("w", newline="", encoding="utf-8") as fh:
                w = csv.DictWriter(fh, fieldnames=["date", "numerator", "denominator"])
                w.writeheader()
                w.writerows(splits)
            with (a.out / f"{name}.csv").open("w", newline="", encoding="utf-8") as fh:
                w = csv.DictWriter(fh, fieldnames=["date", "open", "high", "low", "close", "adj_close"])
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
