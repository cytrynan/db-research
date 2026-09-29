# タスクリスト

tracking: #23

## 🚨 タスク完全完了の原則
- `- [ ]` 未着手 / `- [~]` 着手中 / `- [x]` 完了。`[x]` は完了だけ
- 各タスク行末の issue 番号が対応表。状態を変えたらその場で issue も更新
- 全タスクを `[x]` に。スキップは技術的理由のみ・行に明記

---

## フェーズ1: 事実の抽出（F5・スキーマ）

- [~] 0008_fact.sql・`ingest/facts.py`（explicit / dated_text / inferred・削除→COPY）・`dbr facts`・fixture `dated/`・統合テスト（件数・冪等） (#24)

## フェーズ2: 時点の問い合わせ（F5）

- [ ] `features/asof`（as_of / history / parse_at）・`ask` の asof 分岐と `--at`・ユニット＋統合（時点フィルタ・昇順） (#25)

## フェーズ3: 全体（F6）

- [ ] 0009_summary.sql・`ingest/summarize.py`（抽出型 3 段・source_hash）・`features/overview`・`ask` の overview 分岐・統合テスト（3 段・冪等） (#26)

## フェーズ4: bench（count / asof / overview）

- [ ] `bench/{count,asof,overview}.py`・`_guess_view` を count スライスへ移動・`questions.md` の期待欄に asof の日付・CLI `bench --kind count|asof|overview`・統合テスト（fake） (#27)

## フェーズ5: 実データと品質ゲート

- [ ] memory を取り込み・埋め込み（plain/ctx）→ references/dev/memory で `facts`・`summarize` → `bench --kind count|asof|overview` → JSON と `docs/overview-answers.md`・`docs/bench-results.md` に転記・ruff/mypy/pytest（unit・db） (#28)

## フェーズ6: 記録と受入検証

- [ ] 振り返り・README・別コンテキストの受入検証・issue クローズ (#29)

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

### 受入検証（別コンテキスト）
- 

### 次回への改善提案
- 
