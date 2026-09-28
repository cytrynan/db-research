# 要求内容

> 厚さ: **T3**（永続スキーマに触れる＝不可逆性あり）。フル3点セット＋識別子契約。

## 概要

研究の土台を作る: Docker の PostgreSQL（localhost 限定）、SQL マイグレーション、OKF フォルダの取り込み（F1）、②数える用のビュー（F4 の最小形）、CLI `dbr migrate / ingest / count`。埋め込み・検索・型判定は次の作業単位。

## 背景

PRD の KPI「再現性（`docker compose up` → 取り込み → 測定が1コマンドで完走）」の前半を先に固める。取り込みが冪等で境界（ループバック・`private.md`）が機構で守られていないと、以降の検索実験の数値が信用できない。

## 実装対象の機能

### 1. 環境とスキーマ
- `compose.yaml` で `pgvector/pgvector:pg16` を `127.0.0.1:5432` にだけ公開
- `migrations/0001〜0004` と runner `dbr migrate`（`schema_migrations` で適用済みを飛ばす）
- `shared/db.connect()`: DSN のホストがループバック以外なら `LoopbackViolation`

### 2. 取り込み（F1・埋め込みなし）
- フロントマター解析: 素 OKF／くろこ拡張（`metadata:` ネスト、`updated:`、日付だけの `at`、`verified` リスト・単一）を dict で受け `jsonb` に保存。`format` 列に `okf|kuroko` を記録
- チャンク分割（見出し単位・800 トークン上限・コードブロックをまたがない）＋文脈文（テンプレ生成: 「<bundle>/<rel_path> の <heading_path>」）
- 冪等: `content_hash` 一致は skip。再実行で行数が増えない
- 境界: `private.md` は走査除外＋DB トリガー拒否。`IngestReport` に `rejected` があれば**全体停止**

### 3. 数える（F4 最小）
- ビュー `v_by_bundle` / `v_by_type` / `v_unverified` / `v_stale`
- `dbr count <view名>`。未定義名は `UnknownAggregate`

## 受け入れ条件

### 環境とスキーマ
- [ ] `docker compose up -d` → `uv run dbr migrate` が exit 0。再実行で「適用 0 件」
- [ ] `DBR_DSN` のホストを `example.com` にすると `dbr migrate` / `ingest` が接続前に `LoopbackViolation` で exit ≠ 0（故障注入テスト）

### 取り込み
- [ ] `tests/fixtures/okf-plain`（素 OKF 3ファイル）と `tests/fixtures/kuroko`（拡張 4ファイル: memory ネスト・日付だけ・`updated:`・`verified` リスト）が全件取り込まれ、`format` 列が期待どおり
- [ ] 2回目の `ingest` で `document` / `chunk` の行数が**増えない**（before/after 差分ゼロ）
- [ ] `tests/fixtures/with-private`（`private.md` ダミー入り）→ `private.md` の行が **0**、かつ INSERT を直接試みるとトリガーが拒否
- [ ] `type` 無しのファイルは取り込まれ `type IS NULL`、`IngestReport.failed` には数えない（WARN のみ）
- [ ] `~/.agents/knowledge/dev`（実データ・個人データなし）を取り込んで exit 0、件数がファイル数と一致

### 数える
- [ ] `dbr count v_by_bundle` が fixture で期待件数を返し、3回実行で同じ値
- [ ] `dbr count nope` が `UnknownAggregate` で定義済み一覧を表示

## 成功指標
- 統合テスト（`-m db`）と故障注入3種（ループバック・`private.md`・未定義ビュー）が PASS
- 実データ `knowledge/dev`（約50ファイル）の取り込みが 30 秒以内（埋め込みなし）

## スコープ外
- 埋め込み・pgvector 列・HNSW（次の作業単位。`chunk_embedding` 表もまだ作らない）
- 型判定（F2）・検索（F3）・時点（F5）・全体（F6）・bench（F7）
- `references/` の取り込み（境界テストが通ってから。この単位では fixture と `knowledge/dev` のみ）
- 外部 Embedder の遮断（Embedder 自体が無いので次単位で）

## 参照ドキュメント
- `docs/product-requirements.md` F1・F4・非機能「セキュリティ」
- `docs/functional-design.md` データモデル・Ingest・Counter・エラー表
- `docs/architecture.md` スタック・方式選定
- `docs/repository-structure.md` 配置
- `docs/development-guidelines.md` データ境界・SQL 規約・テストマーカー

## 識別子契約（bundle 名・rel_path・ビュー名）

対象: CLI 引数 `bundle`（ユーザー入力）と走査で得る `rel_path`、`count` のビュー名。

- **特殊キー**: `bundle` / ビュー名はユーザー入力。**素の dict のキーに使わない**（ビュー名→SQL の対応は固定の `dict` に対する `.get()` で照合し、入力側をキーに書き込まない）。`bundle` は語彙 `{references, dev, stock, tax, scout, memory, experiments}` に限定し、それ以外は typer で拒否
- **正規化**: `rel_path` は POSIX 区切り（`/`）・NFC・先頭 `./` 除去を**書き側（ingest）と読み側（検索・count）の両方**で適用。`bundle` は小文字化しない（語彙で完全一致）
- **衝突**: `(bundle, rel_path)` の再登録は `content_hash` が同じなら skip、違えば更新。**skip と更新を `IngestReport` で出し分ける**（無警告の上書きにしない）
- **不在**: 未定義のビュー名は `UnknownAggregate`（定義済み一覧を表示）。存在しないフォルダは typer のパス検証で拒否
