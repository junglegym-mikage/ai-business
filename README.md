# ai-business

小規模事業者向けAIサービスの有料需要を検証するリポジトリ（AI Content Studio）。

- `index.html`：SNS投稿パックの販売ページ（試作・決済不可）
- `gbp/`：Googleマップ整備パックの販売ページ（試作・決済不可）
- `samples/`：架空店舗のサンプル
- `docs/`：市場比較・提案文・QA・引き継ぎ（`docs/CLAUDE_HANDOFF.md`が最新状況）
- `kpi.csv`, `templates/leads.csv`：計測用テンプレート

テスト：`python3 tests/check_pages.py`

注意：`main`はGitHub Pagesで公開される。`main`へのマージは本番公開と同じ扱いで、オーナーの承認が必要。
