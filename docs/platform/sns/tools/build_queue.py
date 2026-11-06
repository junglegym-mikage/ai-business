"""投稿表（content_w1.SCHEDULE）とキャプションから queue.json を作る。

承認は ig_publish.py approve <日付> で approvals.json に記録する（内容が変わると自動で未承認に戻る）。
"""
import json
import re
from pathlib import Path

import content_w1 as C
import content_w2 as C2

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


PINNED = [
    "このアカウントでできること\n\n①経営のAI化 ②家計・積立 ③目標ロードマップ ④受験ロードマップを、AIでつくります。\n事例はすべて架空です。結果を保証するものではありません。",
    "AIで道筋をつくる、とは\n\n① 今の現在地を知る\n② ゴールまでのルートを作る\n③ 毎月、数字を記録する\n④ 道筋を自動で作り直す",
    "ご利用の前に\n\n・結果（売上・資産・目標達成・合格など）を保証するものではありません\n・専門家による個別の助言ではありません\n・投稿の事例はすべて架空です\n・AIで作成し、運営者が確認しています\n・受付の状況は、プロフィールのリンク先でご確認ください",
]


def new_caption(sp):
    cap = sp["caption"]
    if "保証" not in cap:
        cap += f"\n\n※{sp['note']}。"
    name = {1: "①経営のAI化", 2: "②家計・積立", 3: "③目標ロードマップ", 4: "④受験ロードマップ"}[sp["series"]]
    return f"{cap}\n{name}はプロフィールのリンクから\n\n{sp['tags']}"


SERVICE = "プロフィールのリンクからサービス一覧へ"
BUY1 = "①AI化セットはプロフィールのリンクから。モニター価格9,800円・先着3名"
NOTE = "AIで作成し、運営者が確認しています。"
# 11/1 は旧時刻（0730/1215）で投稿済みのため、時刻変更後のIDは投稿表に入れない（二重投稿防止）
SKIP = {"2026-11-01-story", "2026-11-01-0710", "2026-11-01-1155"}


def caption_v2(sp):
    """2026-11-06〜：販売は自社サイト。①は最後の1行で申し込みを案内、②③④はサービス一覧へ。ココナラへの誘導はしない。"""
    cap = sp["caption"]
    cap += f"\n\n※{sp['note']}。{NOTE}" if "保証" not in cap else f"\n※事例は架空です。{NOTE}"
    if sp["series"] == 1:
        return f"{cap}\n\n{sp['tags']}\n\n{BUY1}"
    return f"{cap}\n{SERVICE}\n\n{sp['tags']}"


def week(C, folder, story_name=lambda s: s):
    out = []
    for date, keys, (story, o1, o2) in C.SCHEDULE:
        out.append(dict(id=f"{date}-story", at=f"{date}T06:40:00+09:00", type="STORIES", file=f"{folder}/{story_name(story)}.jpg",
                        poll=f"{o1}／{o2}（APIではアンケートを付けられないため、付ける場合はアプリで追加）"))
        for t, k in zip(C.TIMES, keys):
            hh, mm = t.split(":")
            cap = caption_v2(C.REELS[k])
            assert len(cap) <= 2200 and "ココナラ" not in cap, k
            out.append(dict(id=f"{date}-{int(hh):02d}{mm}", at=f"{date}T{int(hh):02d}:{mm}:00+09:00", type="REELS",
                            file=f"{folder}/reel-{k}.mp4", caption=cap))
    return out


def main():
    old = old_captions()
    q = []
    for i, cap in enumerate(PINNED, 1):  # 固定投稿（APIの画像はJPEGのみ）。投稿後にピン留めは手動
        q.append(dict(id=f"pinned-{i}", at="2026-10-31T22:20:00+09:00", type="IMAGE", file=f"{W1}/pinned-{i}.jpg", caption=cap))
    for date, keys, (story, o1, o2) in C.SCHEDULE:
        q.append(dict(id=f"{date}-story", at=f"{date}T06:40:00+09:00", type="STORIES", file=f"{W1}/{story}.jpg",
                      poll=f"{o1}／{o2}（APIではアンケートを付けられないため、付ける場合はアプリで追加）"))
        for t, k in zip(C.TIMES, keys):
            hh, mm = t.split(":")
            if k in OLD:
                f, cap = f"{W1}/{k}.mp4", old[OLD[k]]
            else:
                f, cap = f"{W1}/reel-{k}.mp4", new_caption(C.REELS[k])
            assert len(cap) <= 2200, k
            q.append(dict(id=f"{date}-{int(hh):02d}{mm}", at=f"{date}T{int(hh):02d}:{mm}:00+09:00", type="REELS", file=f, caption=cap))
    q = [x for x in q if x["id"] not in SKIP]
    q += week(C2, "docs/platform/sns/week2")
    (SNS / "queue.json").write_text(json.dumps(q, ensure_ascii=False, indent=1) + "\n")
    print(len(q), "items")


if __name__ == "__main__":
    main()
