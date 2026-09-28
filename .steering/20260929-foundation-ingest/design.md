# 設計書

## アーキテクチャ概要

縦割り（`docs/architecture.md`）。この単位で作るのは `shared/db`、`features/ingest`、`features/count`、`cli.py`、`migrations/`。

```
cli.py ──migrate──▶ shared/db/migrate.py ──▶ migrations/*.sql
       ──ingest───▶ features/ingest/__init__.run() ──▶ frontmatter / chunker / context / handler ──▶ shared/db.connect()
       ──count────▶ features/count/__init__.ask_view() ──▶ VIEWS dict ──▶ SELECT
shared/db/__init__.connect(dsn) ──▶ loopback.assert_loopback(dsn) ──▶ psycopg.connect
```

## コンポーネント設計

### 1. `shared/db`
**責務**: 接続（ループバック検査）、マイグレーション適用
**実装の要点**:
- `assert_loopback(dsn)`: `psycopg.conninfo.conninfo_to_dict` で host を取り、`{"localhost","127.0.0.1","::1"}` 以外（空＝Unix ソケットも Windows では無いので拒否）は `LoopbackViolation`。**接続を試みる前に判定**
- `connect(dsn) -> psycopg.Connection`: 上を通してから `psycopg.connect(dsn, row_factory=dict_row)`
- `migrate(conn, dir)`: `schema_migrations(version text pk, applied_at timestamptz)` を自作。`NNNN_*.sql` を昇順で読み、未適用だけ1トランザクションずつ実行。戻り値＝適用件数

### 2. `migrations/`
| ファイル | 内容 |
|---|---|
| `0001_extensions.sql` | `CREATE EXTENSION IF NOT EXISTS vector;`（列はまだ作らないが拡張の存在確認を兼ねる） |
| `0002_document.sql` | `document(id bigserial pk, bundle text, rel_path text, format text check in ('okf','kuroko'), fm jsonb, type text, status text default 'stable', generated_at timestamptz, verified_at timestamptz, stale_after date, content_hash text, ingested_at timestamptz default now(), unique(bundle, rel_path))` ＋ **トリガー**: `rel_path` の末尾が `private.md` なら `RAISE EXCEPTION 'private.md is never ingested'` |
| `0003_chunk.sql` | `chunk(id bigserial pk, document_id fk on delete cascade, ordinal int, heading_path text, body text, context text, tokens int, unique(document_id, ordinal))`。`tsv` 生成列は**次単位**（分かち書き方式と同時に） |
| `0004_views_count.sql` | `v_by_bundle`（bundle, docs, chunks）／`v_by_type`（bundle, type, n）／`v_unverified`（bundle, n where verified_at is null and status<>'deprecated'）／`v_stale`（bundle, n where stale_after < current_date） |

### 3. `features/ingest`
**責務**: フォルダ → document/chunk
**実装の要点**:
- `frontmatter.py`: `python-frontmatter` で `(metadata dict, body)`。`parse(text) -> ParsedDoc(fm, body, format, type, status, generated_at, verified_at, stale_after)`
  - 判定: `fm.get("metadata", {}).get("type")` があれば `kuroko`（memory）。それ以外で `description` があり `type` が閉じた語彙（`Tech Note`…）なら `kuroko`。それ以外で `type` があれば `okf`。`type` 無しは `okf` 扱い＋`type=None`
  - 時刻: `generated`/`verified` は dict でも list でも受ける。`at` が `date` 型（YAML が日付だけを date にする）なら `datetime(…, tzinfo=+09:00)` に補完。`verified` が list なら `max(at)`
  - `updated:` は無視（`fm` には残る）
- `chunker.py`: 見出し（`#`〜`###`）で分割→`heading_path`。コードフェンス内の `#` は見出し扱いしない。800 トークン超は段落境界で分割（トークン数は `len(text)//2` の近似で可。次単位で tokenizer に差し替え）
- `context.py`: `f"{bundle}/{rel_path} — {heading_path}"` のテンプレ生成のみ（LLM 生成は次単位）
- `handler.py`: 走査（`private.md` と `.bak` を除外・`rel_path` 正規化）→ parse → hash（fm+body の SHA-256）→ 既存行と照合（同 hash → skip、異 → 更新＝chunk 全削除＋再挿入、無 → 挿入）。`IngestReport(inserted, updated, skipped, failed, rejected)`。`rejected>0` は例外で全体停止
- `__init__.run(root: Path, bundle: str, dsn: str) -> IngestReport`

### 4. `features/count`
- `VIEWS: dict[str, str] = {"v_by_bundle": "SELECT * FROM v_by_bundle ORDER BY bundle", ...}`（識別子契約: 入力はキー照合のみ）
- `ask_view(name, dsn) -> list[dict]`。不在は `UnknownAggregate(sorted(VIEWS))`

### 5. `cli.py`（typer）
- `dbr migrate`／`dbr ingest <root> --bundle <語彙>`／`dbr count <view>`。DSN は `--dsn` または env `DBR_DSN`。出力は表＋末尾に JSON 1行（`--json` で JSON のみ）

## データフロー

### ingest
```
1. assert_loopback(dsn)
2. walk(root): *.md、private.md/.bak/隠しdir を除外、rel_path 正規化
3. parse → ParsedDoc、失敗は failed++ して続行
4. hash 照合 → insert / update / skip
5. chunk → context → INSERT chunk
6. 全ファイルを1トランザクションで commit（実装時に変更: 境界違反で**全体を** rollback するため）。rejected>0 なら rollback して例外
7. IngestReport を返す
```

## エラーハンドリング戦略
- `LoopbackViolation(host)`／`PersonalDataRejected(rel_path)`／`FrontmatterError(rel_path, reason)`／`UnknownAggregate(known: list[str])`
- CLI は例外種別ごとに exit code: Loopback=3、Rejected=4、UnknownAggregate=2、その他=1
- メッセージに本文を含めない（パス・件数・理由まで）

## テスト戦略
### ユニット（DB 不要）
- `frontmatter`: 素／memory ネスト／日付だけ／`verified` リスト／`type` 無し／YAML 壊れ
- `chunker`: 見出し分割・フェンス内 `#`・800 超の分割
- `loopback`: localhost / 127.0.0.1 / ::1 / example.com / 空 host
- `count.VIEWS`: 未定義名で `UnknownAggregate`、`__proto__` 相当の変な名前も同じ扱い
### 統合（`-m db`・Docker 必須・未起動は失敗）
- `migrate` 2回で2回目は 0 件
- fixture 3種の取り込み・`format` 列・2回目の行数不変
- `private.md` トリガー拒否（直接 INSERT でも）
- `v_*` の値が fixture の期待と一致・3回同値
### 故障注入
- 上の Loopback／private.md／未定義ビューの3つを「実際に落として」確認するテストを `tests/integration/test_fault_injection.py` に集約

## 依存ライブラリ（pyproject に追加）
```toml
dependencies = ["psycopg[binary]>=3.2", "typer>=0.12", "python-frontmatter>=1.1", "pyyaml>=6"]
[project.scripts]
dbr = "dbr.cli:app"
```
（pgvector Python パッケージは次単位）

## ディレクトリ構造（この単位で追加）
```
compose.yaml  .env.example  migrations/0001..0004
src/dbr/{__init__,cli}.py
src/dbr/shared/db/{__init__,loopback,migrate,test_loopback}.py
src/dbr/features/ingest/{__init__,frontmatter,chunker,context,handler,test_ingest}.py
src/dbr/features/count/{__init__,test_count}.py
tests/integration/{conftest,test_migrate,test_ingest_idempotent,test_fault_injection,test_count_stable}.py
tests/fixtures/{okf-plain,kuroko,with-private}/
```

## 実装の順序
1. pyproject 依存・compose・.env.example・`shared/db`（loopback→connect→migrate）・migrations 0001-0002 → `dbr migrate` が通る
2. migrations 0003-0004
3. `ingest`（frontmatter → chunker → context → handler → CLI）
4. `count`
5. fixtures・ユニット・統合・故障注入
6. 実データ `knowledge/dev` で実行・README 更新・振り返り

## セキュリティ考慮事項
- ループバック検査は**接続前**。トリガーは DB 側の二重防御。`.env` は gitignore（`.env.example` のみコミット）
- fixture の `private.md` は「ダミー本文」だけ（実物をコピーしない）

## パフォーマンス考慮事項
- ファイル単位 commit（1件失敗で全体を失わない）。`knowledge/dev` 50 ファイルで 30 秒以内が目標（埋め込みなしなので余裕）

## 将来の拡張性
- `chunk` に `tsv` 生成列と `chunk_embedding` 表を**新番号のマイグレーションで**追加（既存ファイルは編集しない）
- `context.py` を LLM 生成に差し替えられるよう関数1つに閉じる
