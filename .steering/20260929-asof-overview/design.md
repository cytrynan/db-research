# 設計書

## アーキテクチャ概要

縦割り継続。新スライス `features/asof`・`features/overview`、取り込み側に `features/ingest/facts.py`・`summarize.py`。bench は `features/bench/{count,asof,overview}.py`。

```
cli.py ─ facts ────▶ ingest/facts.py（抽出）──▶ fact
       ─ summarize ▶ ingest/summarize.py ──▶ summary
       ─ ask ──────▶ classify ─┬─ find → search
                               ├─ count → count.ask_view（_guess_view）
                               ├─ asof → asof.as_of / history
                               └─ overview → overview.answer（summary＋embed_ctx）
       ─ bench --kind count|asof|overview
```

## コンポーネント設計

### 1. `ingest/facts.py`
```python
DATE_VERB = re.compile(r"(20\d{2}-\d{2}-\d{2})[ 　]*(K申告|K承認|K決定|K指示|決定|承認|分離|申告|記録|算出|停止|廃止|変更|開始|導入|確定|更新)")
@dataclass(frozen=True) class FactRow: document_id, chunk_id|None, subject, value, valid_from, valid_to, recorded_at, valid_source
def extract_from_chunk(doc, chunk) -> list[FactRow]      # dated_text（heading_path＋body の各行）
def extract_explicit(doc) -> FactRow | None              # fm.valid
def run_facts(bundle, dsn) -> FactsReport(explicit, dated_text, inferred)
```
- 行の走査: `heading_path` の末尾見出しと body を `\n` で分けた各行。日付が見出し側にある場合（例「収益目標（2026-07-26 K決定）」）は見出し行を value にする
- subject＝`f"{last_heading} / {line_head40}"`（日付・動詞を除去・NFKC）。lexemes＝`lexemes(subject + "\n" + value)`
- valid_from＝`datetime(y,m,d,tzinfo=JST)`。不正な日付（2026-13-40）は無視
- 削除→COPY で挿入（bundle 単位・1 トランザクション）

### 2. `features/asof`
```python
def as_of(question, at: datetime, *, dsn, bundles=None, k=5) -> list[FactHit]
def history(question, *, dsn, bundles=None, k=20) -> list[FactHit]
def parse_at(question) -> datetime | None   # YYYY-MM-DD → その日 23:59:59 JST、YYYY-MM → 月末 23:59:59
```
SQL（as_of）:
```sql
SELECT f.*, d.bundle, d.rel_path, ts_rank_cd(f.tsv, q) AS score
FROM fact f JOIN document d ON d.id = f.document_id, to_tsquery('simple', %(q)s) q
WHERE f.tsv @@ q AND f.valid_from <= %(at)s AND (f.valid_to IS NULL OR %(at)s < f.valid_to)
ORDER BY score DESC, f.valid_from DESC, f.id LIMIT %(k)s
```
- `or_tsquery` は `search/fts.py` のものを再利用（同じ tokenize）
- 該当 0 件は空リスト → CLI は「該当する記録なし」exit 0

### 3. `ingest/summarize.py`（抽出型）
- section: `first_paragraph(chunk.body, 200)`（コードフェンスは飛ばす）
- document: `description` ＋ H1/H2 一覧（`chunk.heading_path` の先頭 2 階層を重複除去）＋ `type/status/verified_at/stale_after`
- bundle: `v_by_bundle`/`v_by_type`/`v_unverified`/`v_stale` の値＋各文書の `rel_path: description`
- `source_hash`＝元テキストの sha256。再構築は bundle 単位で全削除→挿入。`tokens` は近似
- `target_key`: bundle＝`bundle 名`、document＝`str(document.id)`、section＝`str(chunk.id)`

### 4. `features/overview`
```python
def answer(question, *, dsn, embedder, bundles=None, top_docs=5) -> OverviewAnswer(bundle_summaries, doc_summaries, evidence_ids)
```
- bundles 未指定→質問中の bundle 名（references/dev/memory/…）を拾う、無ければ全 bundle
- 上位文書＝`search(question, mode="embed_ctx", k=50)` → `dedupe_by_document` → 先頭 5
- 回答テキスト＝bundle 要約 → 各文書の document 要約（description＋見出し）。**本文の抜粋は出さない**（要約は description と見出しで構成）

### 5. bench 追加
- `bench/count.py`: Q11〜14 → `_guess_view`（cli から `features/count` へ移す）→ 3 回実行 → `stable`
- `bench/asof.py`: 期待欄から `references/x.md` と `20xx-xx-xx` を抽出。`parse_at(question)` があれば `as_of` 無ければ `history`。上位 3 件に「ファイル一致∧日付一致」があれば正解。Q16 のように期待が `なし` なら「該当 0 件または期待日付以前の事実なし」を正解
- `bench/overview.py`: Q19〜20 の `answer` を `docs/overview-answers.md` へ（`| # | 質問 | 回答 | K採点(1-5) |`）

### 6. CLI
- `dbr facts --bundle <b>`／`dbr summarize --bundle <b>`／`dbr ask`（asof/overview 分岐・`--at 2026-08-15` で時点指定可）／`dbr bench --kind count|asof|overview`

## データフロー（ask asof）
```
1. classify → asof（または --kind asof）
2. parse_at(question) → at があれば as_of、無ければ history
3. or_tsquery(question) で fact.tsv を検索 → 時点条件 → 上位 k
4. 出力: valid_from（日付）・bundle/rel_path・value の抜粋（120 字）・valid_source・valid_to
```

## エラーハンドリング戦略
- `--at` が解釈不能 → exit 2。事実 0 件 → 「該当する記録なし」exit 0
- `summarize` で embed_ctx の埋め込みが無い bundle → overview は bundle 要約だけ返し WARN
- 抽出時の不正日付は無視（件数を WARN に）

## テスト戦略
### ユニット
- `DATE_VERB` の検出（見出し側・本文側・全角スペース・不正日付・動詞なし）
- `parse_at`（日付／月／なし／不正）
- `first_paragraph`（フェンス飛ばし・200 字）
### 統合（`-m db`）
- fixture `tests/fixtures/dated/`（valid キー 1・日付行 3・日付なし 1）で facts の件数・冪等
- `as_of` の時点フィルタ・`history` の昇順
- `summarize` の 3 段・冪等・`source_hash`
- CLI `ask` 4 型 exit 0、`bench --kind count|asof|overview`（fake 埋め込み）

## 依存ライブラリ
追加なし。

## ディレクトリ構造（追加）
```
migrations/0008_fact.sql  0009_summary.sql
src/dbr/features/ingest/{facts,summarize}.py（+ test）
src/dbr/features/asof/{__init__,test_asof}.py
src/dbr/features/overview/{__init__,test_overview}.py
src/dbr/features/bench/{count,asof,overview}.py
tests/fixtures/dated/*.md
tests/integration/{test_facts,test_asof,test_summarize,test_bench_types}.py
docs/overview-answers.md
```

## 実装の順序
1. 0008・facts.py・`dbr facts` → 統合テスト
2. asof スライス・`ask` 分岐・`--at`
3. 0009・summarize.py・overview スライス・`ask` 分岐
4. bench count/asof/overview・questions.md の期待欄
5. memory 取り込み・埋め込み → 実データで facts/summarize/bench → docs 転記
6. 受入検証・振り返り

## セキュリティ考慮事項
- fact.value・summary.text は個人データを含むが、DB はローカル限定（D-5）。bench の JSON には value を**出さない**（日付・パス・正否だけ）。overview-answers.md は description と見出しだけで構成し本文抜粋を含めない

## パフォーマンス考慮事項
- 抽出・要約は取り込み済み断片の走査のみ（1,077＋memory 分）。数秒〜十数秒

## 将来の拡張性
- `valid_source` に `llm` を足せば LLM 抽出を並べて比較できる。`summary` も `method` 列を足すだけで LLM 要約と比較可能（次単位）
