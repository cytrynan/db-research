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
