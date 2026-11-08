# Fix Plan — Phase 6: App formatter + linter (#13)

**Severity:** 🟡
**Agent:** general-purpose. App conventions: Astro 7 + TS strict + `noUncheckedIndexedAccess`; zod from `astro/zod`; tests are `node:test` files `src/lib/*.test.ts` (`npm test`, coverage floor 70 %); `npm run check` = `astro check`; no `any`, no `@ts-ignore`; **exact** version pins in `package.json` (no `^`/`~`); `package-lock.json` committed; node ≥ 22.22 (`.nvmrc`).
**Depends on:** Phase 3 (3.3 edits `app/src/lib`; the one-time rewrite in 6.2 comes after it)
**Fix units:** 3
**Files affected:** 8 existing (+ 3 new; 6.2 rewrites `app/src` as a whole)
**Closes:** #13 (put `Closes #13` in the PR body)

**Pins (from #13: published at least 14 days before 2026-11-08, so before 2026-10-25; verified on the npm registry):**

| Package | Version | Published |
|---|---|---|
| `prettier` | `3.9.10` | 2026-10-10 |
| `prettier-plugin-astro` | `1.1.2` | 2026-10-23 |
| `eslint` | `10.13.0` | 2026-10-16 |
| `@eslint/js` | `10.0.1` | 2026-02-06 |
| `eslint-plugin-astro` | `3.2.1` | 2026-09-17 |
| `typescript-eslint` | `8.72.0` | 2026-10-19 (peer `typescript >=4.8.4 <6.1.0`: OK with 6.0.3) |

Do **not** take a newer version (eslint 10.14.0 and typescript-eslint 8.72.1 are under 14 days old). If `npm audit --audit-level=moderate` fails on one of these pins, stop and report. Never `--force`.

## Within-phase Dependencies

6.1 → 6.2 → 6.3. 6.2 is a one-time mechanical rewrite in its own commit (`style(app): prettier --write`), so the PR review can skip it. Record its hash in `.git-blame-ignore-revs`, and create that file if it is absent.

## Fix Units

### Fix Unit 6.1: Dependencies, configs, scripts
- **Files:** `app/package.json`, `app/package-lock.json`
- **New files:** `app/eslint.config.js`, `app/.prettierrc.json`, `app/.prettierignore`
- **Violation pattern (Grep):** `N/A`
- **Expected after fix:** 0 matches
- **Reference example:** target `eslint.config.js`:
  ```js
  import js from '@eslint/js';
  import tseslint from 'typescript-eslint';
  import astro from 'eslint-plugin-astro';

  export default [
    { ignores: ['dist/', '.astro/', 'node_modules/', 'test-fixtures/'] },
    js.configs.recommended,
    ...tseslint.configs.recommended,
    ...astro.configs['flat/recommended'],
    {
      rules: {
        '@typescript-eslint/no-explicit-any': 'error',
        '@typescript-eslint/consistent-type-imports': 'error',
      },
    },
  ];
  ```
- **HOW TO FIX:**
  1. `npm install --save-dev --save-exact` the six pins above (one command, then check `package.json` has no `^`).
  2. `.prettierrc.json`: match the existing style so that the rewrite in 6.2 stays small. That style is single quotes, semicolons, trailing commas and 120 columns (see `src/lib/ledger.ts`): `{"printWidth": 120, "singleQuote": true, "trailingComma": "all", "plugins": ["prettier-plugin-astro"], "overrides": [{"files": "*.astro", "options": {"parser": "astro"}}]}`. `.prettierignore`: `dist/`, `.astro/`, `node_modules/`, `package-lock.json`, `test-fixtures/`.
  3. `package.json` scripts: `"lint": "eslint ."`, `"format": "prettier --write ."`, `"format:check": "prettier --check ."`.
  4. `npm audit --audit-level=moderate` → 0; `npm run check && npm test` are still green.

### Fix Unit 6.2: One-time format, then lint clean
- **Files:** `app/src`, `app/astro.config.mjs`
- **Violation pattern (Grep):** `N/A`
- **Expected after fix:** 0 matches
- **Reference example:** —
- **HOW TO FIX:**
  1. `npm run format`, then commit **only** that (`style(app): prettier --write (one-time, #13)`). Add the hash to `.git-blame-ignore-revs`.
  2. `npm run lint`. Fix by hand: `consistent-type-imports` (REVIEW §2 🔵: `src/lib/mlflow.ts:5-10`, `src/lib/weavit.ts:2` mix value and type imports; `npx eslint --fix` handles most), and any `astro/*` findings. While here, fix the two `(err as Error).message` casts (`ledger.ts:107`, `mlflow.ts:119`) as `err instanceof Error ? err.message : String(err)`. Do not disable a rule to get green. A rule that is wrong for Astro gets a scoped `files:` override in `eslint.config.js` with a comment.
  3. `npm run lint && npm run format:check && npm run check && npm test && npm run build` are all green.

### Fix Unit 6.3: Wire into CI and the `gates-app` pre-push hook; record the choice
- **Files:** `.github/workflows/ci.yml`, `.pre-commit-config.yaml`, `decisions.md`, `ARCHITECTURE.md`
- **Violation pattern (Grep):** `cd app && npm run check && npm test'`
- **Expected after fix:** 0 matches
- **Reference example:** the `app` job steps in `ci.yml` (`npm audit`, then `astro check`).
- **HOW TO FIX:**
  1. `ci.yml`, job `app`: after `npm audit`, add the steps `- name: lint (eslint)` → `run: npm run lint` and `- name: format (prettier --check)` → `run: npm run format:check`.
  2. `.pre-commit-config.yaml`, hook `gates-app`: `entry: bash -c 'cd app && npm run lint && npm run format:check && npm run check && npm test'`. Update the CI header comment if it lists the app gates.
  3. `decisions.md`: ADR "App formatter + linter: prettier + eslint flat config". Context: #13. Decision: the pins, typescript-eslint `recommended` + `no-explicit-any` + `consistent-type-imports`, eslint-plugin-astro `flat/recommended`, prettier matched to the existing style. Alternatives: Biome (no Astro template support at the pinned date), or no formatter. Consequences: one rewrite commit, in `.git-blame-ignore-revs`.
  4. `ARCHITECTURE.md` Tech Stack + "App" layer: add eslint/prettier and the npm scripts.

## Verification

- `grep -n "cd app && npm run check && npm test'" .pre-commit-config.yaml` → 0.
- `cd app && npm ci && npm audit --audit-level=moderate && npm run lint && npm run format:check && npm run check && npm test && npm run build`.
- `/check`, then a PR whose body says `Closes #13`.

<!-- plan-validate: READY 2026-11-08 sha256:627a6b6499db -->
