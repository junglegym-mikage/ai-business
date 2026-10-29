# trading/paper-state — ペーパートレード（模擬売買）の実行記録

**実資金ではありません。** 模擬資金 5 万円での売買判定・約定・損益を毎営業日記録するブランチです。

- `state/report.md`：最新の日次レポート（評価額・保有・翌日の注文・停止状態）
- `state/trades.csv`：約定の記録（手数料・スリッページ込み）
- `state/equity.csv`：日ごとの評価額
- `state/state.json`：再開用の状態（手で編集しない）

実行：毎営業日の朝（日本時間）に Claude の予定タスクがこのブランチへ空コミットを push → GitHub Actions（paper-trade）が
`trading/develop` のコードでテスト → データ取得 → 模擬売買 → 結果をここにコミット。
停止中（state/report.md の「停止状態」）は新規注文を出しません。解除はオーナーの判断です。
