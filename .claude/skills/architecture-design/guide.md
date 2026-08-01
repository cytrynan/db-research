# アーキテクチャ設計ガイド

## 基本原則

### 1. 技術選定には理由を明記

**悪い例**:
```
- Node.js
- TypeScript
```

**良い例** (下記は node-ts を採用した場合の記述例。実際はプロジェクトで採用したスタックについて書く):
```
- Node.js v24.11.0 (LTS)
  - 2026年4月までの長期サポート保証により、本番環境での安定稼働が期待できる
  - 非同期I/O処理に優れ、APIサーバーとして高いパフォーマンスを発揮
  - npmエコシステムが充実しており、必要なライブラリの入手が容易

- TypeScript 5.x
  - 静的型付けによりコンパイル時にバグを検出でき、保守性が向上
  - IDEの補完機能が強力で、開発効率が高い
  - チーム開発における型定義の共有により、コードの可読性と品質が担保される

- npm 11.x
  - Node.js v24.11.0に標準搭載されており、別途インストール不要
  - workspaces機能によりモノレポ構成に対応
  - package-lock.jsonによる依存関係の厳密な管理が可能
```

### 2. 機能単位の縦割りを既定にする

**1機能に必要なコードは1ディレクトリに同居させます。** AIエージェントが1タスクで読むファイル数を
減らすことが目的です。関係のないコードは「無駄」なだけでなく、**判断を惑わせる妨害物**として
実際に精度を下げます（コンテキストは埋まる前から劣化する）。

```
src/features/create-order/     ← この1ディレクトリで機能が完結
├── index.ts                   ← 唯一の入口
├── handler.ts                 ← ビジネス判断
├── validate.ts                ← 検証はここに置く
└── create-order.test.ts
```

**避けたい状態**: 1つの機能を直すのに `controllers/` `services/` `repositories/` `dto/` `mappers/` を
順に開く必要がある構造。エージェントは層を探し回った末に、**頼んでいない抽象を勝手に発明したり、
起こりえないエラーケースを「修正」し始めます**。

**規律2つ**:
1. `shared/` を投機的に作らない（3スライスで実際に重複してから移す）
2. スライスの外を触る変更は仕様級の判断として `.steering/` に書き戻す

**層で横に割ってよい例外**: 共有ビジネスルールが支配的（金融計算・リスク管理等）／不変条件を
中央集約しないと整合性が壊れる／強いドメインモデリングが要る。この場合は依存を一方向に保ちます:

```
UI → Service → Data (OK)
UI ← Service (NG)
UI → Data (NG)
```

### 2-b. 機能名 → ディレクトリの対応表を維持する

`docs/architecture.md` に対応表を1枚置き、機能追加のたびに1行足します。
エージェントが「どこを見ればいいか」を探索でなく参照で解決できるようになり、無駄な探索が減ります。

### 3. 測定可能な要件

すべてのパフォーマンス要件は測定可能な形で記述します。

## 縦割りスライスの設計

### スライスの粒度

1スライス = **1ユースケース（1エンドポイント／1コマンド）**。「注文機能」ではなく
「注文を作成する」「注文を取得する」「注文を取消す」で割ります。

```typescript
// src/features/create-order/handler.ts
// 責務: この1ユースケースを入口から永続化まで完結して持つ
export async function createOrder(input: CreateOrderInput): Promise<Order> {
  const validated = validateCreateOrder(input);      // 検証は隣のファイル
  const order = { ...validated, id: newId(), createdAt: now() };
  await db.orders.insert(order);                     // データアクセスも同居（汎用リポジトリを挟まない）
  return order;
}
```

**やらないこと**:
- 使う予定のないインターフェース・抽象を先に作る（投機的な抽象）
- 1件しか実装がない汎用リポジトリ／汎用マッパーを挟む
- 他スライスの内部ファイルを直接 import する（`index.*` 経由にする）

## 層分離を選んだ場合の設計（例外時のみ）

### 各レイヤーの責務

**UIレイヤー**:
```typescript
// 責務: ユーザー入力の受付とバリデーション
class CLI {
  // OK: サービスレイヤーを呼び出す
  async addTask(title: string) {
    const task = await this.taskService.create({ title });
    console.log(`Created: ${task.id}`);
  }

  // NG: データレイヤーを直接呼び出す
  async addTask(title: string) {
    const task = await this.repository.save({ title }); // ❌
  }
}
```

**サービスレイヤー**:
```typescript
// 責務: ビジネスロジックの実装
class TaskService {
  // ビジネスロジック: 優先度の自動推定
  async create(data: CreateTaskData): Promise<Task> {
    const task = {
      ...data,
      estimatedPriority: this.estimatePriority(data),
    };
    return this.repository.save(task);
  }
}
```

**データレイヤー**:
```typescript
// 責務: データの永続化
class TaskRepository {
  async save(task: Task): Promise<void> {
    await this.storage.write(task);
  }
}
```

## パフォーマンス要件の設定

### 具体的な数値目標

```
コマンド実行時間: 100ms以内(平均的なPC環境で)
└─ 測定方法: console.timeでCLI起動から結果表示まで計測
└─ 測定環境: CPU Core i5相当、メモリ8GB、SSD

タスク一覧表示: 1000件まで1秒以内
└─ 測定方法: 1000件のダミーデータで計測
└─ 許容範囲: 100件で100ms、1000件で1秒、10000件で10秒
```

## セキュリティ設計

### データ保護の3原則

1. **最小権限の原則**
```bash
# ファイルパーミッション
chmod 600 ~/.devtask/tasks.json  # 所有者のみ読み書き
```

2. **入力検証**
```typescript
function validateTitle(title: string): void {
  if (!title || title.length === 0) {
    throw new ValidationError('タイトルは必須です');
  }
  if (title.length > 200) {
    throw new ValidationError('タイトルは200文字以内です');
  }
}
```

3. **機密情報の管理**
```bash
# 環境変数で管理
export DEVTASK_API_KEY="xxxxx"  # コード内にハードコードしない
```

## スケーラビリティ設計

### データ増加への対応

**想定データ量**: [例: 10,000件のタスク]

**対策**:
- データのページネーション
- 古いデータのアーカイブ
- インデックスの最適化

```typescript
// アーカイブ機能の例: 古いタスクを別ファイルに移動
class ArchiveService {
  async archiveCompletedTasks(olderThan: Date): Promise<void> {
    const oldTasks = await this.repository.findCompleted(olderThan);
    await this.archiveStorage.save(oldTasks);
    await this.repository.deleteMany(oldTasks.map(t => t.id));
  }
}
```

## 依存関係管理

### バージョン管理方針

```json
{
  "dependencies": {
    "commander": "^11.0.0",  // マイナーバージョンアップは自動
    "chalk": "5.3.0"         // 破壊的変更のリスクがある場合は固定
  },
  "devDependencies": {
    "typescript": "~5.3.0",  // パッチバージョンのみ自動
    "eslint": "^9.0.0"
  }
}
```

**方針**:
- 安定版は固定(^でマイナーバージョンまで許可)
- 破壊的変更のリスクがある場合は完全固定
- devDependenciesはパッチバージョンのみ自動(~)

## チェックリスト

- [ ] すべての技術選定に理由が記載されている
- [ ] 採用パターン（縦割り／層分離）が明記され、層分離を選んだ場合は理由が書かれている
- [ ] 「機能名 → ディレクトリ」の対応表がある
- [ ] `shared/` を投機的に作らない規律が書かれている
- [ ] パフォーマンス要件が測定可能である
- [ ] セキュリティ考慮事項が記載されている
- [ ] スケーラビリティが考慮されている
- [ ] バックアップ戦略が定義されている
- [ ] 依存関係管理のポリシーが明確である
- [ ] テスト戦略が定義されている