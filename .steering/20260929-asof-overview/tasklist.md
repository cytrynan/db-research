# タスクリスト

tracking: #23

## 🚨 タスク完全完了の原則
- `- [ ]` 未着手 / `- [~]` 着手中 / `- [x]` 完了。`[x]` は完了だけ
- 各タスク行末の issue 番号が対応表。状態を変えたらその場で issue も更新
- 全タスクを `[x]` に。スキップは技術的理由のみ・行に明記

---

## フェーズ1: 事実の抽出（F5・スキーマ）

- [x] 0008_fact.sql・`ingest/facts.py`（explicit / dated_text / inferred・削除→COPY）・`dbr facts`・fixture `dated/`・統合テスト（件数・冪等） (#24)

## フェーズ2: 時点の問い合わせ（F5）

- [x] `features/asof`（as_of / history / parse_at）・`ask` の asof 分岐と `--at`・ユニット＋統合（時点フィルタ・昇順） (#25)

## フェーズ3: 全体（F6）

- [x] 0009_summary.sql・`ingest/summarize.py`（抽出型 3 段・source_hash）・`features/overview`・`ask` の overview 分岐・統合テスト（3 段・冪等） (#26)

## フェーズ4: bench（count / asof / overview）

- [x] `bench/{count,asof,overview}.py`・`_guess_view` を count スライスへ移動・`questions.md` の期待欄に asof の日付・CLI `bench --kind count|asof|overview`・統合テスト（fake） (#27)

## フェーズ5: 実データと品質ゲート

- [x] memory を取り込み・埋め込み（plain/ctx）→ references/dev/memory で `facts`・`summarize` → `bench --kind count|asof|overview` → JSON と `docs/overview-answers.md`・`docs/bench-results.md` に転記・ruff/mypy/pytest（unit・db） (#28)

## フェーズ6: 記録と受入検証

- [x] 振り返り・README・別コンテキストの受入検証・issue クローズ (#29)

---

## 実装後の振り返り

### 実装完了日
2026-09-29

### 計画と実績の差分
**計画と異なった点**:
- ③の問い合わせは「fact 表を質問語で直接検索」から **「① 探し物で断片→文書を絞り、その範囲内で時間で絞る（無ければ履歴で補う）」** に変わった。設計時は fact 表の全文検索だけで足りると考えていたが、日付だけ合う無関係な事実が上位に来た（asof 2/4 → 4/4）
- 日付＋動詞の抽出は「隣接」から「同一行 20 字以内」に緩めた（「2026-08-24 A枠の能動営業停止」型）。dated_text 180→293 件
- 「YYYY-MM より前」を期間の直前の瞬間として解釈する規則を足した（当初は「以前／までに」も直前扱いにしていたが、受入検証 D2 で「基準日を含む」に直した）
- overview の回答は bundle 要約の**先頭行だけ**を載せる形に変えた（全文だと 71KB になり K が読めない → 14KB）
- 正解欄（questions.md）を 3 箇所更新した（Q15 に fuyou.md、Q18 に sales-routine、Q16 に 2026-08-10）。前 2 つは DB が返した「同じ事象の別記録」が正しかったため。**Q16 の 2026-08-10 は受入検証で裏づけ無しと判明し撤回**（止まった点 3 件目）

**新たに必要になったタスク**:
- summary 表に FK が無いので、テストの `clean_db` で別に TRUNCATE し、`run_summarize` に孤児掃除を足した
- timestamptz は接続 TZ（UTC）で返るので `.date()` が 1 日ずれた → JST へ戻す `_dt` を asof に追加

### 止まった点・失敗した点（**必須。1件以上**）
- **何が起きたか**: 初回 asof bench が 2/4。Q18 は「2026-08-24 A枠の能動営業停止」を抽出できず、Q16 は無関係な事実が上位
- **原因**: ①regex が日付と動詞の隣接しか見ていなかった ②「時点」を fact 表の全文検索だけで解こうとし、「何について」を絞る工程が無かった
- **次にどうするか**: 型を 4 つに分けても、③④は ① を内側に含む。**時点の問いは探し物で範囲を絞ってから**が設計原則。regex は実データの出現形（日付＋目的語＋動詞）を先に集計してから書く（今回は集計せずに書いて 1 回外した）
- **何が起きたか（2 件目）**: fact の日付が `.date()` で 1 日ずれ、統合テストが落ちた
- **原因**: psycopg が timestamptz を UTC で返す。JST 0 時 ＝ UTC 前日 15 時
- **次にどうするか**: 日付を表示・比較する層で必ず `astimezone(JST)`。DB の TZ に依存しない
- **何が起きたか（3 件目）**: bench-results・questions・tasklist・知見の 4 か所に「記録の日付不整合（INDEX 08-11 vs work.md 08-10）」を書いたが、受入検証で「work.md に 2026-08-10 は無い」と反証された
- **原因**: DB の `valid_from` を SQL で直接見た時に UTC 表示（`2026-08-10 15:00:00+00`）の日付部分だけを読み、原本ファイルを grep せずに「本文の日付」と断定した。2 件目（`.date()` のずれ）を直した直後だったのに、目視の経路には同じ罠が効いた
- **次にどうするか**: 実データについて「発見」と書く前に原本を grep する（1 コマンド）。timestamptz を SQL で見る時は `AT TIME ZONE 'Asia/Tokyo'` を付ける。転記前レビュー（A4②）の対象に「実データからの発見」も含める
- **何が起きたか（4 件目）**: D3 の修正で dedupe キーを（日付, 行）に変えただけでは、実データの dev bundle で `fact_uniq` に当たり COPY が UniqueViolation（同じ見出し・同じ日付・動詞だけ違う 2 行）
- **原因**: 畳み込みのキーと DB の一意索引（subject, valid_from）が別々に定義されていて、片方だけ直した
- **次にどうするか**: 識別子は「抽出側の dedupe」と「DB の一意制約」を同じ定義にする。今回は 0010 で索引に `md5(value)` を足した（既存マイグレーションは編集しない規則 D-3 に従う）

### 学んだこと
**技術的な学び**:
- 具体: 「INDEX.md 2026-08-11 vs work.md 2026-08-10 の不整合」と記録したが、work.md に 08-10 は無く、DB の timestamptz（UTC 表示 `2026-08-10 15:00:00+00`）の日付部分を読んだ誤認だった（受入検証が反証）
  - 抽象: **「発見」を記録する前に原本を grep する**。DB の派生表示から正本の内容を断定しない。同じ罠（timestamptz の UTC 表示）はコードでは直していたのに、目視では踏んだ
- 具体: asof の正解セットに、人が INDEX から作った期待より DB が返した別ファイルの方が網羅的だった（Q15・Q18）
  - 抽象: 正解セットは実行結果で育てる。ただし追加の理由を必ず書き、採点を甘くする変更と区別する
- 具体: 抽出型の bundle 要約（全文書 1 行ずつ）を回答に貼ると 71KB
  - 抽象: 要約階層の「上位」は件数と代表だけにし、一覧は根拠 id で辿らせる

**プロセス上の改善点**:
- bench → 数字 → 1 問の原因を現物で見る → 直す → 再測定、を 5 往復（a〜e）。1 往復 1〜2 分で回るので、設計を頭で詰めるより速かった
- ゲート付き commit は `set -o pipefail` で安定して止まるようになった（この単位で 2 回止めた）

**リポジトリをまたいで使える知見**:
- `dev/postgres-fts-pgvector.md` §6 に「時点検索は探し物で範囲を絞ってから」「timestamptz の .date() ずれ」を追記。「記録の日付不整合」は受入検証後に**誤記として取り下げ**、「目視でも JST に戻す」「日付窓は次の日付で打ち切る」「識別子に行の内容を含める」「正解判定の空＝何でも一致は禁止」に置き換えた

### 受入検証（別コンテキスト）
- 実施: 2026-09-29・`readonly-reviewer`（Opus 5.5。Codex は usage limit のため例外(c)・本日 4 回目）。対象 commit `b245b9e`。256,645 tok・73 tool uses・24.0 分。dbr_test への書き込みあり（統合テスト実行のため・自己申告・許容）、実データ DB・リポは無変更
- 結果: 要件 6 点中 **PASS 1 / FAIL 5**＝D1 `--at` の検査が甘い／D2 「以前・までに」が基準日を除外／D3 20 字窓が次の日付を跨ぐ・同 subject の別行が畳まれる／D4 overview で対象 bundle だけ埋め込み無しの代替欠落／D5 `is_correct` の空側ワイルドカード。＋近道検査 1 件（期待値を実装と同じ commit で変更。**Q16 の 2026-08-10 は原本に無い**）＋任意 12 件。レビュー係の誤指摘 0
- 回収（次の commit）: D1〜D5 すべて修正＋テスト 5 本追加（132 passed・カバレッジ 90.65%）。D3 は識別子の定義の問題だったので `0010_fact_uniq_value.sql`（`fact_uniq` に `md5(value)`）。任意のうち回収: scope=chunks の表示、fallback 見出し（「最初の記録」→「関連する記録・関連度順」）、`--kind` 語彙外の拒否、summarize の日付直書き、`valid.to` の最終日を含める、pick_bundles の部分一致。**未回収 3 件**: summary の source_hash 陳腐化 WARN、recorded_at の規則（generated_at 無しは ingested_at）の明文化、Q12 の `v_unverified` 補集合運用
- 再測定: asof **4/4**（v7・2 回実行で per_question 一致）。dated_text 293→295。訂正は `docs/bench-results.md` v7 と `questions.md` Q16 備考

### 次回への改善提案
- ④ overview を LLM 要約（ローカル or 外部・K 承認要）と比較する。抽出型の天井を K 採点で先に取る
- `valid_to` の自動推定（同 subject の後続事実で閉じる）を、誤閉じ率を測ってから入れる
- 「開始」の記録が無いと「その時点で動いていたか」に肯定で答えられない → 記録規約に「開始日を書く」を提案
- 検索側: `embed_ctx_rerank`・語彙一致が効く質問の追加（前単位からの持ち越し）
