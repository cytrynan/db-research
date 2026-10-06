# 設計: 常用化（daily-use）

> この文書が設計の正本。実装係（sync）はこれを直接読む。cli.py の配線は司令塔が行う。
> 既存の決定を守る: D-5（DB はループバックのみ）・D-9（正本は Markdown、DB は派生）・D-13（埋め込み・並べ直しはローカルモデルのみ）・D-14/D-16（ask の既定）。

## 全体像

```
Claude Code セッション ──(stdio MCP)── dbr mcp ──┐
                                               │ HTTP (127.0.0.1:47821)
K のシェル ── dbr ask ──(常駐あり)──────────────┼──▶ dbr serve（埋め込みモデル常駐・sync スレッド）──▶ PostgreSQL(127.0.0.1:5432)
              └──(常駐なし/--no-daemon)── 単発経路（従来どおり in-process）──────────────────────────▶ 同上
```

- **ask の計算を `features/ask` に抽出**し、CLI・常駐・MCP の 3 入口が同じ関数を呼ぶ（既定の計算経路＝測定経路を 1 か所に）。
- 常駐は **モデルを 1 回だけ読む**プロセス。ask はそこへ JSON を投げる薄いクライアントになる。
- 同期は `features/sync` に独立モジュールとして置き、CLI の `dbr sync` と常駐のスレッドの両方から呼ぶ。

## モジュールと契約（名前はこのとおりに。識別子の揺れを防ぐ）

### 1. `src/dbr/features/ask/__init__.py`（司令塔）

```python
@dataclass(frozen=True)
class AskOptions:
    kind: str = "auto"            # auto | find | count | asof | overview
    mode: str = "embed_ctx"       # D-14
    agg: str = "rrf_top3"         # D-14
    rerank_top: int | None = None
    scope: str = DEFAULT_SCOPE    # D-16
    boost_w: float = DEFAULT_BOOST
    k: int = 5
    model: str = DEFAULT_MODEL
    reranker: str = DEFAULT_RERANKER_NAME
    at: str | None = None         # YYYY-MM-DD / YYYY-MM
    llm: str = "none"

class AskError(Exception):        # exit code を持つ（2 引数不正 / 5 モデル・埋め込み不在 / 3 ループバック）
    code: int

def answer(question: str, opts: AskOptions, *, dsn: str,
           embedder_for: Callable[[str], Embedder],
           reranker_for: Callable[[str], Reranker],
           llm_for: Callable[[str], Any]) -> dict[str, Any]:
    """cli.py の ask 本体をそのまま移す。戻り値は従来 --json が出していた dict。
    追加キー: kind_fallback: bool（unknown→find に倒したとき True・reason に明記）。"""

def format_text(out: dict[str, Any]) -> str:
    """従来のテキスト出力（stdout に出していた文字列）を out から組み立てる。"""
```

- **型判定のフォールバック（D-17）**: `opts.kind == "auto"` かつ分類が `unknown` → `kind="find"`・`kind_fallback=True`・`reason="既知の語彙に当たらない → 探し物として検索（推定）"`。`RuleClassifier` と `dbr classify` は変えない（判定器は正直なまま。倒すのは ask 層）。
- 既存の検査順序（`--kind` 語彙外・`--scope` 語彙外・`--at` 書式 は型に関係なく先に exit 2）は維持する（受入検証 D1 の再現を壊さない）。

### 2. `src/dbr/shared/embed/offline.py`（司令塔）

```python
ENV_ONLINE = "DBR_HF_ONLINE"
def apply_offline_default() -> None:
    """DBR_HF_ONLINE=1 でなければ HF_HUB_OFFLINE=1 / TRANSFORMERS_OFFLINE=1 を setdefault。
    huggingface_hub は import 時に環境変数を読むので、torch / sentence_transformers を import する前に呼ぶ。"""
```

- 呼び出し点: `cli.py` の先頭（typer の import より前）と `features/serve` の起動。
- モデル未取得で失敗したら `LocalE5` の `EmbedderUnavailable` メッセージに「`DBR_HF_ONLINE=1` を付けて 1 回だけ取得する」を足す。

### 3. `src/dbr/features/sync/__init__.py`（実装係・Sonnet）

```python
BUNDLES_ORDER: tuple[str, ...] = ("references", "dev", "memory", "stock", "tax", "scout", "experiments")

def bundle_roots() -> dict[str, Path]:
    """bundle → 正本フォルダ。既定は
       references = ~/.claude/references
       memory     = ~/.claude/projects/C--Users-meer0/memory
       dev / stock / tax / scout / experiments = ~/.agents/knowledge/<bundle>
     環境変数 DBR_ROOT_<BUNDLE 大文字>（例 DBR_ROOT_MEMORY）があれば上書き。存在しないフォルダも dict には入れる（呼び手が skip を決める）。"""

@dataclass
class BundleSyncReport:
    bundle: str
    root: str
    skipped_missing_root: bool = False
    inserted: int = 0; updated: int = 0; unchanged: int = 0; excluded: int = 0; failed: int = 0
    pruned: int = 0                 # 正本から消えたので DB から削除した document 数
    embedded_plain: int = 0; embedded_ctx: int = 0
    facts: dict[str, int] | None = None      # run_facts の to_dict（変更があった bundle だけ）
    summaries: dict[str, int] | None = None  # run_summarize の to_dict（同上）
    seconds: float = 0.0
    warnings: list[str] = field(default_factory=list)

@dataclass
class SyncReport:
    bundles: list[BundleSyncReport]
    seconds: float
    def changed(self) -> bool: ...   # どれかの bundle に inserted/updated/pruned があったか
    def to_dict(self) -> dict[str, Any]: ...

def prune(dsn: str, bundle: str, root: Path) -> int:
    """DB にあって正本に無い document を削除して件数を返す。
    「正本にある」の定義は ingest と同じ関数で決める: iter_markdown(root) → normalize_rel_path → is_excluded で除外。
    document の削除で chunk / chunk_embedding / fact は FK CASCADE で消える。summary は FK を持たないので
    自分で消す: level='document' AND target_key = <document.id の文字列> / level='section' AND target_key IN (<その文書の chunk.id の文字列>)。
    ※ summary.target_key は id の文字列（summarize.py 参照）。bundle 階層は run_summarize が作り直す。"""

def run_sync(dsn: str, embedder: Embedder, *, bundles: Sequence[str] | None = None,
             roots: Mapping[str, Path] | None = None,
             log: Callable[[str], None] = print) -> SyncReport:
    """bundle ごとに: ingest.run → prune → run_embed(plain) → run_embed(ctx) → （変更があれば）run_facts → run_summarize。
    - roots 省略時は bundle_roots()。root が存在しなければ skipped_missing_root=True で次へ（例外にしない）
    - ingest.run の PersonalDataRejected はそのまま投げる（境界違反は全体停止＝既存方針）
    - 「変更があった」= inserted + updated + pruned > 0。無ければ facts / summarize は走らせない（冪等・無変更 sync は秒で終わる）
    - run_embed は毎回呼んでよい（未生成分だけ計算する既存の冪等実装）
    - log は 1 bundle 1 行（本文・ファイル名の一覧は出さない。件数だけ）"""
```

- 置き場: `src/dbr/features/sync/__init__.py`・ユニット `src/dbr/features/sync/test_sync.py`・統合 `tests/integration/test_sync.py`（`pytestmark = pytest.mark.db`、`clean_db` fixture、`tmp_path` に fixtures をコピーして変更・削除を再現）。
- 使う既存 API: `dbr.features.ingest.run / iter_markdown / normalize_rel_path / is_excluded`（handler.py）、`dbr.features.ingest.embed.run_embed`、`dbr.features.ingest.facts.run_facts`、`dbr.features.ingest.summarize.run_summarize`、`dbr.shared.db.connect`。**これらの既存関数は変更しない**。
- 必須テスト（R5）: ①内容変更→`content_hash` 更新・古い chunk/embedding が残らない ②削除→document/chunk/chunk_embedding/fact/summary(document・section) が消える ③無変更→全 0・facts/summaries は None ④root 不在→skipped ⑤`bundle_roots()` の環境変数上書き（monkeypatch）。埋め込みは `FakeEmbedder` を使う。
- **実装時の差分（2026-10-06・実装係の判断を司令塔が採用。実装がこの形）**: ①`prune()` は root が存在しないと `ValueError`（未マウントのフォルダを「全部消えた」と読んで DB を空にしない。`run_sync` は先に skip するので挙動は上のとおり） ②`roots` を渡したときはその dict にある bundle だけが対象（テストが既定フォルダ＝実データへ逃げない） ③`BundleSyncReport.changed()` を追加 ④**facts / summarize の再構築条件は「変更あり」または `summaries_stale(dsn, bundle)`**（bundle 要約行が無い、または `stale_summaries` が非空）。ingest 後に落ちた回の自己修復のため。`BundleSyncReport.rebuilt_reason`（`changed` / `stale_summaries` / None）に理由を残す。

### 4. `src/dbr/features/serve/__init__.py` と `client.py`（司令塔）

- サーバー: 標準ライブラリ `http.server.ThreadingHTTPServer`、**bind は 127.0.0.1 のみ**（引数で変えられない）。ポート既定 `47821`（環境変数 `DBR_PORT`）。
  - `GET /health` → `{"status":"ok","pid","model","uptime_s","last_sync":{"at","seconds","changed"}|null,"sync_running":bool}`
  - `POST /ask` body=`{"question", "opts": AskOptions のフィールド}` → `answer()` の dict（エラーは `{"error","code"}` と HTTP 4xx/5xx）
  - `POST /sync` → `run_sync` を同期実行して `SyncReport.to_dict()`（既に走行中なら終わるのを待ってから走る。※当初案の 409 は受入検証の回収で変更）
  - `POST /shutdown` → 200 を返してから停止
  - 埋め込み器は名前ごとに 1 個保持（辞書キャッシュ）。`LocalE5.encode` は `threading.Lock` で直列化（CPU 推論の安全側）。
  - sync スレッド: 起動直後に 1 回、以後 `--sync-interval` 分（既定 30・0 で無効）ごと。`run_sync` の例外はログに出してスレッドは続ける。
  - ログ: `~/.dbr/serve.log`（件数・時刻のみ。本文は書かない）。
- クライアント（`client.py`）: `health(port, timeout=2.0)`（当初 0.3。起動直後の同期中に切断したので受入検証の回収で 2 秒に）, `ask_remote(question, opts, port)`, `ensure_daemon(port, *, start_timeout=90.0) -> bool`。`ensure_daemon` は health 不応答なら `subprocess.Popen([sys.executable, "-m", "dbr.cli", "serve", "--port", ...], creationflags=DETACHED_PROCESS|CREATE_NEW_PROCESS_GROUP, stdin=DEVNULL, stdout/stderr=serve.log)` で起こし、health が ok になるまで 0.5 秒間隔で待つ。
- `dbr ask` の経路選択: `--no-daemon` or `DBR_NO_DAEMON=1` → 単発。それ以外は health → 無ければ ensure_daemon → ask_remote。起動に失敗したら WARN を stderr に出して単発へフォールバック（止めない）。
- `dbr serve [--port] [--sync-interval 30] [--stop]`、`dbr sync [--bundle ...] [--json]`。

### 5. `src/dbr/features/mcp_server/__init__.py`（司令塔）

- 依存 `mcp`（公式 Python SDK・FastMCP）。stdio。ツール: `ask(question, kind="auto", at=None, k=5) -> dict`（常駐へ中継・無ければ自動起動）、`count(view) -> dict`、`sync() -> dict`、`health() -> dict`。torch 等の重い import はしない（1 セッション 1 プロセスなので軽く保つ）。
- `dbr mcp` コマンド。登録コマンド（README に記載・実行は K 承認後）: `claude mcp add --scope user dbr -- uv run --project C:\Users\meer0\dev\db-research dbr mcp`

### 6. 測定（司令塔）

- before: 2026-10-05 の実測（count 0.8 秒／find・asof・overview 25〜29 秒／オフライン 20 秒）。
- after: 常駐稼働で同じ 4 質問 × 5 回。初回自動起動の所要。`bench --kind find --modes embed_ctx --agg rrf_top3 --scope boost --label v11`（取り込み拡大後）と `--kind asof`・`--kind count`。
- 結果は `docs/bench-results.md` v11 節へ。数値はスクリプト出力から転記する（手で書き写さない）。

## 既存文書への反映（R8）

- FD: Classifier 節「find に倒さない」→ D-17 の形に書き換え。Serve / Sync / MCP の節を追加。ユースケース図に常駐経路。
- architecture: 常駐プロセス・ポート・オフライン既定・`~/.dbr/`。
- PRD F2 の「候補 2 つを提示して止まる」→ 推定して検索する（K 指示 2026-10-06）。
- decisions: D-17 / D-18 / D-19。
