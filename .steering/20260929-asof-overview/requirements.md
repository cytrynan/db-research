# 要求内容

> 厚さ: **T3**（永続スキーマ `fact`・`summary` を追加）。フル3点セット＋識別子契約。

## 概要

③時点（F5）と④全体（F6）を実装し、`dbr ask` が 4 型すべてに答える。合わせて ② count・③ asof の bench を追加し、20 問のうち残り 10 問を測る。要約は **LLM を使わない抽出型**（決定的・ローカル）で始める。

## 背景

検索（① find）は 3 単位で一区切り。研究の主題「型で振り分ける」を閉じるには、RAG が構造的に答えられない ②③④ の受け皿が動いている必要がある。③は OKF に有効時間が無いことが分かっており（D-10）、独自キー `valid` と本文中の日付表現から事実を機械抽出する。

## 実装対象の機能

### 1. スキーマ（新番号のみ）
- `0008_fact.sql`: `fact(id, document_id fk cascade, chunk_id fk cascade null, subject text, value text, valid_from timestamptz, valid_to timestamptz null, recorded_at timestamptz, valid_source text check in ('explicit','dated_text','inferred'), lexemes text, tsv generated, unique(document_id, coalesce(chunk_id,0), subject, valid_from))`＋GIN(tsv)＋(valid_from) 索引
- `0009_summary.sql`: `summary(id, level text check in ('bundle','document','section'), target_key text, text text, source_hash text, tokens int, unique(level, target_key))`

### 2. 事実の抽出（F5・`dbr facts --bundle`）
- **explicit**: フロントマター `valid: { from, to }` → 文書全体の事実（subject＝description か H1）
- **dated_text**: `heading_path`＋本文の各行から `YYYY-MM-DD` ＋ 動詞（K申告／K承認／K決定／K指示／決定／承認／分離／申告／記録／算出／停止／廃止／変更／開始／導入／確定／更新）を検出 → subject＝直近見出し＋行頭 40 字（日付を除く）、value＝その行（300 字まで）、valid_from＝日付（JST 0 時）、recorded_at＝文書の `generated_at`（無ければ valid_from）、valid_to＝NULL（閉じる根拠が無いため）
- **inferred**: 上のどれも無い文書は `generated_at` を valid_from とする文書全体の事実 1 件（`valid_source='inferred'`）
- bundle 単位で **全削除→再抽出**（決定的＝同じ入力なら同じ行）。個人データの本文を DB 外へ出さない

### 3. 時点の問い合わせ（F5）
- `as_of(question, at)`: fact.tsv を OR クエリで検索 → `valid_from <= at AND (valid_to IS NULL OR at < valid_to)` → `ts_rank_cd` 降順・同点 `valid_from` 降順・`id`
- `history(question)`: 時点条件なし・`valid_from` 昇順
- `ask` の asof 分岐: 質問に `YYYY-MM(-DD)?` があれば `as_of`（月だけなら月末）、無ければ `history`。回答は「日付／ファイル／行の抜粋／根拠の種別（explicit/dated_text/inferred）」

### 4. 全体（F6・`dbr summarize --bundle`・抽出型）
- section: 断片の最初の段落（200 字まで）
- document: `description`＋H1/H2 見出し一覧＋メタ（type/status/verified/stale）
- bundle: 文書数・type 別・未確認数・期限切れ数＋各文書の 1 行（description）
- `ask` の overview 分岐: 対象 bundle（質問に bundle 名があればそれ、無ければ全部）の bundle 要約＋質問に近い上位 5 文書（embed_ctx）の document 要約。根拠の summary id を返す
- 全削除→再構築で決定的。`source_hash` で陳腐化を検知（ハッシュ不一致の要約は WARN）

### 5. bench
- `--kind count`: Q11〜Q14 を `_guess_view` で解き、3 回実行して同値か（`stable: true`）と値を JSON に
- `--kind asof`: Q15〜Q18。正解＝`questions.md` の期待欄のバッククォート内（ファイルパスと `YYYY-MM-DD`）。**上位 3 件に「ファイル一致かつ日付一致」の事実があれば正解**
- `--kind overview`: Q19〜Q20 の回答本文を `docs/overview-answers.md` に書き出す（K が 5 段階で採点する欄つき）。自動採点はしない
- `questions.md` の期待欄に asof の日付をバッククォートで追記する（Q15: 2026-08-11、Q16: 2026-08-11、Q17: 2026-07-26、Q18: 2026-08-24）

### 6. 取り込みの拡張
- `memory` バンドル（`~/.claude/projects/C--Users-meer0/memory`）を取り込み・埋め込み（Q18 の正解が memory にある）

## 受け入れ条件
- [ ] `dbr migrate` で 0008・0009 が適用、再実行 0 件。0001〜0007 は無変更
- [ ] fixture（日付つきの行 3 件・`valid` キー 1 件・日付なし 1 件）で `facts` が explicit 1・dated_text 3・inferred 1 を抽出し、2 回目も行数が増えない
- [ ] `as_of(q, 2026-08-15)` が 2026-08-11 の事実を返し、2026-09-01 の事実を返さない（fixture）。`history` が昇順
- [ ] `summarize` 後に bundle/document/section の 3 段が存在し、2 回目で行数不変
- [ ] `dbr ask "<asof 質問>"` が日付・ファイル・抜粋・根拠種別を返す。`dbr ask "<overview 質問>"` が bundle 要約＋上位文書を返す（4 型すべて exit 0）
- [ ] bench: count 4 問が `stable: true`、asof 4 問の正答数を JSON に、overview 2 問の回答が `docs/overview-answers.md` にある
- [ ] 実データ（references＋dev＋memory）で `facts`／`summarize`／`bench --kind count|asof|overview` が完走し、結果を `docs/bench-results.md` に転記
- [ ] ruff / mypy / pytest（unit・db）PASS、カバレッジ 80% 以上

## 成功指標
- asof 4 問中 **3 問以上**正解（Q16「以前は何と書いてあった」は履歴が無いので「その時点の記録なし」を正解扱いにする＝期待欄に明記）
- count 4 問 `stable: true`

## スコープ外
- LLM による要約生成・事実抽出（次単位以降。まず抽出型で天井を測る）
- `valid_to` の自動推定（同一 subject の後続事実で閉じる）— 誤閉じの害が大きいので今回は NULL
- Attested Computation（F8）・外部 API

## 識別子契約（`subject`・`level`/`target_key`・`bundle`）
- **特殊キー**: `subject` は本文由来の文字列。dict のキーに使わず、SQL パラメータでのみ扱う。`level` は固定語彙 3 値（CHECK 制約）。`target_key` は `bundle` 名／`document.id`／`chunk.id` の文字列で、生成側が組み立てる（ユーザー入力を含めない）
- **正規化**: `subject` は NFKC・前後空白除去・日付部分を除去してから保存。照合は tsv（lexemes）で行い、文字列一致に依存しない
- **衝突**: `(document_id, chunk_id, subject, valid_from)` の重複は抽出時に dict で畳む（同じ行に同じ日付が 2 回出ても 1 件）。`summary` は `(level, target_key)` 一意・再構築は全削除→挿入
- **不在**: 事実が 1 件も無い問い合わせは「該当する記録なし」を返す（find に倒さない）。`at` が解釈できない日付は exit 2
