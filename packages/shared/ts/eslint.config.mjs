import { fileURLToPath } from 'node:url';
import { dirname } from 'node:path';
import tseslint from 'typescript-eslint';

const __dirname = dirname(fileURLToPath(import.meta.url));

export default tseslint.config(
  {
    files: ['src/**/*.ts'],
    extends: [tseslint.configs.recommendedTypeChecked],
    languageOptions: {
      parserOptions: {
        projectService: true,
        tsconfigRootDir: __dirname,
      },
    },
  },
  {
    ignores: ['node_modules/', 'dist/', '*.config.*'],
  },
);
