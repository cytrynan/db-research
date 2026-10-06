# 要求: 常用化（daily-use）— 研究の土台を「毎日くろこが使う道具」にする

> 段: **T2**（スキーマ変更なし・課金なし・外部ユーザーなし・外部 API なし＝問1 全 No。仕様はこちらで決めるので受入基準と非スコープを明示）。
> 識別子契約: 不要（ユーザー入力の文字列を識別子として保存・照合する項目が無い。bundle 名・view 名・kind は閉じた語彙で検査するだけ、質問文は保存しない）。
> 発端: K 指示 2026-10-06「stock/・tax/・scout/・experiments/ も取り込んで。実用段階でない理由の 4 点について取り組みたい」。4 点の実測は 2026-10-05 の報告（型判定・応答時間・鮮度・入口）。

## brief

1. **取り込み範囲を全 7 bundle に**: references / dev / memory に加えて stock / tax / scout / experiments（`~/.agents/knowledge/` 配下・個人データを置かない共有知見）を取り込む。bundle → 既定パスの台帳をコードに 1 か所で持ち、以後の同期の対象にする。
2. **型判定のフォールバック**: `dbr ask` は型を判定できない質問を **① 探し物として検索する**（exit 2 で止めない）。判定器（`dbr classify`）は `unknown` を返し続け、回答には「推定（語彙に当たらず探し物として検索）」と明示する。
3. **常駐で 3 秒**: 埋め込みモデルを読み込んだプロセス（`dbr serve`・ループバック HTTP）を常駐させ、`dbr ask` はそこに問い合わせる。未起動なら自動で起こす。HF Hub への問い合わせは既定で切る（モデルはキャッシュ済み・D-13 の「ローカルのみ」を通信面でも守る）。
4. **自動同期**: `dbr sync` が全 bundle の 変更・新規・削除 を DB に反映する（取り込み → 削除の反映 → 埋め込み → fact → summary を差分で）。常駐プロセスが起動時と一定間隔で実行する。
5. **エージェントの入口**: `dbr mcp`（stdio の MCP サーバー・常駐へ中継）を用意し、くろこがどのセッションからでも `ask` / `count` / `sync` を呼べる形にする。Claude Code への登録コマンドは README に書く（登録そのものは K 承認後）。
6. **測定と記録**: 取り込み範囲の拡大後に ① find の既定経路を再測定して v11 として記録する（母集団が 145→約 270 文書に増えた影響を数値で残す）。応答時間は before/after を記録する。

## 受入基準（correctness。これに効く指摘だけが差し戻し対象）

- **R1 取り込み**: `dbr sync` 後、`v_by_bundle` に 7 bundle が並び、各 bundle の document 件数 ＝ 正本フォルダの `.md` 件数（`private.md`・`*.bak*`・ドットディレクトリ配下を除く）。`private.md` は document に 0 件（SQL で確認）。
- **R2 型判定**: 語彙に当たらない質問（例「Codex の起動で PATH の罠は何だった？」）が `--kind` 無しで exit 0・find の結果を返し、テキスト出力と JSON（`kind_fallback: true`）に推定である旨が出る。`dbr classify` の同じ質問は `unknown` のまま。既存の型判定テスト（20 問）は不変。
- **R3 常駐**: 常駐稼働時、`dbr ask` の find / asof / overview が **3 秒以内**、count が **1 秒以内**（各 5 回連続・K の PC）。常駐未起動の初回は自動起動して **90 秒以内**に応答。`--no-daemon`（または環境変数 `DBR_NO_DAEMON=1`）で従来の単発経路が動く。同じ質問に対する常駐経由と単発経路の JSON は、揮発値（秒数・summary id 等）を除いて一致する。
- **R4 通信**: 常駐・単発とも `HF_HUB_OFFLINE=1` を既定にし、起動ログに HF Hub への問い合わせ警告（「unauthenticated requests to the HF Hub」）が出ない。モデル未取得のときは「`DBR_HF_ONLINE=1` を付けて 1 回取得」と案内して exit 5。
- **R5 同期**: 統合テストで ①ファイルの内容変更 → sync で `content_hash` が更新され、古い断片・埋め込みが残らない ②ファイル削除 → sync で document / chunk / chunk_embedding / fact と、その文書の summary（document・section 階層）が消える ③無変更の sync は全 bundle 0 変更で終わる（冪等）。常駐は起動時に 1 回、以後 `--sync-interval`（既定 30 分）ごとに sync し、`/health` に最後の同期時刻と結果を出す。
- **R6 入口**: `dbr mcp` が stdio で `ask` / `count` / `sync` / `health` の 4 ツールを公開し、MCP クライアントからの `list_tools` と `ask`（常駐経由）が通る（統合テスト・fake 埋め込み）。
- **R7 ゲート**: `bash scripts/gate.sh` が PASS（ruff / mypy strict / pytest db 込み・カバレッジ 80%）。
- **R8 記録**: `docs/bench-results.md` v11、FD（Classifier・Serve・Sync・MCP）、architecture（常駐プロセス・ポート・オフライン）、decisions（D-17 フォールバック・D-18 常駐とオフライン・D-19 同期）、README 使い方、RESUME、`docs/log.md`。

## 非スコープ（この単位ではやらない）

- scope の語彙（LEXICON）に stock/tax/scout/experiments の枝を足すこと・既存語彙の手直し（held-out の質問を足してから＝RESUME 1）
- 質問セットの拡張・④ LLM 層の再採点・`valid_to` の自動推定（RESUME 1〜3）
- Windows タスクスケジューラへの常駐登録（自動起動で足りる。要るなら別単位で K 判断）
- 常駐 HTTP の認証（ループバック限定のみ。単一利用者の PC で、ローカルプロセスは正本ファイルも直接読める）
- `claude mcp add` の実行（K 承認後に K の環境で 1 回。コマンドは README に書く）
- Supabase・外部 API・スキーマ変更
