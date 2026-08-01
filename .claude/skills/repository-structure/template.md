# リポジトリ構造定義書 (Repository Structure Document)

> **注記:** ファイル名・拡張子の例は TypeScript (`.ts`) で記載しています。プロジェクトの言語の慣習（`.py` / `.go` / `.rs` や snake_case 等）に読み替えてください。

## プロジェクト構造

> **既定は機能単位の縦割り**（`docs/architecture.md` の採用パターンと必ず一致させること）。
> 層分離を採用した場合のみ、下の「例外: 層分離を採用した場合」の構造に差し替える。

```
project-root/
├── src/
│   ├── features/          # 機能単位のスライス（1機能=1ディレクトリ）
│   │   ├── [機能1]/
│   │   │   ├── index.ts       # 唯一の入口
│   │   │   ├── handler.ts     # ビジネス判断
│   │   │   ├── validate.ts    # 検証（この機能専用）
│   │   │   ├── types.ts
│   │   │   └── [機能1].test.ts
│   │   └── [機能2]/
│   └── shared/            # 3スライス以上で実際に重複してから作る
├── tests/                 # 横断テストのみ（ユニットテストはスライス内に同居）
│   ├── integration/
│   └── e2e/
├── docs/                  # プロジェクトドキュメント
├── config/                # 設定ファイル
└── scripts/               # ビルド・デプロイスクリプト
```

**例外: 層分離を採用した場合**（`docs/architecture.md` に理由を書いたときのみ）

```
src/
├── [layer1]/              # [説明]
├── [layer2]/              # [説明]
└── [layer3]/              # [説明]
```

## ディレクトリ詳細

### src/ (ソースコードディレクトリ)

#### [ディレクトリ1]

**役割**: [説明]

**配置ファイル**:
- [ファイルパターン1]: [説明]
- [ファイルパターン2]: [説明]

**命名規則**:
- [規則1]
- [規則2]

**依存関係**:
- 依存可能: [ディレクトリ名]
- 依存禁止: [ディレクトリ名]

**例**:
```
[ディレクトリ名]/
├── [example-file1].ts
└── [example-file2].ts
```

#### [ディレクトリ2]

**役割**: [説明]

**配置ファイル**:
- [ファイルパターン1]: [説明]

**命名規則**:
- [規則1]

**依存関係**:
- 依存可能: [ディレクトリ名]
- 依存禁止: [ディレクトリ名]

### tests/ (テストディレクトリ)

#### unit/

**役割**: ユニットテストの配置

**既定（縦割り）**: ユニットテストは `tests/unit/` に集めず、**テスト対象と同じスライス内に置く**。
1機能を読むのに開くディレクトリを増やさないため。

```
src/features/create-order/
├── handler.ts
└── create-order.test.ts    # 対象の隣
```

**層分離を採用した場合のみ**:
```
tests/unit/
└── src/                    # srcディレクトリと同じ構造
    └── [layer]/
        └── [filename].test.ts
```

**命名規則**:
- パターン: `[テスト対象ファイル名].test.ts`
- 例: `TaskService.ts` → `TaskService.test.ts`

#### integration/

**役割**: 統合テストの配置

**構造**:
```
tests/integration/
└── [feature]/              # 機能単位でディレクトリ分割
    └── [scenario].test.ts
```

#### e2e/

**役割**: E2Eテストの配置

**構造**:
```
tests/e2e/
└── [user-scenario]/        # ユーザーシナリオ単位
    └── [flow].test.ts
```

### docs/ (ドキュメントディレクトリ)

**配置ドキュメント**:
- `product-requirements.md`: プロダクト要求定義書
- `functional-design.md`: 機能設計書
- `architecture.md`: アーキテクチャ設計書
- `repository-structure.md`: リポジトリ構造定義書(本ドキュメント)
- `development-guidelines.md`: 開発ガイドライン
- `glossary.md`: 用語集

### config/ (設定ファイルディレクトリ - 該当する場合)

**配置ファイル**:
- 設定ファイル
- 定数定義ファイル

**例**:
```
config/
├── default.ts
└── constants.ts
```

### scripts/ (スクリプトディレクトリ - 該当する場合)

**配置ファイル**:
- ビルドスクリプト
- 開発補助スクリプト

## ファイル配置規則

### ソースファイル

| ファイル種別 | 配置先 | 命名規則 | 例 |
|------------|--------|---------|-----|
| [種別1] | [ディレクトリ] | [規則] | [例] |
| [種別2] | [ディレクトリ] | [規則] | [例] |

### テストファイル

| テスト種別 | 配置先 | 命名規則 | 例 |
|-----------|--------|---------|-----|
| ユニットテスト | tests/unit/ | [対象].test.ts | TaskService.test.ts |
| 統合テスト | tests/integration/ | [機能].test.ts | task-crud.test.ts |
| E2Eテスト | tests/e2e/ | [シナリオ].test.ts | user-workflow.test.ts |

### 設定ファイル

| ファイル種別 | 配置先 | 命名規則 |
|------------|--------|---------|
| 環境設定 | config/environments/ | [環境名].ts |
| ツール設定 | プロジェクトルート | [ツール名].config.js |
| 型定義 | src/types/ | [対象].d.ts |

## 命名規則

### ディレクトリ名

- **機能スライス（既定）**: 動詞＋対象、kebab-case。1ユースケース=1ディレクトリ
  - 例: `create-order/`, `get-order/`, `cancel-order/`
  - 「注文機能」のような大括りにせず、ユースケース単位で割る
- **レイヤーディレクトリ**（層分離を採用した場合のみ）: 複数形、kebab-case
  - 例: `services/`, `repositories/`, `controllers/`

### ファイル名

- **クラスファイル**: PascalCase
  - 例: `TaskService.ts`, `UserRepository.ts`
- **関数ファイル**: camelCase
  - 例: `formatDate.ts`, `validateEmail.ts`
- **定数ファイル**: UPPER_SNAKE_CASE
  - 例: `API_ENDPOINTS.ts`, `ERROR_MESSAGES.ts`

### テストファイル名

- パターン: `[テスト対象].test.ts` または `[テスト対象].spec.ts`
- 例: `TaskService.test.ts`, `formatDate.spec.ts`

## 依存関係のルール

### スライス間の依存（既定）

```
features/[機能A]/  →  features/[機能B]/index.ts   (OK: 入口経由のみ)
features/[機能A]/  →  shared/                     (OK)
features/[機能A]/  →  features/[機能B]/handler.ts (❌ 内部への直接参照)
shared/            →  features/                   (❌ 逆流)
```

**`shared/` を作る条件**: 同じコードが **3スライス以上で実際に重複してから** 移す。
「そのうち共通化するから」で先に作ると、共有層という形で層構造が復活する。

**スライスの外を触る変更**（`shared/` の変更・スライス新設・スライス間依存の追加）は
実装者の裁量で黙って行わず、`.steering/` に仕様級の判断として書き戻す。

### レイヤー間の依存（層分離を採用した場合のみ）

```
UIレイヤー
    ↓ (OK)
サービスレイヤー
    ↓ (OK)
データレイヤー
```

**禁止される依存**:
- データレイヤー → サービスレイヤー (❌)
- データレイヤー → UIレイヤー (❌)
- サービスレイヤー → UIレイヤー (❌)

### モジュール間の依存

**循環依存の禁止**:
```typescript
// ❌ 悪い例: 循環依存
// fileA.ts
import { funcB } from './fileB';

// fileB.ts
import { funcA } from './fileA';  // 循環依存
```

**解決策**:
```typescript
// ✅ 良い例: 共通モジュールの抽出
// shared.ts
export interface SharedType { /* ... */ }

// fileA.ts
import { SharedType } from './shared';

// fileB.ts
import { SharedType } from './shared';
```

## スケーリング戦略

### 機能の追加

新しい機能を追加する際の配置方針（縦割りの場合）:

1. **原則**: 規模によらず `src/features/<ユースケース名>/` を1つ足す（既存スライスに相乗りしない）
2. **大きすぎるスライス**: ユースケース単位に割り直す（1スライス1ユースケース）
3. **重複が出た**: 3スライスで重複してから `shared/` へ移す

**例**:
```
src/features/
├── create-task/          # 既存
├── list-tasks/           # 既存
└── archive-task/         # 追加: 新しいスライスを1つ足すだけ
```

**併せて `docs/architecture.md` の「機能名→ディレクトリ」対応表に1行追加する。**

### ファイルサイズの管理

**ファイル分割の目安**:
- 1ファイル: 300行以下を推奨
- 300-500行: リファクタリングを検討
- 500行以上: 分割を強く推奨

**分割方法**:
```typescript
// 悪い例: 1ファイルに全機能
// TaskService.ts (800行)

// 良い例: 責務ごとに分割
// TaskService.ts (200行) - CRUD操作
// TaskValidationService.ts (150行) - バリデーション
// TaskNotificationService.ts (100行) - 通知処理
```

## 特殊ディレクトリ

### .steering/ (ステアリングファイル)

**役割**: 特定の開発作業における「今回何をするか」を定義

**構造**:
```
.steering/
└── [YYYYMMDD]-[task-name]/
    ├── requirements.md      # 今回の作業の要求内容
    ├── design.md            # 変更内容の設計
    └── tasklist.md          # タスクリスト
```

**命名規則**: `20250115-add-user-profile` 形式

### .claude/ (Claude Code設定)

**役割**: Claude Code設定とカスタマイズ

**構造**:
```
.claude/
├── commands/                # スラッシュコマンド
├── skills/                  # タスクモード別スキル
└── agents/                  # サブエージェント定義
```

## 除外設定

### .gitignore

プロジェクトで除外すべきファイル:
- `node_modules/`
- `dist/`
- `.env`
- `.steering/` (タスク管理用の一時ファイル)
- `*.log`
- `.DS_Store`

### .prettierignore, .eslintignore

ツールで除外すべきファイル:
- `dist/`
- `node_modules/`
- `.steering/`
- `coverage/`