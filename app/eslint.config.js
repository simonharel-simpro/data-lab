import js from '@eslint/js';
import tseslint from 'typescript-eslint';
import astro from 'eslint-plugin-astro';
import pluginSecurity from 'eslint-plugin-security';

export default [
  { ignores: ['dist/', '.astro/', 'node_modules/', 'test-fixtures/'] },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  ...astro.configs['flat/recommended'],
  pluginSecurity.configs.recommended,
  {
    // build-time code: reads repo files and indexes repo data, never user input
    files: ['src/lib/**'],
    rules: { 'security/detect-non-literal-fs-filename': 'off', 'security/detect-object-injection': 'off' },
  },
  {
    rules: {
      '@typescript-eslint/no-explicit-any': 'error',
      '@typescript-eslint/consistent-type-imports': 'error',
    },
  },
];
