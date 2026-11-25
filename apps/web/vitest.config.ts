import path from 'node:path';
import { defineConfig } from 'vitest/config';

export default defineConfig({
  // tsconfig keeps `jsx: preserve` for Next; tests compile JSX themselves.
  esbuild: { jsx: 'automatic' },
  resolve: {
    alias: { '@': path.resolve(__dirname) },
  },
  test: {
    // Component tests opt into jsdom with `// @vitest-environment jsdom`.
    environment: 'node',
    exclude: ['node_modules', '.next', 'e2e'],
  },
});
