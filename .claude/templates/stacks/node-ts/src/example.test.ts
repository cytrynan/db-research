import { describe, it, expect } from 'vitest';
import { add, subtract, multiply, divide } from './example';

describe('Math operations', () => {
  describe('add', () => {
    it('正の数を足すと正しい結果が返る', () => {
      // Given: 準備
      const a = 2;
      const b = 3;

      // When: 実行
      const result = add(a, b);

      // Then: 検証
      expect(result).toBe(5);
    });

    it('負の数を足すと正しい結果が返る', () => {
      // Given: 準備
      const a = -2;
      const b = 3;

      // When: 実行
      const result = add(a, b);

      // Then: 検証
      expect(result).toBe(1);
    });
  });

  describe('subtract', () => {
    it('正の数を引くと正しい結果が返る', () => {
      // Given: 準備
      const a = 5;
      const b = 3;

      // When: 実行
      const result = subtract(a, b);

      // Then: 検証
      expect(result).toBe(2);
    });
  });

  describe('multiply', () => {
    it('正の数をかけると正しい結果が返る', () => {
      // Given: 準備
      const a = 2;
      const b = 3;

      // When: 実行
      const result = multiply(a, b);

      // Then: 検証
      expect(result).toBe(6);
    });

    it('0をかけると0が返る', () => {
      // Given: 準備
      const a = 5;
      const b = 0;

      // When: 実行
      const result = multiply(a, b);

      // Then: 検証
      expect(result).toBe(0);
    });
  });

  describe('divide', () => {
    it('正の数で割ると正しい結果が返る', () => {
      // Given: 準備
      const a = 6;
      const b = 3;

      // When: 実行
      const result = divide(a, b);

      // Then: 検証
      expect(result).toBe(2);
    });

    it('0で割るとエラーをスローする', () => {
      // Given: 準備
      const a = 5;
      const b = 0;

      // When/Then: 実行と検証
      expect(() => divide(a, b)).toThrow('Division by zero is not allowed');
    });
  });
});
