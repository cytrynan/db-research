# 実装ガイド (Implementation Guide)

> **注記:** 本ガイドのコード例は TypeScript です。命名・型・エラーハンドリング・テストの**考え方**は言語共通なので、プロジェクトの言語（Python / Go / Rust など）の同等イディオムに読み替えて適用してください。

## コーディング規約（コード例は TypeScript）

### 型定義

**組み込み型の使用**:
```typescript
// ✅ 良い例: 組み込み型を使用
function processItems(items: string[]): Record<string, number> {
  return items.reduce((acc, item) => {
    acc[item] = (acc[item] || 0) + 1;
    return acc;
  }, {} as Record<string, number>);
}

// ❌ 悪い例: typingモジュールからインポート
import { List, Dict } from 'typing';
function processItems(items: List[str]): Dict[str, int] { }
```

**型注釈の原則**:
```typescript
// ✅ 良い例: 明示的な型注釈
function calculateTotal(prices: number[]): number {
  return prices.reduce((sum, price) => sum + price, 0);
}

// ❌ 悪い例: 型推論に頼りすぎる
function calculateTotal(prices) {  // any型になる
  return prices.reduce((sum, price) => sum + price, 0);
}
```

**インターフェース vs 型エイリアス**:
```typescript
// インターフェース: 拡張可能なオブジェクト型
interface Task {
  id: string;
  title: string;
  completed: boolean;
}

// 拡張
interface ExtendedTask extends Task {
  priority: string;
}

// 型エイリアス: ユニオン型、プリミティブ型など
type TaskStatus = 'todo' | 'in_progress' | 'completed';
type TaskId = string;
type Nullable<T> = T | null;
```

### 命名規則

**変数・関数**:
```typescript
// 変数: camelCase、名詞
const userName = 'John';
const taskList = [];
const isCompleted = true;

// 関数: camelCase、動詞で始める
function fetchUserData() { }
function validateEmail(email: string) { }
function calculateTotalPrice(items: Item[]) { }

// Boolean: is, has, should, canで始める
const isValid = true;
const hasPermission = false;
const shouldRetry = true;
const canDelete = false;
```

**クラス・インターフェース**:
```typescript
// クラス: PascalCase、名詞
class TaskManager { }
class UserAuthenticationService { }

// インターフェース: PascalCase
interface TaskRepository { }
interface UserProfile { }

// 型エイリアス: PascalCase
type TaskStatus = 'todo' | 'in_progress' | 'completed';
```

**定数**:
```typescript
// UPPER_SNAKE_CASE
const MAX_RETRY_COUNT = 3;
const API_BASE_URL = 'https://api.example.com';
const DEFAULT_TIMEOUT = 5000;

// 設定オブジェクトの場合
const CONFIG = {
  maxRetryCount: 3,
  apiBaseUrl: 'https://api.example.com',
  defaultTimeout: 5000,
} as const;
```

**ファイル名**:
```typescript
// クラスファイル: PascalCase
// TaskService.ts
// UserRepository.ts

// 関数・ユーティリティ: camelCase
// formatDate.ts
// validateEmail.ts

// コンポーネント(React等): PascalCase
// TaskList.tsx
// UserProfile.tsx

// 定数: kebab-case または UPPER_SNAKE_CASE
// api-endpoints.ts
// ERROR_MESSAGES.ts
```

### 関数設計

**単一責務の原則**:
```typescript
// ✅ 良い例: 単一の責務
function calculateTotalPrice(items: CartItem[]): number {
  return items.reduce((sum, item) => sum + item.price * item.quantity, 0);
}

function formatPrice(amount: number): string {
  return `¥${amount.toLocaleString()}`;
}

// ❌ 悪い例: 複数の責務
function calculateAndFormatPrice(items: CartItem[]): string {
  const total = items.reduce((sum, item) => sum + item.price * item.quantity, 0);
  return `¥${total.toLocaleString()}`;
}
```

**関数の長さ**:
- 目標: 20行以内
- 推奨: 50行以内
- 100行以上: リファクタリングを検討

**パラメータの数**:
```typescript
// ✅ 良い例: オブジェクトでまとめる
interface CreateTaskOptions {
  title: string;
  description?: string;
  priority?: 'high' | 'medium' | 'low';
  dueDate?: Date;
}

function createTask(options: CreateTaskOptions): Task {
  // 実装
}

// ❌ 悪い例: パラメータが多すぎる
function createTask(
  title: string,
  description: string,
  priority: string,
  dueDate: Date,
  tags: string[],
  assignee: string
): Task {
  // 実装
}
```

### エラーハンドリング

**カスタムエラークラス**:
```typescript
// エラークラスの定義
class ValidationError extends Error {
  constructor(
    message: string,
    public field: string,
    public value: unknown
  ) {
    super(message);
    this.name = 'ValidationError';
  }
}

class NotFoundError extends Error {
  constructor(
    public resource: string,
    public id: string
  ) {
    super(`${resource} not found: ${id}`);
    this.name = 'NotFoundError';
  }
}

class DatabaseError extends Error {
  constructor(message: string, public cause?: Error) {
    super(message);
    this.name = 'DatabaseError';
    this.cause = cause;
  }
}
```

**エラーハンドリングパターン**:
```typescript
// ✅ 良い例: 適切なエラーハンドリング
async function getTask(id: string): Promise<Task> {
  try {
    const task = await repository.findById(id);

    if (!task) {
      throw new NotFoundError('Task', id);
    }

    return task;
  } catch (error) {
    if (error instanceof NotFoundError) {
      // 予期されるエラー: 適切に処理
      logger.warn(`タスクが見つかりません: ${id}`);
      throw error;
    }

    // 予期しないエラー: ラップして上位に伝播
    throw new DatabaseError('タスクの取得に失敗しました', error as Error);
  }
}

// ❌ 悪い例: エラーを無視
async function getTask(id: string): Promise<Task | null> {
  try {
    return await repository.findById(id);
  } catch (error) {
    return null; // エラー情報が失われる
  }
}
```

**エラーメッセージ**:
```typescript
// ✅ 良い例: 具体的で解決策を示す
throw new ValidationError(
  'タイトルは1-200文字で入力してください。現在の文字数: 250',
  'title',
  title
);

// ❌ 悪い例: 曖昧で役に立たない
throw new Error('Invalid input');
```

### 非同期処理

**async/await の使用**:
```typescript
// ✅ 良い例: async/await
async function fetchUserTasks(userId: string): Promise<Task[]> {
  try {
    const user = await userRepository.findById(userId);
    const tasks = await taskRepository.findByUserId(user.id);
    return tasks;
  } catch (error) {
    logger.error('タスクの取得に失敗', error);
    throw error;
  }
}

// ❌ 悪い例: Promiseチェーン
function fetchUserTasks(userId: string): Promise<Task[]> {
  return userRepository.findById(userId)
    .then(user => taskRepository.findByUserId(user.id))
    .then(tasks => tasks)
    .catch(error => {
      logger.error('タスクの取得に失敗', error);
      throw error;
    });
}
```

**並列処理**:
```typescript
// ✅ 良い例: Promise.allで並列実行
async function fetchMultipleUsers(ids: string[]): Promise<User[]> {
  const promises = ids.map(id => userRepository.findById(id));
  return Promise.all(promises);
}

// ❌ 悪い例: 逐次実行
async function fetchMultipleUsers(ids: string[]): Promise<User[]> {
  const users: User[] = [];
  for (const id of ids) {
    const user = await userRepository.findById(id); // 遅い
    users.push(user);
  }
  return users;
}
```

## データベース操作（トランザクション・冪等性・マイグレーション）

### 副作用をトランザクションの外に置かない

「トランザクションでコミット → その後に監査ログ・通知を書く」は広く見かける形だが、
**後段が失敗すると、業務データは作成済みなのに呼び出し元へエラーを返す**。
再送するクライアント（モバイル・リトライ付きジョブ）と組み合わさると、そのまま重複データになる。

```typescript
// ❌ 悪い例: コミット後に監査ログ。ここで落ちると「作成済みなのに失敗」を返す
const id = await db.$transaction(async (tx) => { /* 作成 */ });
await writeAuditLog(userId, "CREATED", id);   // ← 失敗すると呼び出し元は失敗扱い
return { ok: true, id };

// ✅ 良い例: 1件登録のような軽い処理なら監査ログもトランザクション内に入れる
const id = await db.$transaction(async (tx) => {
  /* 作成 */
  await writeAuditLog(userId, "CREATED", id, tx);   // tx を渡す
  return id;
});
```

ログ関数側は**トランザクションクライアントを省略可能な引数**で受けると、既存の呼び出しを壊さずに済む:

```typescript
type Db = PrismaClient | Prisma.TransactionClient;
export async function writeAuditLog(/* … */, client: Db = db) { /* … */ }
```

### 再送されうる登録には冪等キーを置き、重複は「成功」で返す

自然キー（シリアル番号・注文番号など）がある経路は一意制約が事実上の防波堤になるが、
**自然キーが無い経路には防波堤がゼロ**になる。「既存の登録処理と同じ構造だから安全」という
推論はここで破れるので、**自然キーの有無を必ず確認する**。

```typescript
// ✅ クライアントが採番したキーに unique を張り、重複は成功として既存 ID を返す
const existing = await db.record.findUnique({ where: { clientKey }, select: { id: true } });
if (existing) return { ok: true, id: existing.id };   // 副作用は作らない
try {
  /* 作成 */
} catch (e) {
  if (isUniqueViolation(e, "clientKey")) {            // 同時実行で擦り抜けた場合
    const found = await db.record.findUnique({ where: { clientKey }, select: { id: true } });
    if (found) return { ok: true, id: found.id };
  }
  throw e;
}
```

- **重複をエラーで返すと再送ループになる**（クライアントは失敗として扱い、送り続ける）
- 冪等ヒット時は**副作用（在庫の増減・監査ログ・通知）を作らない**。作ると数字が二重に動く
- キーは**処理を開始した瞬間に採番し、再送時に採番し直さない**。採番し直すと冪等キーが機能しない
  （クライアント側の実装者に必ず伝える。設計書に書かないと確実に漏れる）

### 一意制約違反のエラー形は推測せず実測する

ORM が返すエラーの `target` 等の形はバージョン・コネクタで変わる。
実測（Prisma 5.22 / PostgreSQL）では `code = "P2002"` / `meta.target = ["clientKey"]` と
**フィールド名の配列**で返り、インデックス名ではなかった。

**実 DB に一意制約違反を1回起こして確認する**（数分で終わる）。外すと
「重複時だけ想定と違う分岐に落ちる」という、通常のテストで気づきにくい壊れ方をする。
判定は文字列・配列の**両方を受ける**形にしておく。

### 連番の採番は「トランザクション境界」で壊れる

「既存の最大値を読んで +1」型の採番（伝票番号・コード）を**トランザクションの中でループして
呼ぶと、全件が同じ番号になる**。採番関数がトランザクション外のクライアントで読んでいると、
**未コミット行が見えない**ため最大値が動かない。2件目で一意制約違反になり、全体が巻き戻る。

```typescript
// ❌ tx 内で 1 件ずつ採番: 全件同じ番号 → 2件目で unique 違反
for (const draft of drafts) {
  await tx.order.create({ data: { number: await generateNumber(), ...draft } });
}

// ✅ 必要数をまとめて採番して配る
const numbers = await generateNumbers(drafts.length);
```

置き場所は「**同じトランザクションで作成するか**」で決める。

| 状況 | 採番の位置 |
|---|---|
| 採番の直後に同じ tx で作成する | tx 内でまとめて採番（`tx` を引数に取る関数にする）。衝突の窓が最小 |
| 既存の単発採番関数を変えられない | トランザクションの外で一括採番して連番を配る |

- 既存の単発作成関数が**内部にトランザクションとリトライを持っている**場合、それは
  入れ子にできない。一括適用では採番だけを切り出し、衝突は一意制約違反として
  **全体を巻き戻す**ほうが素直（半分だけ入った状態を作らない）。
- 番号の計算そのものは純関数（prefix・既存番号の配列・件数 → 連番）に分ける。
  DB なしで桁溢れや他形式の混在をテストできる。

### トランザクションの本体は「クライアントを引数に取る関数」にして、DB なしでテストする

`db.$transaction(async (tx) => { …長い本体… })` と書くと、本体の検証に実 DB が要る。
**本体を `writeXxx(tx, args)` として独立させる**と、`tx` の形だけを満たす偽クライアントを
渡して「何をどの順で書いたか」を配列で確定できる。

```typescript
const calls: string[] = [];
const tx = {
  parent: { create: async () => { calls.push("parent.create"); return { id: "p1" }; } },
  // 呼んではいけない操作は「呼ばれた瞬間に落ちる」実装にしておく
  child:  { update: () => { throw new Error("child.update を呼んではいけません"); } },
} as unknown as TransactionClient;

expect(calls).toEqual(["parent.create", /* … */]);   // 参照される側から作る順序を固定
```

- **「この経路では絶対に更新／削除を出さない」という設計判断は、テストにする。**
  偽クライアント側の throw と、**実装ファイルのソースを読んで禁止パターンが無いことを
  検証する**テストの二重で守る（後から善意で足されても落ちる）。照合前にコメント行を落とす。
- **更新の `data` はホワイトリストで組む。** 「差分の配列」をそのまま展開すると、
  触ってはいけない列（自動採番のコード・人の手入力）に届く経路が残る。
  テストは想定外のフィールドを混ぜて `data` に出ないことを確かめる。
- テストランナーによっては `import.meta.url` が `file:` スキームでない（jsdom 環境など）。
  実装ファイルを読むテストは作業ディレクトリからの相対パスで辿る。

### マイグレーションを無人（非対話）で作る

エージェントの実行環境には TTY が無いため、**対話前提のマイグレーションコマンドは実行できない**
（Prisma の `prisma migrate dev` は `--name` を付けても
`environment is non-interactive, which is not supported` で拒否される）。

対処は**同じツールが持つ非対話の経路**を使うこと。Prisma なら差分 SQL を生成 → 適用に分ける:

```bash
# 生成（migrate diff は公式の SQL 生成器。手書きにはならない）
prisma migrate diff --from-schema-datasource <schema> --to-schema-datamodel <schema> --script \
  > "prisma/migrations/$(date -u +%Y%m%d%H%M%S)_<説明>/migration.sql"
# 適用・確認
prisma migrate deploy && prisma migrate status
```

- ディレクトリ名のタイムスタンプは **UTC**（ローカル時刻だと既存の並びと逆転しうる）
- 生成した SQL は**ファイルに書き出したら必ず中身を目視**する（更新通知バナー等が混ざることがある）
- **`NOT NULL` カラムの追加前に、対象テーブルの実行数を数える**。0 件であることを根拠にしてから
  必須にする。0 件でないなら勝手に消さず、nullable にするか既定値を与えるかを依頼者に確認する

### 作業ディレクトリを共有しているとき、スキーマ差分は他方の変更を巻き込む

差分生成コマンド（Prisma の `migrate diff --from-schema-datasource --to-schema-datamodel` 等）が
出すのは「**いま DB にある状態**」と「**いまスキーマ定義ファイルに書いてある全部**」の差であり、
「自分が加えた変更」ではない。

1つの作業ディレクトリで複数の作業が並行していると、相手がモデルを書き足した直後の差分に
**相手のテーブル・カラムが混入**する。そのまま適用すると、相手の変更が自分の名前の
マイグレーションとして履歴に入り、相手が後から取る差分は空になる（相手のマイグレーションが消える）。

スキーマ定義ファイルを触る作業は**同時に走らせない**:

1. 着手前に相手へ通知して**排他を宣言**する
2. 生成した SQL を**目視し、自分の変更しか入っていないことを確認**する
   （件数ではなくテーブル名・カラム名を読む）
3. 適用 → クライアント再生成 → コミット → **相手に解放を通知**
4. 2番手は開始前に最新のスキーマ定義を取り込んでから 1 へ戻る

開発用 DB のインスタンスも通常1つの共有資源なので、**リセット・シード投入も同じ排他の対象**にする。

## コメント規約

### ドキュメントコメント

**TSDoc形式**:
```typescript
/**
 * タスクを作成する
 *
 * @param data - 作成するタスクのデータ
 * @returns 作成されたタスク
 * @throws {ValidationError} データが不正な場合
 * @throws {DatabaseError} データベースエラーの場合
 *
 * @example
 * ```typescript
 * const task = await createTask({
 *   title: '新しいタスク',
 *   priority: 'high'
 * });
 * ```
 */
async function createTask(data: CreateTaskData): Promise<Task> {
  // 実装
}
```

### インラインコメント

**良いコメント**:
```typescript
// ✅ 理由を説明
// キャッシュを無効化して最新データを取得
cache.clear();

// ✅ 複雑なロジックを説明
// Kadaneのアルゴリズムで最大部分配列和を計算
// 時間計算量: O(n)
let maxSoFar = arr[0];
let maxEndingHere = arr[0];

// ✅ TODO・FIXMEを活用
// TODO: キャッシュ機能を実装 (Issue #123)
// FIXME: 大量データでパフォーマンス劣化 (Issue #456)
// HACK: 一時的な回避策、後でリファクタリング必要
```

**悪いコメント**:
```typescript
// ❌ コードの内容を繰り返すだけ
// iを1増やす
i++;

// ❌ 古い情報
// このコードは2020年に追加された (不要な情報)

// ❌ コメントアウトされたコード
// const oldImplementation = () => { ... };  // 削除すべき
```

## セキュリティ

### 入力検証

```typescript
// ✅ 良い例: 厳密な検証
function validateEmail(email: string): void {
  if (!email || typeof email !== 'string') {
    throw new ValidationError('メールアドレスは必須です', 'email', email);
  }

  const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
  if (!emailRegex.test(email)) {
    throw new ValidationError('メールアドレスの形式が不正です', 'email', email);
  }

  if (email.length > 254) {
    throw new ValidationError('メールアドレスが長すぎます', 'email', email);
  }
}

// ❌ 悪い例: 検証なし
function validateEmail(email: string): void {
  // 検証なし
}
```

### 外から来た文字列をファイルパスに入れない（識別子は形を検証してから使う）

アップロードやレビュー画面のように「複数のリクエストにまたがって入力を持ち回る」処理では、
入力を一時ディレクトリに置き、識別子で引くのが軽い。このとき**識別子の形を検証する関門**を
1 箇所に置く。

```typescript
// ✅ 内容ハッシュ（16進64桁）以外は受け付けない。パス操作の前に必ず通す
export function isValidFileHash(value: string): boolean {
  return /^[0-9a-f]{64}$/.test(value);
}
```

- 保管ファイルの名前は**識別子そのもの**にする。元のファイル名は表示用にメタデータへ置き、
  **パス区切り文字を落としてから**保存する。
- `../../etc/passwd` のような入力で「何も読まない・何も消さない」ことを**テストで固定**する。
- **保持期間を決めて自動で消す。** 一時保管の中身は業務データそのものなので置き続けない。
  明示的に破棄する手段も UI に出す。
- ⚠️ ファイルでの持ち回りは**単一プロセス前提**になる。水平分割するときは共有ストレージか
  DB へ移す必要がある——この制約を**実装ファイルの冒頭に書いておく**（書かないと静かに壊れる）。

### 大きい入力は「フォーム送信の仕組み」ではなく HTTP エンドポイントで受ける

多くのフレームワークは、フォーム送信ハンドラ（サーバー関数）のリクエスト本文に既定の
サイズ上限を置いている。数 MB のファイルをそこで受けると、**上限を上げるための設定変更**が
必要になる。設定ファイルの変更が承認事項になっている運用では、**上限の無い通常の HTTP
エンドポイントで受ける**ほうが手数も承認も少ない。

- **「実測してから決める」より先に既定値を確認する。** 既定値が分かっていて入力サイズの
  見積りが確実に超えるなら実測は不要。判断の根拠（既定値と見積り）を残せばよい。
- 承認・適用のリクエストは **ID の配列だけ**を送る形にすると本文が小さいまま保てる。
  数千行を 1 送信にすると、本文サイズと「1 操作で全部承認してしまう」事故を同時に抱える。

### 外部ツールを子プロセスで起動するなら、シェルを使わずに起動できる形を選ぶ

アプリから別のツール（別リポジトリのスクリプト、CLI）を起動する設計は、
**シェルを経由しない argv 実行**が基本。設定値でコマンドを差し替えられるようにするなら、
シェルを挟んだ瞬間に「設定値にメタ文字を入れられる」問題が生まれる。

ところが**パッケージマネージャのラッパー（`npm` / `npx` / `yarn` / `pnpm`）はシェル無しで
起動できない環境がある**。Windows ではそれらはバッチファイルで、近年のランタイムは
セキュリティ対策としてシェル無しのバッチ起動を拒否する。

- **回避は「ラッパーを経由しない」。** 対象が持っている CLI のプレーンなスクリプトを
  ランタイムで直接叩く（例: `node <repo>/node_modules/<tool>/dist/cli.mjs <args>`）。
- ランタイムのパスは**実行中のプロセスのもの**を使う（PATH に無い環境でも動く）。
- ⚠️ **子プロセスの起動失敗は同期例外で来ることがある。** エラーイベントのハンドラだけでは
  素通りしてプロセスごと落ちる。**起動呼び出しを try/catch で囲む**。
- 設定でコマンドを差し替えられるなら、**動かないコマンドは理由付きで弾く**。
  「設定できるのに動かない」を残すと、原因の分からない失敗になる。
- 出力先やフラグは**呼び出し側が決めて末尾に足す**。設定値から渡させると、
  危険なフラグ（生データの出力など）を足せる経路が残る。
- 子プロセスの `stdout` / `stderr` は**末尾数行だけ**保持する。全文を貯めると
  業務データがログに溜まる。

### 機密情報の管理

```typescript
// ✅ 良い例: 環境変数から読み込み
import { config } from './config';

const apiKey = process.env.API_KEY;
if (!apiKey) {
  throw new Error('API_KEY環境変数が設定されていません');
}

// ❌ 悪い例: ハードコード
const apiKey = 'sk-1234567890abcdef'; // 絶対にしない！
```

## パフォーマンス

### データ構造の選択

```typescript
// ✅ 良い例: Mapで O(1) アクセス
const userMap = new Map(users.map(u => [u.id, u]));
const user = userMap.get(userId); // O(1)

// ❌ 悪い例: 配列で O(n) 検索
const user = users.find(u => u.id === userId); // O(n)
```

### ループの最適化

```typescript
// ✅ 良い例: 不要な計算をループの外に
const length = items.length;
for (let i = 0; i < length; i++) {
  process(items[i]);
}

// ❌ 悪い例: 毎回lengthを計算
for (let i = 0; i < items.length; i++) {
  process(items[i]);
}

// ✅ より良い: for...ofを使用
for (const item of items) {
  process(item);
}
```

### メモ化

```typescript
// 計算結果のキャッシュ
const cache = new Map<string, Result>();

function expensiveCalculation(input: string): Result {
  if (cache.has(input)) {
    return cache.get(input)!;
  }

  const result = /* 重い計算 */;
  cache.set(input, result);
  return result;
}
```

## テストコード

### テストの構造 (Given-When-Then)

```typescript
describe('TaskService', () => {
  describe('create', () => {
    it('正常なデータでタスクを作成できる', async () => {
      // Given: 準備
      const service = new TaskService(mockRepository);
      const taskData = {
        title: 'テストタスク',
        description: 'テスト用の説明',
      };

      // When: 実行
      const result = await service.create(taskData);

      // Then: 検証
      expect(result).toBeDefined();
      expect(result.id).toBeDefined();
      expect(result.title).toBe('テストタスク');
      expect(result.description).toBe('テスト用の説明');
      expect(result.createdAt).toBeInstanceOf(Date);
    });

    it('タイトルが空の場合ValidationErrorをスローする', async () => {
      // Given: 準備
      const service = new TaskService(mockRepository);
      const invalidData = { title: '' };

      // When/Then: 実行と検証
      await expect(
        service.create(invalidData)
      ).rejects.toThrow(ValidationError);
    });
  });
});
```

### モックの作成

```typescript
// ✅ 良い例: インターフェースに基づくモック
const mockRepository: TaskRepository = {
  save: jest.fn(),
  findById: jest.fn(),
  findAll: jest.fn(),
  delete: jest.fn(),
};

// テストごとに動作を設定
beforeEach(() => {
  mockRepository.findById = jest.fn((id) => {
    if (id === 'existing-id') {
      return Promise.resolve(mockTask);
    }
    return Promise.resolve(null);
  });
});
```

## リファクタリング

### マジックナンバーの排除

```typescript
// ✅ 良い例: 定数を定義
const MAX_RETRY_COUNT = 3;
const RETRY_DELAY_MS = 1000;

for (let i = 0; i < MAX_RETRY_COUNT; i++) {
  try {
    return await fetchData();
  } catch (error) {
    if (i < MAX_RETRY_COUNT - 1) {
      await sleep(RETRY_DELAY_MS);
    }
  }
}

// ❌ 悪い例: マジックナンバー
for (let i = 0; i < 3; i++) {
  try {
    return await fetchData();
  } catch (error) {
    if (i < 2) {
      await sleep(1000);
    }
  }
}
```

**連動する定数は導出式にする**: 「この値が正しいのは、別の定数がこの値のときだけ」という定数を
リテラルで書くと、片方を変更したときにもう片方が**黙って腐る**（名前を付けて定数化しただけでは
この依存は守れない）。

```typescript
// ✅ 良い例: しきい値を上限から導出する
const IP_LAST = 239;                    // .240 以降は別用途に予約（2026-08-25 決定）
const CAPACITY = IP_LAST - IP_START + 1;
const SWITCH_THRESHOLD = CAPACITY + 1;  // 入り切らない数になったら切替

// ❌ 悪い例: 上限 254 のときに正しかった値が、上限変更後も生き残る
const SWITCH_THRESHOLD = 45;
```

- 導出式にできない事情（外部仕様・法規）があるときは、**由来を日付つきコメントで**書く。
- 定数を変更したら、**同じ単位・同じ桁の数字リテラルを grep** して連動漏れを探す。


### 関数の抽出

```typescript
// ✅ 良い例: 関数を抽出
function processOrder(order: Order): void {
  validateOrder(order);
  calculateTotal(order);
  applyDiscounts(order);
  saveOrder(order);
}

function validateOrder(order: Order): void {
  if (!order.items || order.items.length === 0) {
    throw new ValidationError('商品が選択されていません', 'items', order.items);
  }
}

function calculateTotal(order: Order): void {
  order.total = order.items.reduce(
    (sum, item) => sum + item.price * item.quantity,
    0
  );
}

// ❌ 悪い例: 長い関数
function processOrder(order: Order): void {
  if (!order.items || order.items.length === 0) {
    throw new ValidationError('商品が選択されていません', 'items', order.items);
  }

  order.total = order.items.reduce(
    (sum, item) => sum + item.price * item.quantity,
    0
  );

  if (order.coupon) {
    order.total -= order.total * order.coupon.discountRate;
  }

  repository.save(order);
}
```

## チェックリスト

実装完了前に確認:

### コード品質
- [ ] 命名が明確で一貫している
- [ ] 関数が単一の責務を持っている
- [ ] マジックナンバーがない
- [ ] 型注釈が適切に記載されている
- [ ] エラーハンドリングが実装されている

### セキュリティ
- [ ] 入力検証が実装されている
- [ ] 機密情報がハードコードされていない
- [ ] SQLインジェクション対策がされている

### パフォーマンス
- [ ] 適切なデータ構造を使用している
- [ ] 不要な計算を避けている
- [ ] ループが最適化されている

### テスト
- [ ] ユニットテストが書かれている
- [ ] テストがパスする
- [ ] エッジケースがカバーされている

### ドキュメント
- [ ] 関数・クラスにTSDocコメントがある
- [ ] 複雑なロジックにコメントがある
- [ ] TODOやFIXMEが記載されている(該当する場合)

### ツール
- [ ] Lintエラーがない
- [ ] 型チェックがパスする
- [ ] フォーマットが統一されている
