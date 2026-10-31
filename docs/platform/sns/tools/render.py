"""SNS素材の生成（全投稿リール・ストーリーズ画像・固定投稿画像）。

使い方: python3 render.py <出力フォルダ> [--brand "運営名"]
- フォントは Noto Sans CJK（SIL Open Font License。商用利用可）
- 事例はすべて架空。保証・効果の数字は入れない（common.md 5章）
"""
import argparse
import math
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FONT = "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"
FONT_R = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"
BG = (15, 27, 45)
BG2 = (24, 40, 64)
WHITE = (245, 247, 250)
MUTED = (160, 174, 192)
ACC = {0: (200, 210, 225), 1: (46, 196, 182), 2: (244, 162, 97), 3: (155, 140, 255), 4: (255, 107, 107)}
SERIES = {0: "AIで道筋をつくる", 1: "①経営のAI化", 2: "②家計・積立", 3: "③目標ロードマップ", 4: "④受験ロードマップ"}
FPS = 30
W, H = 1080, 1920
BRAND = ""
SWIPE = False  # カルーセルとして書き出すときだけ「スワイプ ▶」を出す（今はリールのみ）


def font(size, bold=True):
    return ImageFont.truetype(FONT if bold else FONT_R, size, index=0)


def ease(t):
    t = max(0.0, min(1.0, t))
    return 1 - (1 - t) ** 3


NO_HEAD = set("、。，．・：；？！」』）】〕〉》ー～ぁぃぅぇぉっゃゅょァィゥェォッャュョ")
NO_TAIL = set("「『（【〔〈《")


def wrap(draw, text, f, maxw):
    """日本語の禁則（行頭に句読点・閉じかっこ・小書き文字を置かない、行末に開きかっこを置かない）つき折り返し。"""
    lines = []
    for para in text.split("\n"):
        cur = ""
        for ch in para:
            if draw.textlength(cur + ch, font=f) > maxw and cur:
                if ch in NO_HEAD:  # 前の文字ごと次の行へ送る
                    carry = cur[-1]
                    cur = cur[:-1]
                    lines.append(cur)
                    cur = carry + ch
                elif cur[-1] in NO_TAIL:
                    carry = cur[-1]
                    lines.append(cur[:-1])
                    cur = carry + ch
                else:
                    lines.append(cur)
                    cur = ch
            else:
                cur += ch
        if cur and lines and len(cur) <= 3 and len(lines[-1]) > 6:
            # 短すぎる最終行を作らない：前の行の末尾を数文字おろす（禁則を守る位置で）
            prev = lines[-1]
            k = 4 - len(cur)
            while k < len(prev) - 3 and (prev[-k] in NO_HEAD or prev[-k - 1] in NO_TAIL):
                k += 1
            lines[-1], cur = prev[:-k], prev[-k:] + cur
        if cur:
            lines.append(cur)
    return lines


def text_block(img, d, lines, y, size, color=WHITE, t=1.0, stagger=0.25, center=True, x=90, bold=True, gap=1.3):
    """行ごとに下からフェードイン。t は 0〜(行数*stagger+1)。"""
    f = font(size, bold)
    for i, line in enumerate(lines):
        p = ease((t - i * stagger) / 0.6) if t < 99 else 1.0
        if p <= 0:
            y += int(size * gap)
            continue
        layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
        ld = ImageDraw.Draw(layer)
        tw = ld.textlength(line, font=f)
        tx = (img.width - tw) / 2 if center else x
        ld.text((tx, y + (1 - p) * 40), line, font=f, fill=color + (int(255 * p),))
        img.alpha_composite(layer)
        y += int(size * gap)
    return y


def frame_base(series, w=W, h=H, safe_top=230):
    img = Image.new("RGBA", (w, h), BG + (255,))
    d = ImageDraw.Draw(img)
    for i in range(h):  # やわらかいグラデーション
        c = tuple(int(BG[k] + (BG2[k] - BG[k]) * i / h) for k in range(3))
        d.line([(0, i), (w, i)], fill=c + (255,))
    acc = ACC[series]
    d.rounded_rectangle([90, safe_top, 90 + d.textlength(SERIES[series], font=font(34)) + 48, safe_top + 62], 31, fill=acc + (255,))
    d.text((114, safe_top + 8), SERIES[series], font=font(34), fill=BG + (255,))
    foot = "AIで、仕事・お金・目標・受験の道筋をつくる" + (f"｜{BRAND}" if BRAND else "")
    f = font(26, False)
    d.text(((w - d.textlength(foot, font=f)) / 2, h - (430 if h == H else 70)), foot, font=f, fill=MUTED + (255,))
    return img, d


def end_card(series, t):
    img, d = frame_base(series)
    acc = ACC[series]
    y = text_block(img, d, [SERIES[series] + "は", "プロフィールの", "リンクから"], 640, 78, t=t * 3)
    p = ease(t * 3 - 1.0)
    if p > 0:
        d.rounded_rectangle([240, y + 40, 840, y + 150], 55, outline=acc + (int(255 * p),), width=5)
        msg = "▲ プロフィールへ"
        d.text(((W - d.textlength(msg, font=font(44))) / 2, y + 66), msg, font=font(44), fill=acc + (int(255 * p),))
    note = "事例は架空です／結果を保証するものではありません"
    d.text(((W - d.textlength(note, font=font(28, False))) / 2, 1300), note, font=font(28, False), fill=MUTED + (255,))
    return img


def bars(img, d, items, y0, t, acc, unit, maxv, highlight=None):
    f = font(40)
    fv = font(40)
    for i, (label, v) in enumerate(items):
        p = ease(t - i * 0.35)
        if p <= 0:
            continue
        y = y0 + i * 170
        d.text((90, y), label, font=f, fill=WHITE + (int(255 * min(1, p * 1.5)),))
        bw = int(760 * v / maxv * p)
        col = acc if (highlight is None or highlight == i) else (80, 96, 120)
        d.rounded_rectangle([90, y + 62, 90 + max(bw, 8), y + 122], 14, fill=col + (255,))
        txt = f"{v}{unit}"
        d.text((90 + max(bw, 8) + 20, y + 66), txt, font=fv, fill=WHITE + (int(255 * p),))


# ---------- リール ----------
def reel1(t):
    """①：事務作業、月に何時間か数えたことある？"""
    s, acc = 1, ACC[1]
    if t < 3:
        img, d = frame_base(s)
        text_block(img, d, ["事務作業、", "月に何時間か", "数えたことある？"], 640, 96, t=t * 2)
    elif t < 5.5:
        img, d = frame_base(s)
        text_block(img, d, ["数えると、", "AI化する場所が", "見えてくる"], 640, 88, t=(t - 3) * 2.5)
    elif t < 11.5:
        img, d = frame_base(s)
        text_block(img, d, ["例：ある整体院（架空）"], 400, 52, color=MUTED, t=99)
        bars(img, d, [("予約の返信", 15), ("回数券の管理", 4), ("売上の集計", 3)], 560, (t - 5.5) * 1.2, acc, "時間/月", 15)
        if t > 9:
            p = ease((t - 9) / 0.8)
            msg = "合計 約22時間／月"
            d.text(((W - d.textlength(msg, font=font(64))) / 2, 1120), msg, font=font(64), fill=acc + (int(255 * p),))
    elif t < 15:
        img, d = frame_base(s)
        text_block(img, d, ["例：ある整体院（架空）"], 400, 52, color=MUTED, t=99)
        bars(img, d, [("予約の返信", 15), ("回数券の管理", 4), ("売上の集計", 3)], 560, 99, acc, "時間/月", 15, highlight=0)
        text_block(img, d, ["一番大きいところから", "AI化する"], 1110, 70, t=(t - 11.5) * 2)
    elif t < 18.5:
        img, d = frame_base(s)
        text_block(img, d, ["まずは1週間、", "作業と時間を", "書き出そう"], 600, 92, t=(t - 15) * 2.5)
        p = ease((t - 16.5) / 0.6)
        if p > 0:
            for i, it in enumerate(["□ 何の作業？", "□ 1回何分？", "□ 週に何回？"]):
                d.text((300, 1020 + i * 80), it, font=font(50), fill=acc + (int(255 * p),))
    else:
        img = end_card(s, (t - 18.5) / 1.2)
    return img


def reel2(t):
    """③：同じゴールでもルートは1つじゃない"""
    s, acc = 3, ACC[3]
    if t < 3:
        img, d = frame_base(s)
        text_block(img, d, ["目標まで、", "あと何か月？", "今の数字から逆算"], 640, 96, t=t * 2)
    elif t < 9:
        img, d = frame_base(s)
        text_block(img, d, ["ルートは1つじゃない", "例：資格の試験（架空）"], 360, 50, color=MUTED, t=99)
        sx, sy, gx, gy = 170, 1300, 900, 560
        d.ellipse([sx - 22, sy - 22, sx + 22, sy + 22], fill=WHITE + (255,))
        d.text((sx - 50, sy + 36), "スタート", font=font(38), fill=WHITE + (255,))
        d.polygon([(gx, gy - 70), (gx + 70, gy - 45), (gx, gy - 20)], fill=acc + (255,))
        d.line([(gx, gy - 70), (gx, gy + 20)], fill=WHITE + (255,), width=6)
        d.text((gx - 40, gy - 130), "ゴール", font=font(38), fill=WHITE + (255,))
        routes = [("A 独学", (0.15, 0.9)), ("B 講座を使う", (0.5, 0.5)), ("C 得意から", (0.9, 0.15))]
        cols = [acc, (120, 200, 255), (255, 200, 120)]
        for k, (name, (cx, cy)) in enumerate(routes):
            p = ease((t - 3 - k * 1.2) / 1.6)
            if p <= 0:
                continue
            ctrl = (sx + (gx - sx) * cx, sy + (gy - sy) * cy - 120 + k * 60)
            pts = []
            n = int(60 * p) + 1
            for j in range(n):
                u = j / 60
                x = (1 - u) ** 2 * sx + 2 * (1 - u) * u * ctrl[0] + u ** 2 * gx
                y = (1 - u) ** 2 * sy + 2 * (1 - u) * u * ctrl[1] + u ** 2 * gy
                pts.append((x, y))
            if len(pts) > 1:
                d.line(pts, fill=cols[k] + (255,), width=10, joint="curve")
            lx, ly = pts[len(pts) // 2] if len(pts) > 2 else pts[0]
            d.text((lx + 20, ly - 20), name, font=font(40), fill=cols[k] + (255,))
    elif t < 13:
        img, d = frame_base(s)
        text_block(img, d, ["どれを選ぶかは", "「今の現在地」で決まる"], 520, 76, t=(t - 9) * 2)
        p = ease((t - 10.5) / 0.8)
        if p > 0:
            rows = [("使える時間", "平日1時間？休日3時間？"), ("予算", "テキストだけ？講座も？"), ("得意・苦手", "どこから始める？")]
            for i, (a, b) in enumerate(rows):
                y = 860 + i * 130
                d.text((120, y), a, font=font(46), fill=acc + (int(255 * p),))
                d.text((420, y + 4), b, font=font(40, False), fill=WHITE + (int(255 * p),))
    elif t < 18:
        img, d = frame_base(s)
        text_block(img, d, ["数字を入れると、", "道筋が毎月更新される"], 430, 72, t=(t - 13) * 2)
        p = ease((t - 14.5) / 0.8)
        if p > 0:
            d.rounded_rectangle([140, 700, 940, 1260], 30, fill=(32, 52, 82, int(255 * p)))
            d.text((180, 730), "現在地ボード（架空の例）", font=font(38), fill=MUTED + (int(255 * p),))
            q = ease((t - 16) / 0.8)
            now = "80" if q < 0.5 else "130"
            eta = "10か月目ごろ" if q < 0.5 else "8か月目ごろ"
            for i, (a, b) in enumerate([("現在地（累計時間）", now), ("目標", "250"), ("見込み（参考計算）", eta)]):
                y = 820 + i * 130
                d.text((180, y), a, font=font(40, False), fill=WHITE + (int(255 * p),))
                d.text((640, y), b, font=font(48), fill=acc + (int(255 * p),))
            d.text((180, 1200), "※ 見込みは過去の数字を延ばした参考計算", font=font(26, False), fill=MUTED + (int(255 * p),))
    else:
        img = end_card(s, (t - 18) / 1.2)
    return img


def reel3(t):
    """①：AIに入れてはいけない情報3つ"""
    s, acc = 1, ACC[1]
    items = [("1", "お客さんの名前・連絡先"), ("2", "パスワード・ID"), ("3", "カード番号・契約書の原本")]
    if t < 2.8:
        img, d = frame_base(s)
        text_block(img, d, ["業務で使うAIに", "許可なく入れない", "情報 3つ"], 640, 96, t=t * 2)
    elif t < 10:
        img, d = frame_base(s)
        text_block(img, d, ["許可なく入れない情報"], 400, 60, color=MUTED, t=99)
        for i, (n, label) in enumerate(items):
            p = ease((t - 2.8 - i * 2.2) / 0.7)
            if p <= 0:
                continue
            y = 600 + i * 220
            d.ellipse([90, y, 190, y + 100], fill=(255, 107, 107, int(255 * p)))
            d.line([(118, y + 28), (162, y + 72)], fill=WHITE + (int(255 * p),), width=10)
            d.line([(162, y + 28), (118, y + 72)], fill=WHITE + (int(255 * p),), width=10)
            d.text((220, y + 18), label, font=font(56), fill=WHITE + (int(255 * p),))
    elif t < 15.5:
        img, d = frame_base(s)
        text_block(img, d, ["入れる情報は", "必要最小限に"], 480, 92, t=(t - 10) * 2)
        p = ease((t - 11.8) / 0.8)
        if p > 0:
            d.rounded_rectangle([90, 760, 990, 1230], 28, fill=(32, 52, 82, int(255 * p)))
            for i, ln in enumerate(["・使うAIの規約と設定を確認", "・名前を伏せても、組み合わせで", "　個人がわかることがある", "・必要な情報だけを入れる"]):
                d.text((130, 800 + i * 100), ln, font=font(48, False), fill=WHITE + (int(255 * p),))
    else:
        img = end_card(s, (t - 15.5) / 1.2)
    return img


REELS = [("reel-mon-1-business.mp4", reel1, 21.0), ("reel-wed-3-goal.mp4", reel2, 20.5), ("reel-sat-1-business.mp4", reel3, 18.0)]


def render_reel(out, fn, dur):
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
           "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo", "-shortest",
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart", str(out)]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for i in range(int(dur * FPS)):
        p.stdin.write(fn(i / FPS).convert("RGB").tobytes())
    p.stdin.close()
    p.wait()


# ---------- カルーセル（1080x1350） ----------
CW, CH = 1080, 1350


def slide(series, title, body=None, num=None, note=None, cover=False):
    img, d = frame_base(series, CW, CH, safe_top=70)
    acc = ACC[series]
    if cover:
        y = text_block(img, d, wrap(d, title, font(92), 900), 360, 92, t=99)
        if body:
            text_block(img, d, wrap(d, body, font(48, False), 900), y + 50, 48, color=MUTED, t=99, bold=False)
        if SWIPE:
            d.text((CW - 330, CH - 160), "スワイプ ▶", font=font(40), fill=acc + (255,))
    else:
        y = 210
        if num:
            d.text((90, y), num, font=font(120), fill=acc + (255,))
            y += 150
        y = text_block(img, d, wrap(d, title, font(74), 900), y, 74, t=99, center=False)
        if body:
            for para in body:
                y = text_block(img, d, wrap(d, para, font(52, False), 900), y + 40, 52, t=99, center=False, bold=False, gap=1.45)
    if note:
        f = font(26, False)
        d.text(((CW - d.textlength(note, font=f)) / 2, CH - 130), note, font=f, fill=MUTED + (255,))
    return img.convert("RGB")


def carousel_money():
    s = 2
    n = "一般的な考え方です。個別の商品はおすすめしていません"
    return [
        slide(s, "固定費を\n見直す順番", "毎月かかるお金は、\n見直しやすい順に見るとラク", cover=True),
        slide(s, "通信費", ["スマホ・ネットのプランと、実際に使っているデータ量を並べて比べる", "使っていないオプションがないか確認"], "1", n),
        slide(s, "サブスク", ["毎月払っているサービスを全部書き出す", "この1か月で使ったかどうかで、残すか決める"], "2", n),
        slide(s, "保険", ["保障の内容が重なっていないかを確認する", "見直すときは、保障がなくなる期間を作らない"], "3", n),
        slide(s, "住居費", ["金額が大きいぶん、更新や引っ越しのタイミングで考える", "急いで決めない"], "4", n),
        slide(s, "家計の「今」を見える化", ["②家計・積立の現在地ボードは、数字を入れると目標までの道筋が毎月更新されます", "②家計・積立は\nプロフィールのリンクから"], None, "結果や運用成果を保証するものではありません"),
    ]


def carousel_exam():
    s = 4
    n = "架空の例です。合格を保証するものではありません"
    return [
        slide(s, "模試の結果、\nどう読む？", "点数より大事なのは\n「差」と「次の一手」", cover=True),
        slide(s, "教科ごとに\n「今」と「目安」の差を書く", ["英語 偏差値59（目安60・差-1）", "数学 偏差値52（目安60・差-8）", "国語 偏差値56（目安60・差-4）"], "1", n),
        slide(s, "差が大きい教科から優先する", ["上の例なら、まず数学", "ただし、志望校の配点や出題範囲も合わせて考える", "差が小さい教科は\n「維持しながら少しずつ」"], "2", n),
        slide(s, "同じ会社の\n模試どうしで比べる", ["偏差値は、模試の会社や受ける人で変わる", "違う模試の数字は、そのまま比べない"], "3", n),
        slide(s, "次の模試の目標を\n1つだけ決める", ["例：数学の計算問題を8割取る", "目標が1つだと、毎日の勉強が決めやすい"], "4", n),
        slide(s, "受験までの道筋を見える化", ["④受験ロードマップは、模試の結果を入れると教科別の現在地と次の目標がわかります", "入試の日程・制度は学校などの公式情報で確認を", "④受験ロードマップは\nプロフィールのリンクから"], None, "合格を保証するものではありません"),
    ]


# ---------- スライドをリールにする（全投稿リール化） ----------
def slides_reel(slides, series, cover_sec=2.6, sec=3.8):
    """カルーセル用の 1080x1350 スライドを 1080x1920 の縦動画に並べる。
    上 230px・下 340px の安全域の間（y=230〜1580）に置き、切り替えはフェード＋少し上へ。"""
    base, _ = frame_base(series)
    base = base.convert("RGB")
    plan, t0 = [], 0.0
    for i, s in enumerate(slides):
        dur = cover_sec if i == 0 else sec
        plan.append((t0, dur, s))
        t0 += dur
    total = t0 + 2.6

    def fn(t):
        if t >= t0:
            return end_card(series, (t - t0) / 1.2)
        img = base.copy()
        for st, dur, s in plan:
            if st <= t < st + dur:
                p = ease((t - st) / 0.45)
                lay = Image.new("RGB", img.size, (0, 0, 0))
                lay.paste(s, (0, 230 + int((1 - p) * 50)))
                mask = Image.new("L", img.size, 0)
                mask.paste(int(255 * p), (0, 230 + int((1 - p) * 50), CW, 230 + int((1 - p) * 50) + CH))
                img.paste(lay, (0, 0), mask)
                break
        return img.convert("RGBA")
    return fn, total


# ---------- ストーリーズ（1080x1920。スタンプは投稿時にアプリで貼る） ----------
STORIES = [
    ("mon", 1, "事務作業、\n月に何時間\nかかってる？", "数えたことがある人は少ないかも"),
    ("tue", 2, "毎月払ってる\nサブスク、\nいくつある？", "全部言えたらすごい"),
    ("wed", 3, "今の目標、\n期限は\n決めてる？", "期限があると逆算できる"),
    ("thu", 4, "模試の結果、\n返ってきたら\n見返してる？", "点数より「差」を見るのがコツ"),
    ("sat", 1, "仕事で\nAI、\n使ってる？", "使う前に確認したいことも"),
]


def story_question(series, q, sub):
    """1枚目：質問（中央下にアンケートスタンプを貼る余白）。"""
    img, d = frame_base(series, safe_top=250)
    y = text_block(img, d, q.split("\n"), 420, 96, t=99)
    text_block(img, d, wrap(d, sub, font(42, False), 900), y + 20, 42, color=MUTED, t=99, bold=False)
    d.text(((W - d.textlength("▼ 答えてみてください", font=font(40))) / 2, 1080), "▼ 答えてみてください", font=font(40), fill=ACC[series] + (255,))
    return img.convert("RGB")  # 1160〜1500 はアンケートスタンプ用に空ける


def story_reel(series):
    """2枚目：リールをストーリーズでシェアするときの背景（中央にリールが重なる）。"""
    img, d = frame_base(series, safe_top=250)
    text_block(img, d, ["新しいリールを", "公開しました"], 360, 64, t=99)
    msg = "▲ タップして見る"
    d.text(((W - d.textlength(msg, font=font(44))) / 2, 1370), msg, font=font(44), fill=ACC[series] + (255,))
    return img.convert("RGB")  # 520〜1340 にシェアしたリールを置く


def pinned():
    out = []
    out.append(slide(0, "このアカウントで\nできること", "①経営のAI化 ②家計・積立\n③目標 ④受験の\nロードマップを、AIでつくります", cover=True))
    img, d = frame_base(0, CW, CH, safe_top=70)
    text_block(img, d, ["AIで道筋をつくる、とは"], 220, 66, t=99)
    steps = ["① 今の現在地を知る", "② ゴールまでのルートを作る", "③ 毎月、数字を記録する", "④ 道筋を自動で作り直す"]
    for i, st in enumerate(steps):
        y = 420 + i * 190
        d.rounded_rectangle([140, y, 940, y + 140], 24, fill=(32, 52, 82, 255))
        d.text((190, y + 40), st, font=font(52), fill=WHITE + (255,))
        if i < 3:
            d.text((520, y + 140), "▼", font=font(40), fill=ACC[1] + (255,))
    out.append(img.convert("RGB"))
    out.append(slide(2, "ご利用の前に", None) if False else _notice())
    return out


def _notice():
    img, d = frame_base(0, CW, CH, safe_top=70)
    text_block(img, d, ["ご利用の前に"], 220, 72, t=99)
    lines = ["・結果（売上・資産・目標達成・合格など）を保証するものではありません",
             "・専門家による個別の助言ではありません",
             "・投稿の事例はすべて架空です",
             "・AIで作成し、運営者が確認しています",
             "・受付の状況は、プロフィールのリンク先でご確認ください"]
    y = 420
    for ln in lines:
        y = text_block(img, d, wrap(d, ln, font(44, False), 880), y, 44, t=99, center=False, bold=False, gap=1.45) + 30
    return img.convert("RGB")


def spec_slides(sp):
    s = sp["series"]
    out = [slide(s, sp["cover"][0], sp["cover"][1], cover=True)]
    for i, (title, body) in enumerate(sp["slides"], 1):
        num = None if title[0].isdigit() else str(i)
        out.append(slide(s, title, body, num, sp["note"]))
    return out


def build_w1plus(out, media=True):
    """増量期1週目：content_w1.py の台本からリール・追加ストーリー・投稿表を作る。"""
    import content_w1 as C
    for day, s, q, sub in (C.EXTRA_STORIES if media else []):
        story_question(s, q, sub).save(out / f"story-{day}-1-question.png", optimize=True)
        story_reel(s).save(out / f"story-{day}-2-reel.png", optimize=True)
    for key, sp in (C.REELS.items() if media else []):
        fn, dur = slides_reel(spec_slides(sp), sp["series"])
        render_reel(out / f"reel-{key}.mp4", fn, dur)
    lines = ["# 増量期1週目の投稿表（1日リール3本＋ストーリー1本）", "",
             "時刻：7:30／12:15／20:30。キャプション・ハッシュタグ・代替テキストは、既存5本は `posts.md`、新しい16本は下記。", ""]
    for date, keys, (story, o1, o2) in C.SCHEDULE:
        lines.append(f"## {date}")
        for t, k in zip(C.TIMES, keys):
            f = k if k.startswith("reel-") else f"reel-{k}"
            lines.append(f"- {t}　`{f}.mp4`" + ("" if k.startswith("reel-") else f"（{C.REELS[k]['cover'][0].replace(chr(10), '')}）"))
        lines.append(f"- ストーリー（朝）　`{story}.png`　アンケート：{o1}／{o2}")
        lines.append("")
    lines.append("---")
    lines.append("")
    for key, sp in C.REELS.items():
        lines += [f"## `reel-{key}.mp4`", "**キャプション**", sp["caption"], "",
                  f"※{sp['note']}。" if "保証" not in sp["caption"] else "", "", f"**ハッシュタグ**：{sp['tags']}", "",
                  f"**代替テキスト**：{sp['alt']}", "", "---", ""]
    (out / "schedule-w1plus.md").write_text("\n".join(l for l in lines) + "\n")


def main():
    global BRAND
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--brand", default="")
    ap.add_argument("--only", default="all")
    a = ap.parse_args()
    BRAND = a.brand
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    if a.only in ("all", "images"):
        for i, im in enumerate(pinned(), 1):
            im.save(out / f"pinned-{i}.png", optimize=True)
        for day, s, q, sub in STORIES:
            story_question(s, q, sub).save(out / f"story-{day}-1-question.png", optimize=True)
            story_reel(s).save(out / f"story-{day}-2-reel.png", optimize=True)
    if a.only == "w1plus":
        build_w1plus(out)
        return
    if a.only in ("all", "reels"):
        reels = list(REELS)
        reels.append(("reel-tue-2-money.mp4",) + slides_reel(carousel_money(), 2))
        reels.append(("reel-thu-4-exam.mp4",) + slides_reel(carousel_exam(), 4))
        for name, fn, dur in reels:
            render_reel(out / name, fn, dur)


if __name__ == "__main__":
    main()
