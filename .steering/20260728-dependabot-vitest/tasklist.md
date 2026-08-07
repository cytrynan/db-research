# tasklist: Dependabot vitest アラート対応（20260728-dependabot-vitest）

tracking: #6

- [x] node-ts スタックの vitest 系 devDependencies を ^3.2.6 へ更新 (#7)
  - [x] `vitest` / `@vitest/ui` / `@vitest/coverage-v8` の3つを揃えて更新（他の依存は触らない）
  - [x] `vitest.config.ts`・`example.test.ts` が v3 で有効なことを目視確認
- [x] scratch 環境で依存解決とテスト実行を検証 (#8)
  - [x] プレースホルダを仮値に置換したコピーで `npm install` が成功する（269パッケージ・30秒）
  - [x] `npx vitest run` でサンプルテストが PASS する（7/7）
  - [x] インストールされた vitest が 3.2.6 以上であることを確認（3.2.7）
- [x] push して Dependabot アラートの解消を確認 (#9)
  - [x] 1コミット（日本語要約1行）で origin/main へ push（07c40a6）
  - [x] `gh api` でアラート #1 の state が fixed（2026-07-28T03:28:44Z）になったことを確認
