# 要求内容（T2: brief＋受入基準＋非スコープ）

> 厚さの判定: 永続スキーマ・課金・外部ユーザー・外部 API に**触れない**（新表なし・ローカルモデルのみ）→ T3 不要。仕様はこちらで決めたいので T2。design.md は作らず、設計の要点はここに書く。

## brief
前単位（`20260929-search-classify`）の確定値で残った3つの測定点を埋める:
①**並べ直し**（ローカル cross-encoder）で言い換え質問（Q06/Q08）が上がるか ②**RRF の重みと候補数**で hybrid が embed を安定して上回るか ③**HNSW の ef_search**（索引を強制して 40/100/250）の recall と速度。
成果物は `bench/results/` の JSON 3 種（find v5・sweep・hnsw）と `docs/bench-results.md` の追記。実装はすべて既存スライスの拡張（`search` に `hybrid_ctx_rerank` と重み付き RRF、`bench` に sweep/hnsw、CLI に `--label`）。

## 設計の要点
- **Reranker**: `shared/rerank/`（Protocol＋ローカル実装）。sentence-transformers の `CrossEncoder` で多言語の小型モデル `cross-encoder/mmarco-mMiniLMv2-L12-H384-v1` を既定（CPU で 150 件を数秒）。入力は `(質問, context + "\n" + body)`。決定性のため `torch.set_num_threads` は既定・バッチ固定
- **Mode 追加**: `hybrid_ctx_rerank` ＝ hybrid_ctx の融合上位 `rerank_top`（既定 150）を cross-encoder のスコアで並べ直し、`k` 件返す。同点は `chunk_id`
- **重み付き RRF**: `rrf(rankings, weights=[w_fts, w_embed], k=60)`。`score = Σ w_i / (k + rank_i)`。既定は等重み（後方互換）
- **候補数**: `search(..., candidates=N)` を引数化（既定 `max(100, k)`）
- **HNSW 強制**: `vector_search(..., force_index=True)` で `SET LOCAL enable_seqscan = off`。厳密結果（force_index=False・Seq Scan）を正として recall@k（上位 k の集合一致率）とレイテンシ（`time.perf_counter`・中央値）を測る
- **bench**:
  - `dbr bench --kind find [--label v5]` → `YYYYMMDD-find[-label].json`（ラベルで上書きを防ぐ）
  - `dbr bench --kind sweep` → hybrid_ctx について `w_fts ∈ {0, 0.25, 0.5, 1.0}` × `candidates ∈ {20, 100, 500}` の 12 セルで recall@5/recall@20/MRR
  - `dbr bench --kind hnsw` → embed（plain）について `ef_search ∈ {40, 100, 250}` × 10 問で、厳密結果との recall@20 一致率と中央値レイテンシ。`EXPLAIN` で Index Scan になっていることを 1 回記録
- **Sudachi の DeprecationWarning**（前単位の任意指摘）を解消

## 受入基準
- [ ] `hybrid_ctx_rerank` が 10 問で動き、2 回実行で JSON 一致（決定性）。Q06/Q08 の順位を v4 と並べて記録（上がる保証はしない＝測定）
- [ ] 重み付き RRF のユニットテスト（手計算一致・等重みで従来と同値）
- [ ] sweep JSON に 12 セル、各セルに recall@5 / recall@20 / MRR。最良セルを docs に明記
- [ ] hnsw JSON に 3 値の ef_search、各値に recall@20（厳密比）と中央値レイテンシ ms。強制時の `EXPLAIN` が Index Scan（統合テストで文字列 `Index Scan` を確認）
- [ ] `--label` 付きで別ファイルに保存され、既存 JSON が上書きされない（ユニットテスト）
- [ ] Sudachi の DeprecationWarning が `pytest -W error::DeprecationWarning src/dbr/shared/text` で出ない
- [ ] `docs/bench-results.md` に v5 節（rerank・sweep・hnsw）を追記。数値は JSON を読み直して転記
- [ ] ruff / mypy / pytest（unit・db・slow）PASS。実データ DB `dbr` は読み取りのみ（`ingest`/`embed`/`reindex` を再実行しない＝埋め込みを作り直さない）

## 非スコープ
- 外部 API（埋め込み・並べ直し）・LLM による文脈文生成・型判定の LLM 化
- asof（F5）・overview（F6）・質問の節一致採点
- 新しい埋め込みモデル・次元変更（表は vector(384) のまま）
- 20 問全体の bench（count/asof/overview は機能実装後）

## 識別子契約（`label`・`mode`）
- `label` はファイル名に入る CLI 入力: `[A-Za-z0-9_-]{1,32}` に限定（typer で検証。パス区切りや `..` を拒否）。保存先は `out_dir / f"{day}-{kind}-{label}.json"` の固定形
- `mode` は `Literal` に `hybrid_ctx_rerank` を追加。未知値は従来どおり `ValueError`
