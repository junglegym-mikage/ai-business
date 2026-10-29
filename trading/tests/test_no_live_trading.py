"""実取引につながる依存・通信がコードに紛れ込んでいないことを確認する（レビュー指摘3）。

trading/src 配下は外部と通信しない純粋な計算コードに限る。
相場データの取得など通信が必要な処理は、別の許可済みモジュールを追加する際に
このテストの許可リストを見直し、PR で理由を説明する。
"""

import ast
import pathlib
import tomllib

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "trading"

NETWORK_MODULES = {"socket", "http", "urllib", "requests", "httpx", "aiohttp", "websocket", "websockets", "ssl"}
BROKER_PACKAGES = {
    "alpaca", "alpaca-py", "alpaca-trade-api", "ib_insync", "ib-insync", "ibapi",
    "kabu", "kabusapi", "tachibana", "oandapyv20", "ccxt", "robin_stocks", "tda-api", "schwab-py",
}


def imported_modules(path: pathlib.Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module.split(".")[0])
    return names


def test_source_has_no_network_or_broker_imports():
    offenders = {}
    for path in SRC.rglob("*.py"):
        bad = imported_modules(path) & (NETWORK_MODULES | {p.replace("-", "_") for p in BROKER_PACKAGES})
        if bad:
            offenders[str(path.relative_to(ROOT))] = sorted(bad)
    assert offenders == {}


def test_dependencies_have_no_broker_clients():
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    deps = list(data["project"].get("dependencies", []))
    for extra in data["project"].get("optional-dependencies", {}).values():
        deps.extend(extra)
    names = {d.split("[")[0].split("=")[0].split(">")[0].split("<")[0].strip().lower() for d in deps}
    assert names & BROKER_PACKAGES == set()
