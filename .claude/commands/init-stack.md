---
description: 技術スタックを対話的に選択して設定ファイル一式を生成する
---

# 技術スタックの初期化

このコマンドは技術スタックを選択し、関連する設定ファイル一式をプロジェクトルートに配置します。

## 実行方法

```
> /init-stack
```

## 実行前の確認

以下のいずれかが既にリポジトリ直下に存在する場合、「上書きしますか?」を必ず確認すること。

- `package.json`
- `pyproject.toml`
- `go.mod`
- `Cargo.toml`

ユーザーが上書きを承諾しない場合は中断する。

## 手順

### ステップ1: スタックの選択

`AskUserQuestion` で技術スタックを尋ねる。

選択肢:

1. **Node.js + TypeScript** — TS / Vitest / ESLint / Prettier / Husky 一式
2. **Python** — uv / ruff / mypy strict / pytest 一式
3. **Go** — go modules / golangci-lint / 標準 testing
4. **Rust** — cargo / clippy / rustfmt
5. **なし (言語非依存)** — 設定ファイルは配置せず、CLAUDE.md だけ更新

選択肢のキー: `node-ts` / `python` / `go` / `rust` / `none`

### ステップ2: テンプレ素材の展開

選択結果に応じて、以下のディレクトリ配下のファイルを **すべて** Read してプロジェクトルートに同じ相対パスで Write する。

| 選択 | 展開元 |
|---|---|
| node-ts | `.claude/templates/stacks/node-ts/` |
| python | `.claude/templates/stacks/python/` |
| go | `.claude/templates/stacks/go/` |
| rust | `.claude/templates/stacks/rust/` |
| none | (展開なし) |

ファイル内の `{{PROJECT_NAME}}` / `{{AUTHOR}}` / `{{PROJECT_DESCRIPTION}}` などのプレースホルダーは **このコマンドでは置換しない**。`/init-project` で一括置換するため、テンプレ素材のまま配置する。

### ステップ3: devcontainer.json への feature 追記

スタックに応じて `.devcontainer/devcontainer.json` の `features` に追記する。

| スタック | 追加する feature |
|---|---|
| node-ts | `ghcr.io/devcontainers/features/node:1` (`version: lts`)、`postCreateCommand: "npm install"` |
| python | `ghcr.io/devcontainers/features/python:1` (`version: "3.12"`)、`postCreateCommand: "uv sync"` |
| go | `ghcr.io/devcontainers/features/go:1` (`version: "1.22"`)、`postCreateCommand: "go mod download"` |
| rust | `ghcr.io/devcontainers/features/rust:1` (`version: "latest"`)、`postCreateCommand: "cargo fetch"` |
| none | (変更なし) |

Edit ツールで `features` ブロック内に追加する。Claude Code feature は維持。

### ステップ4: .gitignore への言語固有エントリ追記

`/init-stack` 実行で言語固有のエントリをここに追記される、というコメント行の下に、スタック別エントリを Edit で追加する。

| スタック | 追加エントリ |
|---|---|
| node-ts | `node_modules/`<br>`npm-debug.log*`<br>`yarn-debug.log*`<br>`yarn-error.log*`<br>`*.tsbuildinfo`<br>`.nyc_output/` |
| python | `__pycache__/`<br>`*.py[cod]`<br>`*$py.class`<br>`.pytest_cache/`<br>`.mypy_cache/`<br>`.ruff_cache/`<br>`.venv/`<br>`venv/`<br>`htmlcov/` |
| go | `*.exe`<br>`*.test`<br>`*.out`<br>`vendor/` |
| rust | `target/`<br>`Cargo.lock` (バイナリの場合は残す、ライブラリなら gitignore) |
| none | (追加なし) |

### ステップ5: CLAUDE.md の技術スタック節を更新

`.claude/templates/stacks/claude-md-sections/<stack>.md` を Read し、その内容で CLAUDE.md の `## 技術スタック` 節 (`## スペック駆動開発の基本原則` の直前まで) を置換する。

Edit ツールで以下のブロックを丸ごと置換:

```markdown
## 技術スタック

> ⚠️ 未設定。`/init-stack` を実行して技術スタックを選択・初期化してください。

<!-- /init-stack 実行でこのセクションが具体的な技術スタック情報に書き換えられます -->
<!-- 選択肢: Node.js + TypeScript / Python / Go / Rust / なし (言語非依存) -->
```

↓ 上記を、選択スタックの claude-md-sections の内容で置換。

### ステップ6: 追加ファイル群の確認

末尾で `AskUserQuestion` を表示:

> 追加ファイル群 (.editorconfig / .env.example / CHANGELOG / CI / Issue・PRテンプレ等) も配置しますか?
> - はい → そのまま `/init-extras` の処理を続行
> - いいえ → ここで終了
> - 後で → ここで終了 (ユーザーは後から `/init-extras` を実行可能)

「はい」の場合は、内部的に `/init-extras` の手順を続行する。

## 完了条件

- 選択スタックの設定ファイル一式がリポジトリ直下に存在する
- `.devcontainer/devcontainer.json` に該当スタックの feature が追加されている
- `.gitignore` に言語固有エントリが追記されている
- `CLAUDE.md` の技術スタック節が選択内容で更新されている

完了時のメッセージ:
```
「技術スタックの初期化が完了しました!

選択したスタック: {スタック名}

次に実行すべきコマンド:
1. /init-project — プロジェクト名・著者名・ライセンス情報の初期化
   (このコマンドで {{PROJECT_NAME}} 等のプレースホルダーが置換されます)
2. /setup-project — 永続ドキュメントの作成

依存関係のインストールは、開発を開始する前に手動で実行してください:
- Node.js: npm install
- Python: uv sync
- Go: go mod download
- Rust: cargo fetch
」
```
