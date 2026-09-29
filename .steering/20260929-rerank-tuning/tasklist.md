# タスクリスト

tracking: #16

## 🚨 タスク完全完了の原則
- `- [ ]` 未着手 / `- [~]` 着手中 / `- [x]` 完了。`[x]` は完了だけ
- 各タスク行末の issue 番号が対応表。状態を変えたらその場で issue も更新
- 全タスクを `[x]` に。スキップは技術的理由のみ・行に明記

---

## フェーズ1: 重み付き RRF・候補数・ラベル

- [~] 重み付き RRF（等重みで従来と同値）・`search(candidates=)`・`bench --label`（識別子契約）＋ユニットテスト (#17)

## フェーズ2: 並べ直し

- [ ] 並べ直し: `shared/rerank`（Protocol・ローカル cross-encoder・Fake）・`hybrid_ctx_rerank`・`ask --mode hybrid_ctx_rerank`＋ユニット／統合（Fake）／slow（実モデル） (#18)

## フェーズ3: HNSW 強制と測定

- [ ] `vector_search(force_index=)`（`SET LOCAL enable_seqscan=off`）・`bench --kind hnsw`（厳密比 recall@20・中央値レイテンシ・EXPLAIN 記録）＋統合テスト（Index Scan の文字列） (#19)

## フェーズ4: sweep

- [ ] `bench --kind sweep`（hybrid_ctx: w_fts 4 値 × candidates 3 値＝12 セル）＋ユニット（グリッド生成・JSON 形） (#20)

## フェーズ5: 実データ測定・Sudachi 警告・品質ゲート

- [ ] 実データで find v5（rerank 含む）2 回・sweep・hnsw を実行し JSON を保存、Sudachi DeprecationWarning 解消、ruff/mypy/pytest（unit・db・slow） (#21)

## フェーズ6: 記録と受入検証

- [ ] `docs/bench-results.md` v5 節（JSON を読み直して転記）・振り返り・別コンテキストの受入検証 (#22)

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
