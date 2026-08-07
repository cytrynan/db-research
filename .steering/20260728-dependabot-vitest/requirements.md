Dependabot critical アラート #1（vitest < 3.2.6・Vitest UI サーバー稼働時に任意ファイルの読取・実行が可能）を解消する。

- 対象: `.claude/templates/stacks/node-ts/package.json` の vitest 系 devDependencies（現状 `^2.0.0`）
- 修正版: vitest 3.2.6 以上（アラートの first_patched_version = 3.2.6）
- このリポジトリはテンプレートであり、ここで直さないと **今後 node-ts スタックで作る全プロジェクトに脆弱な版が伝播する**
- 制約: `{{PROJECT_NAME}}` 等のプレースホルダ構造は維持する（/init-stack が置換する前提）
