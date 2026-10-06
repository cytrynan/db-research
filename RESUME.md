# RESUME — 次のセッションが最初に読むファイル（2026-10-06 更新）

> 目的: 会話の文脈が切れても、ここと `docs/decisions.md`・`.steering/*/tasklist.md` だけで再開できるようにする。

## いまどこか
- **完了した作業単位（9 つ・すべて issue クローズ）**
  1. `20260929-foundation-ingest` — Docker PostgreSQL（localhost 限定）・OKF 取り込み（冪等・private.md 二重拒否）・count ビュー
  2. `20260929-search-classify` — Sudachi→tsvector（OR）・ローカル埋め込み（e5-small）・RRF・型判定（20/20）・bench find
  3. `20260929-rerank-tuning` — 並べ直し（cross-encoder）・重み付き RRF・HNSW 強制・sweep/hnsw bench
  4. `20260929-asof-overview` — fact 表（バイテンポラル）・summary 表（抽出型 3 段）・`dbr ask` の asof / overview・bench count|asof|overview
  5. `20260929-review-leftovers` — summary の陳腐化検知・recorded_at の規則・`v_verified`・`scripts/gate.sh`／`gate.ps1`
  6. `20260929-find-tuning2` — `embed_ctx_rerank`・文書集約（max / rrf_all / rrf_top3）・`bench --kind tune`。**D-14: 既定を embed_ctx＋rrf_top3 に**
  7. `20260930-overview-llm` — ④ にローカル LLM の回答層（Qwen2.5-1.5B・CPU）。**D-15: 配線したが既定は抽出型のまま**（K 採点 抽出型 5/5・LLM 4/3）
  8. `20260930-bundle-scope` — 質問の語から bundle を推定し ① と ④ の証拠を boost。**D-16: 既定 scope=boost w=1.0**（① 1.00/0.883）
  9. `20261006-daily-use` — **常用化**: 取り込みを 7 bundle に拡大（`dbr sync`・D-19）、不明 → 探し物のフォールバック（D-17）、常駐 `dbr serve` と HF オフライン既定（D-18）、エージェントの入口 `dbr mcp`。計算本体を `features/ask` に抽出し CLI・常駐・MCP が同じ関数を呼ぶ
- **確定した測定値**: `docs/bench-results.md`（v4〜v11c）。① find 10 問は **embed_ctx＋rrf_top3＋boost で recall@5 1.00 / MRR 0.883**（v10＝v11。取り込みを 145→269 文書に広げても不変。**in-sample**＝語彙は質問を見ながら作った）。② count 4/4 stable。③ asof 4/4。④ overview は K 採点済み（抽出型 5/5・LLM 4/3＝抽出型で足りる。LLM 層は保留）。
- **応答時間（2026-10-06・常駐あり・温まった状態）**: count 0.46〜0.51 秒 × 5 / find 0.56〜0.58 / asof 0.59〜0.62 / overview 0.67〜0.71（CLI の起動を軽くした後。常駐なしは 20〜29 秒・初回の自動起動込み 23〜27 秒）。**ただし同期直後の最初の数回は 2 秒台**（原因未特定・R3 の「1 秒以内 × 5 回」をその間は外す＝K 判断待ち）。生データは `.steering/20261006-daily-use/tasklist.md`
- **実データ DB `dbr`**（Docker `dbr_pg`・127.0.0.1:5432）: 7 bundle・276 文書・2,918 断片・埋め込み plain/ctx 5,836・fact 565・summary 3,201（2026-10-06・受入検証の回収後）。正本の `.md` 件数と全 bundle で一致（16/59/77/15/4/23/82・private.md 0）。experiments の 6 ファイルは正本側の YAML を直して取り込み済み
- **訂正済みの誤記**: v6 で「INDEX と work.md の日付不整合」と書いたのは timestamptz の UTC 表示の誤読。実データの「発見」は原本を grep してから書く。

## 次にやること（推奨順）
1. ~~K の作業: MCP の登録~~ → **2026-10-06 登録済み**（`claude mcp add --scope user dbr -- uv run --project C:/Users/meer0/dev/db-research dbr mcp`・Status Connected）。新しい Claude Code セッションから `dbr` の `ask` / `count` / `sync` / `health` が呼べる。くろこの日常の参照（`~/.claude/CLAUDE.md` §2 の INDEX.md 経由）をこの入口に切り替えるかは K 判断＝規範の変更
2. **質問セットの拡張（K 判断）**: 20 問はすべて references 向け。**使い始めて「推定で探した質問」（`kind_fallback: true`）と外れた質問を held-out として溜め**、dev / memory / stock / tax 向けの find・overview を各 5 問ほど足す。語彙（LEXICON）の手直しはその後
3. **R3 の判断（K）**: 温まった状態では count 0.5 秒だが、同期直後の最初の数回が 2 秒台（原因未特定。候補: 常駐プロセスの CPU 競合・autovacuum・ファイルキャッシュ）。基準を「温まった状態で」に直すか、原因を潰す単位を切るか
4. ④ の LLM 層の再採点（K 次第）／`valid_to` の自動推定（誤閉じ率を測ってから）／Windows タスクスケジューラでの常駐自動起動（要るなら）

## 再開の手順
```bash
# PC 再起動後は Docker Desktop が落ちている（docker ps が npipe エラー）→ 先に Docker Desktop を起動。起動直後に落ちる時は docker-desktop-recover スキル
docker compose up -d --wait && uv run dbr migrate          # 再実行は 0 件
bash scripts/gate.sh                                        # ruff → mypy → pytest（db 含む・80%）。K は pwsh -File scripts/gate.ps1
uv run dbr ask "未確認の記録は何件？"                        # 常駐が居なければ自動で起こす（約 25 秒）→ 以後 1 秒前後
uv run dbr sync                                             # 正本の変更を反映（常駐が居ればそちらで実行。無変更なら数秒）
```
`private.md` は絶対に取り込まない（走査除外＋トリガー）。常駐を止めるのは `uv run dbr serve --stop`。

## 守ること（決定台帳 `docs/decisions.md` の要点）
- 個人データは手元の PostgreSQL のみ・外部ホスティング禁止（D-5）。埋め込み・並べ直しもローカルモデルのみ（D-13）。HF Hub への問い合わせも既定で切る（D-18）
- 正本は OKF Markdown。DB は捨てて作り直せる派生（D-9）。マイグレーションの既存ファイルは編集しない（D-3）
- 既定の計算経路は `features/ask.answer()` 1 か所。CLI・常駐・MCP で分岐させない（測定経路＝既定経路）
- ゲートは `bash scripts/gate.sh`（pipefail 込み・4 段）を通してから commit。commit は `bash scripts/gate-commit.sh <msg-file>` だけ（直打ちはフックが deny）
- commit / push・受入検証（Codex。不可なら readonly-reviewer/Opus）・振り返りを毎単位で
