---
type: Glossary
description: db-research の用語集。質問の4型（探し物／数える／時点／全体）、検索指標（recall@k・MRR・RRF）、バイテンポラル（有効時間／記録時間）、OKF 関連（バンドル・フロントマター・Attested Computation）、pgvector/HNSW の用語
generated: { by: kuroko/claude-fable-5-1, at: 2026-09-29T08:50:00+09:00 }
status: draft
---

# プロジェクト用語集 (Glossary)

**更新日**: 2026-09-29

## ドメイン用語

### 質問の型（4型）
**定義**: 質問を、答え方が構造的に異なる4種に分けたもの。
| 型 | 英語（コード上の値） | 例 | 答える道具 |
|---|---|---|---|
| 探し物 | `find` | 「◯◯について書いた記録は？」 | ハイブリッド検索 |
| 数える | `count` | 「未確認の記録は何件？」 | SQL ビュー |
| 時点 | `asof` | 「去年9月の時点ではどうだった？」 | バイテンポラル表 |
| 全体 | `overview` | 「全体としてどちらに傾いている？」 | 要約階層 |
**説明**: RAG（上位N件を拾う仕組み）が構造的に答えられるのは `find` だけ、という観察が本研究の出発点。判定不能は `unknown`（`find` に倒さない）。

### 振り分け表
**定義**: K の実際の質問20問を4型にラベル付けした表（`docs/questions.md`）。型判定器の正解データであり、研究の重心を決める根拠。

### 正本（せいほん）
**定義**: 事実の唯一の出所。本研究では OKF 形式の Markdown ファイル群。DB は正本から作り直せる**派生データ**であり、正本を書き換えない。

### バンドル
**定義**: OKF の配布単位（1ディレクトリ）。くろこでは `references` / `dev` / `stock` / `tax` / `scout` / `memory` / `experiments`。`bundle` 列の値。

### くろこ拡張（OKF）
**定義**: くろこの記録規約が OKF v0.2 に足した約束。`description` 必須、`type` の閉じた語彙、memory の `metadata:` ネスト、`INDEX.md`（大文字）、独自キー `valid`。取り込み時に `format = 'kuroko'` として区別し、素の OKF（`'okf'`）と比較する（D-12）。

### 文脈付与（Contextual Retrieval）
**定義**: チャンクの先頭に「このチャンクは何のファイルのどの節の話か」を1〜2文で前置してから埋め込む手法。Anthropic の記事で検索の取りこぼしが 5.7%→3.7%（＋BM25 で 2.9%、＋並べ直しで 1.9%）と報告されている。本研究では `variant = 'ctx'`。

### 決定台帳
**定義**: `docs/decisions.md`。決定は追記のみ、撤回は行を残して状態を変える。③時点の `Fact` 抽出元の1つ。

### 常駐（じょうちゅう）
**定義**: 埋め込みモデルを 1 回だけ読んで居続けるプロセス `dbr serve`（127.0.0.1:47821・D-18）。`dbr ask` と MCP はここへ問い合わせ、居なければ自動で起こす。単発（`--no-daemon`）はモデルを毎回読む従来の経路。

### 同期（sync）
**定義**: `dbr sync`。正本フォルダの変更・新規・削除を DB に反映する差分処理（取り込み → prune → 埋め込み → fact → summary・冪等・D-19）。常駐が起動直後と 30 分ごとに実行する。

### フォールバック（型判定）
**定義**: 判定器が `unknown` を返した質問を `ask` が ① 探し物として検索すること（D-17）。回答の `reason` に「探し物として検索（推定）」、JSON に `kind_fallback: true` が付く。判定器そのものは `unknown` を返し続ける。

### MCP 入口
**定義**: `dbr mcp`。Claude Code のセッションから `ask` / `count` / `sync` / `health` を呼べる stdio の MCP サーバー。常駐へ中継するだけで、モデルは持たない。

## 検索の指標

### recall@k
**定義**: 正解が上位 k 件に含まれた質問の割合。`recall@5 = (上位5件に正解が入った質問数) / (質問数)`。

### MRR（Mean Reciprocal Rank）
**定義**: 正解が出た順位の逆数の平均。1位なら 1、2位なら 0.5。順位の良さまで見る指標。

### RRF（Reciprocal Rank Fusion）
**定義**: 複数の検索結果を順位だけで統合する方法。`score = Σ 1/(k + rank_i)`（本研究は k=60）。スコアの尺度が違う埋め込み検索と全文検索を正規化なしで混ぜられる。

### ハイブリッド検索
**定義**: 埋め込み（意味の近さ）と全文検索（語句の一致）を両方走らせて統合する検索。`Mode` の `hybrid` 系。

### 並べ直し（リランキング）
**定義**: 一次検索の上位（本研究は150件）を、より重い判定器（cross-encoder 等）で並べ直して上位20件に絞る工程。

## 時間の用語（バイテンポラル）

### 有効時間（valid time）
**定義**: 事実が**実際に正しかった期間**。`valid_from` / `valid_to`。`valid_to IS NULL` は現在も有効。

### 記録時間（transaction time）
**定義**: その事実を**記録した時刻**。`recorded_at`。OKF の `generated.at` はこちら側。

### バイテンポラル
**定義**: 有効時間と記録時間の2本を持つ設計。「去年9月時点で当時知っていた答え」と「今から見た去年9月の正しい答え」を区別できる。OKF には有効時間のキーが無いため、独自キー `valid: { from, to }` を足す（D-10）。

### inferred / explicit（`valid_source`）
**定義**: `Fact` の有効期間が `valid` キー由来（explicit）か、`generated.at` からの暫定推定（inferred）か。inferred は回答で「暫定」と明示する。

## 技術用語

### PostgreSQL
本研究の唯一の DB。Docker 上で localhost にのみ公開。バージョン 16 系。

### pgvector
PostgreSQL に `vector` 型と近傍検索を足す拡張。埋め込み列と HNSW インデックスに使う。

### HNSW / `ef_search`
近似最近傍のインデックス方式。`ef_search` は検索時に探索する候補数で、既定 40。上げると正確さが上がり遅くなる（Supabase の解説では 100 で accuracy@10 ≈ 0.98、250 で ≈ 0.99 の例）。

### tsvector / GIN
PostgreSQL 標準の全文検索用の型とインデックス。日本語は分かち書き（SudachiPy）してから `to_tsvector('simple', …)` に渡す。

### 埋め込み（embedding）
文章を数値ベクトルに変えたもの。近いベクトル＝意味が近い。ローカルモデル（sentence-transformers）と外部 API の2経路。`references` / `memory` はローカルのみ。

### 冪等（べきとう）
同じ操作を何回やっても結果が変わらないこと。`ingest` の再実行で行数が増えないことを before/after で検証する。

### ループバック
自分自身（`localhost` / `127.0.0.1` / `::1`）への接続。個人データの DB はこれ以外を拒否する。

## OKF 関連

### OKF（Open Knowledge Format）
Google Cloud が公開した、AI が読み書きする知識を「YAML フロントマター付き Markdown のディレクトリ」で表す仕様（v0.2）。必須キーは `type` のみ。未知キー・リンク切れ・index 欠落で拒否しない寛容設計。

### フロントマター
Markdown 先頭の `---` で囲んだ YAML。`type` / `description` / `generated` / `verified` / `status` / `stale_after` 等。本研究では `jsonb` に丸ごと保存する。

### アクター表記
`human:<id>`（人）／`<producer>/<version>`（エージェント。例 `kuroko/claude-fable-5-1`）／`process:<id>`（自動処理）。

### Attested Computation
OKF v0.2 の型。数値の公認された計算方法を1ファイルにし、エージェントはパラメータ値だけ埋める。必須キーは `runtime`。②「数える」の定義固定と同じ発想で、Post-MVP（F8）の候補。

## ステータス・状態

### 文書の `status`（OKF）
| 値 | 意味 |
|---|---|
| `draft` | 未確認の調査・下書き |
| `stable` | 既定（省略時） |
| `deprecated` | 廃止。削除せず残す |

### 取り込みの結果（`IngestReport`）
| 値 | 意味 |
|---|---|
| `inserted` | 新規に取り込んだ |
| `skipped` | `content_hash` 一致で変更なし |
| `failed` | 解析失敗（件数のみ・本文は出さない） |
| `rejected` | 境界違反（`private.md`・非ループバック・外部送信）。**1件でも全体を停止** |

## データモデル用語（要約）
`document`（1ファイル）→ `chunk`（見出し単位）→ `chunk_embedding`（方式別の埋め込み）。`fact`（有効期間つきの事実）、`summary`（要約階層）、`question`（測定用）。詳細は [functional-design.md](functional-design.md)。

## エラー・例外
| クラス | 発生条件 | 対処 |
|---|---|---|
| `LoopbackViolation` | DSN の host がループバック以外 | ローカルの DSN を使う |
| `PersonalDataExportBlocked` | 外部 Embedder に `references`/`memory` を渡した | ローカル Embedder を使う。解除は設定フラグ＋K承認 |
| `FrontmatterError` | YAML 解析失敗 | 該当ファイルを skip・件数に計上 |
| `UnknownAggregate` | ②で未定義の集計を求めた | 定義済みビューを使うか、マイグレーションで追加 |
