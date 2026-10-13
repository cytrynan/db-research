# docs 更新ログ

> ドキュメント記録規約（OKF準拠。正本: `development-guidelines` スキルの `guides/recording.md`）。
> `docs/` 配下のドキュメントを作成・更新・廃止したら、同じ作業内でここに1行追記する。新しい順。
> 書式: `* **Creation|Update|Deprecation**: [タイトル](ファイル名.md) — 何をどう変えたか (アクター)`

<!-- /setup-project でドキュメントを作成したら、最初のエントリをここに追記してください。例:

## 2026-08-01
* **Creation**: [プロダクト要求定義書](product-requirements.md) — 初版作成・ユーザー承認済み (claude/claude-sonnet-5)
-->

## 2026-10-13
* **Update**: [決定台帳](decisions.md) — D-21（DB の自動復旧: docker restart/unpause/start・手動停止は触らない・10 分に 1 回）を追加 (kuroko/claude-fable-5-1)
* **Update**: [機能設計書](functional-design.md)・[アーキテクチャ設計書](architecture.md) — Serve 節と「状態の置き場」に自動復旧（recovery.py）の動作・成功判定・無効化を追記 (kuroko/claude-fable-5-1)
* **Update**: [決定台帳](decisions.md) — D-20（利用ログ usage.jsonl に質問文と上位ヒット・DB-UNREACHABLE.flag・dbr_pg の restart）を追加 (kuroko/claude-fable-5-1)
* **Update**: [機能設計書](functional-design.md) — Serve 節: ログを運用ログ serve.log と利用ログ usage.jsonl の 2 本に分け項目を定義、DB 停止の検知フラグと `/health` の 2 項目を追記 (kuroko/claude-fable-5-1)
* **Update**: [アーキテクチャ設計書](architecture.md) — 「状態の置き場」に `~/.dbr/` の 3 ファイルと `restart: unless-stopped` の限界を追記 (kuroko/claude-fable-5-1)

## 2026-10-08
* **Update**: [機能設計書](functional-design.md)・[アーキテクチャ設計書](architecture.md) — 認証情報の置き場を「環境変数のみ」から「環境変数か、リポ直下 `.env`（DSN は `--dsn` → `DBR_DSN` → `.env` の順）」に訂正（MCP が全ツール失敗した件の修正 `.steering/20261008-mcp-dsn-fallback` に追随） (kuroko/claude-opus-5-5)

## 2026-10-06
* **Update**: [アーキテクチャ設計書](architecture.md)・[決定台帳](decisions.md) — 応答時間の実測を受入検証の回収後の値に追随（count 0.46〜0.51 秒 × 5・同期直後の数回は 2 秒台で原因未特定）。評価係の指摘①「回収後に旧値のまま commit した」の回収 (kuroko/claude-fable-5-1)
* **Update**: [測定結果](bench-results.md) — v11c: commit `ede32a0`（dirty なし）で find / count / asof を再測定し v11b と一致（「-dirty の JSON は確定版で測り直す」の実施） (kuroko/claude-fable-5-1)
* **Update**: [機能設計書](functional-design.md) — Serve 節のクライアントを実装に合わせて訂正（health の待ちは 2 秒・閉じたポートでは 2 秒かかる・`ensure_daemon` は子が先に終わったら待たない・`/sync` は走行中の同期を待つ＝409 を返さない。受入検証 2 巡目の指摘 B） (kuroko/claude-fable-5-1)
* **Update**: [測定結果](bench-results.md) — v11b（受入検証の回収後・276 文書・2,918 断片で既定経路を再測定: find 1.00/1.00/0.883・順位は v11 と全問一致・count 4/4・asof 同一）と、応答時間の表に「修正後（CLI の起動を軽くした）」列を追加（count 0.46〜0.51 秒 × 5・find/asof/overview 0.56〜0.71 秒・同期直後の 7 回は 2 秒台） (kuroko/claude-fable-5-1)
* **Update**: [決定台帳](decisions.md) — D-17（不明 → 探し物のフォールバック）・D-18（常駐と HF オフライン既定・応答時間の実測）・D-19（`dbr sync` への一本化・陳腐化による再構築）を追加 (kuroko/claude-fable-5-1)
* **Update**: [機能設計書](functional-design.md) — Classifier 節を D-17 の形に書き換え。Ask（3 入口の共通部）・Serve（F8）・Sync（F9）・MCP（F10）の節と構成図の常駐経路を追加 (kuroko/claude-fable-5-1)
* **Update**: [アーキテクチャ設計書](architecture.md) — 対応表に ask / serve / sync / mcp_server を追加、常駐プロセスと状態の置き場・外部通信なしの節、応答時間と sync の実測 (kuroko/claude-fable-5-1)
* **Update**: [プロダクト要求定義書](product-requirements.md) — F2 の受け入れ条件を「判定器は不明を返す・ask は探し物として検索し推定を明示」に（D-17） (kuroko/claude-fable-5-1)
* **Update**: [測定結果](bench-results.md) — v11: 取り込みを 7 bundle（269 文書・2,834 断片）に拡大した後の既定経路の再測定（find 1.00/0.883・count 4/4・asof 4/4＝v10 と同値）と応答時間の before/after (kuroko/claude-fable-5-1)

## 2026-10-03

* **Update**: [検索品質の測定結果](bench-results.md) — v10 に「受入検証で分かった限界と訂正」節（in-sample・外れた時の被害は未測定・部分一致の誤推定・boost の実装修正・bench の検索回数）。発見 1 の裏づけの無い原因記述を訂正、格子の中の最小と明記。修正後の再測定 v10b（git f9eff51・clean）が v10 と全セル一致 (kuroko/claude-fable-5-1)
* **Update**: [決定台帳](decisions.md) — D-16 の理由欄に受入検証の追記（in-sample・格子・外れた時の被害は未測定） (kuroko/claude-fable-5-1)
* **Update**: [機能設計書](functional-design.md) — scope の boost を「2 列の安定マージ・負のスコアは割る」に、overview の warnings と scope 検査を追記 (kuroko/claude-fable-5-1)

## 2026-09-30

* **Update**: [overview の回答](overview-answers.md)・[検索品質の測定結果](bench-results.md) — 既定 boost で ④ を再生成（v10）。Q19 の LLM 回答で根拠外のファイル名 2 件を初検出（v10 節に記録） (kuroko/claude-fable-5-1)
* **Update**: [検索品質の測定結果](bench-results.md) — v10 節（bundle の絞り込み: ① none 0.90/0.861 → filter・boost 1.00/0.883、④ の期待文書 Q19 1→2・Q20 0→1）と総括の ①④ 行 (kuroko/claude-fable-5-1)
* **Update**: [決定台帳](decisions.md) — D-16: 既定 scope=boost w=1.0（暫定・技術語→dev の枝は未測定） (kuroko/claude-fable-5-1)
* **Update**: [機能設計書](functional-design.md) — Search(F3) に scope（推定・boost/filter）、Overview に証拠の bundle 絞り込み (kuroko/claude-fable-5-1)
* **Update**: [質問セット（20問）](questions.md) — Q19 の期待欄をパスに書き直し（文言は同じ・scope bench の機械照合のため・測定前） (kuroko/claude-fable-5-1)
* **Update**: [overview の回答](overview-answers.md)・[検索品質の測定結果](bench-results.md)・[決定台帳](decisions.md) — K 採点（抽出型 5/5・LLM 4/3）を記入し、④ は抽出型で足りる・LLM 層は保留と結論。overview-answers に verified: human:K (kuroko/claude-fable-5-1)
* **Update**: [検索品質の測定結果](bench-results.md)・[決定台帳](decisions.md)・[overview の回答](overview-answers.md) — 受入検証の回収: v9c（検出器改訂・証拠を ① と同じ 500 断片で選ぶ）の行と Q20 の証拠の変化、v1 プロンプト原文、秒の訂正（37〜198） (kuroko/claude-fable-5-1)
* **Update**: [検索品質の測定結果](bench-results.md) — v9 節（④ ローカル LLM の回答層: プロンプト v1/v2 の秒・文字数・根拠外 0・2 回一致、判断の質と証拠の偏りの観察、D-15） (kuroko/claude-fable-5-1)
* **Update**: [決定台帳](decisions.md) — D-15: ④ の回答層にローカル LLM を配線・既定は抽出型のまま・証拠の切り方を先に直す (kuroko/claude-fable-5-1)
* **Update**: [overview の回答（K 採点用）](overview-answers.md) — 抽出型／LLM（Qwen2.5-1.5B・プロンプト v2）の 2 列・根拠外の言及列・K 採点欄 2 列に更新（process:dbr-bench が生成） (kuroko/claude-fable-5-1)
* **Update**: [機能設計書](functional-design.md) — Overview(F6) に回答層（ローカル LLM・同じ証拠のみ・根拠外の言及検出・2 回一致）と上位文書の集約 rrf_top3 を追記 (kuroko/claude-fable-5-1)

## 2026-09-29

* **Update**: [検索品質の測定結果](bench-results.md)・[決定台帳](decisions.md) — 受入検証 R4 の訂正: 「8 問が 1 位」→ 7 問、並べ直しの窓幅の感度を集約 max でなく rrf_top3 の値で記述、`ask` 既定は bench と同じ 500 断片で集約する旨を追記 (kuroko/claude-fable-5-1)
* **Update**: [検索品質の測定結果](bench-results.md) — v8 節（embed_ctx_rerank・文書集約 3 種・rerank_top 10〜150 の格子。並べ直し器は Q02/Q06 を落とす／rrf_top3 は損なしで MRR 0.807→0.861／rerank_top 20 は 1 問依存で脆い）と総括の ① 行を更新 (kuroko/claude-fable-5-1)
* **Update**: [決定台帳](decisions.md) — D-14: ① 探し物の既定＝embed_ctx＋rrf_top3（暫定・N=10）。並べ直しは既定にしない (kuroko/claude-fable-5-1)
* **Update**: [機能設計書](functional-design.md) — Search(F3) に embed_ctx_rerank・文書集約 Agg・`ask` の既定（D-14）を追記 (kuroko/claude-fable-5-1)
* **Update**: [検索品質の測定結果](bench-results.md) — ② v7 節に判定器の修正（count bench に正解ビュー照合 view_ok／all_views_ok・再測定 4/4 一致）を追記 (kuroko/claude-fable-5-1)
* **Update**: [機能設計書](functional-design.md) — 受入検証 R6: Fact 制約「旧行の valid_to を閉じて新行を挿入・削除しない」を実装どおり（bundle 単位の全削除→再挿入）に訂正、Temporal 節に dated_text、Overview に陳腐化検知の範囲 (kuroko/claude-fable-5-1)
* **Update**: [機能設計書](functional-design.md) — `v_verified` は deprecated も数える（`v_unverified` とは補集合でない）ことを明記（受入検証の境界ケースより） (kuroko/claude-fable-5-1)
* **Update**: [検索品質の測定結果](bench-results.md) — ② v7 節（Q12 を `v_verified` で再測定・4/4 stable）、recorded_at 規則と source_hash 陳腐化 WARN の実データ確認を追記 (kuroko/claude-fable-5-1)
* **Update**: [機能設計書](functional-design.md) — Fact の recorded_at 規則（generated.at、無ければ valid_from）と valid_source に dated_text、識別子を実装どおり（md5(value)・0010）に、Counter に `v_verified`（0011）、Overview に source_hash の陳腐化 WARN と `--check` を追記 (kuroko/claude-fable-5-1)
* **Update**: [質問セット（20問）](questions.md) — Q12 の期待を `v_unverified` の補集合から `v_verified` へ（問いの定義そのものをビューに固定） (kuroko/claude-fable-5-1)
* **Update**: [検索品質の測定結果](bench-results.md) — v7 節（受入検証 D1〜D5 の回収後に asof を再測定 4/4・2 回一致・dated_text 293→295）と、v6「発見 2（INDEX と work.md の日付不整合）」の**取り下げ**（timestamptz の UTC 表示を日付と誤読） (kuroko/claude-fable-5-1)
* **Update**: [質問セット（20問）](questions.md) — Q16 の正解日付から `2026-08-10` を**撤回**（work.md に記載なし・受入検証で反証。誤読の経緯を備考に明記）、「より前／以前」の解釈を備考に追記 (kuroko/claude-fable-5-1)
* **Update**: [技術仕様書](architecture.md) — ③ の索引を実装どおり（`fact_uniq` に md5(value)・0010）に訂正 (kuroko/claude-fable-5-1)
* **Update**: [検索品質の測定結果](bench-results.md) — v6 節（②count 4/4 stable・③asof 4/4＝断片→文書→全体の 2 段で到達、経緯 a〜e と正解欄の追加理由・INDEX と work.md の日付不整合の発見・④overview は K 採点待ち・20 問の総括） (kuroko/claude-fable-5-1)
* **Update**: [質問セット（20問）](questions.md) — Q15 の正解ファイルに `references/fuyou.md` を追加（同じ「2026-08-11 分離」の記録が fuyou.md 冒頭にもある。断片スコープの bench で先に返ったため） (kuroko/claude-fable-5-1)
* **Update**: [質問セット（20問）](questions.md) — Q16 の正解日付に `2026-08-10` を追加（work.md 本文の日付。INDEX.md の 2026-08-11 と食い違う＝記録の不整合を発見） (kuroko/claude-fable-5-1)
* **Update**: [質問セット（20問）](questions.md) — Q18 の正解ファイルに `memory/sales-routine-two-mechanisms.md` を追加（初回 bench でこのファイルの 2026-08-24 の事実が返り、内容が正しかった＝期待欄の網羅漏れ。変更理由を備考に明記） (kuroko/claude-fable-5-1)
* **Update**: [質問セット（20問）](questions.md) — asof 4 問（Q15〜Q18）の期待欄に正解日付をバッククォートで追記（bench --kind asof の採点用）。Q18 は memory バンドル前提 (kuroko/claude-fable-5-1)
* **Update**: [検索品質の測定結果](bench-results.md) — 受入検証の指摘を反映: sweep の説明文を訂正（「単調に下がる」は誤り・(0.5, 20) が最良と同点の 4 セル）、索引使用フラグの判定を索引名に変えた旨を注記 (kuroko/claude-fable-5-1)
* **Update**: [検索品質の測定結果](bench-results.md) — v5 に embed_ctx（文脈付き埋め込み単体）を追加: recall@5 0.90 / MRR 0.811 で 6 方式中最良。並べ直し（0.751）は hybrid_ctx を改善するが単体に届かない (kuroko/claude-fable-5-1)
* **Update**: [検索品質の測定結果](bench-results.md) — v5 節を追加（並べ直し recall@5 0.90 / MRR 0.751、RRF 掃引で fts 重み 0＝文脈付き埋め込み単体が MRR 0.811 で最良、HNSW ef_search 40/100/250 の厳密比 0.93/0.985/1.0・速度差なし） (kuroko/claude-fable-5-1)
* **Update**: [検索品質の測定結果](bench-results.md) — 確定値を v4（断片 500・hybrid 各系 500 件、git fd55c29）に更新。hybrid 0.70→0.80 recall@5・MRR 0.552、hybrid_ctx MRR 0.676。v3 の JSON を git から復元して保存 (kuroko/claude-fable-5-1)
* **Update**: [検索品質の測定結果](bench-results.md) — 受入検証の指摘を反映（v2 の JSON が残っていない旨を注記）。bench の断片打ち切り（100→500）は確定値に影響なしを実測済み (kuroko/claude-fable-5-1)
* **Update**: [開発ガイドライン](development-guidelines.md) — 統合テストは別 DB `dbr_test`（`DBR_TEST_DSN`）を使う旨を追記（実データ DB を TRUNCATE しないため） (kuroko/claude-fable-5-1)
* **Creation**: [検索品質の測定結果](bench-results.md) — find 10 問×4方式（確定 v3: fts 0.40 / embed 0.80 / hybrid 0.70 / hybrid_ctx 0.80 recall@5・MRR 最良 hybrid_ctx 0.675）と v1→v3 の方法論欠陥（AND・同点揺れ・HNSW 未使用） (kuroko/claude-fable-5-1)
* **Update**: [質問セット（20問）](questions.md) — Q10 の期待欄で正解に含めない tax/ パスをバッククォートから外す（bench のパーサは `` ` `` 内だけを正解と読む） (kuroko/claude-fable-5-1)
* **Update**: [決定台帳](decisions.md) — D-13（埋め込みはローカルモデルのみで開始・K承認）を追加、未決を更新 (kuroko/claude-fable-5-1)
* **Update**: [開発ガイドライン](development-guidelines.md) — DSN 例を 127.0.0.1 に変更（localhost は Windows で ::1 先行→Docker Desktop に届かず 130 秒待つ実測）。README に使い方（migrate/ingest/count）を追記 (kuroko/claude-fable-5-1)
* **Creation**: [質問セット（20問）](questions.md) — references/INDEX.md のトリガー語・横断トピックから作成（find10/count4/asof4/overview2）。正解は所在のみ・値は書かない (kuroko/claude-fable-5-1)
* **Creation**: [用語集](glossary.md) — 初版（4型・recall@k/MRR/RRF・バイテンポラル・OKF/くろこ拡張・pgvector/HNSW・例外クラス） (kuroko/claude-fable-5-1)
* **Creation**: [開発ガイドライン](development-guidelines.md) — 初版（データ境界3遮断＝故障注入必須・SQL 既存マイグレーション編集禁止・pytest マーカー db/e2e/slow・レビュー必須6項目・セットアップ手順） (kuroko/claude-fable-5-1)
* **Creation**: [リポジトリ構造定義書](repository-structure.md) — 初版（src/dbr/features/<7機能>/ ＋ shared/db・shared/embed、migrations/ 番号順、bench/results は commit、依存の向き） (kuroko/claude-fable-5-1)
* **Creation**: [技術仕様書](architecture.md) — 初版（PostgreSQL16+pgvector Docker・psycopg3・typer・SudachiPy→tsvector 採用・RRF・HNSW ef_search 40/100/250 測定・ローカル埋め込みを個人バンドルの唯一経路・未決3件） (kuroko/claude-fable-5-1)
* **Creation**: [機能設計書](functional-design.md) — 初版（データモデル: document/chunk/chunk_embedding/fact/summary/question・コンポーネント7つ・RRF 統合・ループバック強制・エラー表・テスト戦略）。PRD 承認後の自動生成 (kuroko/claude-fable-5-1)
* **Verify**: [プロダクト要求定義書](product-requirements.md) — K承認（修正2点: 検索品質を最優先KPI化／OKF素とくろこ拡張の両取り込み＋比較）を反映し verified 付与・status: stable (human:K / kuroko/claude-fable-5-1)
* **Update**: [決定台帳](decisions.md) — D-11（検索品質最優先）・D-12（OKF 2形式の比較採用）を追加、未決を更新 (kuroko/claude-fable-5-1)
* **Creation**: [プロダクト要求定義書](product-requirements.md) — 初版ドラフト（F1〜F7 MVP・F8/F9 将来・KPI 型別正答率・ローカル接続強制）。K 承認待ち (kuroko/claude-fable-5-1)
* **Creation**: [決定台帳](decisions.md) — 2026-09-29 の決定 D-1〜D-10（D-4a 撤回含む）と未決事項を台帳化 (kuroko/claude-fable-5-1)
* **Creation**: [研究の方向づけ（2026-09-29）](ideas/20260929-research-direction.md) — 質問4分類・データ置き場の境界・OKF正本＋DB派生索引・有効期間の独自キー方針を下書き化 (kuroko/claude-fable-5-1)
