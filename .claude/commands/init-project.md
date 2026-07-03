---
description: プロジェクトメタ情報 (名前・著者・ライセンス・remote) を一括初期化
---

# プロジェクトメタ情報の初期化

このコマンドは、プロジェクト名・著者名・ライセンス年・git remote URL を取得し、関連ファイル内のプレースホルダー (`{{PROJECT_NAME}}` 等) を一括で置換します。

## 実行方法

```
> /init-project
```

## 実行前の確認

このコマンドは多くのファイルを書き換えます。実行前に変更をコミットしていることを推奨してください。

## 手順

### ステップ1: 情報の取得

以下を対話的に取得する (各値を順に質問する):

1. **プロジェクト名**: 英数字とハイフンのみ推奨 (例: `my-awesome-app`)
2. **プロジェクト説明** (任意): 1行程度の説明 (例: `スペック駆動開発のためのXXツール`)
3. **著者名**: 例 `Jane Doe` または `Jane Doe <jane@example.com>`
4. **ライセンス年**: 既定値は現在の年 (西暦4桁)
5. **git remote URL** (任意): 例 `git@github.com:user/repo.git`。空欄でスキップ可能。

### ステップ2: 関連ファイルの一括置換

以下のファイルが存在する場合に Edit ツールで置換する。存在しないファイルはスキップする。

#### プレースホルダー対応表

| プレースホルダー | 置換内容 |
|---|---|
| `{{PROJECT_NAME}}` | ステップ1のプロジェクト名 |
| `{{PROJECT_DESCRIPTION}}` | ステップ1の説明 (未入力の場合は空文字) |
| `{{AUTHOR}}` | ステップ1の著者名 |
| `{{YEAR}}` | ステップ1のライセンス年 |

#### 対象ファイル

- `package.json` — `name`, `description`, `author` フィールド
- `pyproject.toml` — `[project]` の `name`, `description`, `authors`
- `go.mod` — `module {{PROJECT_NAME}}` 行
- `Cargo.toml` — `[package]` の `name`, `description`, `authors`
- `.devcontainer/devcontainer.json` — `name`, `workspaceFolder`（※ `workspaceFolder` は実際のマウント先 `/workspaces/<クローン先フォルダ名>` と一致させる必要がある。フォルダ名とプロジェクト名が異なる場合は、フォルダ名側に合わせること）
- `LICENSE` — `[year]` / `[fullname]` 等のプレースホルダー (元の形式に応じて置換)
- `README.md` — 冒頭の `# {{PROJECT_NAME}}` 見出し (もし存在すれば)
- `src/main.rs` 内の `use {{PROJECT_NAME}}::add;` — Rust スタックのみ（※下記の正規化に注意）

各ファイルを Edit ツールで `replace_all: true` で置換する。

#### ⚠️ Rust のクレート名正規化（重要）

Cargo はパッケージ名のハイフンをクレート識別子ではアンダースコアへ自動変換する。
そのため **ソースコード内の `use` / `extern crate` などクレート名参照だけは、`{{PROJECT_NAME}}` を「ハイフン→アンダースコアに変換した名前」で置換**すること（`Cargo.toml` の `name` は元のハイフン名のままでよい）。

例: プロジェクト名が `my-awesome-app` の場合

- `Cargo.toml`: `name = "my-awesome-app"` （そのまま）
- `src/main.rs`: `use my_awesome_app::add;` （**アンダースコア化**。`use my-awesome-app::add;` はコンパイルエラー）

プロジェクト名にハイフンが無い場合は変換不要。

### ステップ3: LICENSE の更新

LICENSE が MIT 形式の場合、次のパターンで著者名と年を置換する。

```
Copyright (c) [year] [fullname]
```
↓
```
Copyright (c) {YEAR} {AUTHOR}
```

(現状の LICENSE が既存著者名のままなら、その値を置換する。読み込んで状況を確認する。)

### ステップ4: git の初期化案内

#### 4-1. git の状態を確認
- `.git/` ディレクトリの有無を Glob で確認

#### 4-2. 状態に応じた案内

**git リポジトリでない場合**:
```
このディレクトリはまだ git リポジトリではありません。
以下のコマンドで初期化してください:

  git init
  git add .
  git commit -m "chore: initial commit"
```

**git リポジトリだが remote が未設定の場合**:
(ユーザーが remote URL を入力した場合のみ)
```
以下のコマンドで remote を設定してください:

  git remote add origin {remote-url}
  git branch -M main
  git push -u origin main
```

git コマンドは Claude が自動実行せず、提示するだけ。

## 完了条件

- 上記対象ファイル内のプレースホルダーがユーザー入力値で置換されている
- (該当する場合) LICENSE の著者名と年が置換されている

完了時のメッセージ:
```
「プロジェクトメタ情報の初期化が完了しました!

設定した値:
- プロジェクト名: {project_name}
- 説明: {description}
- 著者: {author}
- ライセンス年: {year}

次のステップ:
- /init-extras を実行して追加ファイル群を配置 (任意)
- /setup-project を実行して永続ドキュメントを作成
」
```
