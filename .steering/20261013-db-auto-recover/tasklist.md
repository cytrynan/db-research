# タスクリスト（20261013-db-auto-recover）

tracking: #63

brief: [brief.md](brief.md)

## 🚨 タスク完全完了の原則
- `- [ ]` 未着手 / `- [~]` 着手中 / `- [x]` 完了。`[x]` は完了だけ
- 各タスク行末の issue 番号が対応表。状態を変えたらその場で issue も更新
- 全タスクを `[x]` に。スキップは技術的理由のみ・行に明記

---

## フェーズ1: 復旧モジュールと配線

- [x] `features/serve/recovery.py`: `Recoverer`（inspect → restart / unpause / start / 触らない の分岐・cooldown 10 分・無効化・docker 不在・probe で DB 接続を最長 60 秒待つ）＋ユニット（R1 の 7 分岐・R3 の故障注入） (#64)
- [x] 配線: `Resources.recoverer` と `mark_db_unreachable` からのスレッド起動・成功後の `run_sync()`・serve.log / フラグ本文追記 / `/health.last_recovery`。`serve(auto_recover=)`・CLI `--no-auto-recover`・環境変数。ユニット（R2 の合流・R7 の無効化） (#65)

## フェーズ2: 実機の故障注入と文書

- [x] 実機 3 型: (a) `docker kill` → start で復旧、(b) `docker pause` → unpause で復旧、(c) `docker stop` → 触らない（結果を振り返りに記録。常駐は新コードで起こし直す） (#66)
- [x] 文書: FD Serve 節・architecture・README・decisions D-21・RESUME・docs/log.md・`dev/docker-desktop-windows.md` (#67)

## フェーズ3: 検証と締め

- [x] R1〜R8 の自己判定表 → 受入検証（Codex。usage limit なら例外(c)で readonly-reviewer）→ 回収 → 回収後 diff の再確認 → `gate-commit` → 振り返り → issue クローズ (#68)

---

## 実装後の振り返り

- **完了日**: 2026-10-13（司令塔: kuroko/claude-fable-5-1。前単位 usage-log の直後に連続）
- **実機の故障注入（3 型・UTC）**: (a) 03:28 `docker kill`→exited/137→同期 2 回失敗→常駐が `docker start`→20 秒以内に running・`SELECT 1` OK→同期成功でフラグ消滅。(b) 03:51 `docker pause`→`/ask` が 5.1 秒で ConnectionTimeout→`unpause`→復旧。(c) 03:53 `docker stop`（exit 0）→同期 2 回失敗→`skipped_clean_stop`・コンテナは触らず・フラグ本文に「手で止められています。復旧: docker start dbr_pg」→手で start→同期 2.3 秒でフラグ消滅。
- **計画と実績の差分**:
  - 1 回目の (b) は**検証コマンド側の不備**（Git Bash から日本語 JSON を POST→cp932 で壊れ「JSON を読めません」）で ask が DB に届かず未測定。ASCII の質問で再測定。
  - 1 回目の (c) は (a) の復旧から 10 分以内で `skipped_cooldown` になり、「手動停止は触らない」の判定に到達しなかった。→ **inspect→手動停止の判定を抑止判定より前**に移した（inspect は無害・操作だけ抑止）。ユニット `test_clean_stop_is_reported_even_during_cooldown` を追加。
  - R8 の 1 回目の全体実行で `test_unknown_route_is_logged_as_other`（今回の差分で触っていない 404 経路のログ）が 1 回だけ FAIL。単独・serve 群・2 回目の全体では再現せず。**原因未特定**（検証係に「今回の変更が壊しうる経路」の有無を依頼）。
- **学んだこと（具体→抽象）**:
  - 「クラッシュか手動停止か」は exit code で見分けられる（stop=0・kill=137・crash=255）。→ **自動復旧は "止まっている" でなく "なぜ止まったか" を見て、人の意思（手動停止）を上書きしない**。
  - 故障注入を連続で打つと、前の注入の抑止が次の注入の判定を隠す。→ **抑止つきの監視役を検証するときは、注入ごとに抑止をリセット（常駐の起こし直し）するか、抑止の前に判定を置く**。
  - 検証コマンド自体が壊れていると「復旧しなかった」と誤読する。→ 実機検証では**まず注入が効いたこと（ask がエラーになった・コンテナ状態が変わった）を見てから**復旧を判定する。
- **受入検証（Codex・2 巡）**: 1 巡目（13:16 JST・usage limit 解除直後）は Codex の sandbox から uv が起動できず（キャッシュのアクセス拒否）**静的レビューのみ**。必須 3 件: P1 probe が固まると 60 秒の上限も復旧ロックも抜けられない／P2 障害中の mark が行列化し、復旧後に古い要求が健全な DB を再起動しうる／P3 `_append_flag` の exists→open("a") が同期の削除と競合してフラグを復活させる。3 件とも経路が実在すると判断して採用: P1＝probe を別スレッド＋`join(残り時間)` で打ち切り、P2＝`acquire(blocking=False)` で待たず `skipped_in_progress`＋running なら操作直前に DB を見て届けば `skipped_healthy`、P3＝`_flag_lock` で write/append/clear を排他＋append は `open("r+")`（無いファイルを作らない）。任意 2 件（brief の文言・attempt/_recover の全例外を結果として記録）も採用。回帰テスト 5 本追加（285→290）。回収後に (a') kill→start・(b') pause→unpause を実機で再測定し PASS。2 巡目（Codex・静的）: P1 部分回収（False の後の sleep が残り時間を超える／期限後の True）・P2 PASS・P3 PASS＋**新規必須**「`skipped_healthy` が同期へ合流せずフラグが残る」→ 両方採用（sleep を残り時間以下に・`skipped_healthy` も `run_sync()` へ）。期限後の True を `started_not_ready` にする案は不採用（join の上限が poll 1 回分なので実時計では起きず、起きても DB に届いた事実のほうが運用上正しい）。任意の「競合の回帰テスト」は不採用（ロック内部にフックが要る）。回帰 2 本追加（290→292）。3 巡目（Codex・静的）: 必須 1・2 とも PASS・新規必須なし。任意「待機上限の説明を『待ちの指定を残り時間以内に制限する（OS 遅延は別）・観測できた成功は採用』と区別する」を brief J5 に反映。
- **止まった点**: ①Bash ヒアドキュメントで 2 回連続スクリプトが構文エラー、さらにヒアドキュメント内の `"\n"` がツール層で実改行に畳まれて Python の文字列が壊れた→ Write ツールでファイルに書いて実行する方式に切替（前単位と同じ罠を再度踏んだ。**バックスラッシュを含むコードはヒアドキュメントに書かない**）。④`test_hung_probe` を Fake 時計で書いたら期限が進まず 30 秒固まった（期限の消費は `join` の実時間で起きる）→ この試験だけ実時計。②mypy: `psycopg.connect(**dict)` は型が通らず、明示 kwarg に分岐。③Codex usage limit（13:15 解除・15 分以内）→ 解除待ちの背景実行。
- **リポ外へ出した知見**: `dev/docker-desktop-windows.md` 教訓 4（inspect で打ち分け・exit 0 は触らない・成功判定は SELECT 1・10 分抑止）＋ `dev/log.md` 1 行。
