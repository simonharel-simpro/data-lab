# Fix Plan — Phase 3: App boundaries (TS)

**Status:** ✅ Complete — branch fix-phase-3-app-boundaries, 2026-11-05
**Severity:** 🟡
**Agent:** general-purpose. Brief it on `app/` conventions:
- Astro 7.4.1 static output;
- `src/lib/*.ts` must **not** import `astro:*`, so that `node --test` (type stripping) runs them;
- zod comes from `astro/zod` (already in `src/lib/card.ts`) and resolves under plain node;
- tests are `src/**/*.test.ts`, written with `import { test, beforeEach } from 'node:test'` and `import assert from 'node:assert/strict'`;
- `npm test` enforces 70 % line coverage; `npm run check` is `astro check`.

**Depends on:** Phase 2 preferred (its pre-push hook runs `astro check` + tests on this work)
**Fix units:** 4
**Files affected:** 12

## Within-phase Dependencies

Run **3.1 → 3.2 → 3.3 → 3.4**. They share `src/lib/mlflow.ts` / `mlflow-rest.ts` / `mlflow.test.ts`, and 3.2's zod types must compile under 3.1's flag.

## Fix Units

### Fix Unit 3.1: Enable `noUncheckedIndexedAccess` and fix the 10 resulting errors
- **Files:** `app/tsconfig.json`, `app/src/content.config.ts`, `app/src/lib/completeness.ts`, `app/src/lib/mlflow.ts`, `app/src/integrations/export-guard.test.ts`, `app/src/lib/completeness.test.ts`, `app/src/lib/mlflow.test.ts`
- **Violation pattern (Grep):** `N/A`
- **Expected after fix:** 0 matches (additive: `"noUncheckedIndexedAccess": true` in `app/tsconfig.json`; `npx tsc --noEmit -p .` clean)
- **Reference example:** the errors, measured with `npx tsc --noEmit --noUncheckedIndexedAccess -p .` on 2026-11-04:
  ```
  src/content.config.ts(11,5)        generateId returns string | undefined
  src/integrations/export-guard.test.ts(20,16)
  src/lib/completeness.test.ts(54,39), (57,34)
  src/lib/completeness.ts(31,29)     h[1].normalize(...)
  src/lib/mlflow.test.ts(104,16), (105,20), (164,16)
  src/lib/mlflow.ts(75,33), (75,55)  finite[0].run / finite[0].value
  ```
- **HOW TO FIX:**
  1. `tsconfig.json`: keep `"extends": "astro/tsconfigs/strict"` and add `"compilerOptions": { "noUncheckedIndexedAccess": true }`. This is the smallest diff that fixes the finding. `strictest` also turns on `exactOptionalPropertyTypes` and more, which is out of scope.
  2. `content.config.ts:11`: `generateId: ({ entry }) => entry.split('/')[0] ?? entry`. The `*/PROJECT.md` pattern guarantees a segment, so the `?? entry` only satisfies the type. Add a one-line comment saying so.
  3. `completeness.ts:31`: `const name = h[1]; if (name !== undefined) { chunks.push({ name: name.normalize('NFC').trim(), lines: [] }); continue; }`. Do not use `!`.
  4. `mlflow.ts:75`: write `const best = finite[0];` and check it. The empty case already returns earlier, so for the type, reuse **exactly** that earlier branch's return value when `!best`.
  5. Tests: narrow with `assert.ok(x)` before use (or `.at(0)` + `assert.ok`). Never use `!`.
  6. `npm run check && npm test`: green.

### Fix Unit 3.2: Validate MLflow REST responses with zod; derive the types; pin the parsers
- **Files:** `app/src/lib/mlflow-rest.ts`, `app/src/lib/mlflow.ts`
- **New files:** `app/src/lib/mlflow-rest.test.ts`
- **Violation pattern (Grep):** `const isObject = |typeof (e|info)\.\w+ !== 'string'`
- **Expected after fix:** 0 matches
- **Reference example:** `app/src/lib/card.ts` (`import { z } from 'astro/zod'`, `z.infer`)
- **HOW TO FIX:**
  1. In `mlflow-rest.ts`, define:
     ```ts
     const Experiment = z.object({ experiment_id: z.string(), name: z.string() });
     const Metric = z.object({ key: z.string(), value: z.unknown() });
     const Run = z.object({
       info: z.object({
         run_id: z.string(),
         run_name: z.string().optional().catch(undefined),
         experiment_id: z.string(),
         start_time: z.coerce.number().catch(0),
       }),
       data: z.object({ metrics: z.array(z.unknown()).default([]) }).default({ metrics: [] }),
     });
     const ExperimentsResponse = z.object({ experiments: z.array(Experiment).default([]) });
     const RunsResponse = z.object({ runs: z.array(Run).default([]) });
     export type MlflowExperiment = z.infer<typeof Experiment>;
     export type MlflowMetric = z.infer<typeof Metric>;
     ```
     Keep the behaviour current tests pin:
     - an absent list means empty;
     - a missing `run_name` stays undefined;
     - a non-numeric `start_time` becomes 0;
     - metrics without a string `key` are **dropped**: post-parse `data.metrics.flatMap((m) => { const r = Metric.safeParse(m); return r.success ? [r.data] : []; })`, which yields `MlflowMetric[]` (a plain `.filter` would leave the type `unknown[]` and fail `tsc`);
     - a malformed experiment or run **throws** `Error('unexpected response: …')`.
  2. Implement `parseExperiments`/`parseRuns` as `safeParse`, throwing `new Error(\`unexpected response: ${r.error.issues[0]?.message ?? 'shape'}\`)` on failure. Callers already map thrown errors to `unavailable`.
  3. Export `export type MlflowRun = Omit<z.infer<typeof Run>, 'data'> & { data: { metrics: MlflowMetric[] } };` (`z.infer` alone would type `metrics` as `unknown[]`). The `export type { MlflowRun }` in `mlflow.ts` keeps working.
  4. Delete `isObject` and `listOf`. Existing tests must pass **unchanged**. If one fails, the schema changed behaviour; fix the schema, not the test.
  5. Replace the unchecked casts at `mlflow-rest.ts:25,27` with `err instanceof Error ? err.name : undefined` and `err instanceof Error ? err.message : String(err)`.
  6. New `mlflow-rest.test.ts` pins the parsers, using hand-written fixtures:
     - a missing `run_name` gives `undefined`;
     - a non-numeric `start_time` gives `0`;
     - a metric without a string `key` is dropped;
     - an absent `runs` gives `[]`;
     - a malformed run or experiment throws `/unexpected response/`.

### Fix Unit 3.3: One module owns the app's env var names: `src/lib/config.ts`
- **Files:** `app/src/lib/mlflow.ts`, `app/src/content.config.ts`, `app/src/integrations/export-guard.ts`, `app/src/lib/mlflow.test.ts`
- **New files:** `app/src/lib/config.ts`, `app/src/lib/config.test.ts`
- **Violation pattern (Grep):** `env\.DATALAB_`
- **Expected after fix:** 0 matches (the three live reads today: `mlflow.ts:23`, `content.config.ts:9`, `export-guard.ts:9`; comments, error strings and the test `env` literal at `mlflow.test.ts:8` legitimately keep the `DATALAB_` name)
- **Reference example:** snippet:
  ```ts
  // The only module that knows the app's env var names. Each reader takes `env`, so tests stay hermetic.
  export type Env = Record<string, string | undefined>;

  /** Never MLFLOW_URL / MLFLOW_TRACKING_URI (Demo-RAG's, F-2). */
  export const mlflowUri = (env: Env = process.env): string =>
    env.DATALAB_MLFLOW_TRACKING_URI ?? 'http://127.0.0.1:5050';
  /** Exists only for the CI build fixtures (app/test-fixtures/*). */
  export const projectsDir = (env: Env = process.env): string => env.DATALAB_PROJECTS_DIR ?? '../projects';
  export const isStrictExport = (env: Env = process.env): boolean => env.DATALAB_STRICT_EXPORT === '1';
  ```
- **HOW TO FIX:**
  1. Create `config.ts` from the snippet.
  2. In `mlflow.ts`, delete the local `Env` type and `mlflowUri`, and add `import { mlflowUri, type Env } from './config.ts'`. The `env: Env = process.env` defaults stay as they are, because they are already injectable. Don't add a re-export shim. In `mlflow.test.ts`, remove `mlflowUri` from the line-4 import (the two tests using it move to `config.test.ts` in step 5).
  3. `content.config.ts`: `base: projectsDir()`. `export-guard.ts`: use `isStrictExport(env)` in place of `env.DATALAB_STRICT_EXPORT === '1'`, and import `Env` from `config.ts`.
  4. `import.meta.env.DEV` in `Metric.astro` and `Base.astro` **stays**. It is Astro's build flag, unavailable under `node --test`, and not a project env var. State this scope in the PR body.
  5. `config.test.ts`:
     - `projectsDir({})` gives `'../projects'`;
     - `projectsDir({ DATALAB_PROJECTS_DIR: 'x' })` gives `'x'`;
     - `isStrictExport({ DATALAB_STRICT_EXPORT: '1' })` gives `true`, and `'true'` gives `false`.

     Move the `'F-2: …ignores MLFLOW_URL'` and `'G-10: app default matches .env.example'` tests here unchanged.

### Fix Unit 3.4: Isolate the global build report between tests
- **Files:** `app/src/lib/mlflow.test.ts`, `app/src/integrations/export-guard.test.ts`
- **Violation pattern (Grep):** `N/A`
- **Expected after fix:** 0 matches (additive: one top-level `beforeEach(() => readReport().clear())` per file)
- **Reference example:** `app/src/lib/report.ts` (`globalThis.__datalabBuildReport`)
- **HOW TO FIX:**
  1. In both files, add a top-level `beforeEach(() => readReport().clear());` and remove the now-redundant inline `readReport().clear()` calls.
  2. `'F-1: warmUp never rejects'`: pass the file's existing `env` const (`mlflow.test.ts:8`) and a fake fetch, so it never polls the real default URI. Do not add a new `DATALAB_` literal.
  3. Add `'should warn once per project when the same reason repeats'`: stub with `t.mock.method(console, 'warn')`. `reportUnavailable('p', 'r')` twice gives 1 call; a new reason gives 2.

<!-- plan-validate: READY 2026-11-04 sha256:aaca88aabcb0 -->
