#!/usr/bin/env python3
"""Static checks for the landing pages. Standard library only.

Usage: python3 tests/check_pages.py
Exit code 0 = all checks passed.
"""
import pathlib
import re
import sys
from html.parser import HTMLParser

ROOT = pathlib.Path(__file__).resolve().parent.parent
SALES_PAGES = ["index.html", "gbp/index.html"]
SAMPLE_PAGES = ["samples/gbp-diagnosis-sample.html"]

# Affirmative claims we must not publish. Negations like 保証しません are allowed.
FORBIDDEN = [r"保証します", r"保証いたします", r"必ず", r"確実に", r"治る", r"治ります",
             r"No\.?\s?1", r"ナンバーワン", r"業界最安"]
PLACEHOLDERS = [r"example\.com", r"000-0000", r"xxx@", r"TODO", r"\[氏名\]", r"\[住所\]"]


class Collector(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links, self.meta, self.title, self._in_title, self.lang = [], [], "", False, None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "html":
            self.lang = a.get("lang")
        if tag == "a" and "href" in a:
            self.links.append(a["href"])
        if tag == "meta":
            self.meta.append(a)
        if tag == "title":
            self._in_title = True

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._in_title:
            self.title += data


def visible_text(html):
    html = re.sub(r"<(style|script)[^>]*>.*?</\1>", "", html, flags=re.S)
    return re.sub(r"<[^>]+>", "", html)


def check(rel, failures, sales):
    path = ROOT / rel
    html = path.read_text(encoding="utf-8")
    c = Collector()
    c.feed(html)
    text = visible_text(html)
    if c.lang != "ja":
        failures.append(f"{rel}: <html lang> is not 'ja'")
    if not any(m.get("name") == "viewport" for m in c.meta):
        failures.append(f"{rel}: missing viewport meta")
    if not c.title.strip():
        failures.append(f"{rel}: missing <title>")
    for href in c.links:
        if re.match(r"^(https?:|mailto:|tel:|#)", href):
            continue
        target = (path.parent / href.split("#")[0]).resolve()
        if target.is_dir():
            target = target / "index.html"
        if not target.exists():
            failures.append(f"{rel}: broken internal link -> {href}")
    for pat in FORBIDDEN:
        if re.search(pat, text):
            failures.append(f"{rel}: forbidden claim matched /{pat}/")
    for pat in PLACEHOLDERS:
        if re.search(pat, html):
            failures.append(f"{rel}: placeholder left in page /{pat}/")
    if sales and not re.search(r"(購入|お支払い)[^。]*できません", text):
        failures.append(f"{rel}: missing 'no purchase/payment yet' notice")
    if not sales and "架空" not in text:
        failures.append(f"{rel}: sample is not labeled as fictional (架空)")


def main():
    failures = []
    for rel in SALES_PAGES:
        check(rel, failures, sales=True)
    for rel in SAMPLE_PAGES:
        check(rel, failures, sales=False)
    total = len(SALES_PAGES) + len(SAMPLE_PAGES)
    if failures:
        print("FAIL")
        for f in failures:
            print(" -", f)
        sys.exit(1)
    print(f"OK: {total} pages passed all checks")


if __name__ == "__main__":
    main()
