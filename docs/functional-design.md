---
type: Functional Design
description: db-research の機能設計。OKF 取り込み・質問の型判定・4型それぞれの回答経路（ハイブリッド検索／SQL ビュー／バイテンポラル／要約階層）・測定ハーネスのデータモデルとコンポーネント
generated: { by: kuroko/claude-fable-5-1, at: 2026-09-29T08:00:00+09:00 }
status: draft
---

# 機能設計書 (Functional Design Document)

> 入力: [product-requirements.md](product-requirements.md)（K承認済み・D-1〜D-12）。コード例は Python 3.12 と SQL で書く。

## システム構成図

```mermaid
graph TB
    K[K / くろこ]
    CLI[CLI: dbr ask ／ MCP: dbr mcp]
    SRV[常駐 dbr serve\n127.0.0.1:47821・モデル保持・30 分ごとに sync]
    CLS[型判定 classify\n不明は find へ倒す（D-17）]
    SRCH[① 探し物 search]
    CNT[② 数える count]
    TMP[③ 時点 asof]
    SUM[④ 全体 overview]
    ING[取り込み ingest]
    EMB[埋め込み embed]
    PG[(PostgreSQL + pgvector\nlocalhost のみ)]
    MD[/正本: OKF Markdown\nreferences / knowledge / memory/]
    BENCH[測定 bench]

    K --> CLI
    CLI -->|HTTP・居なければ起こす| SRV
    SRV --> CLS
    SRV -->|sync| ING
    CLI -.->|--no-daemon| CLS
    CLS -->|①| SRCH
    CLS -->|②| CNT
    CLS -->|③| TMP
    CLS -->|④| SUM
    SRCH --> PG
    CNT --> PG
    TMP --> PG
    SUM --> PG
    MD -->|読み取り専用| ING
    ING --> EMB
    ING --> PG
    BENCH --> CLS
    BENCH --> SRCH
    BENCH --> CNT
    BENCH --> TMP
```

- 正本（Markdown）への矢印は**一方向**。本基盤は Markdown を書き換えない。
- `PG` はループバック接続のみ。`ingest` は接続先がループバック以外なら起動時に拒否する。

## 技術スタック

| 分類 | 技術 | 選定理由 |
|------|------|----------|
| 言語 | Python 3.12 / uv / ruff / mypy strict / pytest | テンプレ標準（D-2）。研究用スクリプトと CLI を同じ言語で |
| DB | PostgreSQL 16 系（Docker）＋ pgvector | 4型すべてを1つの DB で受ける（D-2/D-7）。Supabase 対応版と同じメジャーを選ぶ（機能差が無い範囲で D-4） |
| 全文検索 | PostgreSQL 標準 `tsvector` ＋ 日本語トークナイズ | 方式は architecture で確定（未決）。候補: `pg_bigm`（Supabase 対応）／アプリ側で分かち書きして `simple` 辞書 |
| 埋め込み | 抽象 `Embedder` インターフェース。実装は外部 API とローカルモデルの2種 | `references/` 本文を外部へ送るかは未決。差し替え可能にして研究を止めない |
| DB アクセス | psycopg 3 ＋ 素の SQL（ORM 不使用） | SQL そのものが研究対象。ビュー・範囲型・インデックスを隠さない |
| マイグレーション | SQL ファイル＋番号順適用（自作の薄い runner） | D-3。Supabase にもそのまま流せる形 |
| CLI | `typer` | サブコマンドと型付き引数が最小コストで書ける |

## データモデル定義

### エンティティ: Document（1 Markdown ファイル）

```python
@dataclass(frozen=True)
class Document:
    id: int
    bundle: str            # references / dev / stock / tax / scout / memory / experiments
    rel_path: str          # バンドル起点の相対パス（一意キー: bundle + rel_path）
    format: str            # 'okf' | 'kuroko'  ← D-12 の比較用。どの形式で解釈したか
    fm: dict               # フロントマター全体（jsonb）
    type: str | None       # fm.type（memory は fm.metadata.type）
    status: str            # draft | stable | deprecated（省略時 stable）
    generated_at: datetime | None
    verified_at: datetime | None   # verified がリストなら最大の at
    stale_after: date | None
    content_hash: str      # 本文+fm の SHA-256。冪等取り込みの判定キー
    ingested_at: datetime
```

**制約**:
- `(bundle, rel_path)` 一意。再取り込みで `content_hash` が同じ行は**更新しない**（冪等）
- `rel_path` が `private.md` に一致する行は挿入禁止（トリガーで拒否）
- 日付だけの `generated.at` は `00:00:00+09:00` を補って保存し、`fm` 側に原文を残す

### エンティティ: Chunk（見出し単位の断片）

```python
@dataclass(frozen=True)
class Chunk:
    id: int
    document_id: int
    ordinal: int           # 文書内の順番
    heading_path: str      # "H1 > H2 > H3"
    body: str              # 断片本文
    context: str | None    # 文脈文（「このファイルは◯◯の△△節」）。文脈付与あり/なしの比較用
    tokens: int
    tsv: TSVector          # 全文検索用（生成列）
    embedding: Vector | None   # 次元は Embedder に依存。embedding_model 列で区別
    embedding_model: str | None
```

**制約**:
- `(document_id, ordinal)` 一意
- 埋め込みは `context + body` に対して生成する（文脈付与あり）／`body` のみ（なし）を **別行でなく別列** で持たない。方式比較は `embedding_model` に `':ctx'` 接尾辞を付けた**別レコード集合**として持つ（同一チャンクに複数埋め込み → `chunk_embedding` 子テーブルへ分離）

### エンティティ: ChunkEmbedding（方式別の埋め込み）

```python
@dataclass(frozen=True)
class ChunkEmbedding:
    chunk_id: int
    variant: str           # 'plain' | 'ctx'
    model: str
    embedding: Vector
```

### エンティティ: Fact（③ 時点用・バイテンポラル）

```python
@dataclass(frozen=True)
class Fact:
    id: int
    document_id: int
    subject: str           # 何についての事実か（例: "評価係の起動条件"）
    value: str             # 事実の内容
    valid_from: datetime
    valid_to: datetime | None      # None = 現在も有効
    recorded_at: datetime          # 記録時間＝generated.at。無ければその事実の valid_from（2026-09-29 確定。ingested_at は使わない）
    valid_source: str      # 'explicit'（fm.valid）| 'dated_text'（本文の日付＋動詞）| 'inferred'（generated.at を暫定使用）
```

**制約**:
- 識別子は `(document_id, COALESCE(chunk_id,0), subject, valid_from, md5(value))`（0008→0010）。設計時案の部分一意 `(subject) WHERE valid_to IS NULL` は valid_to を自動で閉じない方針のため未採用
- 再抽出は bundle 単位で**全削除→再挿入**（決定的＝同じ入力なら同じ行。`valid_to` を閉じる更新はしない。設計時案「旧行の valid_to を閉じて新行を挿入・削除しない」は未採用＝2026-09-29 受入検証 R6 で訂正）
- `valid_source = 'inferred'` の行は、③の回答で「暫定」と明示する

### エンティティ: Summary（④ 全体用・要約階層）

```python
@dataclass(frozen=True)
class Summary:
    id: int
    level: str             # 'bundle' | 'document' | 'section'
    target_key: str        # bundle 名 / document_id / chunk_id
    text: str
    source_hash: str       # 元テキストのハッシュ（陳腐化検知）
    model: str
    tokens_in: int
    tokens_out: int
```

### エンティティ: Question（測定用）

```python
@dataclass(frozen=True)
class Question:
    id: int
    text: str
    kind: str              # 'find' | 'count' | 'asof' | 'overview'   ← K が付けた正解ラベル
    expected: dict         # find: 正解 rel_path 群 / count: 数値 / asof: 事実 / overview: 採点対象
```

### ER図

```mermaid
erDiagram
    DOCUMENT ||--o{ CHUNK : has
    CHUNK ||--o{ CHUNK_EMBEDDING : has
    DOCUMENT ||--o{ FACT : yields
    DOCUMENT ||--o{ SUMMARY : summarized_as
    QUESTION }o--o{ DOCUMENT : expects

    DOCUMENT {
        int id PK
        text bundle
        text rel_path
        text format
        jsonb fm
        text type
        text status
        timestamptz generated_at
        timestamptz verified_at
        date stale_after
        text content_hash
    }
    CHUNK {
        int id PK
        int document_id FK
        int ordinal
        text heading_path
        text body
        text context
        tsvector tsv
    }
    CHUNK_EMBEDDING {
        int chunk_id FK
        text variant
        text model
        vector embedding
    }
    FACT {
        int id PK
        int document_id FK
        text subject
        text value
        timestamptz valid_from
        timestamptz valid_to
        timestamptz recorded_at
        text valid_source
    }
    SUMMARY {
        int id PK
        text level
        text target_key
        text text
    }
    QUESTION {
        int id PK
        text text
        text kind
        jsonb expected
    }
```

## コンポーネント設計

### Ingest（F1）

**責務**:
- フォルダ走査 → フロントマター解析（素の OKF／くろこ拡張の両対応）→ チャンク分割 → 文脈文生成 → 埋め込み → 挿入
- 冪等性（`content_hash` 一致なら skip）と `private.md` 除外
- 接続先のループバック検査

**インターフェース**:
```python
class Ingester:
    def __init__(self, conn: Connection, embedder: Embedder, *, variants: set[str]) -> None: ...
    def run(self, root: Path, bundle: str) -> IngestReport: ...   # 件数・skip・エラーを返す

class FrontmatterParser:
    def parse(self, text: str) -> ParsedDoc: ...   # format を 'okf' | 'kuroko' で判定して返す

class Chunker:
    def split(self, markdown: str, *, max_tokens: int = 800) -> list[RawChunk]: ...

def assert_loopback(dsn: str) -> None: ...   # host が localhost/127.0.0.1/::1 以外なら例外
```

**依存関係**: `Embedder`、`psycopg`、`FrontmatterParser`、`Chunker`

**形式判定の規則（D-12）**:
| 観測 | format |
|---|---|
| `metadata:` 配下に `type` がある | `kuroko`（memory 拡張） |
| `description` があり `type` が閉じた語彙に一致 | `kuroko` |
| 上記以外で `type` がある | `okf` |
| `type` が無い | 取り込むが `type=None`・WARN |

### Classifier（F2）

**責務**: 質問文 → `find | count | asof | overview | unknown` ＋ 理由

**インターフェース**:
```python
class Classifier(Protocol):
    def classify(self, question: str) -> Classification: ...   # kind, reason, confidence

class RuleClassifier(Classifier): ...      # 語彙ルール（何件・いくつ・合計 → count / 時点・いつ・当時 → asof / 全体・傾向 → overview）
class LLMClassifier(Classifier): ...       # 4型の定義と例を渡して1語で返させる（外部 API 利用時のみ）
```

**設計上の決め**: 判定器は判定不能を `unknown` として返す（判定器の中では倒さない・PRD F2）。**倒すのは `ask` 層**（`features/ask.resolve_kind`）: `--kind auto` かつ `unknown` のとき `find` として検索し、`reason` を「既知の語彙に当たらない → 探し物として検索（推定）」、`kind_fallback: true` にして推定であることを明示する（D-17・2026-10-06。それ以前は候補 2 つを提示して exit 2 で止めていた）。`--kind` を明示したときはフォールバックしない。

### Search（F3・① 探し物）

**責務**: 方式を切り替えて上位N件を返す

**インターフェース**:
```python
Mode = Literal["embed", "embed_ctx", "fts", "hybrid", "hybrid_ctx", "hybrid_ctx_rerank", "embed_ctx_rerank"]
Agg = Literal["max", "rrf_all", "rrf_top3"]   # 断片→文書の集約（順位ベース・2026-09-29）

class Searcher:
    def search(self, q: str, *, mode: Mode, k: int = 20) -> list[Hit]: ...
    # Hit: rel_path, heading_path, body, score, source ('embed'|'fts'|'both')
```

**アルゴリズム設計（ハイブリッド統合）**:
- 埋め込み検索: `ORDER BY embedding <=> :q LIMIT 100`（cosine）
- 全文検索: `ts_rank_cd(tsv, query) LIMIT 100`
- 統合: **RRF（Reciprocal Rank Fusion）** `score = Σ 1/(60 + rank_i)`。スコアの尺度が違う2系を混ぜるのに正規化が要らない
- `hybrid_ctx`: 埋め込み側を `variant='ctx'` の子テーブルで検索
- `hybrid_ctx_rerank`: 上位150件を並べ直し器（外部 API または cross-encoder）に通して上位20件
- `embed_ctx_rerank`: 文脈付き埋め込みの候補 `max(rerank_top, k)` 件だけを並べ直す（既定 rerank_top=20・全文検索を混ぜない。2026-09-29）
- **文書集約**（断片列→文書列）: `max`＝最良断片の順位、`rrf_top3`＝文書ごとの上位 3 断片の Σ1/(60+順位)（**既定・D-14**）、`rrf_all`＝全断片（断片の多い長い文書を持ち上げて崩れる＝v8）
- **`ask` の既定**: mode=`embed_ctx`・agg=`rrf_top3`（D-14・2026-09-29・recall@5 0.90 / MRR 0.861）。それまでの既定 `hybrid_ctx` は v5 で 0.80 / 0.676
- **bundle の絞り込み（scope・D-16・2026-09-30）**: 質問の語（閉じた語彙。生活・体・お金・家・仕事 → references／実装・設定 → dev／方針・案件 → memory）から対象 bundle を推定し、既定 `boost`（w=1.0）は推定 bundle の文書スコアを (1+w) 倍に持ち上げ、推定内・推定外の 2 列を安定マージする（各列の相対順位は入力のまま。負のスコアは (1+w) で割る＝持ち上げでスコアが下がらない。非降順の入力では推定内の順位が下がることはある。スコア降順の入力では「持ち上げてスコア降順」と同じ）。`filter` は推定 bundle だけで検索、`none` は従来。bundle 名が質問に明示されていればそれを優先。v10 で ① 1.00 / 0.883（in-sample。限界は bench-results v10「受入検証」節: 部分一致の誤推定・held-out 未測定・並べ直し付きモードでの効き方は未測定）

### Counter（F4・② 数える）

**責務**: 名前付きビューを呼ぶだけ。**LLM に SQL を書かせない**（PRD F4 の「3回とも同じ数字」）

**ビュー（マイグレーションで定義）**:
| ビュー | 定義 |
|---|---|
| `v_unverified` | `verified_at IS NULL AND status <> 'deprecated'` の件数（bundle 別） |
| `v_verified` | `verified_at IS NOT NULL` の件数（bundle 別。0011・2026-09-29 追加＝Q12「確認済みは何件」を補集合でなく定義そのもので答える）。**`status: deprecated` も数える**（判定は verified_at の有無だけ。`v_unverified` は deprecated を除くので、2 つは補集合ではない） |
| `v_by_type` | `type` 別件数 |
| `v_stale` | `stale_after < current_date` の件数 |
| `v_by_bundle` | bundle 別件数・チャンク数・平均トークン |

**インターフェース**:
```python
class Counter:
    def ask(self, question: str) -> CountAnswer: ...   # 質問 → ビュー名の対応表（辞書）→ 実行。対応しない質問は「未定義の集計」と返す
```

### Temporal（F5・③ 時点）

**責務**: `Fact` の抽出と as-of 問い合わせ

**インターフェース**:
```python
class FactExtractor:
    def extract(self, doc: ParsedDoc) -> list[Fact]: ...   # fm.valid → explicit／本文・見出しの「日付＋動詞」行 → dated_text／どちらも無ければ generated.at で inferred

class Temporal:
    def as_of(self, subject: str, at: datetime) -> list[Fact]: ...
    # SELECT * FROM fact WHERE subject = :s AND valid_from <= :at AND (valid_to IS NULL OR :at < valid_to)
    def history(self, subject: str) -> list[Fact]: ...   # valid_from 順
```

**MVP の範囲**: `Fact` は**フロントマターの `valid` キーと、本文・見出しの「YYYY-MM-DD＋動詞」行（同一行 20 字窓・次の日付で打ち切り）から機械抽出**する（2026-09-29 実装。設計時の「決定台帳の行から」は dated_text がそれを包含）。本文からの自由抽出（LLM）は Post-MVP。

### Overview（F6・④ 全体）

**責務**: 要約階層の生成と参照（P1）。要約は元テキストの `source_hash` を持ち、回答時に同じ関数で再計算して違えば「要約が古い」と WARN する（`dbr summarize --bundle X --check`＝陳腐化ありで exit 6。section レベルは対象外）。検知の範囲: bundle のハッシュは各文書の rel_path＋description だけを覆い、種別・未確認・期限切れの件数の変化は document レベルの changed で捕まえる。「期限切れ（今日時点）」は日付の進行だけで古くなるのでハッシュでは検知しない（要約の作り直しは運用で）

**回答層（2026-09-30 追加）**: 抽出型の回答（bundle 要約の先頭行＋上位文書の document 要約＝証拠）に加え、`--llm <ローカルモデル>` を指定すると**同じ証拠だけを渡してローカル LLM（transformers・CPU・貪欲デコード）が日本語 3〜5 文の回答を書く**（プロンプト v2: 観点ごとにファイル名を 1 つ以上）。回答中のファイル名・数値のうち証拠に無いものを `unsupported_mentions` で機械検出し（ハルシネーションの下界）、bench は 2 回生成して一致（reproducible）と所要秒を記録する。外部 API は使わない（D-13 と同じ境界）。上位文書の選び方は ① の既定と同じ集約 rrf_top3・同じ断片数 AGG_CHUNKS（D-14）。**証拠の bundle は scope（D-16・既定 boost）で推定した bundle に絞る**（bundle 要約も推定側だけ。推定理由と「他の bundle は対象外／候補に残す」を warnings に 1 行。語彙外の scope は ValueError）

**インターフェース**:
```python
class Summarizer:
    def build(self, level: str, target_key: str) -> Summary: ...   # 下位要約を束ねて上位を作る
class Overview:
    def answer(self, question: str, *, bundle: str) -> OverviewAnswer: ...   # 根拠にした Summary の id を返す
```

### Ask（計算本体・3 入口の共通部）

**責務**: 型判定 → 該当コンポーネント → 回答 dict。CLI（単発）・常駐（F8）・MCP（F10）の 3 入口が**同じ `answer()`** を呼ぶ（既定の計算経路＝測定経路を 1 か所に）。

```python
@dataclass(frozen=True)
class AskOptions: kind, mode, agg, rerank_top, scope, boost_w, k, model, reranker, at, llm
class AskError(Exception): code  # 2 引数不正 / 3 ループバック違反 / 5 モデル・埋め込み不在
def answer(question, opts, *, dsn, embedder_for, reranker_for, llm_for) -> dict   # 従来の --json と同じ dict ＋ kind_fallback / notes
def format_text(out) -> str        # stdout の文面（常駐経由でも単発でも同じ）
```

`embedder_for` 等は名前 → 実装の供給者。CLI は毎回作り、常駐は 1 回読んだものを返す。

### Serve（F8・常駐）

**責務**: 埋め込みモデルを 1 回だけ読んだプロセスを常駐させ、ループバック HTTP で ask / sync に答える（D-18）。

- bind は **127.0.0.1 固定**（既定ポート 47821・環境変数 `DBR_PORT`）。経路は `GET /health` / `POST /ask` / `POST /sync` / `POST /shutdown` の 4 つだけ
- モデル（埋め込み・並べ直し・LLM）は名前ごとに 1 個保持し、推論は Lock で直列化
- 起動直後に 1 回、以後 `--sync-interval` 分（既定 30・0 で無効）ごとに Sync（F9）を別スレッドで実行。`/health` に最後の同期（時刻・秒・変更の有無・エラー）
- クライアント（`serve/client.py`）: `health`（**2 秒**で不応答＝居ない。起動直後の同期中は応答が遅れるので 0.3 秒では誤判定した＝2026-10-06 実測。閉じたポートへは Windows ではタイムアウトまで待つので、常駐が居ないときの `dbr serve` / `dbr sync` は 2 秒遅れる）・`ask_remote`・`ensure_daemon`（`python -m dbr.cli serve` を切り離して起こし health を待つ・既定 90 秒。起こした子が先に終わったら待たずに諦める）・`stop_daemon`
- `POST /sync` は走行中の同期があれば**終わるのを待ってから**走る（409 を返さない）。定期スレッド側は重なった周期を飛ばす
- `dbr ask` の経路: `--no-daemon` / `DBR_NO_DAEMON=1` / `--dsn` 明示 → 単発。それ以外は常駐（居なければ起こす。起こせなければ WARN を出して単発に倒す）
- ログは 2 本（D-20・2026-10-13）: **運用ログ** `~/.dbr/serve.log` は経路名・件数・時刻だけ。**利用ログ** `~/.dbr/usage.jsonl` は 1 要求 1 行の JSON（`client`＝mcp / cli / cli-local / bench / other の許可リスト・`question`・`kind_requested`→`kind`・`kind_fallback`・`k`・`mode`/`agg`/`scope`・`status`＝ok / error / daemon_unavailable・`code`・`error`・`ms`・`n_hits` と上位 `hits`（doc・heading 120 字・score。**断片本文は書かない**）。count は `view`/`n_rows`、asof は `n_facts`、overview は `n_summaries`）。書くのは `/ask` ハンドラ（CLI 経由・MCP 経由の全要求）＋ CLI 単発経路（`cli-local`）＋ MCP で常駐を起こせなかった時（`daemon_unavailable`）。集計は `dbr usage [--days N] [--json] [--path]`（client×status・フォールバック率・p50/p90・0 件だった質問・code 別エラー）。認証は持たない（単一利用者の PC。ローカルプロセスは正本も直接読める）
- **DB 停止の検知** `~/.dbr/DB-UNREACHABLE.flag`: 同期が **DB の接続段（`psycopg.OperationalError`）で 2 回連続**失敗したら書く（取り込み拒否など DB 以外の同期失敗は数えない）（30 分間隔 → DB 死後 1 時間以内。1 回は一過性を許す）、`/ask` が `psycopg.OperationalError`（接続段）で落ちたら即書く、**同期が成功したら消す**（ask の成功では消さない）。`/health` に `consecutive_sync_failures` / `db_unreachable`。SessionStart フック `~/.claude/hooks/check-regression-flags.py` が拾って警告する。
- **自動復旧（D-21・`serve/recovery.py`）**: フラグを書いた直後に別スレッドで `docker inspect dbr_pg` → `running`/`paused` は `docker restart`/`unpause`、`exited` で exit code ≠ 0（クラッシュ 255・kill 137）は `docker start`、**exit 0（手で `docker stop` した）は触らない**（フラグ本文に「手で止められています」）。成功判定は DB に接続して `SELECT 1`（状態変更コマンド後に最長 60 秒。probe は別スレッドで打ち切るので固まった DB でも返る）。`running` の時は**操作の直前にも 1 回 DB を見て、届けば打たない**（`skipped_healthy`）。DB に届いたと確認できた 2 経路（`recovered` / `skipped_healthy`）は即 `run_sync()` へ合流し、成功でフラグが消える。1 常駐あたり 10 分に 1 回（再起動ループ防止）・別の試行が走行中なら待たずに戻る（`skipped_in_progress`）。フラグの書く・追記・消すは 1 つのロックで排他。`docker` が無い・応答しない時は `docker_unavailable` を記録して終わる（Docker Desktop の復旧は人の作業）。無効化は `dbr serve --no-auto-recover` / `DBR_NO_AUTO_RECOVER=1`。結果は serve.log（`recovery <status>`）・フラグ本文・`/health.last_recovery` / `auto_recover`実測 2026-10-08〜13: DB が「稼働中なのに応答しない」まま 3 日気づかれなかった（serve.log に `sync error` 20 行）

### Sync（F9・同期）

**責務**: 正本フォルダの変更・新規・削除を DB に反映する（D-19）。

```python
BUNDLES_ORDER = ("references", "dev", "memory", "stock", "tax", "scout", "experiments")
def bundle_roots() -> dict[str, Path]      # 既定パス。DBR_ROOT_<BUNDLE> で上書き
def prune(dsn, bundle, root) -> int        # DB にあって正本に無い document を削除（root 不在は ValueError＝誤って全削除しない）
def run_sync(dsn, embedder, *, bundles=None, roots=None, log=print) -> SyncReport
```

- bundle ごとに ingest → prune → embed(plain) → embed(ctx) → （`changed` または要約が陳腐化していれば）facts → summarize。「正本にある」の定義は ingest と同じ関数（`iter_markdown` / `is_excluded`）
- document の削除は FK CASCADE で chunk / chunk_embedding / fact に伝わる。summary は FK を持たないので prune が document・section 階層の行を消し、bundle 階層は summarize が作り直す
- `rebuilt_reason`（`changed` / `stale_summaries` / None）で、何を理由に fact と summary を作り直したかを報告に残す

### MCP（F10・エージェントの入口）

**責務**: Claude Code のセッションから `ask` / `count` / `sync` / `health` を呼べる stdio の MCP サーバー（`dbr mcp`）。常駐（F8）へ中継するだけで、torch 等は import しない（セッションごとに 1 プロセス起きるため）。登録は `claude mcp add --scope user dbr -- uv run --project <repo> dbr mcp`（K が 1 回）。

### Bench（F7・測定）

**責務**: `Question` を流し、型別の指標を出す

**インターフェース**:
```python
class Bench:
    def run(self, questions: list[Question], *, modes: list[Mode]) -> BenchReport: ...
    # find: recall@5 / recall@20 / MRR を mode 別に
    # count: 完全一致率（3回実行の一致も検査）
    # asof: 一致率
    # overview: K の採点を読み込んで平均
    def to_markdown(self) -> str: ...
    def to_json(self) -> dict: ...
```

## ユースケース図

### `dbr ask` の流れ

```mermaid
sequenceDiagram
    participant K
    participant CLI
    participant CLS as Classifier
    participant X as 該当コンポーネント
    participant PG

    K->>CLI: dbr ask "未確認の記録は何件？"
    CLI->>CLS: classify(q)
    CLS-->>CLI: kind=count, reason="何件"
    CLI->>X: Counter.ask(q)
    X->>PG: SELECT * FROM v_unverified
    PG-->>X: rows
    X-->>CLI: CountAnswer(定義=v_unverified, 値)
    CLI-->>K: 数値 + 使った定義名 + SQL
```

**フロー説明**:
1. 型判定が先。判定結果と理由を必ず出力に含める
2. 型に対応するコンポーネント**だけ**を呼ぶ（②の質問で検索を走らせない）
3. 回答には根拠（ファイルパス／ビュー名と SQL／Fact の有効期間／Summary の id）を必ず添える

### `dbr ingest` の流れ

```mermaid
sequenceDiagram
    participant K
    participant CLI
    participant ING as Ingester
    participant EMB as Embedder
    participant PG

    K->>CLI: dbr ingest ~/.agents/knowledge/dev
    CLI->>ING: assert_loopback(dsn)
    ING->>ING: 走査 → parse → chunk → context
    ING->>PG: content_hash 照合（既存は skip）
    ING->>EMB: 新規チャンクの埋め込み（variant 別）
    ING->>PG: INSERT document / chunk / chunk_embedding / fact
    ING-->>CLI: IngestReport(新規 n, skip m, 拒否 0)
```

## API設計
該当なし（CLI と Python 関数のみ。Web API は作らない＝PRD スコープ外）。

## ファイル構造（データ保存形式）

DB のスキーマは `migrations/NNNN_*.sql` に置く。番号順に適用し、適用済みは `schema_migrations` 表で管理。

```
migrations/
├── 0001_extensions.sql      # CREATE EXTENSION vector; （全文検索拡張は architecture で確定後）
├── 0002_document.sql
├── 0003_chunk.sql           # tsv 生成列・GIN インデックス
├── 0004_chunk_embedding.sql # HNSW インデックス（variant/model 別）
├── 0005_fact.sql            # 部分一意インデックス（valid_to IS NULL）
├── 0006_summary.sql
├── 0007_views_count.sql     # v_unverified など
└── 0008_question.sql
```

## パフォーマンス最適化

- HNSW インデックス（`m=16, ef_construction=64` を初期値。`ef_search` は測定で振る）。IVFFlat は比較対象として測るだけ
- 全文検索は GIN。`tsv` は生成列にして取り込み時に計算
- 埋め込み生成は取り込み時のみ。`content_hash` が同じチャンクは再計算しない（API コストの上限）
- ③は `subject` ＋ `valid_from` の複合インデックスで1クエリ

## セキュリティ考慮事項

- **ループバック強制**: `assert_loopback(dsn)` を `ingest`/`ask` の起動時に必ず通す。故障注入テストで `host=example.com` を渡して拒否を確認
- **`private.md` 除外**: 走査で除外＋DB トリガーで二重に拒否
- **外部 API への送信**: `Embedder` 実装が外部通信する場合、`bundle in {'references', 'memory'}` なら**拒否**（K の承認が出るまで）。承認後は設定ファイルの明示フラグで解除
- 認証情報は環境変数か、リポ直下の `.env`（gitignore）。DSN の解決順は `--dsn` → 環境変数 `DBR_DSN` → `.env` の `DBR_DSN`（`.env` から読むのはこのキーだけ。MCP が env なしで起こす常駐もこれで接続できる・2026-10-08）

## エラーハンドリング

| エラー種別 | 処理 | ユーザーへの表示 |
|-----------|------|-----------------|
| 接続先がループバックでない | 起動時に例外・何も書かない | `拒否: 個人データの DB はローカル接続のみ（host=...）` |
| フロントマター解析失敗 | そのファイルを skip・件数に計上 | `WARN: <path> フロントマター不正（理由）` |
| `type` 無し | 取り込む（`type=None`） | `WARN: <path> type 無し` |
| 埋め込み API 失敗 | そのチャンクは埋め込み無しで保存・後で `dbr embed --retry` | `WARN: 埋め込み失敗 n 件（再試行: dbr embed --retry）` |
| 型判定 `unknown` | 回答しない | `型を判定できません。候補: count / find。--kind で指定してください` |
| ②で未定義の集計 | 回答しない | `この集計は定義されていません。定義済み: v_unverified, ...` |

## テスト戦略

### ユニットテスト
- `FrontmatterParser`: 素 OKF／くろこ拡張／memory ネスト／日付だけ／`verified` リスト・単一／`type` 無し
- `Chunker`: 見出し分割・上限トークン・コードブロックをまたがない
- `RuleClassifier`: 20問セット（fixture）で正解ラベル一致 ≥ 90%
- `assert_loopback`: localhost/127.0.0.1/::1 は通す・それ以外は例外（故障注入）
- RRF 統合: 既知の順位から期待スコアを計算して一致

### 統合テスト（Docker の PostgreSQL 必須・`pytest -m db`）
- `ingest` 冪等: 2回実行で `document`/`chunk` の行数が**増えない**（before/after の差分）
- `private.md` を含む fixture フォルダ → 取り込み後に該当行が**0**（トリガー拒否）
- ②: 同じ質問3回で同じ数値
- ③: 方針変更3回の fixture で各時点の `as_of` が一致
- マイグレーション: 空 DB から全適用 → 再適用で no-op

### E2E（測定）
- `dbr bench` を fixture 質問で2回実行し JSON が一致（再現性 KPI）
