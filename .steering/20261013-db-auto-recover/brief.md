# brief: DB の自動復旧（db-auto-recover）

> 段: **T2**（スキーマ変更なし・課金なし・外部ユーザーなし・外部 API なし。常駐が `docker` を自動で打つ＝運用への副作用があるので受入基準と非スコープを明示）。識別子契約: 不要（コンテナ名は定数で閉じる）。
> 発端: `20261013-usage-log` の非スコープ J6「稼働中なのに応答しない DB は検知だけで自動復旧しない」→ K「自動復旧も進めて」（2026-10-13）。前提: フラグ `~/.dbr/DB-UNREACHABLE.flag` の仕組み（D-20）は故障注入 2 回で検証済み。

## やること
1. `features/serve/recovery.py`: `Recoverer.attempt(reason)` — `docker inspect` で状態を見て **`running`/`paused` → `docker restart`／`unpause`**、**`exited` で exit code ≠ 0 → `docker start`**、**`exited` で exit code 0（手で `docker stop` した）→ 触らない**。実行後は DB へ実際に接続できるまで最長 60 秒待ち、結果（`recovered` / `started_not_ready` / `skipped_clean_stop` / `skipped_cooldown` / `skipped_disabled` / `docker_unavailable` / `failed`）を返す。
2. `Resources.mark_db_unreachable` から復旧を起動（別スレッド。ask の 500 応答を遅らせない）。復旧に成功したら即 `run_sync()` を走らせ、成功でフラグが消える既存経路に合流。結果は serve.log（`recovery <status>`）・フラグ本文への追記・`/health.last_recovery` に残す。
3. 抑止: 同じ常駐で **10 分に 1 回**まで（再起動ループ防止）。`dbr serve --no-auto-recover` / 環境変数 `DBR_NO_AUTO_RECOVER=1` で無効化。
4. 故障注入: ユニット（runner/probe/時計を差し替え）＋実機 2 型——**(a) クラッシュ型** `docker kill dbr_pg`（exit 137）→ 同期 2 回 → 常駐が `docker start` → 同期成功 → フラグ消滅。**(b) 稼働中なのに応答しない型** `docker pause dbr_pg` → ask か同期で接続失敗 → 常駐が `docker unpause` → 復旧。加えて **(c) 手動停止** `docker stop`（exit 0）→ 常駐は触らない・フラグ本文に「手で止められている」と出る。
5. 文書: FD Serve 節・architecture・README・decisions **D-21**・RESUME・docs/log.md・`dev/docker-desktop-windows.md` の新節に追記。

## 実装者が決めた仕様級判断（レビューの採点基準）
- J1: コンテナ名は定数 `dbr_pg`（compose.yaml の `container_name` と同じ）。環境変数やペイロードから取らない。打つのは `docker inspect` / `restart` / `start` / `unpause` の 4 つだけ（`rm`・`compose down`・ボリューム操作は決して打たない）。各コマンドは timeout 60 秒。
- J2: **exit code 0 の停止は K の意思とみなして起こさない**（`docker stop` は SIGTERM → PG は 0 で終わる。クラッシュは 255・kill は 137）。フラグ本文に「手で止められています。`docker start dbr_pg`」と書く。
- J3: 抑止は 10 分（`COOLDOWN_S`）。同期間隔 30 分より短く、ask 連打で `docker restart` が連続しない長さ。復旧の試行時刻は常駐プロセス内だけで持つ（再起動で忘れてよい）。
- J4: 復旧は daemon スレッドで走らせ、呼び手（同期スレッド・HTTP ハンドラ）を待たせない。テストは `recover_in_thread=False` で同期的に走らせる。
- J5: 復旧成功後の `run_sync()` は wait=False（走行中なら飛ばす。次の周期で消える）。復旧の成功判定は **DB に接続して `SELECT 1` が返る**こと（コンテナ状態ではない。「稼働中なのに応答しない」を成功と誤認しないため）。**probe は別スレッドで走らせ残り時間で打ち切る**（接続後に固まる DB でも、状態変更コマンド後の DB 待機は、待ちの指定を常に残り時間以内に制限する＝wait_ready_s=60 秒＋poll 1 回分で返る。OS のスケジューリング遅延は別。期限の直後に観測できた成功は採用する。inspect・操作コマンドはそれぞれ最大 60 秒・直前確認は最大 5 秒で、attempt 全体の上限はその和）。**running の時は操作の直前にも 1 回 probe し、届くなら打たない**（`skipped_healthy`）。別の試行が走行中なら待たずに `skipped_in_progress`（受入検証 2026-10-13 P1/P2 で追加）。
- J6: `docker` が無い／応答しない（Docker Desktop 自体が死んでいる）ときは `docker_unavailable` を記録して終わる（Docker Desktop の復旧は `docker-desktop-recover` スキル＝人の作業）。

## 受入基準
- R1（ユニット・分岐）: 状態 running → `restart`、paused → `unpause`、exited/137 → `start`、exited/0 → 何も打たず `skipped_clean_stop`、docker 不在（FileNotFoundError）→ `docker_unavailable`、環境変数で無効 → `skipped_disabled`、10 分以内の再試行 → `skipped_cooldown`（inspect は走るが状態変更コマンドは呼ばない。受入検証で順序を変更）。
- R2（ユニット・合流）: restart 成功＋probe 真 → `recovered` → `run_sync` が呼ばれフラグが消える。probe が 60 秒偽のまま → `started_not_ready`、フラグは残り本文に試行結果が追記される。
- R3（ユニット・故障注入）: runner が非 0 → `failed`、フラグは残る、serve.log に `recovery failed`、同じ理由で再び mark しても抑止中は状態変更コマンドを呼ばない。
- R4（実機 a）: `docker kill dbr_pg` → `/sync` ×2 → 常駐が `start` → 60 秒以内に `/health.db_unreachable=false`・`last_recovery.status=recovered`・コンテナ running・フラグ無し。
- R5（実機 b）: `docker pause dbr_pg` → `/ask`（接続失敗）→ 常駐が `unpause` → 同上。
- R6（実機 c）: `docker stop dbr_pg` → `/sync` ×2 → コンテナは exited のまま・`last_recovery.status=skipped_clean_stop`・フラグ本文に「手で止められています」。→ `docker start` で手動復旧。
- R7: `/health` に `last_recovery`（at・action・status・detail）。`dbr serve --no-auto-recover` で起こした常駐は mark しても docker を呼ばない（ユニット）。
- R8: ゲート通過・既存 266 テスト不変。

## 非スコープ
- Docker Desktop 自体の復旧（`docker-desktop-recover` スキル）。
- PostgreSQL が「稼働中なのに応答しない」根本原因の特定。
- 復旧試行の usage.jsonl への記録（運用ログ serve.log と `/health` に残す）。
