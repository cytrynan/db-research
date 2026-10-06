# タスクリスト

tracking: #47

## 🚨 タスク完全完了の原則
- `- [ ]` 未着手 / `- [~]` 着手中 / `- [x]` 完了。`[x]` は完了だけ
- 各タスク行末の issue 番号が対応表。状態を変えたらその場で issue も更新
- 全タスクを `[x]` に。スキップは技術的理由のみ・行に明記

---

## フェーズ1: 計算経路の抽出と型判定のフォールバック（司令塔）

- [x] `features/ask`（`AskOptions`・`answer`・`format_text`・`AskError`）へ cli.py の ask 本体を移し、unknown→find のフォールバック（D-17・`kind_fallback`）を入れる。`shared/embed/offline.py`（HF オフライン既定・`DBR_HF_ONLINE`）。既存テスト不変＋ユニット（フォールバック・検査順序） (#48)

## フェーズ2: 同期（実装係 Sonnet）と常駐（司令塔）— 並行

- [x] `features/sync`（`bundle_roots`・`prune`・`run_sync`・`SyncReport`）＋ユニット＋統合テスト（変更・削除・無変更・root 不在・環境変数） (#49)
- [x] `features/serve`（ループバック HTTP・モデル常駐・sync スレッド・`/health` `/ask` `/sync` `/shutdown`）と `client.py`（health・ask_remote・ensure_daemon 自動起動）＋テスト（スレッド起動の統合・自動起動は Popen を差し替えたユニット） (#50)

## フェーズ3: 配線・入口・取り込み（司令塔）

- [x] cli.py: `ask`（常駐経由/`--no-daemon`/自動起動失敗時のフォールバック）・`serve`・`sync`・`mcp` の配線。`features/mcp_server`（FastMCP・4 ツール・常駐へ中継）＋テスト（list_tools・ask 中継）。README に使い方と登録コマンド (#51)
- [x] 実データで `dbr sync`（7 bundle）→ R1 を SQL で確認。応答時間 after を 4 質問 × 5 回で測定、初回自動起動の所要も記録 (#52)

## フェーズ4: 測定・記録・検証

- [x] `bench --kind find`（embed_ctx・rrf_top3・boost・`--label v11`）と count / asof を再測定し `docs/bench-results.md` v11 に記録。FD / architecture / PRD F2 / decisions（D-17〜D-19）/ RESUME / docs/log.md を更新 (#53)
- [~] 受入検証（Codex・読み取り専用・R1〜R8）→ 指摘の回収 → `bash scripts/gate-commit.sh` → 振り返り・orchestration.md・評価係（orchestrator-reviewer）→ issue クローズ (#54)

---

## 実装後の振り返り

### 実装完了日
2026-10-06（受入検証と評価係の結果は末尾に追記）

### 計画と実績の差分
- **設計どおり**: モジュール名・関数名・HTTP の 4 経路・`AskOptions` のフィールド・経路選択（`--no-daemon` / `DBR_NO_DAEMON` / `--dsn` 明示）・MCP の 4 ツール。
- **設計から変えた点（実装係の判断を採用・design.md §3 に未反映＝本節が正本）**: ①`prune()` は root 不在で `ValueError`（未マウントのフォルダを「全部消えた」と読んで DB を空にしない） ②`roots` を渡したときはその dict の bundle だけが対象 ③`BundleSyncReport.changed()` を追加 ④**facts / summarize の再構築条件を「変更あり」から「変更あり、または要約が陳腐化（`stale_summaries` 非空・bundle 要約行なし）」に広げた**（ingest 後に落ちた回の自己修復。`rebuilt_reason` で理由を残す）。
- **設計から変えた点（司令塔）**: `apply_offline_default()` の呼び出し点を「cli.py 先頭と serve」から **ローカルモデルを読む 3 か所（embed / rerank / llm の `local.py`）の import 直前**に変えた（huggingface_hub は import 時に環境変数を読むので、読む場所の直前が最も確実で、テストも書けた）。
- **依存の想定違い**: MCP SDK は 2.3.0 が入り、1.x の `FastMCP` は `MCPServer`（`mcp.server.mcpserver`）に改名、`Tool.inputSchema` は `input_schema`。設計の「FastMCP」は名前だけの差。
- **R1 は当初 6/7 bundle で一致**: experiments は 82 ファイル中 6 件がフロントマターの YAML 不正（`description` / `status` の値に `: ` を含む→ScannerError）で WARN・未取り込みだった（`experiment-backlog.md`、`omc-experiment/EXPERIMENT-LOG.md`、`orca-experiment/EXPERIMENT-LOG.md`、`ruflo-experiment/EXPERIMENT-LOG.md`、`tdd-experiment/round5/results/measurements-r6.md`、同 `measurements-r7.md`）。受入検証（Codex・指摘 3）を受けて**正本側で値を引用符で囲む書式修正**を行い（本文・generated は不変・`experiments/log.md` に 1 行）、再同期後に **7/7 bundle で件数一致**（16/59/77/15/4/23/82・private.md 0 件を SQL で確認）。memory は `MEMORY.md` が type 無し WARN（取り込みは成功）。
- **R3 の count**: 修正前の測定で 5 回中 1 回が 1.08 秒。受入検証（指摘 4）を受けて CLI の起動で psycopg と検索モジュールを読まない形にし（`import dbr.cli` 0.78→0.16 秒）、温まった状態で **count 0.46〜0.51 秒 × 5 回連続**（`uv run`）・find/asof/overview 0.56〜0.71 秒。ただし**同期直後の最初の 7 回は 2.0〜2.3 秒**で、その間は字義の「1 秒以内」を外す（原因は未特定。`uv run` 単体は 0.14 秒なので起動側ではない）。基準を変えるかは K 判断。
- **初回 sync は 450 秒**で PRD の「全件 5 分以内」を超えた（埋め込み 2,042 断片 × 2 variant を CPU で）。以後は差分だけ（無変更 2.3 秒）。

### 受入検証の指摘と回収（Codex・読み取り専用・2026-10-06）
1 巡目の判定: R2・R5・R8 PASS／R1・R3・R4・R6 FAIL／R7 UNVERIFIED（Codex の書込制限で gate.sh を回せず。司令塔が実行し 215→227 passed・90.46%・GATE OK）。必須の指摘 4 件と観察 2 件はすべて実在を再現してから回収した:
1. **R6: MCP の `count(view="v_by_bundle")` が exit 2**（ビュー名を質問文として `guess_view` に渡し、`v_by_bundle` だけ語彙に当たらない）→ `guess_view` が正規化したビュー名の完全一致を先に返す。テスト: 5 ビュー名＋HTTP 経由 5 ビュー（`test_serve_hardening.py`）。
2. **R4: `dbr serve` のモデル未取得が exit 1**（単発 ask は exit 5＋案内）→ `serve` コマンドで `EmbedderUnavailable` を exit 5＋`DBR_HF_ONLINE=1` の案内に揃えた。テスト: `test_cli_serve.py`。
3. **R1: experiments 6 件の未取り込み**→ 正本側の YAML を引用符で修正・再同期・7/7 一致（上の R1 bullet）。
4. **R3: count 1.08 秒**→ CLI の起動を軽くした（上の R3 bullet）。
- 観察 1（負の `Content-Length` で本文上限を回避できる）→ `0 <= length <= MAX_BODY` 以外と非整数を 400 で拒否。テスト: 生ソケットで `Content-Length: -1`。
- 観察 2（未知の path 文字列がログに乗る）→ 既知 4 経路以外は `other` と記録。テスト: `/secret...` が `POST other` になる。
- 回収中に見つけた別件: 起動直後の同期（CPU で埋め込み中）に health の問い合わせ（0.3 秒）が待ち切れず切断→ `ConnectionAbortedError` のトレースバックが serve.log に 5 回。health のタイムアウトを 2 秒に、サーバー側は `handle_error` で 1 行ログに。あわせて HTTP の `/sync` は走行中の同期を待ってから走る（`run_sync(wait=True)`・409 を返さない）。
- Codex が指摘しなかったが司令塔が直したもの: なし。Codex の指摘で却下したもの: なし。
- **2 巡目（解消確認・2026-10-06）**: Codex は usage limit（解除 19:30）で起動できず、**例外(c)で readonly-reviewer（Claude Opus 5.5）が代行**。7 点すべて「修正済」（指摘 2 は同梱テストと別に実経路＝`sentence_transformers` だけを壊した偽モジュールで exit 5 を確認・指摘 5 は生ソケットで −1/−100/65537/abc/1e3 と境界 65536/65537・指摘 7 は走行中の同期に `/sync` が 0.59 秒待って 200）。回帰: 指定テスト 72 passed・全テスト 225 passed（slow 2 除外）・カバレッジ 89.49%・ruff/mypy PASS・parity 4 型一致・経路選択・offline_before_import PASS。**stdio MCP の `list_tools` に 4 ツール**（1 巡目で UNVERIFIED だったもの）。必須の指摘 2 件: **A（R3 持ち越し）** 同期直後の 2 秒台は未解消＝K 判断／**B（R8）** FD が health 0.3 秒・design.md が 409 のまま → 両方を実装に合わせて直した。観察 6 件のうち 3 件を回収（壊れたリクエスト行で `self.path` 未設定→`getattr`・GET/POST 以外のメソッド名を `other`・`ensure_daemon` が子の終了を見て 90 秒待たない＋テスト）、`/sync` の待ちと SyncBusy の回帰テスト（`test_resources.py`）を追加。残 2 件（切断 1 回でログ 4 行・`test_cli_serve` が `serve()` を丸ごと差し替える）は記録のみ。

### 応答時間の生データ（2026-10-06・K の PC・他セッション稼働中・修正前）
| 質問 | run1 | run2 | run3 | run4 | run5 |
|---|---|---|---|---|---|
| count「未確認の記録は何件？」 | 1083 ms | 906 | 881 | 874 | 878 |
| find「Codex の起動で PATH の罠は何だった？」 | 1034 | 976 | 1034 | 973 | 939 |
| asof「2026-08 時点で評価係の起動条件は？」 | 1107 | 1045 | 1067 | 1015 | 1040 |
| overview「dev の記録は全体としてどう？」 | 1254 | 1229 | 1076 | 1047 | 1091 |

初回（常駐の自動起動込み・count）24,470 ms。

### 応答時間の生データ（2026-10-06・修正後＝CLI の起動を軽くした・常駐あり・単位 ms）
| 質問 | run1 | run2 | run3 | run4 | run5 |
|---|---|---|---|---|---|
| count（`uv run`・温まった状態） | 509 | 476 | 508 | 493 | 462 |
| count（venv の `dbr.exe` 直接・10 回） | 411 438 441 452 386 426 418 441 442 422 |||||
| find（3 回） | 569 | 576 | 559 | | |
| asof（3 回） | 585 | 597 | 623 | | |
| overview（3 回） | 701 | 705 | 671 | | |
| 同期直後の最初の 7 回（count 5・find 2） | 2074 | 2211 | 2261 | 2010 | 2192（find 2133・1504） |

初回（常駐の自動起動込み・count）22,863 ms。`uv run python -c pass` 136〜147 ms。`import dbr.cli` 0.78 → 0.16 秒（psycopg・検索モジュールを読まない）。

（修正前の生データ）before（2026-10-05・常駐なし）: count 844 / find 26,949・28,251 / asof 28,587 / overview 26,182 / find with `HF_HUB_OFFLINE=1` 19,744 / 起動のみ 1,052。

### 学んだこと（具体例 → 抽象）
- **「数値はスクリプト出力から転記」が効いた実例**: v11 の「新 bundle の文書が上位 5 に入った問数」を手で数えて 6 問・10 件と issue に書いた直後、JSON から機械計算すると 5 問・7 件だった（dev を新 bundle に数え間違えた）。→ **集計は人（モデル）が数えず、JSON を読むスクリプトに数えさせ、文章はその出力から組み立てる**（bench-results は機械転記なので正しい値。issue のコメントは訂正コメントで直した）。
- **応答時間の内訳は「起動だけ」を別に測ると一発で割れる**: `dbr --help` 1.05 秒・`HF_HUB_OFFLINE=1` で 19.7 秒・既定 27 秒 → モデル読み込み ≈18 秒・Hub 確認 ≈7 秒・起動 ≈1 秒。→ **遅い処理は「何もしない呼び出し」と「外部通信を切った呼び出し」を先に測る**と、常駐で消える部分とオフラインで消える部分が分かる。
- **環境変数で効かせる既定は「読む側の import 直前」に置く**: `HF_HUB_OFFLINE` は huggingface_hub の import 時に評価される。cli.py 先頭に置くと「別経路で先に import された」場合に効かない。→ **ライブラリの設定を環境変数で入れるなら、そのライブラリを import する関数の中・import の直前で setdefault する**（利用者の明示値は上書きしない）。
- **実装係の「設計上の穴」の指摘は設計側の責任**: 「変更なしなら再構築しない」は冪等性の最適化として正しいが、途中で落ちた回の自己修復が無かった。Sonnet が自発的に指摘し、`stale_summaries` の再利用で塞げた。→ **差分実行の設計には「前回が途中で止まった」ケースを必ず 1 つ書く**（冪等＝何度やっても同じ、は「完了した回」だけを前提にしがち）。

### 止まった点・失敗
- **Bash のヒアドキュメントで日本語の長文（設計書 3 本）を書こうとして `unexpected EOF` で失敗**（1 本目は通り、2 本目以降が丸ごと落ちた。実装係も同じ現象を報告）。Write ツールに切り替えた。原因は特定していない（引用符を含む長い本文でこの環境の Bash ツールが落ちる、までしか分からない）。
- **cli.py の `ask` を 1 回目に抽出したあと、`ruff format src tests` を無差別に回して実装係の作業中ファイルまで整形対象にした**（結果は「3 files reformatted」で自分のファイルだけだったが、並行作業中は対象を自分のパスに限るべきだった）。以後はパス指定に変えた。
- **`find -not -path "*/.*"` で正本の .md を数えたら全 bundle 0 件**: root 自体が `.claude` / `.agents` 配下なので除外に当たっていた。root へ `cd` して相対で数え直した。→ ドット除外は root 相対で。
- **mypy が実装係の作業中ファイルで止まる／実装係の mypy が司令塔の作業中ファイルで止まる**を 1 回ずつ踏んだ（同じ worktree で並行すると `mypy src` が相手の途中状態を拾う）。→ 並行中は `mypy <自分のパス>`、全体は合流後に 1 回。

### 次回への改善提案
- CLI の起動 0.9 秒を削るなら `dbr` を `uv run` 経由でなく venv の exe を直接叩く（`uv run` の解決コストが乗っている。未計測）。
- 7 bundle 初回 450 秒は埋め込みの CPU 時間。GPU（ある場合）か、`ctx` variant だけ先に作って `plain` を後回しにする分割で初回を半分にできる（`plain` は既定経路で使っていない＝D-14 の embed_ctx）。
