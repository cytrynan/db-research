# 設計書

## アーキテクチャ概要

縦割り継続。追加スライス: `features/search`・`features/classify`・`features/bench`。共有: `shared/embed`（Embedder プロトコル＋ローカル実装）・`shared/text`（分かち書き）。

```
cli.py ─ embed ──▶ features/ingest/embed.py ──▶ shared/embed.local ──▶ chunk_embedding
       ─ ask ────▶ features/classify ──(find)──▶ features/search ──▶ chunk / chunk_embedding
       ─ bench ──▶ features/bench ──▶ questions.md → search(mode×N) → metrics → JSON/Markdown
shared/text.tokenize(text) -> list[str]   # SudachiPy。ingest と search の両方が使う（同じ関数）
```

## コンポーネント設計

### 1. `shared/text`（分かち書き）
- `tokenize(text: str) -> list[str]`: NFC 正規化 → Sudachi（`sudachidict_core`・split mode C）→ `normalized_form()` を小文字化。記号・空白のみは除外
- `lexemes(text) -> str`: `" ".join(tokenize(text))`。ingest はこれを `chunk.lexemes` に保存、検索は `to_tsquery('simple', or_tsquery(q))`（語を OR で結合。AND だと助詞で該当が消える）
- Sudachi の辞書は重い（初期化 1〜2 秒）ので tokenizer はモジュール内で1回だけ作る

### 2. `shared/embed`
```python
class Embedder(Protocol):
    name: str          # 'intfloat/multilingual-e5-small'
    dims: int          # 384
    def embed_passages(self, texts: list[str]) -> list[list[float]]: ...
    def embed_query(self, text: str) -> list[float]: ...
class LocalE5(Embedder): ...   # sentence-transformers。passage:/query: を前置、normalize_embeddings=True
```
- 外部 API 実装はこの単位では作らない（D-13）。`get_embedder(name)` は既定でローカルを返す

### 3. `features/ingest/embed.py`（`dbr embed`）
- 対象: `SELECT c.id, c.body, c.context FROM chunk c JOIN document d ... WHERE d.bundle=%s AND NOT EXISTS (SELECT 1 FROM chunk_embedding e WHERE e.chunk_id=c.id AND e.variant=%s AND e.model=%s)`
- 64 件ずつ `embed_passages` → COPY で `chunk_embedding` へ。戻り値 `EmbedReport(computed, skipped_existing)`
- `variant='ctx'` の入力は `f"{context}\n{body}"`

### 4. `features/search`
```python
Mode = Literal["embed", "fts", "hybrid", "hybrid_ctx"]
@dataclass(frozen=True) class Hit: chunk_id, bundle, rel_path, heading_path, body, score, source
def search(q, *, mode, k=20, dsn, embedder=None, bundles=None) -> list[Hit]
```
- `fts`: `SELECT ..., ts_rank_cd(tsv, query) AS score FROM chunk, to_tsquery('simple', %s /* 語を ' | ' で結合 */) query WHERE tsv @@ query ORDER BY score DESC LIMIT 100`
- `embed`: `SELECT ..., 1 - (e.embedding <=> %s::vector) AS score FROM chunk_embedding e JOIN chunk ... WHERE e.variant=%s AND e.model=%s ORDER BY e.embedding <=> %s::vector LIMIT 100`（`SET LOCAL hnsw.ef_search = %s`）
- `hybrid` / `hybrid_ctx`: fts と embed（variant plain / ctx）の順位を `rrf(rankings, k=60)` で統合し上位 k
- `rrf` は純粋関数（`fuse.py`）でユニットテスト
- **文書単位の順位**（bench 用）: 同一 `rel_path` の最良チャンクを採る `dedupe_by_document(hits)`

### 5. `features/classify`
- `RuleClassifier.classify(q) -> Classification(kind, reason, confidence)`
- ルール（先勝ち・順序が仕様）:
  1. count: `何件|いくつ|何個|合計|件数|何ファイル|内訳`
  2. asof: `いつ(決|分|変)|時点|当時|以前|より前|履歴|いつから|いつまで`
  3. overview: `全体として|全体的|傾向|手厚|薄い|どう反映|まとめると|俯瞰`
  4. find: `どこ(に|で)|どれ|書いた|記録|何を飲|方針|計画|ツール|好み` など、または「？」で終わる一般質問で上記に当たらない場合は **`unknown`** ではなく… → **仕様**: 1〜3 に当たらず、find 語彙にも当たらなければ `unknown`
- 20 問で ≥ 90% になるよう語彙を調整するが、**質問文の固有語（例: "ネスプレッソ"）をルールに入れない**（過学習禁止。ユニットテストで語彙表を固定）

### 6. `features/bench`
- `load_questions(path) -> list[Question]`: Markdown 表の行をパース（`| Qnn | 質問 | 型 | 期待 | 備考 |`）。`期待` から `` `references/xxx.md` `` / `` `knowledge/...` `` のパスを正規表現で抽出（複数可）
- `run_find(questions, modes, dsn, embedder, k=20)`: 各質問・各 mode で `search` → `dedupe_by_document` → 正解パスの最良順位
- `metrics`: `recall_at(k)`, `mrr` は純粋関数（ユニットテスト）
- 出力 JSON: `{"date","git_sha","model","sudachi_dict","ef_search","question_count","modes":{mode:{"recall@5","recall@20","mrr","per_question":[...]}}}`。Markdown 表は同じデータから生成
- 期待パスの `references/foo.md` は DB の `(bundle='references', rel_path='foo.md')` に対応させる（先頭セグメント＝bundle）

### 7. CLI
- `dbr embed <--bundle> [--variant plain] [--model]`／`dbr classify "<q>"`／`dbr ask "<q>" [--mode] [--kind] [--k]`／`dbr bench --kind find [--modes ...] [--out bench/results]`

## データフロー（bench find）
```
1. questions.md → Question[]（kind=find のみ）
2. mode ごとに: search(q) → dedupe_by_document → 正解の順位 r（無ければ None）
3. recall@5 = |r≤5| / N, recall@20, MRR = mean(1/r)
4. JSON を bench/results/YYYYMMDD-find.json に保存（同日再実行は上書き）→ Markdown 表を stdout
```

## エラーハンドリング戦略
- モデル未取得（オフライン）: `EmbedderUnavailable` → CLI exit 5、メッセージにモデル名
- 埋め込み未生成で `embed`/`hybrid` を要求: `NoEmbeddings(bundle, variant, model)` → exit 5（`dbr embed` を案内）
- Sudachi 辞書未導入: `TokenizerUnavailable` → exit 5
- 質問表の行が壊れている: その行を skip して件数を WARN

## テスト戦略
### ユニット
- `tokenize`: 日本語の分かち書き・正規化（「メガネ」「眼鏡」は別語のまま＝正規化しない事実を固定）・記号除去（`slow` でなく通常。辞書は同期時に入る）
- `rrf`: 既知順位 → 期待スコア（手計算）／片方にしか無い文書
- `RuleClassifier`: 20 問 fixture（`docs/questions.md` から生成せず**テスト内に写す**）で ≥ 18/20。加えて `unknown` になる例 2 件
- `metrics`: recall/MRR の手計算一致
- `load_questions`: 表のパースと期待パス抽出（複数パス・`tax/` 混在）
### 統合（`-m db`）
- 0006/0007 適用・再適用 0 件
- ingest 後 `lexemes` 非空・`tsv @@ to_tsquery`（OR） で fixture 該当
- `embed` 冪等（フェイク Embedder＝決定的ベクトルで DB 側を検証。モデルは `slow`）
- `search(mode=fts)` で updated.md が 1 位
### slow（実モデル）
- `LocalE5` が 384 次元・正規化済みを返す。`dbr bench --kind find` 2 回で JSON 一致

## 依存ライブラリ
```toml
"sentence-transformers>=3.0", "sudachipy>=0.6", "sudachidict-core>=20240000", "pgvector>=0.3", "numpy>=1.26"
```
（torch は sentence-transformers 経由。Windows は CPU 版が入る）

## ディレクトリ構造（追加）
```
migrations/0006_chunk_fts.sql  0007_chunk_embedding.sql
src/dbr/shared/text/{__init__,test_text}.py
src/dbr/shared/embed/{__init__,local,fake,test_embed}.py
src/dbr/features/ingest/embed.py（+ test）
src/dbr/features/search/{__init__,fts,vector,fuse,test_search}.py
src/dbr/features/classify/{__init__,rules,test_classify}.py
src/dbr/features/bench/{__init__,questions,metrics,report,test_bench}.py
tests/integration/{test_fts,test_embed_idempotent,test_search_modes}.py
bench/results/.gitkeep
```

## 実装の順序
1. 依存・0006・`shared/text`・ingest で lexemes → 統合テスト（fts 該当）
2. 0007・`shared/embed`（Local＋Fake）・`dbr embed` → 冪等テスト
3. `search`（fts / embed / fuse / hybrid）→ ユニット＋統合
4. `classify` → 20 問 ≥ 18
5. `bench` → questions パース・metrics・JSON/Markdown
6. `references` と `knowledge/dev` を取り込み → `embed` → `bench --kind find` を 2 回 → 表を docs へ転記（A4: JSON を読み直してから転記）

## セキュリティ考慮事項
- `references` の本文はローカルモデルにしか渡さない（外部実装は存在しない）。`bench` の JSON に**本文を出さない**（質問 ID・順位・パスだけ）
- 質問文・検索語は SQL パラメータ。`SET LOCAL hnsw.ef_search` は整数を検証してから埋める

## パフォーマンス考慮事項
- 埋め込みは 64 件バッチ。references＋dev（約 1,500 断片）で CPU 数分を見込む。`--variant` ごとに別実行
- Sudachi tokenizer はプロセスで 1 回生成

## 将来の拡張性
- `Mode` に `hybrid_ctx_rerank` を足すだけで並べ直しが入る（`rerank.py` を追加）
- `Embedder` の外部実装を追加するときは `bundle` による拒否を `get_embedder` 側でなく実装側に置く
