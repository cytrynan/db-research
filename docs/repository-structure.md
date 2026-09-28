---
type: Repository Structure
description: db-research のディレクトリ構成（縦割り: src/dbr/features/<機能>/ ＋ shared/db・shared/embed）、migrations/・bench/・docs/ の配置規則と命名規則、依存の向き
generated: { by: kuroko/claude-fable-5-1, at: 2026-09-29T08:30:00+09:00 }
status: draft
---

# リポジトリ構造定義書 (Repository Structure Document)

> [architecture.md](architecture.md) の「縦割り＋shared/db」と一致させる。Python なので snake_case・`.py`。

## プロジェクト構造

```
db-research/
├── src/dbr/
│   ├── __init__.py
│   ├── cli.py                     # typer アプリ。classify → 該当スライスの入口を呼ぶ薄い配線
│   ├── features/
│   │   ├── ingest/                # F1 取り込み
│   │   │   ├── __init__.py        # 入口: run(root, bundle) -> IngestReport
│   │   │   ├── frontmatter.py     # OKF 素／くろこ拡張の解析・format 判定
│   │   │   ├── chunker.py
│   │   │   ├── context.py         # 文脈文の生成（テンプレ／LLM）
│   │   │   ├── facts.py           # valid キー・決定台帳からの Fact 抽出
│   │   │   ├── handler.py         # 走査→挿入の本体
│   │   │   └── test_ingest.py     # ユニット（DB 不要分）
│   │   ├── classify/              # F2
│   │   │   ├── __init__.py
│   │   │   ├── rules.py
│   │   │   ├── llm.py
│   │   │   └── test_classify.py
│   │   ├── search/                # F3
│   │   │   ├── __init__.py
│   │   │   ├── fts.py             # 分かち書き→tsquery
│   │   │   ├── vector.py
│   │   │   ├── fuse.py            # RRF
│   │   │   ├── rerank.py
│   │   │   └── test_search.py
│   │   ├── count/                 # F4（ビュー名の辞書のみ。SQL は migrations 側）
│   │   ├── asof/                  # F5
│   │   ├── overview/              # F6
│   │   └── bench/                 # F7
│   │       ├── __init__.py
│   │       ├── metrics.py         # recall@k / MRR
│   │       ├── report.py          # Markdown / JSON 出力
│   │       └── test_metrics.py
│   └── shared/
│       ├── db/
│       │   ├── __init__.py        # connect(dsn) … ループバック検査込み
│       │   ├── loopback.py        # assert_loopback
│       │   ├── migrate.py         # migrations/ の番号順適用
│       │   └── test_loopback.py   # 故障注入
│       └── embed/
│           ├── __init__.py        # Embedder プロトコル
│           ├── local.py           # sentence-transformers
│           ├── external.py        # 外部 API（個人バンドル拒否を内蔵）
│           └── test_embed_guard.py
├── migrations/                    # 0001_*.sql … 番号順。Supabase にもそのまま流せる
├── tests/
│   ├── integration/               # Docker の PostgreSQL が要るもの（pytest -m db）
│   │   ├── conftest.py            # compose 起動確認・スキーマ適用・fixture 投入
│   │   ├── test_ingest_idempotent.py
│   │   ├── test_private_md_rejected.py
│   │   ├── test_count_stable.py
│   │   └── test_asof.py
│   ├── e2e/
│   │   └── test_bench_reproducible.py
│   └── fixtures/                  # 取り込み用の小さな OKF バンドル（素／くろこ拡張／private.md 入り）
├── bench/
│   ├── questions.md → docs/questions.md を参照（実体は docs 側）
│   ├── results/                   # YYYYMMDD-<mode>.json（コミットする）
│   └── snapshots/                 # pg_dump（gitignore）
├── docs/                          # 恒久ドキュメント（本書含む）
├── compose.yaml                   # PostgreSQL（pgvector）を localhost:5432 に
├── .env.example
├── pyproject.toml / uv.lock / ruff.toml / .python-version
└── .steering/                     # 作業単位の計画
```

## ディレクトリ詳細

### src/dbr/features/<機能>/
**役割**: 1機能を入口から DB 操作まで完結して持つ
**配置ファイル**: `__init__.py`（入口・公開関数のみ）、`handler.py`（本体）、補助モジュール、`test_<機能>.py`（DB 不要のユニット）
**依存関係**: 依存可能 = 自スライス・`shared/`・他スライスの `__init__`／依存禁止 = 他スライスの内部モジュール

### src/dbr/shared/
**役割**: 全スライスが初日から使う2つだけ（`db`・`embed`）。3つ目を足すときは `.steering/` に理由を書く

### migrations/
**役割**: スキーマの唯一の正本
**命名**: `NNNN_<snake_case>.sql`（4桁ゼロ埋め・欠番不可・既存ファイルは**編集しない**＝変更は新番号で）
**規則**: 各ファイルは冪等でなくてよいが、runner が `schema_migrations` で適用済みを飛ばす。ビューは `CREATE OR REPLACE VIEW`

### tests/
- ユニットはスライス内に同居（縦割りの既定）
- `tests/integration/` は `@pytest.mark.db`。DB が無ければ**スキップでなく失敗**させる（黙って通さない）
- `tests/fixtures/` の OKF バンドルは他人の情報を含めない・`private.md` は**拒否テスト専用のダミー**

### bench/
- `results/*.json` は**コミットする**（研究の一次記録）。ファイル名に日付と方式
- 結果 JSON には `model`・`dict_version`・`ef_search`・`git_sha` を必ず含める

### docs/
- `product-requirements.md` / `functional-design.md` / `architecture.md` / `repository-structure.md`（本書） / `development-guidelines.md` / `glossary.md`
- `decisions.md`（決定台帳）・`questions.md`（質問セットの正本）・`ideas/`・`log.md`

## ファイル配置規則

| ファイル種別 | 配置先 | 命名規則 | 例 |
|------------|--------|---------|-----|
| スライス入口 | `features/<機能>/__init__.py` | 公開関数は動詞 | `run()`, `search()`, `as_of()` |
| SQL | `migrations/` | `NNNN_名前.sql` | `0005_fact.sql` |
| ユニットテスト | 対象の隣 | `test_<機能>.py` | `test_classify.py` |
| 統合テスト | `tests/integration/` | `test_<シナリオ>.py` | `test_ingest_idempotent.py` |
| 測定結果 | `bench/results/` | `YYYYMMDD-<mode>.json` | `20261005-hybrid_ctx.json` |

## 命名規則
- ディレクトリ・モジュール・関数・変数: `snake_case`。クラス: `PascalCase`。定数: `UPPER_SNAKE_CASE`
- スライス名は PRD の機能名に対応させる（ingest / classify / search / count / asof / overview / bench）。増やすときは PRD に F 番号を足してから
- DB の識別子は `snake_case` 単数形（`document`, `chunk`）。ビューは `v_` 接頭辞

## 依存関係のルール

```
features/A/  →  features/B/__init__.py   (OK)
features/A/  →  shared/                  (OK)
features/A/  →  features/B/handler.py    (❌)
shared/      →  features/                (❌ 逆流)
cli.py       →  features/*/__init__.py   (OK・配線のみ。ロジックを書かない)
```

循環依存は禁止。`Embedder` などのプロトコルは `shared/embed/__init__.py` に置き、実装が上位に依存しない形にする。

## スケーリング戦略
- 機能追加＝スライスを1つ足す＋ `architecture.md` の対応表に1行＋ PRD に F 番号
- 1ファイル 300 行目安。`handler.py` が超えたら補助モジュールへ分割（スライスは割らない）

## 特殊ディレクトリ
- `.steering/`（作業計画）・`.claude/`（コマンド・スキル・エージェント）はテンプレの規約どおり

## 除外設定（.gitignore）
- `.venv/` `__pycache__/` `.pytest_cache/` `.mypy_cache/` `.ruff_cache/` `htmlcov/`（配置済み）
- `.env`・`bench/snapshots/`・モデルキャッシュ（`~/.cache` 側なので対象外）
- **`.steering/` はコミットする**（テンプレの既定。履歴として残す）
