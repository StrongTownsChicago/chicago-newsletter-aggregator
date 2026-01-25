/// <reference types="vitest" />
import { defineConfig } from 'vitest/config';
import path from 'path';

export default defineConfig({
  test: {
    environment: 'happy-dom',
    globals: true,
    include: ['src/tests/**/*.test.ts'],
    alias: {
      'astro:middleware': path.resolve(__dirname, './src/tests/mocks/astro-middleware.ts'),
    },
    coverage: {
      provider: 'v8',
      reporter: ['text', 'json', 'html'],
      include: ['src/**/*.ts'],
      exclude: ['src/tests/**'],
    },
  },
});
