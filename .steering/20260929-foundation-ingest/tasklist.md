# タスクリスト

tracking: #1

tracking: #{親issue番号}

## 🚨 タスク完全完了の原則

**このファイルの全タスクが完了するまで作業を継続すること**

### チェックボックスの記法
- `- [ ]` 未着手 / `- [~]` 着手中（いま作業中） / `- [x]` 完了
- `[x]`は「完了」だけに使う。作業中に`[x]`を付けない。

### GitHub issue との対応
- 各タスク行の末尾に子issue番号を書く（`- [ ] {タスク名} (#11)`）。**この行が対応表**
- 状態を変えたら**その場で** issue も更新する（`[~]`→assign+`in-progress` / `[x]`→`gh issue close`）

### 必須ルール
- **全てのタスクを`[x]`にすること**。「時間の都合により」「複雑すぎるため後回し」は禁止
- スキップは技術的理由（方針変更・置き換え・実行不能）のみ。理由を行に明記

---

## フェーズ1: 環境とスキーマ

- [~] 環境とスキーマ: compose・shared/db・migrations 0001-0004 で `dbr migrate` を通す (#2)
  - [ ] pyproject に psycopg[binary]/typer/python-frontmatter/pyyaml と `dbr` スクリプトを追加、`uv sync`
  - [ ] `compose.yaml`（pgvector/pgvector:pg16、`127.0.0.1:5432` のみ公開、volume `dbr_pg`、メモリ上限）と `.env.example`
  - [ ] `shared/db/loopback.py`（`assert_loopback`）＋ユニットテスト5ケース
  - [ ] `shared/db/__init__.py`（`connect`）と `migrate.py`（runner）
  - [ ] `migrations/0001_extensions.sql`・`0002_document.sql`（private.md トリガー込み）・`0003_chunk.sql`・`0004_views_count.sql`
  - [ ] `cli.py` に `migrate` を配線。`docker compose up -d` → `uv run dbr migrate` exit 0、再実行で 0 件

## フェーズ2: 取り込み（F1）

- [ ] 取り込み（F1）: frontmatter / chunker / context / handler / CLI `ingest` (#3)
  - [ ] `frontmatter.py`（素 OKF／くろこ拡張の解析・format 判定・時刻補完）＋ユニットテスト6ケース
  - [ ] `chunker.py`（見出し分割・フェンス無視・800 超分割）と `context.py`（テンプレ文脈文）＋ユニットテスト
  - [ ] `handler.py`（走査・除外・正規化・hash 照合・insert/update/skip・IngestReport・rejected で停止）と `__init__.run`
  - [ ] `cli.py` に `ingest <root> --bundle <語彙>` を配線（語彙外は typer で拒否、exit code 規約）

## フェーズ3: 数える（F4 最小）

- [ ] 数える（F4 最小）: `VIEWS` 辞書・`ask_view`・`UnknownAggregate`・CLI `count` ＋ユニットテスト（未定義名・変な名前） (#4)

## フェーズ4: fixture・統合テスト・故障注入

- [ ] fixture・統合テスト・故障注入（`-m db`） (#5)
  - [ ] `tests/fixtures/{okf-plain,kuroko,with-private}` を作成（他人の情報なし・private.md はダミー）
  - [ ] `tests/integration/conftest.py`（DB 未起動は失敗・スキーマ適用・各テスト前に truncate）と `test_migrate.py`
  - [ ] `test_ingest_idempotent.py`（3 fixture・format 列・2回目の行数不変・type 無し WARN）
  - [ ] `test_fault_injection.py`（Loopback 拒否・private.md トリガー拒否（走査＋直接 INSERT）・未定義ビュー）
  - [ ] `test_count_stable.py`（fixture の期待件数・3回同値）

## フェーズ5: 実データと品質チェック

- [ ] 実データ取り込みと品質ゲート3点 (#6)
  - [ ] `uv run dbr ingest ~/.agents/knowledge/dev --bundle dev` を実行し件数がファイル数と一致・30 秒以内を記録
  - [ ] リント（`uv run ruff check .` / `uv run ruff format --check .`）
  - [ ] 型チェック（`uv run mypy src`）
  - [ ] テスト（`uv run pytest` と `uv run pytest -m db`）

## フェーズ6: ドキュメント更新

- [ ] ドキュメント更新と振り返り (#7)
  - [ ] README.md にセットアップと3コマンドを追記、`docs/log.md` に1行
  - [ ] 実装後の振り返り（このファイルの下部に記録）

---

## 実装後の振り返り

### 実装完了日
{YYYY-MM-DD}

### 計画と実績の差分

**計画と異なった点**:
- 

**新たに必要になったタスク**:
- 

### 止まった点・失敗した点（**必須。1件以上**）

- **何が起きたか**: 
- **原因**: 
- **次にどうするか**: 

### 学んだこと

**技術的な学び**:
- 具体: 
  - 抽象: 

**プロセス上の改善点**:
- 

**リポジトリをまたいで使える知見**:
- 

### 次回への改善提案
- 
