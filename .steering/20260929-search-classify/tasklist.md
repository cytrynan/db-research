# タスクリスト

tracking: #8

tracking: #{親issue番号}

## 🚨 タスク完全完了の原則

**このファイルの全タスクが完了するまで作業を継続すること**

### チェックボックスの記法
- `- [ ]` 未着手 / `- [~]` 着手中（いま作業中） / `- [x]` 完了
- `[x]`は「完了」だけに使う。作業中に`[x]`を付けない。

### GitHub issue との対応
- 各タスク行の末尾に子issue番号を書く。**この行が対応表**。状態を変えたら**その場で** issue も更新する

### 必須ルール
- **全てのタスクを`[x]`にすること**。スキップは技術的理由のみ・理由を行に明記

---

## フェーズ1: 全文検索の土台

- [~] 全文検索の土台: 依存・0006・shared/text（Sudachi）・ingest で lexemes・統合テスト (#9)
  - [ ] pyproject に sudachipy / sudachidict-core / sentence-transformers / pgvector / numpy を追加、`uv sync`
  - [ ] `migrations/0006_chunk_fts.sql`（lexemes・tsv 生成列・GIN）
  - [ ] `shared/text`（tokenize / lexemes・1 回初期化）＋ユニットテスト
  - [ ] ingest の COPY に lexemes を追加
  - [ ] `tests/integration/test_fts.py`（lexemes 非空・`@@` で fixture 該当）

## フェーズ2: 埋め込み

- [ ] 埋め込み: 0007・shared/embed（Local E5 / Fake）・`dbr embed`・冪等テスト (#10)
  - [ ] `migrations/0007_chunk_embedding.sql`（vector(384)・主キー・HNSW cosine）
  - [ ] `shared/embed`（Protocol・LocalE5・FakeEmbedder）＋ `slow` テスト（384 次元・正規化）
  - [ ] `features/ingest/embed.py`（未生成だけ計算・64 件バッチ・COPY・EmbedReport）と CLI `embed`
  - [ ] `tests/integration/test_embed_idempotent.py`（Fake で 2 回→行数不変）

## フェーズ3: 検索（F3）

- [ ] 検索: fts / embed / RRF / hybrid / hybrid_ctx・dedupe_by_document・ユニット＋統合 (#11)
  - [ ] `search/fts.py`・`vector.py`（ef_search は整数検証）・`fuse.py`（rrf 純粋関数）・`__init__.search`
  - [ ] ユニット: rrf 手計算一致・片側のみの文書
  - [ ] `tests/integration/test_search_modes.py`（fts で updated.md 1 位・hybrid が両系を含む）

## フェーズ4: 型判定（F2）

- [ ] 型判定: RuleClassifier・20 問 fixture ≥ 18/20・unknown 2 例・CLI `classify` (#12)

## フェーズ5: 測定（F7 find）と `ask`

- [ ] 測定と ask: questions.md パース・metrics・JSON/Markdown・CLI `bench` / `ask` (#13)
  - [ ] `bench/questions.py`（表パース・期待パス抽出）＋ユニット
  - [ ] `bench/metrics.py`（recall@k・MRR）＋ユニット（手計算）
  - [ ] `bench/report.py`（JSON: git_sha/model/sudachi_dict/ef_search・Markdown 表）
  - [ ] CLI `bench --kind find` / `ask`（classify→search / count／asof・overview は未実装表示）

## フェーズ6: 実データ測定と品質ゲート

- [ ] 実データ測定: references＋knowledge/dev を取り込み→embed（plain/ctx）→bench 2 回→docs へ転記・品質ゲート3点 (#14)
  - [ ] `dbr ingest ~/.claude/references --bundle references`（ローカル DB のみ・D-5）と `knowledge/dev`
  - [ ] `dbr embed` plain / ctx（所要時間を記録）
  - [ ] `dbr bench --kind find` を 2 回実行し JSON 一致を確認
  - [ ] 4 方式の表を `docs/bench-results.md` に転記（JSON を読み直してから）＋ `docs/log.md`
  - [ ] ruff / mypy / pytest（unit・db・slow）

## フェーズ7: 振り返り

- [ ] 振り返り（このファイル下部）・README 更新・別コンテキストの受入検証 (#15)

---

## 実装後の振り返り

### 実装完了日
{YYYY-MM-DD}

### 計画と実績の差分
**計画と異なった点**:
- 

**新たに必要になったタスク**:
- 

### 止まった点・失敗した点（**必須。1件以上**）
- **何が起きたか**: 
- **原因**: 
- **次にどうするか**: 

### 学んだこと
**技術的な学び**:
- 具体: 
  - 抽象: 

**プロセス上の改善点**:
- 

**リポジトリをまたいで使える知見**:
- 

### 次回への改善提案
- 
