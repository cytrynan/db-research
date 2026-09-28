---
type: Development Guidelines
description: db-research の開発規約。Python（ruff/mypy strict）・SQL マイグレーションの書き方・データ境界（個人データはローカルのみ）の守り方・テストのマーカーと故障注入・Git 運用・記録規約
generated: { by: kuroko/claude-fable-5-1, at: 2026-09-29T08:40:00+09:00 }
status: draft
---

# 開発ガイドライン (Development Guidelines)

> 一般規約はテンプレの `development-guidelines` スキル（`guides/implementation.md` / `process.md` / `recording.md` / `verification.md`）が正本。本書は**このリポ固有**の決めだけを書く。

## コーディング規約

### Python
- 命名: `snake_case`（関数・変数）／`PascalCase`（クラス）／`UPPER_SNAKE_CASE`（定数）。Boolean は `is_` / `has_` で始める
- 型: mypy strict を通す。公開関数は必ず型注釈。`Any` を書くときは理由をコメント
- データ構造: 不変の値は `@dataclass(frozen=True)`。DB 行との対応は functional-design のエンティティ名と一致させる
- フォーマット: ruff（設定は `ruff.toml`）。行長は ruff の既定
- コメントは「なぜ」を書く。「何を」はコードで分かる形にする

### SQL（`migrations/`）
- **既存のマイグレーションは編集しない**。変更は新番号で追加（適用済み DB との整合のため）
- 1ファイル1関心事（表・インデックス・ビューを分ける）。ビューは `CREATE OR REPLACE VIEW`
- 識別子は `snake_case` 単数形。ビューは `v_` 接頭辞。時刻列は `timestamptz`
- Python 側の SQL は**すべてパラメータ化**（`%(name)s`）。識別子の文字列連結は禁止。ビュー名は辞書のキーからのみ

### データ境界（最重要・違反は機構で止める）
- **接続はループバックのみ**: DB 接続は必ず `shared.db.connect()` を通す（`psycopg.connect` を直接呼ばない。ruff のカスタムルールが無いので**コードレビューの必須項目**にする）
- **外部 Embedder は個人バンドル拒否**: `shared.embed.external` は `bundle in {"references", "memory"}` で例外。解除は設定フラグのみ
- **`private.md` は走査除外＋トリガー拒否**の二重。fixture に置く `private.md` は拒否テスト用のダミー本文のみ
- **他人の情報を含む記録は取り込まない**（`~/.claude/CLAUDE.md` §0）。fixture も同様
- 上記3つの遮断は**故障注入テストが存在し PASS していること**が完了条件（`tests/integration/test_private_md_rejected.py`、`shared/db/test_loopback.py`、`shared/embed/test_embed_guard.py`）

### エラーハンドリング
- 予期されるエラーは専用クラス（`LoopbackViolation`, `PersonalDataExportBlocked`, `FrontmatterError`, `UnknownAggregate`）
- 個人データの本文をエラーメッセージ・ログに出さない（パス・件数・理由まで）
- 取り込みは**1ファイルの失敗で全体を止めない**（skip して件数に計上）。ただし境界違反（上3つ）は**即座に全体を止める**

## Git運用ルール

### ブランチ
- `main` のみを既定。作業は `feature/<YYYYMMDD>-<task>` を切り、`.steering/` の作業単位と1対1
- 実験（bench の方式比較）は `exp/<name>` ブランチでもよいが、**結果 JSON は main に取り込む**（一次記録を散らさない）

### コミットメッセージ
- `<type>(<scope>): <subject>`。type は `feat` / `fix` / `docs` / `test` / `chore` / `exp`（測定実行）
- 判断を伴う commit は footer に決定文脈（`Directive:` / `Rejected:` / `Constraint:` / `Not-tested:`）
- 末尾の Co-Authored-By はハーネスの指示どおり

### PR
- 個人開発なので PR は任意。`main` へ直接 push 可。ただし**品質ゲート3点（ruff / mypy / pytest）を commit 前に司令塔がもう一度実行**する（CLAUDE.md の3層原則）

## テスト戦略

### マーカー
| マーカー | 意味 | 実行 |
|---|---|---|
| （なし） | DB 不要のユニット | `uv run pytest` |
| `db` | Docker の PostgreSQL が要る統合 | `uv run pytest -m db`。DB 未起動は**失敗**（スキップ禁止） |
| `e2e` | bench の再現性 | `uv run pytest -m e2e` |
| `slow` | 埋め込みモデルを実際に動かす | 既定では除外。`-m slow` で実行 |

### 書き方
- 命名: `test_<対象>_<条件>_<期待>`（例: `test_ingest_rerun_does_not_add_rows`）
- **実データのスナップショットに固定値を書かない**。before/after の差分や関係で検査（CLAUDE.md の原則）
- 数値検証（recall 等）は既知の順位から期待値を手計算した fixture で
- 監視・遮断の類は**故障注入で1回落として確認**してから完了扱い

### モック
- 外部 API（埋め込み・並べ直し）はモック。ローカルモデルは `slow` マーカーで実物
- DB はモックしない（SQL が研究対象）。統合テストで実物を使う

## コードレビュー基準（このリポ固有の必須項目）
- [ ] `psycopg.connect` を直接呼んでいない（`shared.db.connect` 経由）
- [ ] 外部 Embedder が個人バンドルを拒否する経路が残っている
- [ ] SQL がパラメータ化されている
- [ ] マイグレーションの既存ファイルを編集していない
- [ ] 測定結果 JSON に `model` / `dict_version` / `ef_search` / `git_sha` がある
- [ ] エラー出力に本文が含まれていない

## 記録規約（OKF 準拠・テンプレの `guides/recording.md` が正本）
- `docs/` を作成・更新したら同じ作業内で `docs/log.md` に1行（Stop フックが検知）
- `generated.at` / `verified.at` は **UTC オフセット付き datetime**（`2026-09-29T08:40:00+09:00`）。日付だけは `~/.claude/scripts/check-knowledge-base.mjs` が WARN に出す（2026-09-29 追加）
- 測定結果は `bench/results/` の JSON が一次記録。`docs/` の表は転記。**転記前に JSON を1回読み直す**（A4）
- 決定は [decisions.md](decisions.md) に追記。覆したら行を残して撤回

## 開発環境セットアップ

| ツール | 入手 |
|--------|------|
| Python 3.12 / uv | `uv` が `.python-version` を見て用意 |
| Docker Desktop | 既存。落ちたら `docker-desktop-recover` スキル |
| Sudachi 辞書 | `uv sync` で `sudachidict_core` が入る |

```bash
git clone https://github.com/cytrynan/db-research.git
cd db-research
uv sync
cp .env.example .env          # DBR_DSN=postgresql://dbr:dbr@localhost:5432/dbr
docker compose up -d
uv run dbr migrate
uv run dbr ingest ~/.agents/knowledge/dev
uv run pytest && uv run pytest -m db
```

（`.env.example` と `compose.yaml` は最初の `.steering` 作業で作る。）
