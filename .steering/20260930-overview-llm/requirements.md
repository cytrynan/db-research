# 要求内容（brief）

> 厚さ: **T2**（永続スキーマ・課金・外部 API に触れない。ローカル LLM の重みを HF Hub から取得するだけで、K のデータは外に出ない）。設計は本書に内包する。

## 目的（brief）
④ 全体の回答は抽出型（bundle 要約の件数行＋質問に近い上位 5 文書の description・見出し）で、「傾向」「手厚い／薄い」の判断が入っていない（`docs/overview-answers.md`・K 採点待ち）。**同じ根拠（要約階層から取った証拠）だけをローカル LLM に渡して日本語の短い回答を書かせ、抽出型と並べて K が採点できる形**にする。あわせて LLM 回答の**根拠外の言及（ファイル名・数値）を機械検出**し、再現性（貪欲デコード 2 回一致）と生成時間を記録する。外部 API は使わない（D-13 と同じ境界。`references`/`memory` の本文を外へ送る判断は K 承認が要る＝未決のまま）。

## やること
1. **ローカル LLM の入口** `src/dbr/shared/llm/`: `Protocol LLM(name, generate(system, user, max_new_tokens) -> str)`。実装は `local.py`（transformers・CPU・`Qwen/Qwen2.5-1.5B-Instruct` 既定・貪欲デコード＝決定的・`torch.no_grad`）と `fake.py`（決定的ダミー: 証拠の先頭行を切り貼りして返す）。`get_llm(name)` は embed と同じ形
2. **根拠つき生成** `features/overview`: `evidence_text(OverviewAnswer) -> str`（bundle 要約の先頭行＋document 要約をそのまま列挙。本文の断片は含めない＝抽出型と同じ入力）、`narrate(question, evidence, llm) -> Narrative(text, unsupported, seconds)`。プロンプトは「一覧だけを根拠に・ファイル名を挙げて・無いものは無いと言う・日本語 5 文以内」
3. **根拠外の言及の検出** `unsupported_mentions(text, evidence) -> list[str]`: 回答中の `xxx.md` と 2 桁以上の数値のうち、証拠テキストに現れないもの（機械検出＝ハルシネーションの下界）
4. **bench overview の拡張**: `--llm <name|none>`（既定 none）。`overview-answers.md` に「LLM 回答」「根拠外の言及」列を足し、K 採点欄は抽出型・LLM の 2 列に。JSON に model・seconds・unsupported・2 回生成の一致（`reproducible`）を記録
5. `ask` の overview 分岐に `--llm`（既定 none。指定時は narrative も表示）
6. 実データで Q19・Q20 を生成（2 回）→ `docs/overview-answers.md` 更新・`docs/bench-results.md` v9 節・`docs/decisions.md` D-15（ローカル LLM を ④ の比較対象に採用・モデル名・K 採点は保留のまま）

## 受入基準（correctness）
- [ ] `unsupported_mentions` が手計算どおり（証拠に無い `foo.md` と数値 `123` を検出、証拠にある `bar.md`・`53` は検出しない、年月日 `2026-09-29` は 1 つの数値として扱う）
- [ ] fake LLM で `narrate` が決定的（同入力同出力）で、証拠に無いファイル名を含めない
- [ ] `bench --kind overview --llm fake` が answers Markdown に LLM 列を出し、JSON に `reproducible: true` と `unsupported` を持つ。`--llm none` は従来どおり（LLM 列は「—」）
- [ ] 実データ（Qwen2.5-1.5B-Instruct・CPU）で Q19・Q20 の 2 回生成が一致し、JSON の seconds・unsupported が `docs/bench-results.md` v9 節と一致する。unsupported が 0 でない場合はその内容（ファイル名・数値のみ）を v9 に転記する
- [ ] `bash scripts/gate.sh` が exit 0

## 非スコープ
- 外部 LLM API（Claude／OpenAI 等）への本文送信＝K 承認が要る。今回はローカルのみ
- 要約階層そのものを LLM で作り直すこと（抽出型 summary 表はそのまま。LLM は回答層だけ）
- K 採点の代行（採点は K。くろこは採点欄を用意するまで）
- モデルの比較（1.5B のみ。速度が実用外なら 0.5B に落とし、その旨を記録）

## 識別子契約
- 前単位の契約を継承。追加: `--llm` の値は固定語彙（`none` / `fake` / モデル名）。LLM への入力は要約テキストのみ（chunk.body を渡さない）。LLM 回答・証拠は `overview-answers.md`（K 採点用・リポ内）にだけ書き、bench JSON には本文を入れない（件数・秒・unsupported の語だけ）
