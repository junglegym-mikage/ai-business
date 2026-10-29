# Claude × ChatGPT 共同開発の手順（株式システム）

## 全体の流れ
1. **オーナー**が Issue を登録（テンプレート「株式システムのタスク」）
2. **Claude** が `trading/issue-<番号>-…` ブランチで実装し、`trading/develop` 宛ての PR を作成
3. **GitHub Actions（trading-ci）** がテストと認証情報スキャンを実行し、結果を PR にコメント
4. **ChatGPT** が PR を独立レビュー（下の A〜C のどれか）
5. **Claude** が指摘を検証して修正 → CI が再テストして PR に記録
6. ChatGPT が「マージ可」→ **オーナー**が確認してマージ（Claude はマージしない）

実績：PR #2 でこの流れを 4 往復実施し、最終判定「マージ可」まで確認済み（レビュー記録は PR #2 のコメント）。

## ブランチ
| ブランチ | 用途 |
|---|---|
| `main` | 既存の事業サイト。株式システムのコードは入れない |
| `trading/develop` | 株式システムの統合ブランチ（PR の宛先） |
| `trading/issue-…` / `trading/claude-…` | 作業ブランチ |

## ChatGPT のレビュー方法（3段階）
- **A. 今すぐ使える（追加費用なし）**：Claude がアプリ内ブラウザで chatgpt.com に差分を送り、返答を PR に転記する。PR #2 はこの方法。Claude が作業中のときだけ動く。
- **B. ChatGPT にリポジトリを直接読ませる**：ChatGPT の GitHub 連携（読み取り専用）。リポジトリは公開なので、リンクを渡せば読める場面も多いが、連携すると検索・引用が安定する。
- **C. 完全自動（推奨）**：Codex のコードレビュー。PR が作られると ChatGPT 側（Codex）が自動でレビューを投稿する。レビュー基準は `AGENTS.md` の「Code Review Rules」を読む。

## オーナーの操作（MacBook のブラウザで）

### 1. Codex の自動レビューを有効にする（C）
1. chatgpt.com にログイン → 左メニュー「Codex」を開く
2. 「GitHub を接続」→ GitHub の画面で **Only select repositories** → `junglegym-mikage/ai-business` を選んで Install / Authorize
3. chatgpt.com/settings/code-review を開く → リポジトリ `ai-business` を選ぶ → 「Review code」の **Automatic review** をオン
4. 確認：PR #2 に `@codex review` とコメント → 👀 が付き、レビューが投稿されれば成功

費用：ChatGPT の契約プランの利用枠内（追加課金なし）。枠を使い切ると「クレジット購入」が出るが、自分で購入しない限り課金されない。※無料プランで使えるかは要確認。

### 2. Claude Code GitHub Actions を有効にする
1. https://github.com/apps/claude を開く → Install → **Only select repositories** → `ai-business` → Install
   （このアプリはコード・Issue・PR の読み書きなどの権限を求めます）
2. MacBook のターミナルで `claude setup-token` を実行（Claude Code が未インストールなら先に導入）。表示されたトークンをコピー
   - **このトークンはチャット・Issue・メモに貼らない**
3. GitHub のリポジトリ → Settings → Secrets and variables → Actions → **New repository secret**
   - Name: `CLAUDE_CODE_OAUTH_TOKEN` / Secret: 2 でコピーした値 → Add secret
4. PR #4（main 宛て、新規ファイル2つだけ）を確認してマージ
5. 確認：Issue に `@claude このIssueを実装して` とコメント → Claude が作業コメントを返せば成功

費用：サブスクリプション（Pro / Max など）の利用枠を使うので API の従量課金なし。公開リポジトリなので Actions 実行時間も無料。
API キー（`ANTHROPIC_API_KEY`）方式は従量課金になるため、承認なしでは使わない。

### 3. ブランチ保護（このセッションからは設定できなかったため手動）
1. リポジトリ → Settings → Branches → **Add branch protection rule**（または Rules → Rulesets）
2. Branch name pattern: `trading/develop`
3. オン：**Require a pull request before merging** / **Require status checks to pass** → `test` を選択
4. Do not allow bypassing は**オフ**のまま（オーナーがマージできるように）→ Create

`main` も同様に保護できますが、現在 main の事業サイトを GitHub 上で直接編集しているなら、保護すると直接編集できなくなる点に注意。

## ルール（抜粋）
- 実資金取引・証券口座への発注は実装しない（`trading.safety` とテストで担保）
- API キー等は GitHub の Secrets にだけ置く（CI が認証情報スキャンを実行）
- 有料サービスはオーナーの承認なしに使わない
- 詳細は `CLAUDE.md`（実装側）と `AGENTS.md`（レビュー側）
