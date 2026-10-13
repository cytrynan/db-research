# brief: dbr の利用ログ強化と DB 停止の検知（usage-log）

> 段: **T2**（スキーマ変更なし・課金なし・外部ユーザーなし・外部 API なし＝問1 全 No。仕様をこちらで決めたいので受入基準と非スコープを付ける）。識別子契約: 不要（ユーザー入力を識別子として保存・照合しない。`client` 名は許可リストで閉じる）。
> 発端: 2026-10-13 K「現在 Claude が実際に dbr を使っていると思う。正しくログは取れている？」→ 調査の結論「呼んではいるが 10-11 以降は全部失敗。ログは『失敗した』しか残らず、使われ方・役立ち方が分からない」→ K「推奨で進めて。改善に使用するためにログをしっかり取るようにして」。

## 実測した現状（2026-10-13・kuroko/claude-opus-5-5 → 以降 claude-fable-5-1）
- 7 日間の MCP `dbr` 呼び出しは 11 回（ask 7）。ask の成功は 10-07 夜の 2 回だけ。10-11 / 10-12 の ask は `ConnectionTimeout`（会話ログ `~/.claude/projects/*/*.jsonl` を掘って判明）。
- `dbr_pg` の PostgreSQL ログは 10-08 22:04 UTC で途切れ、常駐の 30 分同期は 10-11 以降すべて `sync error ConnectionTimeout`。コンテナの状態は「稼働中」のまま（＝プロセスは生きて機能だけ死ぬ壊れ方）。10-13 10:22 に exit 255 で停止。`restart=no`。
- `~/.dbr/serve.log` は設計どおり「時刻・メソッド・経路名」だけ（FD Serve 節）。呼び出し元（MCP / CLI / ベンチ）・結果（件数・エラー）・応答時間が無く、常駐が起動できなかった失敗は一切残らない。10-06 の ask 174 回が構築中の検証か実用かも判別できない。

## やること
1. **利用ログ `~/.dbr/usage.jsonl`**（1 要求 = 1 行の JSON）。書く場所は常駐の `/ask` ハンドラ（CLI 経由・MCP 経由の全要求が通る 1 か所）＋ CLI の単発経路（`cli-local`）＋ MCP で常駐を起こせなかった時（`daemon_unavailable`。サーバーが居ないので client 側で書く）。項目: `ts` / `client` / `question` / `kind_requested` / `kind` / `kind_fallback` / `reason` / `k` / `at` / `mode` / `agg` / `scope` / `scope_reason` / `status`（ok・error・daemon_unavailable）/ `code` / `error` / `ms` / `n_hits` / `hits`（doc・heading・score の上位、本文は書かない）/ count は `view`・`n_rows`、asof は `n_facts`、overview は `n_summaries`。
2. **`dbr usage [--days N] [--json]`**: usage.jsonl を集計して「改善に使える形」で出す——client × status の件数・フォールバック率・応答時間 p50/p90・**0 件だった質問**（直近 10）・エラー一覧（code 別）。
3. **DB 停止の検知フラグ `~/.dbr/DB-UNREACHABLE.flag`**: 常駐の同期が **DB の接続段（`psycopg.OperationalError`）で 2 回連続**失敗したら書く（取り込み拒否など DB 以外の失敗は数えない＝受入検証で修正）（本文: 時刻・最後のエラー・`docker start dbr_pg` の手引き）、`/ask` が `psycopg.OperationalError`（接続段の失敗）で落ちたら即書く、同期が成功したら消す。`/health` に `consecutive_sync_failures` と `db_unreachable` を足す。`~/.claude/hooks/check-regression-flags.py` の FLAGS に 1 行登録（セッション開始時に既存の警告と同じ形で出る）。
4. **`dbr_pg` の再起動方針**: `compose.yaml` に `restart: unless-stopped`、稼働中コンテナは `docker update --restart unless-stopped dbr_pg`（再作成せず適用）。
5. 文書: FD Serve 節（ログの記述を差し替え）・architecture「状態の置き場」・README（usage.jsonl と `dbr usage`）・decisions **D-20**・RESUME・docs/log.md。

## 実装者が決めた仕様級判断（レビューの採点基準）
- J1: `client` は許可リスト `mcp` / `cli` / `cli-local` / `bench` / `other` に閉じ、ペイロードの未知の値は `other` に落とす（`KNOWN_ROUTES` と同じ流儀。ログに任意文字列を流し込ませない）。`/ask` ペイロードは `{"question", "opts", "client"}` で `client` 省略可（後方互換）。
- J2: ログの書き込み失敗は要求を失敗させない（`_log_line` と同じ。ログは補助）。テストは conftest で `USAGE_PATH` / `FLAG_PATH` を tmp に向ける（serve.log と同じ扱い）。
- J3: `hits` は返した上位（k ≤ 50）だけ・`heading` は 120 字で切る・断片本文（`text`）は書かない。質問文は**書く**（改善に使うため。K 指示 2026-10-13）。
- J4: フラグの閾値は同期の DB 接続失敗 2 回連続（DB 以外の同期失敗は数えない）（30 分間隔 → DB 死後 1 時間以内に出る。1 回は Docker 再起動等の一過性を許す）。`/ask` の `OperationalError` は 1 回で即書く（利用者がいま困っている信号）。解除は同期成功のみ（ask 成功では消さない＝同期が壊れている状態を隠さない）。
- J5: usage.jsonl はローテーションしない（1 行 ≈ 1 KB・1 日 100 問で年 36 MB）。置き場は `~/.dbr/`（正本 `references/` と同じローカル境界。リポ外・restic の対象外）。
- J6: `restart: unless-stopped` は「コンテナが exit した」場合（今日の状態）だけを救う。「稼働中なのに応答しない」（10-08〜10-11）は **3 で検知するだけで自動復旧しない**（復旧役は故障注入で検証してから置く規範＝別単位で提案）。

## 受入基準
- R1: この会話の MCP から `ask` を 1 回呼ぶと usage.jsonl に `client=mcp`・`status=ok`・`n_hits≥1`・`ms>0` の行が 1 行増える。`uv run dbr ask` では `client=cli`、`--no-daemon` では `client=cli-local`。
- R2: 常駐側で `AskError`（例: kind 不正）になった要求も `status=error`・`code` 付きで 1 行残る。MCP で `ensure_daemon` が False の時は `status=daemon_unavailable` の行が残る（Popen 差し替えのユニット）。
- R3: 故障注入——同期ランナーを 2 回連続で `OperationalError` にすると FLAG が存在し本文にエラー名が入る。1 回だけでは存在しない。次の成功で消える。`/health` の `db_unreachable` が追随する。実機: `docker stop dbr_pg` → `/sync` 2 回 → フラグあり → `docker start` → `/sync` → フラグ無し。
- R4: `~/.claude/hooks/check-regression-flags.py` をフラグありで実行すると見出し付きで本文が出る。無しでは無言。
- R5: `dbr usage --days 7` が client × status の表・フォールバック率・p50/p90・0 件質問・エラー一覧を出し、`--json` で同じ内容の dict。fixture の JSONL（ok / error / fallback / 0 件 を含む 6 行以上）で数値が手計算と一致。
- R6: `docker inspect dbr_pg` の RestartPolicy が `unless-stopped`。`compose.yaml` にも同じ記述。
- R7: usage.jsonl / FLAG に断片本文（`text`）が含まれない（grep で 0 件）。テスト実行後に実運用の `~/.dbr/usage.jsonl` が増えていない（conftest の退避）。
- R8: ゲート（`bash scripts/gate.sh`）通過・既存 245 テスト不変。

## 非スコープ
- DB の自動復旧（`docker restart` を常駐が打つ）＝J6。別単位で提案。
- 「Claude が dbr を呼ぶべきだったのに呼ばなかった会話」の計測（dbr 側からは見えない。会話ログの走査は別の道具）。
- usage.jsonl のローテーション・DB への保存・ベンチ経路（`dbr bench` は `search()` 直叩きで常駐を通らない。結果は `bench/results` にある）。
- 常駐が 10-07 に消えた理由の特定（`20261008-mcp-dsn-fallback` の未解決項目のまま）。
