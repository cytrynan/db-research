# タスクリスト

tracking: #39

## 🚨 タスク完全完了の原則
- `- [ ]` 未着手 / `- [~]` 着手中 / `- [x]` 完了。`[x]` は完了だけ
- 各タスク行末の issue 番号が対応表。状態を変えたらその場で issue も更新
- 全タスクを `[x]` に。スキップは技術的理由のみ・行に明記

---

## フェーズ1: ローカル LLM と根拠つき生成

- [x] `shared/llm/`（Protocol・local Qwen2.5-1.5B-Instruct・fake・get_llm）・`overview.evidence_text` / `narrate` / `unsupported_mentions`・ユニット（手計算）＋統合（fake） (#40)

## フェーズ2: bench・CLI と実測

- [~] `bench --kind overview --llm`（answers に LLM 列・JSON に reproducible / seconds / unsupported）・`ask --llm`・統合テスト（fake）・実データで Q19・Q20 を 2 回生成 → `overview-answers.md` (#41)

## フェーズ3: 記録

- [ ] `docs/bench-results.md` v9 節・`docs/decisions.md` D-15・functional-design F6・RESUME.md・振り返り・受入検証（Codex 優先）・issue クローズ (#42)

---

## 実装後の振り返り

（完了後に記入）
