## 技術スタック

- 開発環境: devcontainer
- Node.js LTS (v22.x)
- TypeScript 5.x
- パッケージマネージャー: npm
- テストフレームワーク: Vitest
- Lint: ESLint v9 + typescript-eslint
- Format: Prettier
- Git フック: Husky + lint-staged

## 主要コマンド

```bash
npm run build         # TypeScript コンパイル
npm run dev           # ウォッチモードでコンパイル
npm run lint          # ESLint チェック
npm run format        # Prettier フォーマット
npm run typecheck     # 型チェック
npm test              # テスト実行
npm run test:watch    # テストウォッチモード
npm run test:coverage # カバレッジ計測
```
