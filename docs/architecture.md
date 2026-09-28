---
type: Architecture
description: db-research の技術仕様。PostgreSQL 16＋pgvector（Docker・localhost 限定）、Python 3.12、縦割り構成、全文検索・埋め込み・並べ直しの方式選定と未決事項、性能・セキュリティ・テストの制約
generated: { by: kuroko/claude-fable-5-1, at: 2026-09-29T08:20:00+09:00 }
stale_after: 2027-03-31
status: draft
---

# 技術仕様書 (Architecture Design Document)

> 入力: [product-requirements.md](product-requirements.md)・[functional-design.md](functional-design.md)・[decisions.md](decisions.md)。
> バージョン番号は実装着手時に `uv.lock` / `compose.yaml` で固定し、本書は**方針と理由**を持つ。

## テクノロジースタック

### 言語・ランタイム

| 技術 | バージョン |
|------|-----------|
| Python | 3.12（`.python-version`） |
| uv | 最新安定（`uv.lock` で固定） |
| PostgreSQL | 16 系（Docker 公式 `pgvector/pgvector:pg16` イメージ） |
| Docker Desktop | K の環境の現行版（`docker-desktop-recover` スキルの前提と同じ） |

### フレームワーク・ライブラリ

| 技術 | 用途 | 選定理由 |
|------|------|----------|
| psycopg 3 | DB 接続・素の SQL | SQL が研究対象なので ORM で隠さない。`COPY`・サーバサイドカーソル・型アダプタが揃う |
| pgvector（拡張）＋ `pgvector` Python パッケージ | 埋め込み列と HNSW | 4型を1つの DB で受ける前提（D-2）。Supabase 対応拡張でもある（D-4 の範囲） |
| typer | CLI `dbr` | サブコマンド＋型付き引数。K が覚えるコマンドを2つに保つ |
| python-frontmatter ＋ PyYAML | フロントマター解析 | OKF 素／くろこ拡張の両方を dict として受け、`jsonb` に丸ごと保存 |
| sentence-transformers（ローカル埋め込み） | `references/` 向け埋め込み | **本文を外部へ出さない**経路を最初から持つ（未決事項の間も研究を止めない） |
| 外部埋め込み API（実装は差し替え可能・既定なし） | `knowledge/` 向け埋め込み | 高精度モデルとの比較用。**`references`/`memory` バンドルには使えない**ようコードで遮断 |
| SudachiPy（`sudachidict_core`） | 日本語の分かち書き → `tsvector` | 標準の `simple` 辞書だけでは日本語が1語にならない。アプリ側で分かち書きして `to_tsvector('simple', …)` に渡す（下記「全文検索の方式」） |

### 開発ツール

| 技術 | 用途 | 選定理由 |
|------|------|----------|
| ruff / mypy (strict) / pytest (+cov) | 品質ゲート | テンプレ標準 |
| Docker Compose | PostgreSQL の起動 | `docker compose up` の1コマンドで再現（KPI「再現性」） |
| 自作マイグレーション runner（`dbr migrate`） | `migrations/*.sql` の番号順適用 | 依存を増やさず、同じ SQL を Supabase にも流せる（D-3/D-4） |

## アーキテクチャパターン

**採用したパターン**: 機能単位の縦割り（Vertical Slice）＋ `shared/db`
**理由**: 7つの機能（ingest / classify / search / count / asof / overview / bench）はユースケースが明確に分かれ、互いの内部を知る必要がない。DB 接続とマイグレーション適用だけは**最初から全スライスが使う**ので、「3スライスで重複してから」を待たず `shared/db` を初日に置く（規律1の例外を明示的に取る）。

### 機能名 → ディレクトリ 対応表

| 機能名 | ディレクトリ | 入口 | 概要 |
|--------|-------------|------|------|
| 取り込み（F1） | `src/dbr/features/ingest/` | `__init__.py` | OKF フォルダ → document / chunk / embedding / fact |
| 型判定（F2） | `src/dbr/features/classify/` | `__init__.py` | 質問 → 4型＋理由 |
| 探し物（F3） | `src/dbr/features/search/` | `__init__.py` | 方式切替つきハイブリッド検索 |
| 数える（F4） | `src/dbr/features/count/` | `__init__.py` | 名前付きビューの実行 |
| 時点（F5） | `src/dbr/features/asof/` | `__init__.py` | バイテンポラル問い合わせ |
| 全体（F6） | `src/dbr/features/overview/` | `__init__.py` | 要約階層の生成・参照 |
| 測定（F7） | `src/dbr/features/bench/` | `__init__.py` | 質問セット実行・指標出力 |
| 共有 | `src/dbr/shared/db/` | `__init__.py` | 接続（ループバック検査込み）・マイグレーション runner |
| 共有 | `src/dbr/shared/embed/` | `__init__.py` | `Embedder` プロトコルと実装2種（ingest と search が使う） |

スライス間の呼び出しは入口経由のみ。`ask` コマンドは `classify` → 該当スライスの入口、の順に呼ぶ薄い配線（`src/dbr/cli.py`）。

## 方式の選定（研究の中心・検索品質 D-11）

### 全文検索の方式

| 候補 | 採否 | 理由 |
|---|---|---|
| **アプリ側で分かち書き（SudachiPy）→ `to_tsvector('simple')`**（採用） | ◎ | 拡張なし＝どの PostgreSQL でも動く。分かち書きの粒度（A/B/C）を実験で振れる |
| `pg_bigm`（2-gram） | 比較対象 | 拡張が要る。Supabase での可否は**一次資料未確認**（着手時に確認して表を更新） |
| PGroonga | 見送り | 多機能だが依存が重い。研究の主題は「振り分け」なので過剰 |

### 埋め込みと並べ直し

| 段 | 方式 | 備考 |
|---|---|---|
| 埋め込み（ローカル） | multilingual-e5 系（sentence-transformers） | `references`/`memory` はこれ**のみ** |
| 埋め込み（外部） | 未定（`Embedder` 実装を差し替え） | `knowledge/` のみ。採用時に一次資料（料金・入力上限）を本書に追記 |
| 統合 | RRF（k=60） | 尺度の異なる2系を正規化なしで混ぜる |
| 並べ直し | ローカル cross-encoder（bge-reranker 系）を既定。外部 API は比較対象 | 上位150→20 |
| 文脈付与 | 各チャンクに「ファイル・節・要旨」1〜2文を前置して埋め込む | Anthropic の Contextual Retrieval と同じ考え。生成は LLM またはテンプレ（見出しパスから機械生成）の2通りを測る |

### インデックス

- 埋め込み: HNSW（`vector_cosine_ops`、`m=16`, `ef_construction=64`）。`ef_search` を 40/100/250 で振って recall とレイテンシを測る（一次資料: pgvector / Supabase の HNSW 解説）
- 全文: GIN on `tsv`（生成列）
- ③: `(subject, valid_from)` 複合＋部分一意 `(subject) WHERE valid_to IS NULL`

## データ永続化戦略

### ストレージ方式

| データ種別 | ストレージ | フォーマット | 理由 |
|-----------|----------|-------------|------|
| 正本（記録） | ファイルシステム（`~/.claude/references/` 等） | OKF Markdown | 変更しない。git と restic が守る |
| 索引（document / chunk / embedding / fact / summary） | PostgreSQL（Docker volume `dbr_pg`） | テーブル | 派生データ。**捨てて `dbr ingest` で作り直せる** |
| 質問セット・正解 | `docs/questions.md`（Markdown 表）→ `question` 表へ取り込み | Markdown / テーブル | K が編集できる形を正本にする |
| 測定結果 | `bench/results/YYYYMMDD-<mode>.json` ＋ `docs/` の表 | JSON / Markdown | 差分比較と再現性 |

### バックアップ戦略

- **DB はバックアップしない**（派生データ。復元＝`dbr ingest`）。ただし埋め込みの再計算コストを避けるため `pg_dump` を任意で `bench/snapshots/` に置ける（gitignore）
- 正本は既存の restic（memory `cloud-backup-restic`）の対象。本リポは触らない

## パフォーマンス要件

### レスポンスタイム

| 操作 | 目標時間 | 測定環境 |
|------|---------|---------|
| `ask`（①③④） | 3秒以内 | K の PC・Docker・約3,000チャンク |
| `ask`（②） | 1秒以内 | 同上 |
| `ingest` 全件 | 5分以内（埋め込みはローカルモデル） | 同上 |
| `bench` 全方式 | 30分以内 | 同上 |

### リソース使用量

| リソース | 上限 | 理由 |
|---------|------|------|
| PostgreSQL メモリ | 2GB（compose で制限） | 研究規模（1万チャンク上限） |
| ローカル埋め込みモデル | CPU 実行を既定・GPU は任意 | K の環境で必ず動く経路を既定にする |
| ディスク | 5GB | 埋め込み1024次元×1万×複数 variant を見込む |

## セキュリティアーキテクチャ

### データ保護
- **接続はループバックのみ**: `shared/db` の接続関数が DSN を解析し、host が `localhost` / `127.0.0.1` / `::1` 以外なら例外。テストで故障注入
- **外部送信の遮断**: `Embedder` の外部実装は `bundle in {references, memory}` を拒否（K 承認後は設定ファイルの明示フラグ `allow_external_for_personal: true` でのみ解除）
- **`private.md`**: 走査除外＋DB トリガー拒否の二重
- **機密情報管理**: 接続文字列・API キーは環境変数（`.env` は gitignore）。ドキュメント・ログに書かない

### 入力検証
- CLI 引数はパス存在・バンドル名の語彙・`--kind` の値域を typer で検証
- SQL は**すべてパラメータ化**。ビュー名は辞書のキーからしか来ない（文字列連結禁止）
- エラー表示に実データ本文を出さない（件数・パス・理由まで）

## スケーラビリティ設計

- **想定データ量**: 150〜300ファイル、3,000〜10,000チャンク。それ以上は PRD スコープ外
- **劣化対策**: HNSW と GIN で対数〜線形。1万超で `ef_search` の再測定
- **拡張性**: `Embedder` / `Classifier` / `Reranker` はプロトコル。方式追加＝実装クラス1つ＋`Mode` に1値

## テスト戦略

- **ユニット**: pytest。対象は functional-design の一覧。カバレッジ目標 80%（`shared/db` と `ingest` は 90%）
- **統合**（`-m db`）: Docker の PostgreSQL に接続。冪等・トリガー・ビュー・as-of・マイグレーション再適用
- **E2E**: `dbr bench` を2回走らせ JSON 一致
- **故障注入**: ループバック拒否・外部 Embedder の個人バンドル拒否・`private.md` 拒否の3つは**必ず落として確認**

## 技術的制約

### 環境要件
- OS: Windows 11（K の環境）。PowerShell から `uv run` と `docker compose` が動くこと
- 外部依存: Docker Desktop、（任意）外部埋め込み API のキー

### パフォーマンス制約
- ローカル埋め込みは CPU 前提で設計する（GPU 有無で結果の数値が変わらないこと＝再現性）

### セキュリティ制約
- 個人データを含む DB を外部ホストで動かす構成は**作らない**（D-5）
- Supabase への転用は個人データを含まないバンドルのみ（F9・P2）

## 依存関係管理

| ライブラリ | 用途 | バージョン管理方針 |
|-----------|------|-------------------|
| psycopg / pgvector / typer / python-frontmatter | 中核 | `uv.lock` で固定・意図的に上げる |
| sentence-transformers / SudachiPy / sudachidict | モデル・辞書 | **モデル名と辞書版を測定結果 JSON に記録**（数値の再現に必須） |
| Docker イメージ | PostgreSQL | タグを固定（`pg16` の具体タグを compose に書く） |

## 未決事項（architecture で決めるもの）

| 論点 | 現状 | 決め方 |
|---|---|---|
| 外部埋め込み API の採用 | 未定 | `knowledge/` で比較測定してから。個人データへの適用は K 承認が別途必要 |
| `pg_bigm` の Supabase 対応 | 一次資料未確認 | 比較実験に入れる前に supabase.com の拡張一覧で確認し本表を更新 |
| 文脈文の生成方式 | LLM とテンプレの2通り | bench で比較して既定を決める |
