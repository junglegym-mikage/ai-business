# @mikage_healthcare_support 運営手順（御影ヘルスケアサポート）

- 商品：プロトレーナーが選んだ 姿勢サポートインソール。15,000円（税込・送料無料）。サイズ 23.0〜28.0cm（0.5cm刻み、26.5cm は品切れ中）。ショップ：mikagehealth.base.shop（プロフィールのリンク）。
- 計画：Claude Docs「御影ヘルスケアサポート 拡大計画」（https://claude.ai/artifact/CCdCAynMh6YUyHmN7KGcX3）。ネットは柱④「Instagram・Threadsでトレーナー目線の姿勢・足の知識を発信しBASEへ誘導」。投稿はオーナーが承認してから。
- 2026-11-02 時点：投稿24・フォロワー8。最後の投稿は 2026年2月。

## 投稿づくり（毎週日曜・翌週の月〜日の7本。2026-11-03 オーナー指示で毎日投稿）
1. 最新の `sns-research/mikage_healthcare_support/` の「伸びる型」「台本案」を読む。先週の自分のリールの再生数も見る。
2. テーマの割り振り（目安）：①立ち仕事・歩き仕事の足の疲れ（美容師・看護・介護・販売・飲食）②足裏のアーチ・かかと・靴選びの知識 ③インソールの使い方・サイズの選び方・慣らし方 ④商品紹介（週2本まで）。
3. 冒頭3秒はリサーチの型を使う。構成は結論→理由→具体例を基本にする。
4. caption：最初の1行 → 本文3〜6行 → 「プロトレーナーが選んだインソールは、プロフィールのショップから（15,000円・送料無料）」→ ハッシュタグ5〜8個（#インソール #立ち仕事 #足の疲れ #姿勢 #神戸 など）。最後に「※医療機器ではありません。使い心地には個人差があります。」を入れる（商品に触れる投稿）。
5. 見た目：brand "御影ヘルスケアサポート"、colors {"bg":"#f3efe6","bg2":"#fbf8f2","ink":"#3b2f25","soft":"#8a7a68","gold":"#9a6b3f","seal":"#c0563b","line":"#dccfbd"}。
6. `approved: false` で posts.json に入れて push → オーナーに7本の冒頭と要点を送り、「OK」か直しをもらう。OK なら approved を true にして push。
- 禁止（薬機法・景品表示法）：「治る」「改善」「矯正」「不調にアプローチ」「救う」など効果や治療を思わせる表現、「正規19,800円→15,000円」のような二重価格、同意のないお客様の声。「支える」「サポート」「快適」「楽に」などの使い心地の表現にする。

## データ（`posts.json`）
```json
{"posts": {"2026-11-04": {"approved": false, "theme": "…", "spec": {"type": "slides", "brand": "…", "colors": {…}, "dur": 10, "top": "…", "topFrom": 2.2, "scenes": [{"at": 0, "lines": [["文字", 64, "soft", "sans"], …]}, …]}, "caption": "…"}}, "posted": {}}
```
- scenes：1場面2〜3行。1行は全角12字以内（入らないと小さくなる）。色は ink / soft / gold / seal。1枚目（0〜2秒）が「冒頭3秒」。
- 1本 8〜12秒、4〜6場面。最後の場面は行動の呼びかけ。

## 投稿する（投稿タスクが行う）
0. 今日の日本時間の日付で `posts[日付]` を見る。無い・`approved` が true でない → 投稿しない（未承認なら「承認待ちのため投稿せず」と報告）。`posted[日付]` がある、またはリール一覧の最新キャプションが同じなら投稿済みなので何もしない。
1. 内蔵ブラウザ（mcp__remote-devices__Claude_Browser__）で resize_window を 1200x900 にしてから https://www.instagram.com/mikage_healthcare_support/ を開く。
2. `../common/ig_render.js` と `../common/ig_reel.js` を javascript_exec でそのまま実行。`__igAccount()` が `/mikage_healthcare_support/` でなければ、元のアカウント名を控えてから切り替える（https://www.instagram.com/ → 右上「切り替える」→ 一覧の mikage_healthcare_support）。一覧に無い・パスワードを求められた → 投稿せず報告して終了。切り替え後、`/mikage_healthcare_support/` と「プロフィールを編集」を確認できなければ投稿しない。
3. `__reelStart(spec)` → `__reelStatus()` が done（w=1080・h=1920、duration が spec.dur）になるまで待つ。
4. `await __igOpen()` → `await __reelAttach()` → 「リール動画としてシェア」の案内は OK → 切り取り画面で「元の比率」→「次へ」→ カバーは文字が全部出ているコマ →「次へ」。
5. キャプション欄を computer の left_click でクリック → computer の type で caption を一字一句入力 → 数秒待って `__igCaptionValue() === caption` を確認。Facebook へのシェア・AIラベルはオフのまま。
6. シェア直前に `__igAccount()` が `/mikage_healthcare_support/` のままか再確認 → 「シェア」を left_click。
7. 公開ページで最新リールのキャプションが caption と一致するか確認（空なら `__igOpenEdit()` で入れる。削除・再投稿はしない）。
8. `posted[日付]` に投稿のIDと時刻を書いて push。元のアカウントに切り替えて戻す。resize_window を preset "desktop" に戻す。
9. 報告：投稿した内容、成功/失敗、フォロワー数、直近リールの再生数、新しいコメント・DMと返信案（返信は送らない）。
