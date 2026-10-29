import csv
import datetime as dt
import json
import pathlib
import shutil

from trading.runner import load_bars, run

CONFIG = pathlib.Path(__file__).resolve().parents[1] / "config" / "paper.json"


def write_csv(path, rows):
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["date", "open", "high", "low", "close"])
        w.writeheader()
        w.writerows(rows)


def make_data(tmp: pathlib.Path, days: int, last_close_drop: bool = False):
    """1306.T を右肩上がり（ブレイクアウトが出る）に、USDJPY を一定にした合成データ。"""
    data = tmp / "data"
    data.mkdir()
    start = dt.date(2026, 1, 1)
    rows, fx = [], []
    d = start
    i = 0
    while len(rows) < days:
        if d.weekday() < 5:
            c = 3000 + i * 2
            rows.append({"date": d.isoformat(), "open": c - 1, "high": c + 5, "low": c - 5, "close": c})
            fx.append({"date": d.isoformat(), "open": 150, "high": 150, "low": 150, "close": 150})
            i += 1
        d += dt.timedelta(days=1)
    write_csv(data / "1306.T.csv", rows)
    write_csv(data / "USDJPY.csv", fx)
    return data, [dt.date.fromisoformat(r["date"]) for r in rows]


def cfg_from(tmp: pathlib.Path, start: dt.date) -> pathlib.Path:
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    cfg["start_date"] = start.isoformat()
    cfg["universe"] = [{"symbol": "1306.T", "currency": "JPY"}]
    p = tmp / "cfg.json"
    p.write_text(json.dumps(cfg), encoding="utf-8")
    return p


def test_load_bars_skips_bad_rows(tmp_path):
    p = tmp_path / "x.csv"
    write_csv(p, [
        {"date": "2026-01-02", "open": 1, "high": 2, "low": 1, "close": 2},
        {"date": "bad", "open": 1, "high": 2, "low": 1, "close": 2},
        {"date": "2026-01-03", "open": 1, "high": 1, "low": 2, "close": 1},  # 高値 < 安値
        {"date": "2026-01-01", "open": 1, "high": 2, "low": 1, "close": 2},
    ])
    bars = load_bars(p)
    assert [b.date.isoformat() for b in bars] == ["2026-01-01", "2026-01-02"]


def test_run_enters_next_open_and_writes_outputs(tmp_path):
    data, dates = make_data(tmp_path, 230)
    cfg = cfg_from(tmp_path, dates[210])
    state = tmp_path / "state"
    b = run(cfg, data, state)
    assert b.last_date == dates[-1]
    assert b.trades, "ブレイクアウトで少なくとも1回は約定する"
    first = b.trades[0]
    assert first["side"] == "buy" and first["date"] == dates[211].isoformat()  # 判定日の翌営業日に約定
    for name in ("state.json", "trades.csv", "equity.csv", "report.md"):
        assert (state / name).exists()
    assert "実資金ではありません" in (state / "report.md").read_text(encoding="utf-8")


def test_rerun_is_idempotent_and_resumes(tmp_path):
    data, dates = make_data(tmp_path, 230)
    cfg = cfg_from(tmp_path, dates[210])
    state = tmp_path / "state"
    b1 = run(cfg, data, state)
    n = len(b1.trades)
    b2 = run(cfg, data, state)  # 新しいデータなし → 何も起きない
    assert len(b2.trades) == n and b2.last_date == b1.last_date
    lines = (state / "equity.csv").read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1 + (len(dates) - 210)  # 見出し＋処理日数（重複なし）


def test_incremental_run_matches_single_run(tmp_path):
    data, dates = make_data(tmp_path, 230)
    cfg = cfg_from(tmp_path, dates[205])
    one = run(cfg, data, tmp_path / "one")
    # 途中までのデータで一度実行し、残りを後から足して再実行
    part = tmp_path / "part"
    shutil.copytree(data, part)
    rows = list(csv.DictReader((data / "1306.T.csv").open(encoding="utf-8")))
    write_csv(part / "1306.T.csv", rows[:218])
    run(cfg, part, tmp_path / "inc")
    write_csv(part / "1306.T.csv", rows)
    inc = run(cfg, part, tmp_path / "inc")
    assert inc.trades == one.trades
    assert inc.cash == one.cash
