# Fix Plan — Phase 6: App formatter + linter (#13)

**Status:** ✅ Complete — branch fix-phase-6-app-format-lint, 2026-11-09
**Severity:** 🟡
**Agent:** general-purpose. App conventions: Astro 7 + TS strict + `noUncheckedIndexedAccess`; zod from `astro/zod`; tests are `node:test` files `src/lib/*.test.ts` (`npm test`, coverage floor 70 %); `npm run check` = `astro check`; no `any`, no `@ts-ignore`; **exact** version pins in `package.json` (no `^`/`~`); `package-lock.json` committed; node ≥ 22.22 (`.nvmrc`).
**Depends on:** Phase 3 (3.3 edits `app/src/lib`; the one-time rewrite in 6.2 comes after it)
**Fix units:** 3
**Files affected:** 8 existing (+ 4 new: 3 app configs and `.git-blame-ignore-revs`; 6.2 rewrites `app/` as a whole)
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

**Amendment 2026-11-09 (ESC-6-1; user decisions 2026-11-08 and 2026-11-09).** The pins above fail `npm audit --audit-level=moderate`: GHSA-g3hv-75wg-m249 (minimatch ReDoS, `>=7.0.0 <11.0.1`, 11 moderate) through `eslint@10.13.0`, `@eslint/config-array@0.23.5` and `@typescript-eslint/typescript-estree@8.72.0`, which resolve `minimatch@10.2.6`. The first fixed release is `minimatch@11.0.1` (published 2026-10-27, so under 14 days old on 2026-11-08/09). `minimatch@11.0.1` adds one new transitive dependency, `@isaacs/nonrecursive-glob-match` (`^1.0.1`; the package was created 2026-10-26, so no version is 14 days old either). Its other dependency, `brace-expansion` `^5.0.12` (2026-09-14), already meets the rule. **Exception, for exactly these two packages:** pin both through npm `overrides`, exact.

The 14-day rule applies to the **whole resolved tree** (user decision 2026-11-09). A scratch `npm install --package-lock-only` of these pins (2026-11-09) resolved six more packages under 14 days old: `@eslint-community/regexpp` 4.12.3, `globals` 17.14.0, `postcss-selector-parser` 7.2.0, `@typescript-eslint/{scope-manager,types,visitor-keys}` 8.72.1. Each gets an exact override to an older release that is inside every dependent's declared range and at least 14 days old. With all eight overrides the scratch resolve left only the two exceptions under 14 days, and `npm audit` reported 0 vulnerabilities.

| Package | Version | Published | Why |
|---|---|---|---|
| `minimatch` | `11.0.1` | 2026-10-27 | Fixes GHSA-g3hv-75wg-m249. **Exempt from the 14-day rule (ESC-6-1)** |
| `@isaacs/nonrecursive-glob-match` | `1.0.1` | 2026-10-27 | New dependency of minimatch 11.0.1 (the oldest release its `^1.0.1` accepts). **Exempt (ESC-6-1)** |
| `@eslint-community/regexpp` | `4.12.2` | 2025-10-22 | 14-day rule (4.12.3 is 2026-11-08) |
| `globals` | `17.13.0` | 2026-10-01 | 14-day rule (17.14.0 is 2026-11-01) |
| `postcss-selector-parser` | `7.1.7` | 2026-10-20 | 14-day rule (7.2.0 is 2026-11-08) |
| `@typescript-eslint/scope-manager` | `8.72.0` | 2026-10-19 | 14-day rule (8.72.1 is 2026-10-26); same version `typescript-eslint` pins |
| `@typescript-eslint/types` | `8.72.0` | 2026-10-19 | same |
| `@typescript-eslint/visitor-keys` | `8.72.0` | 2026-10-19 | same |

The exact `"overrides"` block for `app/package.json`:
```json
"overrides": {
  "minimatch": "11.0.1",
  "@isaacs/nonrecursive-glob-match": "1.0.1",
  "@eslint-community/regexpp": "4.12.2",
  "globals": "17.13.0",
  "postcss-selector-parser": "7.1.7",
  "@typescript-eslint/scope-manager": "8.72.0",
  "@typescript-eslint/types": "8.72.0",
  "@typescript-eslint/visitor-keys": "8.72.0"
}
```

All three dependents declare `minimatch` `^10`, so the override is a major bump outside their ranges. It is accepted only if eslint runs under it, judged by exit code: `npm run lint` **exit 0 or 1** (1 = lint findings) is accepted; **exit 2 or an uncaught exception** is a crash. On a crash whose output mentions `minimatch` or `@isaacs/nonrecursive-glob-match`, **stop and report under ESC-6-1**: do not try another version of either package, do not drop an override, and do not add an audit exception (the user decides). Any other crash (e.g. a config error) is a plan or config defect: report it as such, without blaming the override.

## Within-phase Dependencies

6.1 → 6.2 → 6.3. 6.2 is a one-time mechanical rewrite in its own commit (`style(app): prettier --write (one-time, #13)`), so the PR review can skip it.

**Dispatches and commit ownership** (the implementing agent never commits):
- **Dispatch A (agent):** 6.1 steps 1–5, then 6.2 step 1. Hand back.
- **Orchestrator:** commit 6.1's files (`app/package.json`, `app/package-lock.json`, the three new configs) as `build(app): eslint + prettier pins, configs, scripts (#13)`, then the rest of the rewrite alone as `style(app): prettier --write (one-time, #13)`. Then 6.2 step 2.
- **Dispatch B (agent):** 6.2 steps 3–4, then 6.3. Hand back.

Land with a **merge commit** only. Never squash or rebase-merge: both rewrite the rewrite commit's hash, and `.git-blame-ignore-revs` names that hash.

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
  1. Add the exact `"overrides"` block from the Amendment to `app/package.json` first, then `npm install --save-dev --save-exact` the six pins above (one command, then check `package.json` has no `^`). For each of the eight overridden packages run `npm ls <package>`: every line naming `<package>` shows the table's version (`overridden` / `deduped` are expected). If any `npm ls` exits non-zero, prints `invalid`, or shows another version, **stop and report under ESC-6-1**. Do not change a version or drop an override.
  2. Write `app/eslint.config.js` with exactly the Reference example content above.
  3. `.prettierrc.json`: match the existing style so that the rewrite in 6.2 stays small. That style is single quotes, semicolons, trailing commas and 120 columns (see `src/lib/ledger.ts`): `{"printWidth": 120, "singleQuote": true, "trailingComma": "all", "plugins": ["prettier-plugin-astro"], "overrides": [{"files": "*.astro", "options": {"parser": "astro"}}]}`. `.prettierignore`: `dist/`, `.astro/`, `node_modules/`, `package-lock.json`, `test-fixtures/`.
  4. `package.json` scripts: `"lint": "eslint ."`, `"format": "prettier --write ."`, `"format:check": "prettier --check ."`.
  5. `npm audit --audit-level=moderate` → exit 0; `npm run check && npm test` are still green; `npx eslint --version` runs, and `npm run lint` exits 0 or 1 under the overrides (findings are fixed in 6.2; exit 2 or an exception → the Amendment's stop rule). Do **not** run `npm run format` in 6.1.

### Fix Unit 6.2: One-time format, then lint clean
- **Files:** whatever `prettier --write .` rewrites under `app/` (validator dry run 2026-11-09: 27 files under `app/src/` plus `app/.prettierrc.json`; the reformatted `.prettierrc.json` goes into the `build(app)` commit with the other 6.1 files)
- **New files:** `.git-blame-ignore-revs` (repo root)
- **Violation pattern (Grep):** `N/A`
- **Expected after fix:** 0 matches
- **Reference example:** —
- **HOW TO FIX:**
  1. **(Dispatch A, agent)** From `app/`: `npm run format`. Change nothing else, and hand back.
  2. **(Orchestrator)** After the rewrite commit: write its full 40-character hash to `.git-blame-ignore-revs` at the repo root (create the file if absent), preceded by the comment line `# prettier one-time format (#13)`. This file lands with the rest of the phase, not in the rewrite commit.
  3. **(Dispatch B, agent)** `npm run lint`, then `npx eslint --fix .`, then fix by hand **only what `npm run lint` still reports**. The configured `consistent-type-imports` accepts inline `type` specifiers (`import { a, type B }`), so leave those as they are. Expected single remaining finding after `eslint --fix` (validator dry run 2026-11-09): `preserve-caught-error` in `src/lib/mlflow-rest.ts`, on the `throw new Error(\`${path}: …\`)` inside the `catch`. Fix: add the second argument `{ cause: err }`. Also fix the two `(err as Error).message` casts (`ledger.ts:107`, `mlflow.ts:119`; re-find them after the rewrite) as `err instanceof Error ? err.message : String(err)`. Do not disable or override any rule. If a finding cannot be fixed without that (e.g. an `astro/*` rule that misreads valid Astro syntax), **stop and report** the rule, file and line. The user decides.
  4. `npm run lint && npm run format:check && npm run check && npm test && npm run build` are all green.

### Fix Unit 6.3: Wire into CI and the `gates-app` pre-push hook; record the choice
- **Files:** `.github/workflows/ci.yml`, `.pre-commit-config.yaml`, `decisions.md`, `ARCHITECTURE.md`
- **Violation pattern (Grep):** `cd app && npm run check && npm test'`
- **Expected after fix:** 0 matches
- **Reference example:** the `app` job steps in `ci.yml` (`npm audit`, then `astro check`).
- **HOW TO FIX:**
  1. `ci.yml`, job `app`: after `npm audit`, add the steps `- name: lint (eslint)` → `run: npm run lint` and `- name: format (prettier --check)` → `run: npm run format:check`.
  2. `.pre-commit-config.yaml`, hook `gates-app`: `entry: bash -c 'cd app && npm run lint && npm run format:check && npm run check && npm test'`, and `name: app lint + format check + astro check + unit tests + coverage floor`. Leave the `ci.yml` header comment (lines 1–2) unchanged: it does not list the app gates.
  3. `decisions.md`: ADR "App formatter + linter: prettier + eslint flat config". Context: #13. Decision: the pins, typescript-eslint `recommended` + `no-explicit-any` + `consistent-type-imports`, eslint-plugin-astro `flat/recommended`, prettier matched to the existing style. Alternatives: Biome (no Astro template support at the pinned date), or no formatter. Consequences: one rewrite commit, in `.git-blame-ignore-revs`. Also record the eight overrides (the Amendment table): the two exceptions (`minimatch` 11.0.1, `@isaacs/nonrecursive-glob-match` 1.0.1), why (GHSA-g3hv-75wg-m249, ESC-6-1), that they are a dated exception to the 14-day rule (decided 2026-11-08/09; both releases pass 14 days on 2026-11-10), and that the minimatch override crosses the dependents' `^10` range; the six in-range overrides that keep the whole resolved tree under the 14-day rule. Removal condition: once eslint and typescript-eslint ship releases that depend on a fixed minimatch and are at least 14 days old, re-pin and drop every override whose package is then at least 14 days old in its natural resolution.
  4. `ARCHITECTURE.md` Tech Stack + "App" layer: add eslint/prettier and the npm scripts. Update the hooks line that spells out the `gates-app` command (currently line 34: `` `gates-app` (`npm run check && npm test`; ``) to the new entry's commands.

## Verification

- `grep -n "cd app && npm run check && npm test'" .pre-commit-config.yaml` → 0.
- `cd app && npm ci && npm audit --audit-level=moderate && npm run lint && npm run format:check && npm run check && npm test && npm run build`.
- `/check`, then a PR whose body says `Closes #13`.

<!-- plan-validate: READY 2026-11-09 sha256:3e00a2857214 -->
