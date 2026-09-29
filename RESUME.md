# RESUME — 次のセッションが最初に読むファイル（2026-09-29 更新）

> 目的: 会話の文脈が切れても、ここと `docs/decisions.md`・`.steering/*/tasklist.md` だけで再開できるようにする。

## いまどこか
- **完了した作業単位（3つ・すべて issue クローズ・push 済み）**
  1. `20260929-foundation-ingest` — Docker PostgreSQL（localhost 限定）・OKF 取り込み（冪等・private.md 二重拒否）・count ビュー
  2. `20260929-search-classify` — Sudachi→tsvector（OR）・ローカル埋め込み（e5-small）・RRF・型判定（20/20）・bench find
  3. `20260929-rerank-tuning` — 並べ直し（cross-encoder）・重み付き RRF・HNSW 強制・sweep/hnsw bench
- **確定した測定値**: `docs/bench-results.md`（v4/v5）。find 10 問の最良は **embed_ctx（文脈付き埋め込み単体）recall@5 0.90 / MRR 0.811**。全文検索を混ぜると下がる。HNSW は 2,154 行では速度差なし。
- **実データ DB `dbr`**（Docker `dbr_pg`・127.0.0.1:5432）に references（16 文書）＋ dev（53 文書）＝1,077 断片、埋め込み plain/ctx 各 1,077 行が入っている。テストは別 DB `dbr_test`。

## 次にやること（推奨順）
1. **③時点（F5）と④全体（F6）**: `fact`（valid_from/valid_to/recorded_at）と `summary`（bundle→document→section）の表を**新番号のマイグレーション**で足し、`dbr ask` の asof/overview を実装。20 問の残り 10 問（count 4・asof 4・overview 2）を測る
2. 検索側の残り: `embed_ctx_rerank`、断片スコアの文書集約、語彙一致が効く質問の追加
3. 運用: `scripts/gate.sh`（pipefail・ruff・mypy・pytest・coverage）にゲートを固定する

## 再開の手順
```bash
docker compose up -d --wait && uv run dbr migrate          # 再実行は 0 件
uv run pytest -q && uv run pytest -q -m db tests/integration  # 統合は dbr_test
uv run dbr count v_by_bundle                                 # 実データが残っているか
```
埋め込みを作り直す必要は無い（`dbr embed` は未生成分だけ計算）。`private.md` は絶対に取り込まない（走査除外＋トリガー）。

## 守ること（決定台帳 `docs/decisions.md` の要点）
- 個人データは手元の PostgreSQL のみ・外部ホスティング禁止（D-5）。埋め込み・並べ直しもローカルモデルのみ（D-13）
- 正本は OKF Markdown。DB は捨てて作り直せる派生（D-9）。マイグレーションの既存ファイルは編集しない（D-3）
- ゲート（ruff / mypy / pytest / coverage 80%）を通してから commit。連鎖は `set -o pipefail` を先頭に
- commit / push・受入検証（別コンテキスト。Codex 不可なら readonly-reviewer/Opus）・振り返りを毎単位で
