---
description: 開発廃止時のチェックリストを実行 (バナー追加 / .steering 整理 / 秘密情報チェック / タグ案内)
---

# プロジェクトのアーカイブ準備

このコマンドは、リポジトリを廃止・アーカイブする際の準備作業を支援します。

## ⚠️ 注意

このコマンドはファイル削除・移動・README の改変を含みます。
**実行前に必ず全ての変更をコミット・プッシュしてください。**

## 実行方法

```
> /archive-project
```

## 手順

### ステップ0: 実行確認

`AskUserQuestion` で次を確認する:

> このリポジトリをアーカイブしますか? すべての変更をコミット済みであることを確認してください。
> - はい、続行する
> - いいえ、キャンセル

「いいえ」の場合は処理を中断。

### ステップ1: 秘密情報の最終チェック

Glob で以下のパターンを検索し、ヒットがあれば警告メッセージを表示する。

- `.env`
- `.env.local`
- `.env.*`
- `*.pem`
- `*.key`
- `id_rsa*`
- `id_ed25519*`
- `*.p12`
- `*.pfx`

ヒットがあった場合の警告:
```
⚠️ 以下の秘密情報候補ファイルが見つかりました:

{ファイル一覧}

これらをリポジトリにコミットしていないか、最終確認してください。
git log と git ls-files で過去のコミット内も確認することを強く推奨します。

続行しますか? (はい/いいえ)
```

ヒットがない場合は「秘密情報の候補ファイルは見つかりませんでした」と表示。

### ステップ2: アーカイブバナーの追加

`README.md` の最上部 (もし最初の見出し `# ...` がある場合は、その直後) に以下を Edit ツールで挿入する。

```markdown
> ⚠️ **このリポジトリはアーカイブされました ({YYYY-MM-DD})**
>
> 新規の機能追加・バグ修正は行われません。fork や参照は自由ですが、issue / PR への応答は保証されません。
>
> 後継プロジェクト・参考リンク: (該当があれば追記してください)

```

`{YYYY-MM-DD}` は実行日。

ユーザーに「後継リポジトリの URL を表示しますか?」を質問し、入力されたら上記の最終行に追記する。

### ステップ3: .steering の整理

`.steering/` ディレクトリ内のファイルがある場合 (`.gitkeep` 以外)、以下を実行する。

1. `archive/` ディレクトリを作成
2. `.steering/` の中身を `archive/steering-{YYYYMMDD}/` に移動

PowerShell (Windows) の例:
```powershell
$dest = "archive\steering-$(Get-Date -Format yyyyMMdd)"
New-Item -ItemType Directory -Force -Path $dest | Out-Null
Get-ChildItem -Path .steering -Exclude .gitkeep | Move-Item -Destination $dest
```

bash / sh (macOS・Linux) の例:
```bash
dest="archive/steering-$(date +%Y%m%d)"
mkdir -p "$dest"
find .steering -mindepth 1 -maxdepth 1 ! -name .gitkeep -exec mv {} "$dest"/ \;
```

実行環境に応じてどちらかを使う。`.steering/.gitkeep` は維持してディレクトリ自体は残す。

### ステップ4: 依存固定の提案

検出スタックに応じて、ロックファイル/依存固定の案内を表示する。

| スタック | 案内 |
|---|---|
| node-ts | `package.json` の `^` と `~` プレフィックスを除去するか、`npm shrinkwrap` の実行を提案 |
| python | `uv lock` を実行して `uv.lock` を最新に、`pyproject.toml` の `dependencies` を厳密版に固定することを提案 |
| go | `go mod tidy` と `go.sum` のコミット確認を提案 |
| rust | `Cargo.lock` をコミットすることを確認 (ライブラリでも、アーカイブ時は固定すると再現性が高い) |
| none | (案内なし) |

`package.json` の `^` `~` プレフィックス除去は自動では行わない (壊す可能性があるため)、案内のみ。

### ステップ5: 最終リリースタグの案内

git コマンドの案内文字列を表示する (Claude は実行しない):

```
最終リリースタグを作成することを推奨します:

  git tag -a v-final -m "Final release before archiving"
  git push origin v-final
```

### ステップ6: GitHub リポジトリのアーカイブ案内

```
GitHub 上でリポジトリ自体をアーカイブする場合、以下を実行してください:

  gh repo archive <owner>/<repo>

または GitHub Web UI から:
  Settings > General > Danger Zone > Archive this repository

⚠️ アーカイブ後は書き込み不可になります。最終コミットとタグのプッシュを忘れずに。
```

`gh repo archive` は Claude が **自動実行しない**。コマンド文字列の提示のみ。

## 完了条件

- README.md に Archived バナーが追加されている
- `.steering/` 内のファイル (`.gitkeep` 以外) が `archive/steering-{YYYYMMDD}/` に移動されている
- 秘密情報チェックの結果が表示されている
- 依存固定・タグ作成・`gh repo archive` の案内が表示されている

完了時のメッセージ:
```
「アーカイブ準備が完了しました。

実行済み:
✅ README.md にアーカイブバナー追加
✅ .steering/ → archive/steering-{YYYYMMDD}/ に移動
✅ 秘密情報チェック ({結果})

ユーザーが実行する必要のあること:
□ 依存固定 (上記案内に従って)
□ 最終リリースタグの作成
□ git commit & push
□ gh repo archive または GitHub Web UI でのアーカイブ
」
```
