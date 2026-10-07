# brief: MCP `dbr` が全ツール失敗する件の修正（mcp-dsn-fallback）

> 段: **T1**（スキーマ変更なし・課金なし・外部ユーザーなし・外部 API なし＝問1 全 No）。識別子契約: 不要（ユーザー入力を識別子として保存・照合しない）。
> 発端: 2026-10-07〜08、Claude Code の MCP `dbr` が `ask` / `sync` / `health` すべて `Error executing tool <name>` だけを返す（K 指示 2026-10-08）。

## 実測した原因（2026-10-08・kuroko/claude-opus-5-5）
- Docker（`dbr_pg` healthy）・PostgreSQL は正常。**MCP を Claude Code と同じ形（`uv run --project … dbr mcp`・env 追加なし）で stdio から呼ぶと `is_error=True`・本文 `Error executing tool health` を再現**。
- 本当のエラーは `~/.dbr/serve.log` の `ValueError: DSN が未指定です（--dsn か環境変数 DBR_DSN）`（12 回）。`DBR_DSN` は `.env` にしか無く、**`.env` を読む経路がコードに無い**。10-06 に開発シェル（DSN を export 済み）から起こした常駐が 10-07 02:15 UTC 以降に消え、以後 MCP からの自動起動（`ensure_daemon` → `dbr serve`）が毎回 DSN 無しで即死していた。CLI（`uv run dbr ask`）も素のシェルからは同じ理由で失敗する。
- 「詳細なし」の理由: MCP SDK 2.x の `MCPServer` は `ToolError` 以外の例外（ここでは `RuntimeError` / `ValueError`）をクラッシュ扱いにし、クライアントへは `Error executing tool <name>` だけを返す（SDK `mcpserver/exceptions.py` の `UnexpectedToolError`）。

## やること
1. `resolve_dsn` の解決順を **`--dsn` → 環境変数 `DBR_DSN` → リポ直下 `.env` の `DBR_DSN`** にする（CLI・常駐・MCP が起こす常駐の全経路が通る 1 か所）。ループバック検査は従来どおり下流（`connect()` / `assert_loopback`）で効く。
2. MCP の 4 ツールで、想定内の失敗（`ValueError` / `RuntimeError`）を `ToolError` に包み直し、メッセージがクライアントに届くようにする。
3. 実データで `sync` → `ask "試験監督 収入"` が `references/fuyou.md` を返すことを MCP 経由で確認する。

## 実装者が決めた仕様級判断（レビューの採点基準）
- J1: `.env` は**リポ直下の 1 ファイルだけ**（`Path(__file__)` 起点。cwd は見ない＝MCP は Claude Code の cwd で起きるため）。読むのは `DBR_DSN` キーだけで、他のキーを `os.environ` に流し込まない。
- J2: 優先順位は明示 `--dsn` > 環境変数 > `.env`（既存の上書き手段の意味を変えない）。`.env` が無い・読めない・キーが無い時は従来どおり `ValueError`（文言に `.env` の場所を足す）。
- J3: MCP の包み直しは `ValueError` / `RuntimeError` だけ。それ以外の例外は SDK のクラッシュ扱い（詳細は stderr のログ）のまま。
- J4（受入検証の回収で追加）: `.env` が UTF-8 で読めない（cp932 保存など）ときは「未指定」に合流させず、`<path> を UTF-8 で読めません` の `ValueError` にする（キーは書いてあるのに「未指定」と出すと原因を誤誘導するため）。
- 既知の制約（不採用・任意指摘 2）: 簡易パーサは dotenv と 3 点ずれる——同じキーが複数あると先勝ち／`export DBR_DSN=…` は読まない／値の後ろの ` # comment` を値に含める。`cp .env.example .env` の経路では踏まない。

## 振り返り（2026-10-08）
- **検証**: ゲート 244 passed（回収前）→ **245 passed（回収後・cov 90.9%）**。故障注入で 2 つの修正をそれぞれ外すと新テストが FAIL（MCP 2 件・DSN 3 件）。実 MCP（stdio・Claude Code と同じ起動形・cwd 別）で health → 常駐の自動起動・sync・ask「試験監督 収入」→ `references/fuyou.md` が 1 位。この会話の Claude Code からも `mcp__dbr__health` / `ask` が成功。
- **受入検証**: Codex は usage limit（解除 10:37・15 分超）→ 例外(c) で readonly-reviewer（Fable 5.1）。R1〜R6 PASS・必須 1 件（cp932 の `.env`）＝司令塔が再現して採用（J4）・任意 1（`--dsn` の help）採用・任意 2 不採用（上の既知の制約）。回収後の差分は同じ係に再確認させた（R1・R6 PASS・R2・R5 不変・必須 0。`ruff format` の 2 か所を指摘→整形してゲート通過）。
- **止まった点**: 初回の再現スクリプトが SDK 2.x の `CallToolResult.is_error`（1.x は `isError`）で落ちた。また、確認用の MCP クライアント（Python SDK）から起こした常駐は、クライアント終了と一緒に消えた（観測 1 回）。`uv run dbr ask` や venv の python から直接起こした常駐は生き残った（各 1 回）。**仮説**: SDK がサーバーを `KILL_ON_JOB_CLOSE` のジョブに入れ（`mcp/os/win32/utilities.py:207`）、孫の常駐もそのジョブに属するため（未切り分け）。**10-07 に常駐が消えた理由は未特定**（Claude Code 側のプロセス管理は未確認）。修正後は常駐が消えても次の呼び出しで約 25〜30 秒かけて起き直る。
- **具体→抽象**: 開発シェルで export した環境変数に頼る設定は、常駐が生きている間は隠れ、プロセスが入れ替わった時に初めて壊れる。**起動経路が複数ある道具（CLI・常駐・MCP）は、設定の読み込みを全経路が通る 1 か所に置き、「素の環境から起こす」経路で 1 回確かめる**。
