import eslint from '@eslint/js';
import tseslint from 'typescript-eslint';
import prettierConfig from 'eslint-config-prettier';

export default tseslint.config(
  eslint.configs.recommended,
  ...tseslint.configs.recommended,
  prettierConfig,
  {
    rules: {
      '@typescript-eslint/no-unused-vars': [
        'error',
        { argsIgnorePattern: '^_' },
      ],
      '@typescript-eslint/explicit-function-return-type': 'off',
      '@typescript-eslint/explicit-module-boundary-types': 'off',
      '@typescript-eslint/no-explicit-any': 'warn',
    },
  },
  {
    // `.claude/**` は必ず除外する。テンプレ素材 `templates/stacks/*` に別の tsconfig を持つ
    // 雛形が入っており、除外しないと typescript-eslint が
    // 「No tsconfigRootDir was set, and multiple candidate TSConfigRootDirs are present」で
    // 解析に失敗する（typescript-eslint を更新した瞬間に lint が全滅する。2026-08-08 実測）。
    ignores: ['node_modules/**', 'dist/**', '.steering/**', '.claude/**'],
  }
);
