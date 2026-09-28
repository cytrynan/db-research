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

- [x] 全文検索の土台: 依存・0006・shared/text（Sudachi）・ingest で lexemes・統合テスト (#9)
  - [x] pyproject に sudachipy / sudachidict-core / sentence-transformers / pgvector / numpy を追加、`uv sync`
  - [x] `migrations/0006_chunk_fts.sql`（lexemes・tsv 生成列・GIN）
  - [x] `shared/text`（tokenize / lexemes・1 回初期化）＋ユニットテスト
  - [x] ingest の COPY に lexemes を追加
  - [x] `tests/integration/test_fts.py`（lexemes 非空・`@@` で fixture 該当）

## フェーズ2: 埋め込み

- [x] 埋め込み: 0007・shared/embed（Local E5 / Fake）・`dbr embed`・冪等テスト (#10)
  - [x] `migrations/0007_chunk_embedding.sql`（vector(384)・主キー・HNSW cosine）
  - [x] `shared/embed`（Protocol・LocalE5・FakeEmbedder）＋ `slow` テスト（384 次元・正規化）
  - [x] `features/ingest/embed.py`（未生成だけ計算・64 件バッチ・COPY・EmbedReport）と CLI `embed`
  - [x] `tests/integration/test_embed_idempotent.py`（Fake で 2 回→行数不変）

## フェーズ3: 検索（F3）

- [x] 検索: fts / embed / RRF / hybrid / hybrid_ctx・dedupe_by_document・ユニット＋統合 (#11)
  - [x] `search/fts.py`・`vector.py`（ef_search は整数検証）・`fuse.py`（rrf 純粋関数）・`__init__.search`
  - [x] ユニット: rrf 手計算一致・片側のみの文書
  - [x] `tests/integration/test_search_modes.py`（fts で updated.md 1 位・hybrid が両系を含む）

## フェーズ4: 型判定（F2）

- [x] 型判定: RuleClassifier・20 問 fixture ≥ 18/20・unknown 2 例・CLI `classify` (#12)

## フェーズ5: 測定（F7 find）と `ask`

- [x] 測定と ask: questions.md パース・metrics・JSON/Markdown・CLI `bench` / `ask` (#13)
  - [x] `bench/questions.py`（表パース・期待パス抽出）＋ユニット
  - [x] `bench/metrics.py`（recall@k・MRR）＋ユニット（手計算）
  - [x] `bench/report.py`（JSON: git_sha/model/sudachi_dict/ef_search・Markdown 表）
  - [x] CLI `bench --kind find` / `ask`（classify→search / count／asof・overview は未実装表示）

## フェーズ6: 実データ測定と品質ゲート

- [x] 実データ測定: references＋knowledge/dev を取り込み→embed（plain/ctx）→bench 2 回→docs へ転記・品質ゲート3点 (#14)
  - [x] `dbr ingest ~/.claude/references --bundle references`（ローカル DB のみ・D-5）と `knowledge/dev`
  - [x] `dbr embed` plain / ctx（所要時間を記録）
  - [x] `dbr bench --kind find` を 2 回実行し JSON 一致を確認
  - [x] 4 方式の表を `docs/bench-results.md` に転記（JSON を読み直してから）＋ `docs/log.md`
  - [x] ruff / mypy / pytest（unit・db・slow）

## フェーズ7: 振り返り

- [~] 振り返り（このファイル下部）・README 更新・別コンテキストの受入検証 (#15)

---

## 実装後の振り返り

### 実装完了日
2026-09-29

### 計画と実績の差分
**計画と異なった点**:
- 全文検索を `plainto_tsquery`（AND）で書いたら日本語の助詞で該当が消えた（fts recall@5=0.20）。**OR クエリ＋機能語除去**に変更し 0.40。設計時の「plainto_tsquery」は誤り
- 分かち書きの正規化を NFC→**NFKC** に変更（全角英数を畳むため）。Sudachi の `normalized_form` が「メガネ」→「眼鏡」に寄せる事実は想定と逆だったのでテストを事実に合わせた
- `dbr reindex`（lexemes だけ再計算）を追加。分かち書き規則を変えるたびに埋め込み（5 分）を作り直さないため
- ベクトル検索の `ORDER BY` に `c.id` を追加（同点の順序固定）。これが無いと bench が再現しなかった
- 質問表の Q10 で、正解に含めない `tax/...` をバッククォートから外した（パーサは `` ` `` 内だけを正解と読む）

**新たに必要になったタスク**:
- CLI の標準出力を UTF-8 に固定（Windows cp932 で「—」を含む JSON 出力が落ちた）
- `sentence-transformers` 6.x の `get_sentence_embedding_dimension` 改名への追従
- mypy の外部ライブラリ型スタブ無視設定（sudachipy / sentence_transformers / pgvector）

### 止まった点・失敗した点（**必須。1件以上**）
- **何が起きたか**: 初回 bench で fts が 10 問中 8 問ヒット 0。「全文検索は弱い」と結論しかけた
- **原因**: 方式の欠陥（AND＋機能語）。数値を見て「弱い」と読む前に、**未ヒットの質問で実際のクエリを1つ流して該当 0 件の理由を見る**べきだった
- **次にどうするか**: 新しい検索方式は「代表質問 1 つで生の SQL を流して該当件数を見る」煙テストを bench の前に置く（bench は集計なので原因が見えない）
- **何が起きたか（2件目）**: embed の順位が v1→v2 で変わり、再現性 KPI が一度落ちた
- **原因**: 同一本文の断片が同一ベクトルで同点になり、順序がヒープ順依存だった
- **次にどうするか**: 順位を返すクエリは必ず決定的なタイブレーク列を持つ（fts 側には最初から `c.id` があった＝片側だけ揃っていなかった）

### 学んだこと
**技術的な学び**:
- 具体: `EXPLAIN` で `chunk_embedding` の検索が Seq Scan（約 2,000 行）
  - 抽象: **小規模では HNSW は使われない**。`ef_search` を「測った」と言う前に EXPLAIN。索引の実験は `enable_seqscan=off` で強制する
- 具体: hybrid（RRF 等重み）が embed 単体より recall@5 で劣った（0.70 vs 0.80）
  - 抽象: 融合は「弱い側の雑音」を持ち込む。各系を単体で健全にした上で、重み／候補数を振らないと融合の価値は測れない
- 具体: `uv run python` に `/c/Users/...` を渡して FileNotFoundError
  - 抽象: Git Bash のパス変換はコマンド引数にだけ効く。Python 文字列には `C:/...` を書く

**プロセス上の改善点**:
- 統合テスト（`clean_db` が TRUNCATE）と実データの DB を**同じ DB で兼ねている**ため、取り込み中は統合テストを走らせられなかった。次単位で `DBR_TEST_DSN`（別 DB 名）に分ける
- bench の JSON は同日再実行で上書きされる。欠陥版（v1）は手でリネームして残した。**版の違いを残す運用（`--label`）**を足す

**リポジトリをまたいで使える知見**:
- `dev/postgres-fts-pgvector.md` に 5 点（AND 問題・同点揺れ・HNSW 未使用・RRF 逆説・周辺の罠）を記録済み

### 受入検証（別コンテキスト）
- （この後に実施・結果を追記）

### 次回への改善提案
- 並べ直し（ローカル cross-encoder）と RRF の重み／fts 候補数の掃引を次単位に。Q06/Q08（言い換え）が測定点
- `enable_seqscan=off` で ef_search 40/100/250 を測る（HNSW の実験を成立させる）
- テスト用 DB を分離（`dbr_test`）し、実データを消さずに `-m db` を回せるようにする
