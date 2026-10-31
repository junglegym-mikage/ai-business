"""投稿表（content_w1.SCHEDULE）とキャプションから queue.json を作る。

承認は ig_publish.py approve <日付> で approvals.json に記録する（内容が変わると自動で未承認に戻る）。
"""
import json
import re
from pathlib import Path

import content_w1 as C

HERE = Path(__file__).resolve().parent
SNS = HERE.parent
W1 = "docs/platform/sns/week1"
ORDER = ["mon", "tue", "wed", "thu", "sat"]
OLD = {"reel-mon-1-business": "mon", "reel-tue-2-money": "tue", "reel-wed-3-goal": "wed", "reel-thu-4-exam": "thu", "reel-sat-1-business": "sat"}


def old_captions():
    """posts.md の既存5本のキャプション＋ハッシュタグ。"""
    text = (SNS / "week1/posts.md").read_text()
    blocks = re.findall(r"\*\*キャプション\*\*\n(.*?)\n\n\*\*ハッシュタグ\*\*：(.*?)\n", text, re.S)
    return {d: f"{cap.strip()}\n\n{tags.strip()}" for d, (cap, tags) in zip(ORDER, blocks)}


def new_caption(sp):
    cap = sp["caption"]
    if "保証" not in cap:
        cap += f"\n\n※{sp['note']}。"
    name = {1: "①経営のAI化", 2: "②家計・積立", 3: "③目標ロードマップ", 4: "④受験ロードマップ"}[sp["series"]]
    return f"{cap}\n{name}はプロフィールのリンクから\n\n{sp['tags']}"


def main():
    old = old_captions()
    q = []
    for date, keys, (story, o1, o2) in C.SCHEDULE:
        q.append(dict(id=f"{date}-story", at=f"{date}T07:00:00+09:00", type="STORIES", file=f"{W1}/{story}.png",
                      poll=f"{o1}／{o2}（APIではアンケートを付けられないため、付ける場合はアプリで追加）"))
        for t, k in zip(C.TIMES, keys):
            hh, mm = t.split(":")
            if k in OLD:
                f, cap = f"{W1}/{k}.mp4", old[OLD[k]]
            else:
                f, cap = f"{W1}/reel-{k}.mp4", new_caption(C.REELS[k])
            assert len(cap) <= 2200, k
            q.append(dict(id=f"{date}-{int(hh):02d}{mm}", at=f"{date}T{int(hh):02d}:{mm}:00+09:00", type="REELS", file=f, caption=cap))
    (SNS / "queue.json").write_text(json.dumps(q, ensure_ascii=False, indent=1) + "\n")
    print(len(q), "items")


if __name__ == "__main__":
    main()
