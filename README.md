# db-research

K の個人記録を **質問の型（探し物／数える／時点／全体）で振り分けて検索する仕組み** の研究リポジトリ。
決まったことは [docs/decisions.md](docs/decisions.md)、方向づけは [docs/ideas/](docs/ideas/) を参照。

## できること

- 質問文から型を推定して答える（`dbr ask`）。語彙に当たらない質問は探し物として検索し、推定であることを明示する（D-17）。
- ① 探し物: 記録の中から関連する文書を探す。全文検索・埋め込み・その組み合わせ・並べ直しを切り替えられる。
- ② 数える: 定義済みのビュー（bundle 別・type 別・未確認・陳腐化）で件数を出す。
- ③ 時点: 日付つきの事実を抽出しておき、「いつ決めたか」やある時点の状態を答える。
- ④ 全体: bundle → 文書 → 節の要約階層から全体像を答える。
- 7 つの bundle（references/dev/memory/stock/tax/scout/experiments）の変更・新規・削除を DB に反映し、Claude Code のセッションから `ask` / `count` / `sync` / `health` を呼べるようにする。
- 方式ごとの検索品質と速度を測る（`dbr bench`。結果は [docs/bench-results.md](docs/bench-results.md)）。

## 使い方（常用・2026-10-06 時点）

```bash
uv sync
cp .env.example .env            # DBR_DSN=postgresql://dbr:dbr@127.0.0.1:5432/dbr（localhost は使わない）
docker compose up -d --wait     # PostgreSQL 16 + pgvector を 127.0.0.1:5432 にだけ公開
uv run dbr migrate              # migrations/ を番号順に適用（再実行は 0 件）
uv run dbr sync                 # 7 bundle（references/dev/memory/stock/tax/scout/experiments）の変更・新規・削除を反映（取り込み→埋め込み→fact→summary・冪等）
uv run dbr ask "Codex の起動で PATH の罠は何だった？"   # 型を推定して答える。語彙に当たらなければ探し物として検索（推定と明示・D-17）
                                # 初回は常駐（dbr serve・127.0.0.1:47821）を自動で起こす（約 25 秒）。以後は 1 秒前後で返る（D-18）
uv run dbr serve --stop         # 常駐を止める。--no-daemon か DBR_NO_DAEMON=1 で単発計算（従来どおり・モデル読み込み込みで 20 秒前後）
uv run dbr mcp                  # エージェントの入口（stdio MCP: ask / count / sync / health。常駐へ中継）
```

- **Claude Code への登録（K が 1 回・承認後）**: `claude mcp add --scope user dbr -- uv run --project C:\Users\meer0\dev\db-research\db-research-main dbr mcp`
- DSN の解決順は `--dsn` → 環境変数 `DBR_DSN` → **リポ直下 `.env` の `DBR_DSN`**。MCP（Claude Code が env なしで起こす）とそこから起こす常駐は `.env` で接続する（2026-10-08 修正。以前は `.env` を読まず、常駐が消えると MCP の全ツールが `Error executing tool <name>` になった）
- Hugging Face Hub への問い合わせは既定で切ってある（`HF_HUB_OFFLINE=1`）。モデル未取得のときだけ `DBR_HF_ONLINE=1` を付けて 1 回取得する
- 正本フォルダの既定は `~/.claude/references`・`~/.claude/projects/C--Users-meer0/memory`・`~/.agents/knowledge/<bundle>`。環境変数 `DBR_ROOT_<BUNDLE>`（例 `DBR_ROOT_MEMORY`）で上書き

### 研究用（個別コマンド）

```bash
uv run dbr ingest ~/.agents/knowledge/dev --bundle dev   # OKF フォルダを取り込み（冪等）。通常は sync で足りる
uv run dbr count v_by_bundle    # ② 数える: 定義済みビュー（v_by_bundle / v_by_type / v_unverified / v_stale）
uv run dbr embed --bundle dev --variant plain   # 埋め込み（ローカル e5-small・CPU・冪等）。--variant ctx で文脈付き
uv run dbr ask "メガネの度数どこに書いた？"     # 型判定 → find なら検索（--mode fts|embed|hybrid|hybrid_ctx）
uv run dbr bench --kind find    # find 10 問 × 6 方式（並べ直し込み）の recall@5 / recall@20 / MRR（結果: docs/bench-results.md）
uv run dbr bench --kind sweep   # RRF の fts 重み × 候補数の掃引（hybrid_ctx）
uv run dbr bench --kind hnsw    # HNSW を強制して ef_search 40/100/250 の recall（厳密比）とレイテンシ
uv run dbr ask "..." --mode hybrid_ctx_rerank   # ローカル cross-encoder で並べ直し
uv run dbr facts --bundle references     # ③ 時点: 日付つきの事実を抽出（explicit / dated_text / inferred・冪等）
uv run dbr summarize --bundle references # ④ 全体: 抽出型の要約階層（bundle→document→section・冪等）
uv run dbr ask "収益目標を決めたのはいつ？"               # asof: 履歴（--at 2026-08 で時点指定）
uv run dbr ask "references の記録は全体としてどう？"     # overview: bundle 要約＋近い文書の要約
uv run dbr bench --kind count|asof|overview   # ②③④ の測定（overview は docs/overview-answers.md に回答を書き K が採点）
uv run dbr reindex --bundle dev # 分かち書き規則を変えたとき lexemes だけ再計算
uv run pytest                   # ユニット / uv run pytest -m db で統合（Docker 必須）
```

- 個人データの DB は **ループバック接続のみ**（`example.com` 等は exit 3）。`private.md` は走査除外＋DB トリガーで二重拒否
- 品質ゲートは `bash scripts/gate.sh`（K は `pwsh -File scripts/gate.ps1`）: ruff format/check → mypy → pytest（db 含む・カバレッジ 80%）を pipefail で連鎖。**commit は `bash scripts/gate-commit.sh <msg-file>`**（ゲートが通った時だけ add→commit。手で `&&` を並べると起点がずれてゲート失敗のまま commit が通る事故が 4 回起きた）

## 技術の詳細

| 項目 | 内容 |
|---|---|
| 言語・CLI | Python 3.12 / uv / typer（`dbr` コマンド。入口は `src/dbr/cli.py`） |
| DB | PostgreSQL 16 + pgvector（Docker・`compose.yaml`）。ORM は使わず psycopg 3 と素の SQL |
| 日本語の分かち書き | SudachiPy（取り込みと検索で同じ関数を使う） |
| 埋め込み | ローカルの `intfloat/multilingual-e5-small`（CPU）だけで始めている。外部 API は測定の土台ができてから比較対象として足す方針（D-13） |
| エージェントの入口 | stdio の MCP サーバー（`dbr mcp`）。常駐へ中継するだけ |

### 常駐と運用ログ

- 常駐は起動直後と 30 分ごとに `sync` を走らせる（`dbr serve --sync-interval 0` で無効）。状態は `curl http://127.0.0.1:47821/health`（`db_unreachable` が true なら DB に届いていない）、運用ログは `~/.dbr/serve.log`（件数と時刻だけ）
- **利用ログ** `~/.dbr/usage.jsonl`（1 要求 1 行: 呼び出し元・質問文・型・上位ヒット・応答時間・結果。D-20）。集計は `uv run dbr usage --days 7`（呼び出し元×結果・フォールバック率・p50/p90・0 件だった質問・エラー）。同期が 2 回続けて DB に届かない（または ask が接続段で失敗する）と `~/.dbr/DB-UNREACHABLE.flag` が立ち、Claude Code のセッション開始時に警告が出る（常駐が `docker restart/start` で**自動復旧**を試みる＝D-21。手で `docker stop` した時は触らないので `docker start dbr_pg` を手で。同期が成功するとフラグは自動で消える。自動復旧を止めるなら `dbr serve --no-auto-recover`）

### ディレクトリとドキュメント

| パス | 中身 |
|---|---|
| `src/dbr/features/<機能>/` | 機能ごとの縦割り（ask / search / count / asof / overview / ingest / sync / serve / mcp_server / bench など）。テストは同じフォルダに置く |
| `src/dbr/shared/` | DB 接続・埋め込み・並べ直し・LLM・分かち書きの共通部 |
| `migrations/` | 番号順に適用する SQL |
| `tests/integration/` | Docker の PostgreSQL を使う統合テスト（`-m db`） |
| `bench/results/` | 測定結果の JSON |
| [docs/decisions.md](docs/decisions.md) | 決定（D-番号）と根拠 |
| [docs/functional-design.md](docs/functional-design.md) / [docs/architecture.md](docs/architecture.md) | 機能設計と構成 |
| [docs/repository-structure.md](docs/repository-structure.md) | ディレクトリの配置規則と依存の向き |
| [RESUME.md](RESUME.md) | 進捗と、次のセッションが最初に読む再開手順（作業単位の記録は `.steering/`） |

このリポジトリは [claude-code-template](https://github.com/6dorg/claude-code-template) から作成。テンプレートの利用手順（スラッシュコマンド・タスク管理・司令塔方式）はテンプレートの README と、このリポの `CLAUDE.md`・`STRUCTURE.md` にある。

## ライセンス

MIT — 詳細は [LICENSE](./LICENSE) を参照。
