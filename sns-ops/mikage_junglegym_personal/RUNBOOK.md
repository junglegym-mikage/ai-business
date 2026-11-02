# @mikage_junglegym_personal 運営手順（パーソナルジムJungleGym）

- 場所：神戸市東灘区御影中町1-6-7 シティーホームズ御影A 3F。トレーナー：いだ（オーナー）。マンツーマンのパーソナルトレーニング、シルクサスペンションなど。
- プロフィール：「ムリなく続く、大人のための健康習慣を。」「プロが教える姿勢改善・おすすめの健康習慣＆美容」。連絡は公式LINE（プロフィールのリンク）。
- 目的：問い合わせ 週2件・体験 週1件（10億円ロードマップの毎週の目標）。フォロワー数より「体験の問い合わせ」につながるかを見る。
- 2026-11-02 時点：投稿217・フォロワー376。最後の投稿は 10/19。

## 投稿づくり（毎週日曜・翌週の月〜日の7本。2026-11-03 オーナー指示で毎日投稿）
1. 最新の `sns-research/mikage_junglegym_personal/` の「伸びる型」「台本案」を読む（無ければ前回分）。先週の自分のリールの再生数も見る。
2. テーマの割り振り（目安）：①40代からの体づくり・ダイエットのよくある誤解 ②自宅でできる簡単な動き（姿勢・肩・腰まわり。痛みのある人は医療機関へ、と添える） ③ジムの中身（マンツーマン・シルクサスペンション・通い方）④体験の案内（週2本まで）。
3. 冒頭3秒はリサーチで伸びていた型（「実は」「9割が知らない」「〇〇な人は損してる」など）を使う。構成は結論→理由→具体例を基本にする。
4. caption：最初の1行で中身が分かる → 本文3〜6行 → 「体験・ご相談はプロフィールの公式LINEから」→ ハッシュタグ5〜8個（#神戸パーソナルジム #御影 #東灘区 #パーソナルトレーニング #40代ダイエット など）。料金は書かない（プロフィールで案内）。
5. 見た目：brand "パーソナルジム JungleGym｜神戸・御影"、colors {"bg":"#14211b","bg2":"#1f3329","gold":"#e3b04b","seal":"#ff8a5c","line":"#2f4a3c"}。
6. `approved: false` で posts.json に入れて push → オーナーに7本の冒頭と要点を送り、「OK」か直しをもらう。OK なら approved を true にして push。
- 禁止：「必ず痩せる」「〇kg痩せる」など結果の約束、ビフォーアフター写真（同意のないもの）、他のジムの悪口。

## データ（`posts.json`）
```json
{"posts": {"2026-11-04": {"approved": false, "theme": "…", "spec": {"type": "slides", "brand": "…", "colors": {…}, "dur": 10, "top": "…", "topFrom": 2.2, "scenes": [{"at": 0, "lines": [["文字", 64, "soft", "sans"], …]}, …]}, "caption": "…"}}, "posted": {}}
```
- scenes：1場面2〜3行。1行は全角12字以内（入らないと小さくなる）。色は ink / soft / gold / seal。1枚目（0〜2秒）が「冒頭3秒」。
- 1本 8〜12秒、4〜6場面。最後の場面は行動の呼びかけ。

## 投稿する（投稿タスクが行う）
0. 今日の日本時間の日付で `posts[日付]` を見る。無い・`approved` が true でない → 投稿しない（未承認なら「承認待ちのため投稿せず」と報告）。`posted[日付]` がある、またはリール一覧の最新キャプションが同じなら投稿済みなので何もしない。
1. 内蔵ブラウザ（mcp__remote-devices__Claude_Browser__）で resize_window を 1200x900 にしてから https://www.instagram.com/mikage_junglegym_personal/ を開く。
2. `../common/ig_render.js` と `../common/ig_reel.js` を javascript_exec でそのまま実行。`__igAccount()` が `/mikage_junglegym_personal/` でなければ、元のアカウント名を控えてから切り替える（https://www.instagram.com/ → 右上「切り替える」→ 一覧の mikage_junglegym_personal）。一覧に無い・パスワードを求められた → 投稿せず報告して終了。切り替え後、`/mikage_junglegym_personal/` と「プロフィールを編集」を確認できなければ投稿しない。
3. `__reelStart(spec)` → `__reelStatus()` が done（w=1080・h=1920、duration が spec.dur）になるまで待つ。
4. `await __igOpen()` → `await __reelAttach()` → 「リール動画としてシェア」の案内は OK → 切り取り画面で「元の比率」→「次へ」→ カバーは文字が全部出ているコマ →「次へ」。
5. キャプション欄を computer の left_click でクリック → computer の type で caption を一字一句入力 → 数秒待って `__igCaptionValue() === caption` を確認。Facebook へのシェア・AIラベルはオフのまま。
6. シェア直前に `__igAccount()` が `/mikage_junglegym_personal/` のままか再確認 → 「シェア」を left_click。
7. 公開ページで最新リールのキャプションが caption と一致するか確認（空なら `__igOpenEdit()` で入れる。削除・再投稿はしない）。
8. `posted[日付]` に投稿のIDと時刻を書いて push。元のアカウントに切り替えて戻す。resize_window を preset "desktop" に戻す。
9. 報告：投稿した内容、成功/失敗、フォロワー数、直近リールの再生数、新しいコメント・DMと返信案（返信は送らない）。
