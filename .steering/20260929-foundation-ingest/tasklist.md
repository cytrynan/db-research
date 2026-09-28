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

- [x] 環境とスキーマ: compose・shared/db・migrations 0001-0004 で `dbr migrate` を通す (#2)
  - [x] pyproject に psycopg[binary]/typer/python-frontmatter/pyyaml と `dbr` スクリプトを追加、`uv sync`
  - [x] `compose.yaml`（pgvector/pgvector:pg16、`127.0.0.1:5432` のみ公開、volume `dbr_pg`、メモリ上限）と `.env.example`
  - [x] `shared/db/loopback.py`（`assert_loopback`）＋ユニットテスト5ケース
  - [x] `shared/db/__init__.py`（`connect`）と `migrate.py`（runner）
  - [x] `migrations/0001_extensions.sql`・`0002_document.sql`（private.md トリガー込み）・`0003_chunk.sql`・`0004_views_count.sql`
  - [x] `cli.py` に `migrate` を配線。`docker compose up -d` → `uv run dbr migrate` exit 0、再実行で 0 件

## フェーズ2: 取り込み（F1）

- [x] 取り込み（F1）: frontmatter / chunker / context / handler / CLI `ingest` (#3)
  - [x] `frontmatter.py`（素 OKF／くろこ拡張の解析・format 判定・時刻補完）＋ユニットテスト6ケース
  - [x] `chunker.py`（見出し分割・フェンス無視・800 超分割）と `context.py`（テンプレ文脈文）＋ユニットテスト
  - [x] `handler.py`（走査・除外・正規化・hash 照合・insert/update/skip・IngestReport・rejected で停止）と `__init__.run`
  - [x] `cli.py` に `ingest <root> --bundle <語彙>` を配線（語彙外は typer で拒否、exit code 規約）

## フェーズ3: 数える（F4 最小）

- [x] 数える（F4 最小）: `VIEWS` 辞書・`ask_view`・`UnknownAggregate`・CLI `count` ＋ユニットテスト（未定義名・変な名前） (#4)

## フェーズ4: fixture・統合テスト・故障注入

- [x] fixture・統合テスト・故障注入（`-m db`） (#5)
  - [x] `tests/fixtures/{okf-plain,kuroko,with-private}` を作成（他人の情報なし・private.md はダミー）
  - [x] `tests/integration/conftest.py`（DB 未起動は失敗・スキーマ適用・各テスト前に truncate）と `test_migrate.py`
  - [x] `test_ingest_idempotent.py`（3 fixture・format 列・2回目の行数不変・type 無し WARN）
  - [x] `test_fault_injection.py`（Loopback 拒否・private.md トリガー拒否（走査＋直接 INSERT）・未定義ビュー）
  - [x] `test_count_stable.py`（fixture の期待件数・3回同値）

## フェーズ5: 実データと品質チェック

- [x] 実データ取り込みと品質ゲート3点 (#6)（受入条件「件数がファイル数と一致」は 52/53＝1 件 failed。理由は振り返り参照）
  - [x] `uv run dbr ingest ~/.agents/knowledge/dev --bundle dev` を実行: 53 ファイル中 52 取り込み・1 件 YAML 不正で failed（pending-proposals.md・知見側を修正済み）。所要 1.6 秒（接続の罠を直す前は 131 秒）
  - [x] リント（`uv run ruff check .` / `uv run ruff format --check .`）
  - [x] 型チェック（`uv run mypy src`）
  - [x] テスト（`uv run pytest` と `uv run pytest -m db`）

## フェーズ6: ドキュメント更新

- [x] ドキュメント更新と振り返り (#7)
  - [x] README.md にセットアップと3コマンドを追記、`docs/log.md` に1行
  - [x] 実装後の振り返り（このファイルの下部に記録）

---

## 実装後の振り返り

### 実装完了日
2026-09-29

### 計画と実績の差分

**計画と異なった点**:
- `chunk` の挿入を `executemany` から `COPY` に変えた（設計は INSERT 前提）。ただし変えた動機は誤診（下記）で、性能上の必要は無かった。往復1回になる利点はあるので残した
- `*.bak-*` は `.md` で終わらないので走査に乗らず、`excluded` に数えない（設計は「除外して数える」想定）。テストの期待値を実態に合わせた
- 統合テストから `tests.integration.conftest` を import するため `tests/__init__.py` と `pythonpath = ["."]` を追加

**新たに必要になったタスク**:
- `src/dbr/test_cli.py`（typer の CliRunner で exit code 規約を検証）。カバレッジ 78%→88%。cli.py が薄い配線でも「exit code が契約」なので unit で押さえる価値があった
- ruff の全角記号（RUF001/002）を `allowed-confusables` で許可。日本語 docstring を書く前提なら初期設定に入れるべき

### 止まった点・失敗した点（**必須。1件以上**）

- **何が起きたか**: `knowledge/dev`（52 ファイル）の取り込みが 2 分かかり、2 回目（全件 skip）も 2 分だった。最初は「INSERT が遅い」と決めつけて COPY 化したが変わらず
- **原因**: 接続そのものが 130 秒。Windows で `localhost` が先に `::1` に解決され、Docker Desktop は `127.0.0.1` にしかポートを出していないため、IPv6 のタイムアウト後に IPv4 へ落ちていた。段階別に計測（connect 130s / select 1ms / read・parse 10ms）して 1 発で特定
- **次にどうするか**: **遅いと感じたら直す前に段階別に測る**。往復数に比例しない遅さは接続固定費を疑う。対処は `connect()` で `localhost→127.0.0.1` に正規化＋`connect_timeout=5`（1.6 秒に短縮）。知見は `dev/docker-desktop-windows.md` に記録済み

### 学んだこと

**技術的な学び**:
- 具体: `tests/fixtures/kuroko/updated.md` の `description: 規約外キー updated: を持つ` が YAML の ScannerError（plain scalar の中に `: `）。実データ `knowledge/dev/pending-proposals.md` も同じ理由で 1 件 failed
  - 抽象: **OKF の `description` に「キー名: 」を書くと YAML として壊れる**。自由文フィールドは引用符で囲む運用にするか、検査器（check-knowledge-base.mjs）で YAML パース失敗を FAIL に出す
- 具体: `count_rows` の `# noqa: S608` が RUF100（未有効ルールの noqa）で落ちた
  - 抽象: noqa は有効化しているルールにだけ書く。ruff は未有効ルールの noqa を警告にする
- 具体: typer は command が 1 つだけだとサブコマンド無しの CLI になり `dbr migrate` が「余分な引数」になる
  - 抽象: サブコマンド形式を保つには `@app.callback()` を置く

**プロセス上の改善点**:
- **品質ゲートが失敗したのに commit した**（`&&` 連鎖の後の別行で `git commit` を書いていた）。自己申告して次の commit で回収したが、ゲートと commit は**同じ `&&` 連鎖に入れる**か、ゲートの exit を見てから別コマンドで commit する
- タスクを 18 件で起票しようとして上限（10）に当たった。フェーズ単位 6 件に束ねたら issue 一覧が読めるようになった。**親タスク＝フェーズ、サブタスク＝ファイル単位**が丁度よい

**リポジトリをまたいで使える知見**:
- `localhost`→`::1` 先行で Docker Desktop 宛の接続が 130 秒止まる罠（`dev/docker-desktop-windows.md` に記録済み）
- OKF `description` の `: ` で YAML が壊れる（`dev/recording.md` への追記候補・検査器で FAIL 化を提案）

### 受入検証（別コンテキスト・readonly-reviewer / Opus・2026-09-29）
- Codex は usage limit で起動不可 → 例外(c)で Claude が代行
- 判定: 要件2〜6 PASS、**要件1 FAIL**（`hostaddr` / `PGHOSTADDR` / `service` でループバック検査を素通りし、TEST-NET の 192.0.2.1 へ接続を試みた反例）→ 採用して修正: `hostaddr`・`service` を検査、接続時に `hostaddr` を明示して環境変数を無効化。テスト 6 ケース追加
- 近道検査: 3 が該当（tasklist の「件数一致」主張と「1 件 failed」が自己矛盾）→ 文言を実態に訂正。1・2・4 は該当なし
- 任意の指摘から採用: `Private.md`（大文字）が走査・トリガーをすり抜ける → 両方 lower() 比較に（migration 0005・既存 0002 は不変）
- 副作用: レビュー係の pytest 実行で追跡中の `.coverage` が動いた → `.gitignore` に追加し追跡解除（そもそも commit すべきでなかった）

### 次回への改善提案
- 次の作業単位（埋め込み・全文検索）は `chunk` に `tsv` 生成列と `chunk_embedding` 表を**新番号のマイグレーション**で足す。既存 0003 は触らない
- `IngestReport` に「YAML 壊れのファイル一覧」を JSON で出す（今は warnings の文字列だけ）。bench で除外対象を機械的に扱うため
- 検査器 `check-knowledge-base.mjs` に「フロントマターが YAML として読めない」FAIL を足す提案（K 判断）
