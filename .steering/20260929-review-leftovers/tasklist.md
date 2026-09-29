# タスクリスト

tracking: #30

## 🚨 タスク完全完了の原則
- `- [ ]` 未着手 / `- [~]` 着手中 / `- [x]` 完了。`[x]` は完了だけ
- 各タスク行末の issue 番号が対応表。状態を変えたらその場で issue も更新
- 全タスクを `[x]` に。スキップは技術的理由のみ・行に明記

---

## フェーズ1: 要約の陳腐化検知（F6）

- [x] `summarize.py` のハッシュ計算を関数化・`stale_summaries`・`overview.answer` の WARN・`dbr summarize --check`（exit 6）・ユニット＋統合テスト（変更→検知→再要約で解消） (#31)

## フェーズ2: recorded_at の規則（F5）

- [x] `facts.py` の fallback を valid_from に・`recorded_from_valid`・fixture `same-day.md`（generated 無し・verified 有り）・ユニット＋統合・functional-design.md の Fact 規則 (#32)

## フェーズ3: Q12 の定義（F4）

- [x] `0011_view_verified.sql`・`VIEWS`/`guess_view`・ユニットテスト・`questions.md` Q12・実データで migrate → `bench --kind count --label v7` → bench-results 転記 (#33)

## フェーズ4: ゲートの固定と記録

- [~] `scripts/gate.sh`・`scripts/gate.ps1`・README/RESUME の手順差し替え・両方の実行証拠・振り返り・受入検証（Codex）・issue クローズ (#34)

---

## 実装後の振り返り

（完了後に記入）
