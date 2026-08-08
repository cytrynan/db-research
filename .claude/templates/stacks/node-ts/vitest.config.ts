import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    globals: true,
    environment: 'node',
    include: [
      'src/**/*.{test,spec}.{ts,tsx}',
      'tests/**/*.{test,spec}.{ts,tsx}',
    ],
    coverage: {
      provider: 'v8',
      reporter: ['text', 'json', 'html'],
      exclude: [
        'node_modules/**',
        'dist/**',
        '.steering/**',
        // テンプレ素材（`.claude/templates/stacks/*` の雛形ソース）はプロジェクトのコードではない。
        // 除外しないとカバレッジの分母に入り、閾値が実力と無関係に割れる（2026-08-08 実測: 97% → 80.4%）。
        '.claude/**',
        '**/*.config.{ts,js}',
        '**/types/**',
      ],
      thresholds: {
        branches: 80,
        functions: 80,
        lines: 80,
        statements: 80,
      },
    },
  },
});
