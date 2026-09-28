# 要求内容

> 厚さ: **T3**（永続スキーマ: `chunk.tsv`・`chunk_embedding` を追加）。フル3点セット＋識別子契約。

## 概要

① 探し物の検索（F3）と質問の型判定（F2）、測定ハーネス（F7 の find 部分）を作り、**質問セット 20 問のうち find 10 問で方式別の recall@5 / recall@20 / MRR を出す**。埋め込みはローカルモデルのみ（D-13）。

## 背景

PRD の最優先 KPI は検索品質（D-11）。方式 4 段（埋め込みのみ／全文のみ／ハイブリッド／＋文脈付与）を同じ 10 問で比べて表にするのがこの単位のゴール。並べ直し（リランキング）は次単位。

## 実装対象の機能

### 1. スキーマ追加（新番号のマイグレーションのみ）
- `0006_chunk_fts.sql`: `chunk.lexemes text`（分かち書き済み・空白区切り）＋ 生成列 `tsv tsvector GENERATED ALWAYS AS (to_tsvector('simple', lexemes)) STORED` ＋ GIN
- `0007_chunk_embedding.sql`: `chunk_embedding(chunk_id fk cascade, variant text, model text, embedding vector(384), primary key(chunk_id, variant, model))` ＋ HNSW（cosine, m=16, ef_construction=64）

### 2. 取り込みの拡張（F1）
- 分かち書き（SudachiPy・split mode C・正規化形）で `lexemes` を埋める
- `dbr embed --bundle <b> --variant plain|ctx [--model ...]`: 埋め込み未生成の断片だけ計算して `chunk_embedding` へ。`plain` は body、`ctx` は context + "\n" + body
- 既定モデル `intfloat/multilingual-e5-small`（384 次元・CPU）。e5 の作法どおり文書は `passage: `、質問は `query: ` を前置

### 3. 検索（F3）
- `Mode = embed | fts | hybrid | hybrid_ctx`
- fts: 質問も同じ分かち書きで `plainto_tsquery('simple', …)` → `ts_rank_cd`
- embed: `embedding <=> :q` で cosine 距離昇順
- hybrid: 両方の上位 100 件を RRF（k=60）で統合
- 戻り値 `Hit(rel_path, bundle, heading_path, body, score, source)`

### 4. 型判定（F2）
- `RuleClassifier`: 語彙ルールで `find | count | asof | overview | unknown` ＋理由。判定不能は `unknown`（find に倒さない）
- `dbr classify "<質問>"`

### 5. 測定（F7・find のみ）
- `docs/questions.md` の表を読み、`kind=find` の行を対象に、方式ごとに recall@5 / recall@20 / MRR を算出
- 正解は `期待` 列の `references/xxx.md` 形式のパス（複数可）。**ファイル一致**で正解とする（節一致は次単位）
- 出力: Markdown 表（stdout）＋ JSON（`bench/results/YYYYMMDD-find.json`。`model` / `sudachi_dict` / `ef_search` / `git_sha` / `question_count` を含む）
- `dbr bench --kind find`

### 6. CLI `ask`
- `dbr ask "<質問>" [--mode hybrid_ctx] [--kind find]`: classify → find なら search、count なら count、asof/overview は「未実装」と明示して exit 0

## 受け入れ条件

### スキーマ・取り込み
- [ ] `dbr migrate` で 0006・0007 が適用され、再実行 0 件。既存 0001〜0005 は無変更（`git diff --stat` で確認）
- [ ] `ingest` 後に fixture 全断片の `lexemes` が非空、`tsv` が生成されている
- [ ] `dbr embed --bundle memory --variant plain` を 2 回実行しても `chunk_embedding` の行数が増えない（2 回目は計算 0 件）

### 検索
- [ ] fixture（kuroko 4 ファイル）に対し、日本語の語句質問で `fts` が該当ファイルを 1 位に返す（例: 「規約外キー」→ updated.md）
- [ ] `hybrid` の RRF スコアが手計算と一致（ユニットテスト: 既知の順位 → 期待スコア）
- [ ] `references` と `knowledge/dev` を取り込み、**find 10 問で 4 方式の表が出る**（数値の目標は置かない＝初回測定）

### 型判定
- [ ] 20 問の正解ラベルとの一致 **≥ 90%**（18/20 以上）。`unknown` は不一致に数える

### 測定
- [ ] `dbr bench --kind find` を 2 回実行して JSON の数値が一致（再現性）
- [ ] JSON に `git_sha` / `model` / `sudachi_dict` が入っている

## 成功指標
- find 10 問の 4 方式表が `bench/results/` と `docs/`（転記）に存在する
- 統合テスト（`-m db`）・`slow`（モデル実行）が PASS

## スコープ外
- 並べ直し（リランキング）・LLM による文脈文生成・外部埋め込み API（次単位以降）
- asof（F5）・overview（F6）の実装（`ask` は未実装と表示するだけ）
- 質問の節一致による採点（ファイル一致のみ）

## 参照ドキュメント
- `docs/product-requirements.md` F2/F3/F7・KPI「検索品質」
- `docs/functional-design.md` Search / Classifier / Bench・RRF
- `docs/architecture.md` 方式の選定（SudachiPy→tsvector・e5・HNSW）
- `docs/questions.md`

## 識別子契約（`mode`・`variant`・`model`・`kind`）
- **特殊キー**: `mode` / `variant` / `kind` は CLI 入力。固定の語彙（`Literal`）と typer の choices で検証し、dict のキーに使わない。`model` は文字列だが `chunk_embedding` の主キーの一部＝**保存時も照合時も同じ文字列**（trim のみ）
- **正規化**: 質問文は NFC 正規化 → 分かち書き。`rel_path` の照合は ingest と同じ `normalize_rel_path`
- **衝突**: `(chunk_id, variant, model)` 重複は skip（再計算しない）。モデルを変えたら別行＝比較できる
- **不在**: 埋め込み未生成の断片は `embed` 検索の対象外（件数を `bench` の JSON に出す）
