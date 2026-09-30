# 要求内容（brief）

> 厚さ: **T2**（永続スキーマ・課金・外部 API に触れない）。設計は本書に内包する。

## 目的（brief）
④ 全体の証拠（bundle 要約＋上位 5 文書）は全 bundle 横断で選ぶため、「生活の効率化」に dev/ の技術文書が 3 本入り、「健康」で health.md が 500 断片の集約から落ちた（v9c）。① 探し物でも、期待がすべて references の 10 問で上位 5 の 21/50 枠を dev/memory が占める（v8）。**質問の語から対象 bundle を推定し、証拠を絞る（filter）か優先する（boost）方式**を、① の 10 問（順位）と ④ の 2 問（証拠に期待文書が入るか）で測り、既定を数値で決める（D-16）。

## やること
1. **`features/scope`**: `guess_bundles(question) -> Scope(bundles: list[str] | None, reason: str)`。閉じた語彙（生活・体・お金・家・仕事の語 → `references`／実装・設定・ツールチェーンの語 → `dev`／方針・案件・記憶の語 → `memory`）。複数に当たれば和集合、どれにも当たらなければ None（＝全 bundle）。質問文に bundle 名が明示されていれば `overview.pick_bundles` が優先。固有名詞（商品名・人名）は入れない。「ツール」のように両義の語は入れない
2. **適用の 2 方式**（`scope` 引数・固定語彙 `SCOPES = ("none", "filter", "boost")`）:
   - `filter`: `search(..., bundles=推定)`（推定が None なら全 bundle）
   - `boost`: 全 bundle で検索・集約したあと、推定 bundle の文書スコアを `(1 + w)` 倍して並べ直す（同点は元の順位。`w` 既定は測定で決める）
   - `none`: 現行
3. **① への配線**: `ask --scope`（既定は D-16 で決める）、`run_find(..., scope=, boost_w=)`。**④ への配線**: `overview.answer(..., scope=)` は推定 bundle で上位文書を選び、bundle 要約も推定 bundle のものだけを証拠にする（他 bundle は「対象外」と warnings に 1 行）
4. **bench `--kind scope`**: ① の find 10 問 × scope ∈ {none, filter, boost w=0.5, boost w=1.0, boost w=2.0}（mode=embed_ctx・agg=rrf_top3 固定・検索は 1 回で boost は後処理）→ recall@5 / MRR / 質問別順位。④ の overview 2 問 × 同じ scope → 上位 5 文書のうち期待文書の数（`questions.md` の期待欄のパス）と bundle 内訳。JSON に推定 bundle と理由も記録
5. **`questions.md` Q19 の期待欄**を機械可読に（既存の文言「profile / home / money / tools」をバッククォートのパスに書き直す。**測定前に**行い、備考にその旨）
6. 実データで `bench --kind scope --label v10` → `docs/bench-results.md` v10 節・`docs/decisions.md` D-16（既定 scope と w）。既定が変わったら `bench --kind overview --llm Qwen… --label v10` で `overview-answers.md` を作り直す（K の再採点は任意）

## 受入基準（correctness）
- [ ] `guess_bundles` が手計算どおり（生活語 → references／実装語 → dev／両方 → 和集合／該当なし → None／bundle 名の明示は pick_bundles が優先）。語彙は固定リストで、質問文を SQL に連結しない
- [ ] `boost` は決定的で、推定 bundle 外の文書の相対順位を変えない（w=0 なら恒等・同点は元の順位）。`filter` は search の `bundles` にそのまま渡る（統合: fake で bundle 外の文書が返らない）
- [ ] `bench --kind scope` の JSON にセル（find 5 通り・overview 5 通り）と質問別の順位／期待文書の数があり、`--kind find --scope` と `ask --scope` が exit 0（統合: fake）
- [ ] 実データ v10 の数値が bench-results v10 節・D-16 と一致し、既定の scope が数値から導ける。**既定で実際に走る計算経路（scope・w・断片数・集約）が測定と同一**（A6-⑥）
- [ ] `bash scripts/gate.sh` exit 0

## 非スコープ
- 埋め込みや LLM で bundle を推定すること（語彙ルールで始める。外れ方を見てから）
- 質問セットの追加（K 判断待ち。dev/memory 向けの質問が無いので「技術語 → dev」の効き目は今回測れない＝D-16 に明記）
- references/INDEX.md のトリガー語を取り込んで語彙にすること（次の候補。今回は閉じた語彙）

## 識別子契約
- 前単位の契約を継承。追加: `scope` と bundle 名は固定語彙（`SCOPES`・`BUNDLES`）。推定結果はログと JSON に bundle 名だけを書く（質問文の本文は bench の JSON に入れない＝既存どおり）
