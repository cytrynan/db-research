# RESUME — 次のセッションが最初に読むファイル（2026-09-29 更新）

> 目的: 会話の文脈が切れても、ここと `docs/decisions.md`・`.steering/*/tasklist.md` だけで再開できるようにする。

## いまどこか
- **完了した作業単位（5つ・すべて issue クローズ・push 済み）**
  1. `20260929-foundation-ingest` — Docker PostgreSQL（localhost 限定）・OKF 取り込み（冪等・private.md 二重拒否）・count ビュー
  2. `20260929-search-classify` — Sudachi→tsvector（OR）・ローカル埋め込み（e5-small）・RRF・型判定（20/20）・bench find
  3. `20260929-rerank-tuning` — 並べ直し（cross-encoder）・重み付き RRF・HNSW 強制・sweep/hnsw bench
  4. `20260929-asof-overview` — fact 表（バイテンポラル・explicit/dated_text/inferred）・summary 表（抽出型 3 段）・`dbr ask` の asof（断片→文書→全体で絞る）/overview・bench count|asof|overview。受入検証（readonly-reviewer/Opus）の指摘 D1〜D5 を回収済み（0010 で `fact_uniq` に md5(value)）。未回収 3 件は次の単位で回収
  5. `20260929-review-leftovers` — summary の陳腐化検知（`stale_summaries`・overview の WARN・`dbr summarize --check`＝exit 6）、recorded_at の規則（generated.at 無しは valid_from）、`v_verified`（0011・Q12）、`scripts/gate.sh`／`gate.ps1`（故障注入で exit 1 を確認）
- **確定した測定値**: `docs/bench-results.md`（v4〜v7）。① find 10 問の最良は **embed_ctx（文脈付き埋め込み単体）recall@5 0.90 / MRR 0.811**（全文検索を混ぜると下がる。HNSW は 2,154 行では速度差なし）。② count 4/4 stable。③ asof **4/4**（v7・2 回一致）。④ overview は `docs/overview-answers.md` で **K 採点待ち**。
- **実データ DB `dbr`**（Docker `dbr_pg`・127.0.0.1:5432）に references（16）＋dev（53）＋memory（76）＝145 文書・1,230 断片、埋め込み plain/ctx、fact 346 行（dated_text 295・inferred 51）、summary 3 段。テストは別 DB `dbr_test`。
- **訂正済みの誤記**: v6 で「INDEX と work.md の日付不整合」と書いたのは timestamptz の UTC 表示の誤読（work.md に 2026-08-10 は無い）。実データの「発見」は原本を grep してから書く。

## 次にやること（推奨順）
1. **K の採点**: `docs/overview-answers.md` の Q19・Q20 を 1〜5 で採点 → ④ 抽出型の天井を確定してから LLM 要約（ローカル。外部 API は K 承認要）と比較する
2. 検索側の残り: `embed_ctx_rerank`、断片スコアの文書集約、語彙一致が効く質問の追加

## 再開の手順
```bash
docker compose up -d --wait && uv run dbr migrate          # 再実行は 0 件
bash scripts/gate.sh                                        # ruff → mypy → pytest（db 含む・80%）。K は pwsh -File scripts/gate.ps1
uv run dbr count v_by_bundle                                 # 実データが残っているか
```
埋め込みを作り直す必要は無い（`dbr embed` は未生成分だけ計算）。`private.md` は絶対に取り込まない（走査除外＋トリガー）。

## 守ること（決定台帳 `docs/decisions.md` の要点）
- 個人データは手元の PostgreSQL のみ・外部ホスティング禁止（D-5）。埋め込み・並べ直しもローカルモデルのみ（D-13）
- 正本は OKF Markdown。DB は捨てて作り直せる派生（D-9）。マイグレーションの既存ファイルは編集しない（D-3）
- ゲートは `bash scripts/gate.sh`（pipefail 込み・4 段）を通してから commit。手で `&&` を並べない（並べて事故 3 回）
- commit / push・受入検証（別コンテキスト。Codex 不可なら readonly-reviewer/Opus）・振り返りを毎単位で
