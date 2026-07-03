# claude-code-template

Claude Code を使ったスペック駆動開発のための **言語非依存の汎用テンプレート** です。

クローン後、対話的なスラッシュコマンドで技術スタック・プロジェクト情報を初期化し、開発を開始できます。

## 含まれるもの

### 対応技術スタック

`/init-stack` で以下から選択して初期化できます。

| スタック | 構成 |
|---|---|
| **Node.js + TypeScript** | TypeScript / Vitest / ESLint / Prettier / Husky |
| **Python** | uv / ruff / mypy (strict) / pytest |
| **Go** | go modules / golangci-lint / 標準 testing |
| **Rust** | cargo / clippy / rustfmt |
| **なし (言語非依存)** | 設定ファイルは配置しない汎用構成 |

### 共通の開発環境

- **Dev Container** — 環境差異のない開発環境 (Claude Code 込み)
- **`/init-extras`** で追加できる開発支援ファイル群:
  - `.editorconfig`、`.env.example`、`CHANGELOG.md`、`CONTRIBUTING.md`、`SECURITY.md`、`CODE_OF_CONDUCT.md`
  - GitHub Issue/PR テンプレート、CI ワークフロー、Dependabot 設定

### Claude Code スラッシュコマンド

| コマンド | 説明 |
|---|---|
| `/init-stack` | 技術スタックを選択して設定ファイル一式を生成 |
| `/init-project` | プロジェクト名・著者・年・remote を一括設定 |
| `/init-extras` | editorconfig / CI / GitHub テンプレ等を配置 |
| `/setup-project` | 6つの永続ドキュメントを対話的に作成 |
| `/add-feature [機能名]` | 既存パターンに従って機能を実装 |
| `/review-docs [ファイル]` | ドキュメントの詳細レビュー |
| `/archive-project` | 開発廃止時のチェックリストを実行 |

### スキル

| スキル | 説明 |
|---|---|
| `steering` | 作業計画・実装・振り返りの管理 |
| `prd-writing` | プロダクト要求定義書の作成 |
| `functional-design` | 機能設計書の作成 |
| `architecture-design` | アーキテクチャ設計書の作成 |
| `development-guidelines` | 開発ガイドラインの作成 |
| `glossary-creation` | 用語集の作成 |
| `repository-structure` | リポジトリ構造定義書の作成 |

### ディレクトリ構造 (クローン直後)

```
.
├── .claude/              # Claude Code 設定
│   ├── agents/           # サブエージェント定義
│   ├── commands/         # スラッシュコマンド (/init-stack 等)
│   ├── skills/           # スキル定義
│   └── templates/        # /init-* で展開されるテンプレ素材
│       ├── stacks/       # 言語別の設定ファイル
│       └── extras/       # 追加ファイル群 (CI / GitHub 等)
├── .devcontainer/        # Dev Container 設定 (汎用)
├── .steering/            # 作業単位のドキュメント (自動生成)
├── docs/
│   └── ideas/            # アイデアメモ (壁打ち用)
├── .gitignore
├── CLAUDE.md             # Claude Code へのプロジェクト指示
├── LICENSE
└── README.md
```

> 各ファイル・ディレクトリの詳細な説明は [STRUCTURE.md](./STRUCTURE.md) を参照してください。

## 使い方

### 1. このテンプレートをクローン

```bash
git clone <このリポジトリ> <新しいプロジェクト名>
cd <新しいプロジェクト名>
```

### 2. Dev Container で開く (推奨)

VS Code で「Reopen in Container」を選択すると、Claude Code の最新版が自動でインストールされます。

> Dev Container を使うには Docker が必要です。コンテナを使わずローカルで Claude Code を使う場合はこのステップは不要です。

### 3. 技術スタックを初期化

```
/init-stack
```

対話的に以下を行います。

- 技術スタックを選択 (Node.js+TS / Python / Go / Rust / なし)
- 選択したスタックの設定ファイル一式を生成
- `.devcontainer/devcontainer.json` に必要な feature を追記
- `.gitignore` に言語固有エントリを追記
- `CLAUDE.md` の「技術スタック」節を更新
- (任意) 続けて `/init-extras` の処理も実行

### 4. プロジェクト情報を初期化

```
/init-project
```

対話的に以下を取得し、関連ファイル内のプレースホルダーを一括置換します。

- プロジェクト名
- 説明
- 著者名
- ライセンス年
- (任意) git remote URL

### 5. (任意) 追加ファイル群を配置

ステップ3で配置しなかった場合は、ここで実行できます。

```
/init-extras
```

`.editorconfig` / `.env.example` / `CHANGELOG.md` / `CONTRIBUTING.md` / `SECURITY.md` / `CODE_OF_CONDUCT.md` / GitHub Issue/PR テンプレ / CI ワークフロー / Dependabot 設定 を配置します。

### 6. 依存関係のインストール

選択したスタックに応じて手動で実行してください。

```bash
# Node.js + TypeScript
npm install

# Python
uv sync

# Go
go mod download

# Rust
cargo fetch
```

### 7. 永続ドキュメントを作成

```
/setup-project
```

以下を対話的に作成します。

1. `docs/product-requirements.md` — PRD
2. `docs/functional-design.md` — 機能設計書
3. `docs/architecture.md` — 技術仕様書
4. `docs/repository-structure.md` — リポジトリ構造定義書
5. `docs/development-guidelines.md` — 開発ガイドライン
6. `docs/glossary.md` — 用語集

### 8. 機能を実装

```
/add-feature <機能名>
```

ステアリングファイル (`.steering/`) を作成して、計画 → 実装 → 検証を進めます。計画生成後に一度だけ承認を挟み、承認後は実装〜検証を自動で完走します。

## 日常の使い方

通常は会話形式で依頼するだけで Claude Code が適切なスキルを判断します。

```
> PRD に新機能を追加して
> architecture.md のパフォーマンス要件を見直して
> /add-feature ユーザープロフィール編集
> /review-docs docs/product-requirements.md
```

## 開発廃止時

リポジトリをアーカイブする際に実行してください。

```
/archive-project
```

以下を自動で実施 / 案内します。

- 秘密情報の最終チェック (`.env`、鍵ファイル等の検出)
- `README.md` 冒頭に Archived バナーを挿入
- `.steering/` を `archive/steering-YYYYMMDD/` に移動
- 依存固定の提案 (スタックに応じた手順)
- 最終リリースタグ作成の案内
- `gh repo archive` のコマンド案内 (自動実行しません)

## カスタマイズ

### 新しい技術スタックを追加する

`.claude/templates/stacks/<新スタック名>/` に設定ファイル一式を配置し、`.claude/templates/stacks/claude-md-sections/<新スタック名>.md` を追加。`.claude/commands/init-stack.md` の選択肢にも追記してください。

### 追加ファイル群をカスタマイズ

`.claude/templates/extras/` 配下のファイルを編集すれば、`/init-extras` 実行時の出力が変わります。

## ライセンス

MIT — 詳細は [LICENSE](./LICENSE) を参照。
