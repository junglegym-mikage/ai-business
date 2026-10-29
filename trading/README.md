# trading — 日本株・米国株 自動売買システム（ペーパートレード検証専用）

まず 5 万円相当の模擬資金で、売買ルールに利益の再現性があるかを検証するためのコードです。
**実際の証券口座への発注・実資金取引は行いません**（`trading.safety` が止めます）。

## 実行
```bash
cd trading
python -m pip install -e ".[dev]"
python -m pytest
```

## 開発の流れ
1. オーナーが Issue（テンプレート「株式システムのタスク」）を登録
2. Claude が `trading/issue-<番号>-...` ブランチで実装し、`trading/develop` 宛ての PR を作成
3. GitHub Actions（trading-ci）が自動テストし、結果を PR にコメント
4. ChatGPT（Codex）が PR を独立レビュー
5. Claude が指摘を検証・修正し、再テスト結果が PR に記録される
6. 指摘なし（Codex 👍／ChatGPT「マージ可」）＋CI成功なら `trading/develop` へマージ（オーナーの委任で Claude が実施。main へはオーナーのみ）

詳しくは `docs/trading/collaboration.md`。
