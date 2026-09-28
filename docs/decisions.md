---
type: Decision Record
description: 本リポで決まったことの台帳（新しい順・1決定=1行）。経緯は各 ideas/ メモと会話ログ、判断の根拠は「理由」列
generated: { by: kuroko/claude-fable-5-1, at: 2026-09-29T05:00:00+09:00 }
verified: { by: human:K, at: 2026-09-29 }
status: stable
---

# 決定台帳

> 決定は追記のみ。覆したときは行を消さず **status: 撤回** にして、新しい行を上に足す。

## 2026-09-29（キックオフ）

| # | 決定 | 理由 | 状態 |
|---|---|---|---|
| D-10 | **有効期間を OKF とは別に持たせる**。記録側は独自キー `valid: { from, to }`、DB 側は有効時間（`valid_from`/`valid_to`）＋記録時間（`recorded_at`）の2本（バイテンポラル）。旧事実は消さず `valid_to` を閉じる | OKF の `generated.at`/`verified.at` は記録時間のみで、「その時点ではどうだったか」に答えられない。OKF は未知キーを拒否しないので規約内 | 有効 |
| D-9 | **OKF フォルダが正本、DB は捨てて作り直せる派生の索引**。フロントマターは `jsonb` 丸ごと保存＋よく使うキーだけ列化 | OKF の設計思想（`cat` で読める・git で差分）を壊さない。スキーマを何度変えても安全 | 有効 |
| D-8 | 研究の題材データは、まず個人データを含まない OKF 群 `C:\Users\meer0\.agents\knowledge\` から始める | 実物の OKF データで、外部への持ち出し制約に触れない | 有効 |
| D-7 | **研究テーマ＝「質問の型（探し物／数える／時点／全体）で振り分ける検索基盤」を PostgreSQL 上に作る**。RAG 単体の研究ではない | RAG は上位N件を拾う構造のため、数える・時点・全体の質問に構造的に答えられない（動画「RAGのその先」。数値は Anthropic の Contextual Retrieval 記事で裏取り済み） | 有効 |
| D-6 | 最初の一歩は **K が実際に出しそうな質問を20問集めて4型に振り分ける** | 力を入れる型をデータで決める（思い込みで「探し物」に偏らせない） | 有効 |
| D-5 | **K の個人データは手元の PostgreSQL（Docker）のみ。Supabase を含む外部ホスティングには一切載せない** | `~/.claude/CLAUDE.md` §0 の境界と同じ | 有効 |
| D-4 | **Supabase は「将来、会社で使えたらいい」程度の参考枠。研究の制約にしない**。機能差が無いときだけ Supabase 対応の拡張・設定を優先 | 個人データを載せない以上、互換性を強制する理由が無い。会社向け転用の可能性だけ残す | 有効 |
| D-4a | ~~研究中も「Supabase で動く範囲」に限る（バージョン・拡張・設定値）~~ | D-4/D-5 により不要になった | **撤回**（同日） |
| D-3 | スキーマ変更は SQL マイグレーションファイルで管理（管理画面で直接いじらない） | どの PostgreSQL でも同じ DB を作り直せる。移行時は同じファイルを流すだけ | 有効 |
| D-2 | 技術スタック＝Python 3.12＋uv／ruff／mypy strict／pytest。DB＝PostgreSQL＋pgvector（Docker） | テンプレ標準の Python スタック。DB は D-5 の帰結 | 有効 |
| D-1 | リポは `claude-code-template` から作成、`cytrynan/db-research`（private）。名前は `db-research` のまま | `~/.claude/CLAUDE.md` §6 の既定。実用が視野に入っても「研究」の名で意味が通る | 有効 |

## 未決（次に決めること）
- `/init-project` の実行（プロジェクト説明文の確定）→ `/setup-project`（PRD）
- 質問20問の収集（D-6）
- Attested Computation（OKF v0.2）を「数値の定義を1枚」として採用するか（再検討条件に該当）
- 全文検索の方式（PostgreSQL 標準の `tsvector` か、拡張か）＝日本語の分かち書きをどうするか

## 参照
- 方向づけメモ: [ideas/20260929-research-direction.md](ideas/20260929-research-direction.md)
- 一次資料: Anthropic「Introducing Contextual Retrieval」 https://www.anthropic.com/news/contextual-retrieval
- 二次資料: 海外Yパパラジオ「RAGのその先」（2026-09-02）
- Supabase 公式（制約の確認に使用）: roles-superuser / custom-postgres-extensions / free-project-pausing / pricing / migrating-to-supabase/postgres
