# docs 更新ログ

> ドキュメント記録規約（OKF準拠。正本: `development-guidelines` スキルの `guides/recording.md`）。
> `docs/` 配下のドキュメントを作成・更新・廃止したら、同じ作業内でここに1行追記する。新しい順。
> 書式: `* **Creation|Update|Deprecation**: [タイトル](ファイル名.md) — 何をどう変えたか (アクター)`

<!-- /setup-project でドキュメントを作成したら、最初のエントリをここに追記してください。例:

## 2026-09-29

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

## 2026-08-01
* **Creation**: [プロダクト要求定義書](product-requirements.md) — 初版作成・ユーザー承認済み (claude/claude-sonnet-5)
-->
