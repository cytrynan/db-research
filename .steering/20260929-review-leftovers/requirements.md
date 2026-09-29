# 要求内容

> 厚さ: **T3**（永続スキーマにビュー `v_verified` を追加＝マイグレーション 0011）。フル3点セット＋識別子契約（前単位の契約を継承）。

## 概要

前単位（`20260929-asof-overview`）の受入検証で**未回収**だった 3 件と、RESUME.md の運用項目 1 件を閉じる。研究の主題（4 型の振り分け）に新しい測定は足さない。② count の bench だけ、Q12 の定義変更に伴って再測定する。

## 背景

- 受入検証（readonly-reviewer/Opus・2026-09-29）の任意項目のうち、正しさに効くが前単位で回収しなかった 3 件:
  1. summary の `source_hash` は**保存しているだけ**で、元テキストが変わっても検知していない（陳腐化した要約が overview の回答に黙って出る）
  2. fact の `recorded_at` の規則が requirements（generated.at が無ければ valid_from）と実装（無ければ ingested_at）で食い違う。ingested_at は取り込み日（2026-09-29）なので、古い記録に対して数か月ずれる
  3. Q12「K が確認済みの記録は何件」を `v_unverified` の補集合で答えている（問いと定義が逆。② の主張「定義をビューに固定する」に反する）
- ゲート（ruff→mypy→pytest→coverage）は毎回手で連鎖している。`set -o pipefail` 抜けで commit が通った事故が 3 回ある（RESUME.md「守ること」）

## 実装対象の機能

### 1. 要約の陳腐化検知（F6）
- `summarize.stale_summaries(dsn, bundles, levels=("bundle", "document"))`: 現在の document / chunk から**要約時と同じ関数**で source_hash を再計算し、保存値と違う（`changed`）か要約が無い（`missing`）target を返す。ハッシュ計算を run_summarize と別実装にしない
- `overview.answer()` は対象 bundle の陳腐化を確認し、あれば `warnings` に「要約が古い: N 件（`dbr summarize --bundle <b>` で作り直す）」を足す。回答は止めない
- `dbr summarize --bundle X --check`: 書き換えずに陳腐化の一覧（level と target_key のみ・本文は出さない）を出す。無ければ exit 0、あれば **exit 6**（新設。既存の 2/3/4/5 と重ねない）
- section レベルは対象外（overview が使わない。1,230 行の再計算になる）

### 2. recorded_at の規則（F5）
- `generated.at` があればそれ。無ければ**その事実の valid_from**（前単位 requirements の記述に合わせる。ingested_at は使わない）
- `FactsReport.recorded_from_valid` に件数を出し、CLI `facts` の出力に含める
- `docs/functional-design.md` の Fact エンティティに規則を明文化（現行「generated.at 由来」だけの記述を直す）

### 3. Q12 の定義（F4）
- `0011_view_verified.sql`: `v_verified`＝`verified_at IS NOT NULL` の件数（bundle 別）
- `VIEWS` に追加。`guess_view`: 「未確認／unverified」→ `v_unverified`、「確認済／verified」→ `v_verified`（**否定形を先に判定**。`unverified` は `verified` を部分文字列に含む）
- `docs/questions.md` Q12 の期待を `v_verified`（bundle='references'）に。実データで `bench --kind count` を再実行し `docs/bench-results.md` に転記

### 4. ゲートの固定
- `scripts/gate.sh`（くろこ・CI 用。`set -euo pipefail`）と `scripts/gate.ps1`（K 用。PowerShell でそのまま動く）。内容は同じ 4 段: `ruff format --check` → `ruff check` → `mypy` → `pytest -m "db or not db" --cov-fail-under=80`
- README の再開・ゲートの記述と RESUME.md の再開手順を gate に置き換える

## 受入基準（correctness）
- [ ] `stale_summaries` は summarize 直後に空。文書の description を変えて再取り込み（summarize はしない）した後、その document と bundle を `changed` で返す。再 summarize で空に戻る
- [ ] 同じ状態で `overview.answer()` の warnings に「要約が古い」が出る。`dbr summarize --check` は陳腐化なしで exit 0・ありで exit 6
- [ ] generated 無しの文書の dated_text 事実は `recorded_at == valid_from`。`recorded_from_valid` がその件数に一致
- [ ] `v_verified` が verified 付き文書を数える。`guess_view("確認済みは何件")=="v_verified"`、`guess_view("未確認は何件")=="v_unverified"`、`guess_view("unverified")=="v_unverified"`
- [ ] 実データで `bench --kind count` が 4 問 `stable`（Q12 のビューが `v_verified`）
- [ ] `bash scripts/gate.sh` と `pwsh -File scripts/gate.ps1` がどちらも exit 0。ruff / mypy / pytest PASS・カバレッジ 80% 以上

## スコープ外
- section レベルの陳腐化検知・陳腐化した要約の自動再生成（`--check` で見せるまで）
- ④ の LLM 要約比較（K 採点待ち）・`valid_to` の自動推定・検索側の残り

## 識別子契約
- 前単位 `.steering/20260929-asof-overview/requirements.md` の契約を継承
- 追加: `v_verified` は `VIEWS` の固定キー（ユーザー入力を SQL に連結しない）。`--check` の出力は `level:target_key` だけで、要約本文・文書本文は出さない（個人データを CLI に出さない）
