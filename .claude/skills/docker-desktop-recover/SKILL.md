---
name: docker-desktop-recover
description: |
  Windows の Docker Desktop が起動直後にエラーダイアログを出して落ちる／`docker` コマンドが
  `failed to connect to the docker API at npipe:////./pipe/dockerDesktopLinuxEngine` のまま応答しない
  状態から復旧する。原因は前回のクラッシュで残った AF_UNIX ソケット（reparse point）で、
  通常のファイル API では削除できず、親ディレクトリごと退避するしかない。
  次のような時に使う:「Docker が起動しない/落ちる」「docker info が返らない」
  「backend crashed と出る」「dev の DB コンテナが上がらない（＝先に Docker が死んでいる）」。
  逆に、Docker は動いていてコンテナ個別の問題（ビルドが遅い・compose の設定ミス・
  ポート衝突）には使わない。Docker Desktop 以外（Linux の dockerd・Podman）にも使わない。
---

# Docker Desktop (Windows) 起動不能からの復旧

## 何が起きているか

Docker Desktop は起動時に AF_UNIX ソケットファイルを「**消してから作り直す**」。
前回のクラッシュでこのファイルが**削除できない残骸**として残ると、消せない時点で毎回落ちる。

```
starting services: initializing Inference manager:
listening on unix://<HOME>\AppData\Local\Docker\run\dockerInference:
remove ...\dockerInference: The file cannot be accessed by the system.
```

**残骸は複数の場所にできる**（Inference manager と Secrets Engine）。ここが罠で、
片方だけ退避すると「その回は起動が進むが、もう片方で落ちて新しい残骸を作る」ため
振り出しに戻る。**両方を同じ停止状態でまとめて退避しないと直らない。**

## 使い方

まず診断だけ（何も変更しない）:

```bash
powershell -ExecutionPolicy Bypass -File .claude/skills/docker-desktop-recover/scripts/recover.ps1 -Check
```

復旧を実行する:

```bash
powershell -ExecutionPolicy Bypass -File .claude/skills/docker-desktop-recover/scripts/recover.ps1
```

スクリプトがやること:

1. `docker info` の疎通確認（**必ずジョブ＋タイムアウトで叩く**。素で叩くと返らずハングし、
   プロセスが溜まって状況が悪化する）と、直近のクラッシュ理由のログ抽出
2. Docker 関連プロセスの停止
3. 残骸ディレクトリを**まとめてリネーム退避**（削除ではないので元に戻せる）
   - `%LOCALAPPDATA%\Docker\run`
   - `%LOCALAPPDATA%\docker-secrets-engine`
4. Docker Desktop を起動し、`docker info` が返るまで待つ（既定 300 秒）

正常時は何もせず終了する（`-Force` で強制実行）。

> スクリプトは **UTF-8 (BOM 付き)** で保存すること。Windows PowerShell 5.1 は BOM 無し UTF-8 の
> `.ps1` を cp932 として読むため、日本語コメントを含むスクリプトが構文エラーで丸ごと動かなくなる。

## 実行後にやること

- **DB や dev 環境のコンテナは自動で戻らない場合がある。** プロジェクト側の起動コマンド
  （`docker compose up -d` 等）を実行して、必要なコンテナが上がったか確認する
- 再起動ポリシー付きのコンテナ（本番スタック等）が**一緒に上がってくる**ことがある。
  同一ホスト名でポートだけ違う dev 環境を使っている場合、Cookie がポートを区別しないため
  セッションが衝突する。想定外のコンテナが上がっていないか `docker ps` で確認する

## つまずいたときの判断

| 状況 | 対応 |
|---|---|
| 退避（リネーム）自体が失敗する | Docker を掴んだプロセスが残っている。サインアウトまたは OS 再起動後に再実行 |
| 起動したが別のパスのソケットで落ちる | エラーに出たパスを `recover.ps1` の `$TargetDirs` に**追加**する（1つずつ試さない） |
| タイムアウトする | GUI のエラーダイアログを読む。**ログの `<HOME>` はログ側の伏せ字**で、環境変数の展開失敗ではない |

## やってはいけないこと（実測で無駄と分かっている）

- **個別のソケットファイルを消そうとする** — `Remove-Item` / `del` / `[System.IO.File]::Delete()` /
  `\\?\` プレフィックスの**いずれも** `The file cannot be accessed by the system.` で失敗する
- **片方のディレクトリだけ退避して様子を見る** — 直ったように見えて再発する。時間を浪費するだけ
- **`EnableDockerAI: false` にする** — 設定を切っても Inference manager の初期化は走るので回避できない
- **`docker info` を素で叩いて待つ** — 返らずハングし、溜まったプロセスが `wsl -l -v` まで巻き込む

## 誤診しやすい点

- `The filename, directory name, or volume label syntax is incorrect` を見て
  「ユーザー名の非 ASCII 文字が原因」と考えたくなるが、**それだけでは断定できない**
  （ACP=932 / システムロケール ja-JP なら文字は表現できる）。実際の原因は残骸ループだった
- 退避ディレクトリが何個も溜まっている場合、それは「たまに起きる不具合」ではなく**常態**。
  重要な場面（デモ・納品前検証）の前には、作業開始時に `-Check` で疎通を確認しておく
