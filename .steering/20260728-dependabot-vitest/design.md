# design: Dependabot vitest アラート対応

## 方針

vitest を major 2 → 3 に上げる（アラートのパッチ版 3.2.6 が 3系のため）。
vitest 本体とコンパニオンパッケージは major を揃える必要があるため、3点セットで更新する:

| パッケージ | 現状 | 変更後 |
|---|---|---|
| `vitest` | `^2.0.0` | `^3.2.6` |
| `@vitest/ui` | `^2.0.0` | `^3.2.6` |
| `@vitest/coverage-v8` | `^2.0.0` | `^3.2.6` |

他の devDependencies（eslint/prettier/typescript 等）は今回触らない（アラート対象外・1改良=1コミットの原則）。

## 影響確認

- vitest は node-ts スタックにのみ登場（go/python/rust/claude-md-sections には無し）
- `vitest.config.ts` は `defineConfig` + `test.globals/environment/coverage` のみ → v3 でも有効な構文
- `src/example.test.ts` は `describe/it/expect` のみ → 破壊的変更の影響なし
- vitest 3 の要求 Node は ^18.0.0 || ^20.0.0 || >=22 → `@types/node ^20` と整合

## 検証方法（テンプレのため実プロジェクトが無い）

scratch ディレクトリにスタック一式をコピーし、プレースホルダを仮値に置換して
`npm install` → `npx vitest run` を実行。依存解決とサンプルテスト PASS を確認する。
push 後、`gh api` で Dependabot アラート #1 の state が fixed になることを確認する。
