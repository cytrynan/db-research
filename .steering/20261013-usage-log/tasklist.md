# タスクリスト（20261013-usage-log）

tracking: #55

brief: [brief.md](brief.md)

## 🚨 タスク完全完了の原則
- `- [ ]` 未着手 / `- [~]` 着手中 / `- [x]` 完了。`[x]` は完了だけ
- 各タスク行末の issue 番号が対応表。状態を変えたらその場で issue も更新
- 全タスクを `[x]` に。スキップは技術的理由のみ・行に明記

---

## フェーズ1: 利用ログ

- [x] `features/serve/usage.py`: `USAGE_PATH`・`CLIENTS` 許可リスト・`record(...)`（1 行 JSON・失敗は握る・hits の切り詰め）・`summarize(lines, days)`（client×status・fallback 率・p50/p90・0 件質問・code 別エラー）＋ユニット（許可リスト→other・heading 120 字・text を含めない・書込失敗を握る・summarize の数値が手計算と一致） (#56)
- [x] 配線: `/ask` ハンドラで ok / AskError / 例外の 3 経路を record（`client` はペイロードから・既定 other・`ms` 計測）、`client.ask_remote(client=)`、MCP は `mcp` と `daemon_unavailable`、CLI は `cli` / `cli-local`。conftest（serve/・tests/integration/）で `USAGE_PATH` を tmp へ。統合テスト: roundtrip で 1 行（client・n_hits・ms）・kind 不正で status=error・MCP ユニットで daemon_unavailable (#57)

## フェーズ2: DB 停止の検知と再起動方針

- [x] `Resources`: `consecutive_sync_failures`・`FLAG_PATH`・`mark_db_unreachable(reason)` / `clear_db_flag()`（同期 2 連続失敗で書く・成功で消す・`/ask` の `psycopg.OperationalError` で即書く）・`/health` に `consecutive_sync_failures` / `db_unreachable`。ユニット（1 回→無し・2 回→有り＋本文・成功→消える・OperationalError→即）。`~/.claude/hooks/check-regression-flags.py` の FLAGS に登録し、フラグあり／なしで実行して出力を確認 (#58)
- [x] `compose.yaml` に `restart: unless-stopped`、`docker update --restart unless-stopped dbr_pg`、`docker inspect` で確認。実機の故障注入: `docker stop dbr_pg` → `/sync` ×2 → フラグあり → `docker start` → `/sync` → フラグ無し（結果を本ファイルの振り返りに記録） (#59)

## フェーズ3: 集計コマンドと文書

- [x] `dbr usage [--days N] [--json]`（cli.py の配線のみ・計算は usage.summarize）＋ CLI テスト（`src/dbr/test_cli_usage.py`。固定日付の fixture は日が経つと落ちるので now 相対で 7 行を生成し `--path` で渡す形に変更） (#60)
- [x] 文書: FD Serve 節・architecture「状態の置き場」・README・decisions D-20・RESUME・docs/log.md (#61)

## フェーズ4: 検証と締め

- [x] 実経路で R1（MCP→`client=mcp`・CLI→`cli`・`--no-daemon`→`cli-local`）と R5（`dbr usage` の実出力）を確認し R1〜R8 の自己判定表を作る → Codex 読み取り専用レビュー（correctness と明記要件のみ必須・それ以外は任意）→ 指摘の回収 → 回収後の diff を同じ係に再確認 → `bash scripts/gate-commit.sh` → 振り返り → issue クローズ (#62)

---

## 実装後の振り返り

- **完了日**: 2026-10-13（司令塔: kuroko/claude-opus-5-5 で調査→途中から claude-fable-5-1。検証係: readonly-reviewer Opus 5.5 ＝例外(c)。Codex は usage limit・解除 13:15 JST で 15 分超のため即代行）
- **計画と実績の差分**:
  - R5 の「`tests/fixtures/usage/` の固定 JSONL」は作らず、テスト内で now 相対に 7 行生成（固定日付は `--days` の窓から日ごとに外れて落ちる＝実データのスナップショットの原則と同じ罠）。
  - J4 を受入検証で修正: 「同期 2 回連続失敗」→「同期の **DB 接続失敗**（`psycopg.OperationalError`）2 回連続」。元の実装は取り込み拒否など DB 以外の失敗でも「DB に接続できません／docker start」と誤報し、同期が成功するまで消えない形だった。
  - 受入検証の必須 4 件（cli-local の非 AskError 未記録／本文読み取り段の 400 が未記録／DB 以外の同期失敗で誤報／ログ組み立ての例外で成功要求が 500）はすべて再現手順つきで妥当→採用。回帰テスト 5 本を追加（261→266）。
  - R1 の MCP 実測で、このセッションの MCP プロセス（旧コード）経由の行が `client=other` になった。MCP サーバーはセッション起動時にロードされるので、**MCP 入口のコード変更はそのセッションの MCP では効かない**。新コードは stdio から別クライアントで起こして確認した。
- **学んだこと（具体→抽象）**:
  - DB コンテナは `running`・healthcheck 付きのまま 4 日間応答せず、同期エラーは serve.log に 20 行あった。→ **ログに書くだけでは「読む主体がいない」。異常は次に人が座る場所（SessionStart フック）へ押し出す**。restart ポリシーは exit した時しか効かない。
  - 「2 回連続失敗で DB 停止と判定」は、失敗の**原因を見ずに回数だけ**数えると別原因で誤報する。→ **フラグの条件は「何の失敗か」まで型で限定する**（`OperationalError`）。レビューなしだと次に private.md を 1 つ置いた瞬間に誤警報が常設されていた。
  - 利用ログの組み立て（`float(score)` 等）を成功経路の外に置くと、ログの都合で正しい答えが 500 になる。→ **補助処理は入口 1 か所（`log_request`）で全例外を握り、呼び手に例外を見せない**。
- **受入検証**: Codex は usage limit（解除 13:15 JST・15 分超）→ 例外(c)で readonly-reviewer（Opus 5.5）。1 巡目: R1〜R8 の裁定（実機・docker・DB テストは「確認できなかった」と明示）＋必須 4・任意 8。必須 4 件は再現手順つきで妥当→全採用、任意 6 件採用・3 件不採用（理由は依頼文の返信に記載）。2 巡目（回収後の diff を同じ係に追送）: 必須 1〜4 すべて PASS・新規必須 A（ゲート後に直した docstring の行長超過で `ruff check` が落ちる）→ 折り返して回収。「数え方を変えた後のコードで R3 の実機を測り直せ」の勧告に従い再注入: 2026-10-13 02:19 UTC `docker stop` → `/sync` ×2 で consecutive 1（フラグ無し）→ 2（フラグあり・本文に `sync: ConnectionTimeout`）→ `docker start` → `/sync` 23 秒 → フラグ消滅・consecutive 0。
- **止まった点**: ①`ruff format` 後に元の文字列で `str.replace` するパッチが外れ、スクリプトが途中で止まった（半分だけ適用の状態になり、再実行で `assert count==1` が守ってくれた）。パッチは**整形後の実テキストを見てから**書く。②Bash ヒアドキュメントに `"\ud800"` を書くとツール層で `\` が畳まれ、Python が孤立サロゲートとして受けて `UnicodeEncodeError`。スクリプトは Write ツールでファイルに書いて実行する方が安全。③Codex usage limit（1 回目の起動で即）→ 例外(c)。
- **リポ外へ出した知見**: `dev/docker-desktop-windows.md` 新節「コンテナは稼働中のまま中身だけ死ぬ／restart は exit しか救わない」＋ `dev/log.md` 1 行。`~/.claude/hooks/check-regression-flags.py` に FLAGS 1 行（リポ外・commit 対象外）。
- **次の提案（未着手）**: DB の自動復旧（常駐が `docker restart dbr_pg` を打つ。故障注入つき・別単位）／MCP 入口の入力検査エラー（kind 不正等）も利用ログへ／`dbr usage` に route 項目（ask/count/sync/health）。
