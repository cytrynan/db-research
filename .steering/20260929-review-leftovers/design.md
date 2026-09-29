# 設計

> 設計の正本。実装はこのファイルを直接読む。

## 1. 要約の陳腐化検知（`ingest/summarize.py`・`features/overview`）

- run_summarize 内でインラインだった計算を関数に出し、run_summarize と stale_summaries の**両方がそれを使う**（別実装にしない）:
  - `top_headings(chunks) -> list[str]`: heading_path の上 2 段・重複除去・出現順
  - `doc_source_hash(fm, headings) -> str` ＝ `_h(json.dumps(fm, ensure_ascii=False, sort_keys=True, default=str) + "\n".join(headings))`
  - `bundle_source_hash(bundle_lines) -> str` ＝ `_h("\n".join(bundle_lines))`
  - `bundle_line(rel_path, desc) -> str` ＝ `f"- {rel_path}: {desc or '(description なし)'}"`
- `@dataclass StaleSummary(level: str, target_key: str, reason: Literal["changed", "missing"])`
- `stale_summaries(dsn, bundles, levels=("bundle", "document")) -> list[StaleSummary]`: bundle ごとに document を rel_path 順に読み、期待ハッシュを作って `summary.source_hash` と比較。本文は返さない
- `overview.answer()`: bundle 決定後に `stale_summaries(dsn, bundles)` を呼び、件数を warnings に。例外は握らない
- CLI `summarize --check`: run_summarize を呼ばず stale_summaries だけ。1 行 1 件 `level target_key reason` を stderr でなく stdout に。exit 6 = 陳腐化あり（README の exit 表に追加）

## 2. recorded_at（`ingest/facts.py`）

- `run_facts`: `recorded = gen if isinstance(gen, datetime) else None` を extract_* に渡す。`extract_dated` / `extract_explicit` は `recorded_at if recorded_at is not None else when`。inferred は gen が必須なので不変
- `FactsReport.recorded_from_valid: int`（fact 単位で数える）。CLI 出力 `… / recorded_at を valid_from で代用 N`
- functional-design.md「エンティティ: Fact」の `recorded_at` コメントを「generated.at。無ければその事実の valid_from」に

## 3. v_verified（`migrations/0011_view_verified.sql`・`features/count`）

```sql
CREATE OR REPLACE VIEW v_verified AS
SELECT bundle, count(*) AS n
FROM document
WHERE verified_at IS NOT NULL
GROUP BY bundle
ORDER BY bundle;
```
- `VIEWS["v_verified"] = "SELECT * FROM v_verified"`
- `guess_view`: `if "unverified" in q or "未確認" in q → v_unverified` → `elif "verified" in q or "確認済" in q → v_verified` → 以下従来
- `docs/questions.md` Q12 期待 → `v_verified`（bundle='references'）。実データ: `dbr migrate` → `bench --kind count --label v7` → bench-results

## 4. ゲート（`scripts/`）

- `gate.sh`: `set -euo pipefail` → `cd "$(dirname "$0")/.."` → `PYTHONIOENCODING=utf-8` → ruff format --check src tests → ruff check . → mypy src → pytest -m "db or not db" --cov-fail-under=80 -q -p no:cacheprovider → `echo GATE OK`
- `gate.ps1`: 同じ 4 段。各段の直後に `if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }`。`Set-Location (Join-Path $PSScriptRoot '..')`。`$env:PYTHONIOENCODING='utf-8'`
- README「再開の手順」「品質ゲート」と RESUME.md「再開の手順」を `bash scripts/gate.sh`／`pwsh -File scripts/gate.ps1` に

## 5. テスト

- unit（src 同居）: `guess_view` の 4 ケース、`top_headings` の順序・重複除去、`doc_source_hash` の決定性（同入力同値・fm の順序無関係）、`extract_dated(recorded_at=None)` → valid_from
- 統合: (a) fixtures/dated を tmp にコピー → ingest → summarize → `stale_summaries == []` → 1 文書の description を書き換え → ingest（summarize しない）→ その document と bundle が `changed` → `answer()` warnings に「要約が古い」 → CLI `--check` exit 6 → summarize → `--check` exit 0 (b) fixture `same-day.md` を generated 無し・verified 有りに → `recorded_from_valid == 2`・fact の recorded_at == valid_from・`ask_view("v_verified")` が references 1

## 6. 変更しないもの
- 既存マイグレーション（D-3）。summary 表の列は足さない（陳腐化は再計算で判定する）
