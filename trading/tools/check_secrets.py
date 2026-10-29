"""コミットされたファイルに認証情報らしき文字列がないか調べる簡易チェック。

CI で実行し、見つかったら失敗させる。値そのものは出力しない（ファイル名と行番号、種類のみ）。
"""

from __future__ import annotations

import re
import subprocess
import sys

PATTERNS = {
    "Anthropic API key": re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,}"),
    "OpenAI API key": re.compile(r"sk-(?:proj-)?[A-Za-z0-9_\-]{32,}"),
    "GitHub token": re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,}"),
    "AWS access key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "Private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
}

SKIP_SUFFIXES = (".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf")
SELF = "trading/tools/check_secrets.py"


def tracked_files() -> list[str]:
    out = subprocess.run(["git", "ls-files"], capture_output=True, text=True, check=True)
    return [f for f in out.stdout.splitlines() if f and not f.endswith(SKIP_SUFFIXES) and f != SELF]


def scan(paths: list[str]) -> list[tuple[str, int, str]]:
    hits = []
    for path in paths:
        try:
            with open(path, encoding="utf-8", errors="ignore") as fh:
                for lineno, line in enumerate(fh, 1):
                    for kind, pattern in PATTERNS.items():
                        if pattern.search(line):
                            hits.append((path, lineno, kind))
        except OSError:
            continue
    return hits


def main() -> int:
    hits = scan(tracked_files())
    for path, lineno, kind in hits:
        print(f"::error file={path},line={lineno}::{kind} らしき文字列があります（値は表示しません）")
    if hits:
        return 1
    print("認証情報らしき文字列は見つかりませんでした。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
