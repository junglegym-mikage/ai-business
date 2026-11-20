"""Instagram への予約投稿（Meta 公式の Instagram API・統合ログインのシステムユーザートークン・無料）。

GitHub Actions から30分ごとに実行される（仕様：docs/platform/p1-kit/sns-engine.md 6.1）。
投稿するのは次をすべて満たすものだけ：
  - approvals.json に、その投稿の「承認ハッシュ」がある（オーナーOK済み）
    承認ハッシュ＝投稿日時・形式・ファイルの中身（SHA-256）・キャプション・アカウント名から計算。
    承認後にどれかが変わるとハッシュが一致せず、自動的に未承認になる
  - 予定時刻を過ぎていて、遅れが3時間以内
  - posted.json の状態が未投稿（なし）か failed（コンテナ作成前の失敗）
状態：processing（投稿処理中。GitHub に記録してから API を呼ぶ）→ published / failed / unknown。
unknown（投稿できたか確認できない）は自動で再投稿せず、オーナー確認に回す。

アクセストークンは GitHub の Secrets（IG_ACCESS_TOKEN）にオーナーが入れる。ログに出さない。
Instagram のユーザーID はリポジトリ変数 IG_USER_ID。
動画・画像は公開リポジトリの完成素材を jsDelivr の URL（コミット固定）で Instagram に取り込ませる。

使い方:
  python3 ig_publish.py check            # トークンとアカウントの確認（投稿しない）
  python3 ig_publish.py run [--dry]      # 予定どおり投稿（--dry は対象の表示だけ）
  python3 ig_publish.py approve 2026-11-02 [...]   # その日の投稿の承認ハッシュを approvals.json に記録（オーナーOK後に Claude が実行）
"""
import datetime as dt
import hashlib
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

# 新しいアプリは「統合ログイン（ビジネス向けFacebookログイン）」になるため graph.facebook.com と Instagram のユーザーID を使う
# トークンの種類で接続先を切り替える：Instagram のトークン（IG で始まる）は graph.instagram.com、
# ビジネス向けFacebookログインのトークンは graph.facebook.com
API = ("https://graph.instagram.com/v23.0" if os.environ.get("IG_ACCESS_TOKEN", "").startswith("IG")
       else "https://graph.facebook.com/v23.0")
IG_ID = os.environ.get("IG_USER_ID", "")  # リポジトリ変数。Instagram のプロアカウントのID（数字）
ACCOUNT = "process_performance_ai"
REPO = os.environ.get("GITHUB_REPOSITORY", "junglegym-mikage/ai-business")
ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../../.."))
SNS = os.path.join(ROOT, "docs/platform/sns")
QUEUE, POSTED, APPROVALS = (os.path.join(SNS, n) for n in ("queue.json", "posted.json", "approvals.json"))
JST = dt.timezone(dt.timedelta(hours=9))
MAX_LATE = dt.timedelta(hours=3)
TOKEN_WARN_DAYS, TOKEN_STOP_DAYS = 50, 58


def load(p, default):
    return json.load(open(p)) if os.path.exists(p) else default


def save(p, obj):
    with open(p, "w") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
        f.write("\n")


def item_hash(item):
    with open(os.path.join(ROOT, item["file"]), "rb") as f:
        fh = hashlib.sha256(f.read()).hexdigest()
    key = json.dumps([ACCOUNT, item["at"], item["type"], item["file"], fh, item.get("caption", "")], ensure_ascii=False)
    return hashlib.sha256(key.encode()).hexdigest()


def git(*args):
    return subprocess.run(["git", "-C", ROOT, *args], check=True, capture_output=True, text=True).stdout.strip()


def record(posted, msg):
    """posted.json を保存して GitHub に反映。反映できなければ例外（＝投稿しない）。"""
    save(POSTED, posted)
    if not os.environ.get("GITHUB_ACTIONS"):
        return
    git("add", POSTED)
    if subprocess.run(["git", "-C", ROOT, "diff", "--cached", "--quiet"]).returncode == 0:
        return
    git("commit", "-q", "-m", msg)
    for i in range(3):
        try:
            git("pull", "--rebase", "-q")
            git("push", "-q")
            return
        except subprocess.CalledProcessError:
            time.sleep(5)
    raise RuntimeError("posted.json を GitHub に記録できなかった")


def call(method, path, **params):
    token = os.environ["IG_ACCESS_TOKEN"]
    params["access_token"] = token
    data = urllib.parse.urlencode(params)
    url = f"{API}/{path}"
    req = urllib.request.Request(url + "?" + data) if method == "GET" else urllib.request.Request(url, data=data.encode(), method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace").replace(token, "***")
        raise RuntimeError(f"{method} {path} -> {e.code}: {body[:400]}") from None


def media_url(path):
    return f"https://cdn.jsdelivr.net/gh/{REPO}@{git('rev-parse', 'HEAD')}/{path}"


def check_token_age():
    issued = os.environ.get("IG_TOKEN_ISSUED")  # リポジトリ変数（例 2026-11-01）。トークン再発行のたびにオーナーが更新
    if not issued:
        return
    days = (dt.date.today() - dt.date.fromisoformat(issued)).days
    if days >= TOKEN_STOP_DAYS:
        sys.exit(f"トークン発行から{days}日。失効が近いため投稿を止めました。オーナーがトークンを再発行し、IG_TOKEN_ISSUED を更新してください")
    if days >= TOKEN_WARN_DAYS:
        print(f"::warning::トークン発行から{days}日。{TOKEN_STOP_DAYS}日目で投稿を止めます。再発行してください")


def check_account():
    if not IG_ID.isdigit():
        sys.exit("IG_USER_ID（数字）が設定されていません")
    me = call("GET", IG_ID, fields="username")
    if me.get("username") != ACCOUNT:
        sys.exit(f"アカウントが {ACCOUNT} ではないため停止しました")
    return me


def create_container(item):
    url = media_url(item["file"])
    if item["type"] == "REELS":
        return call("POST", f"{IG_ID}/media", media_type="REELS", video_url=url, caption=item.get("caption", ""), share_to_feed="true")["id"]
    if item["type"] == "STORIES":
        key = "video_url" if item["file"].endswith(".mp4") else "image_url"
        return call("POST", f"{IG_ID}/media", media_type="STORIES", **{key: url})["id"]
    return call("POST", f"{IG_ID}/media", image_url=url, caption=item.get("caption", ""))["id"]


def wait_ready(cid):
    for _ in range(40):  # 最大約10分
        st = call("GET", cid, fields="status_code")
        if st.get("status_code") == "FINISHED":
            return
        if st.get("status_code") in ("ERROR", "EXPIRED"):
            raise RuntimeError(f"container status {st.get('status_code')}")
        time.sleep(15)
    raise RuntimeError("container timeout")


def run(dry):
    queue, posted, approvals = load(QUEUE, []), load(POSTED, {}), load(APPROVALS, {})
    now = dt.datetime.now(JST)
    due = []
    for item in queue:
        st = posted.get(item["id"], {}).get("state")
        if st not in (None, "failed"):
            continue
        if approvals.get(item["id"]) != item_hash(item):
            continue
        at = dt.datetime.fromisoformat(item["at"])
        if at > now:
            continue
        if now - at > MAX_LATE:
            if st is None:
                posted[item["id"]] = {"state": "skipped_late", "at": now.isoformat()}
            continue
        due.append(item)
    if dry:
        for i in due:
            print("would publish:", i["id"], i["type"], i["file"])
        return 0
    if not due:
        record(posted, "SNS: 投稿記録を更新")
        return 0
    check_account()
    errors = 0
    for item in due:
        print(f"publish: {item['id']} {item['type']} {item['file']}")
        posted[item["id"]] = {"state": "processing", "at": now.isoformat()}
        record(posted, f"SNS: 投稿処理開始 {item['id']}")
        try:
            cid = create_container(item)
            wait_ready(cid)
        except Exception as e:  # まだ公開していない → failed（次回再試行してよい）
            posted[item["id"]] = {"state": "failed", "at": now.isoformat(), "error": str(e)[:300]}
            record(posted, f"SNS: 投稿失敗 {item['id']}")
            print("  failed:", e)
            errors += 1
            continue
        try:
            mid = call("POST", f"{IG_ID}/media_publish", creation_id=cid)["id"]
            posted[item["id"]] = {"state": "published", "media_id": mid, "at": now.isoformat()}
            print("  published:", mid)
        except Exception as e:  # 公開されたか分からない → unknown（自動で再投稿しない）
            posted[item["id"]] = {"state": "unknown", "container": cid, "at": now.isoformat(), "error": str(e)[:300]}
            print("  unknown:", e)
            errors += 1
        record(posted, f"SNS: 投稿記録 {item['id']}")
    return 1 if errors else 0


def approve(dates):
    queue, approvals = load(QUEUE, []), load(APPROVALS, {})
    n = 0
    for item in queue:
        if item["at"][:10] in dates:
            approvals[item["id"]] = item_hash(item)
            n += 1
    save(APPROVALS, approvals)
    print(n, "items approved for", ", ".join(sorted(dates)))


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "run"
    if mode == "approve":
        return approve(set(sys.argv[2:]))
    if mode == "check":
        me = check_account()
        lim = call("GET", f"{IG_ID}/content_publishing_limit", fields="quota_usage,config")
        print("account:", me.get("username"))
        print("publishing limit:", json.dumps(lim.get("data", lim), ensure_ascii=False))
        check_token_age()
        return
    if os.environ.get("GITHUB_ACTIONS") and os.environ.get("IG_PUBLISH_ENABLED") != "true":
        sys.exit("IG_PUBLISH_ENABLED が true ではないため投稿しません")
    check_token_age()
    sys.exit(run("--dry" in sys.argv))


if __name__ == "__main__":
    main()
