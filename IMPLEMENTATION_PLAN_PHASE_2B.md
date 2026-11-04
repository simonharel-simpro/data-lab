# Phase 2B — Presentation app (Astro)

**Depends on:** Phase 1 (`projects/.gitkeep`, `contracts/name_vectors.json`, `.nvmrc`, compose on 5050).
**Runs in parallel with:** 2A, 2C. **Agent:** `general-purpose` (Astro 7 / TypeScript, Node 22).
**Repo root:** `/home/simon/projects/data-science/data-lab`. **Starting point:** the validated spike
`spike-astro/app/` (read every file in `src/` first) and its sample cards `spike-astro/projects/*/PROJECT.md`.

## Context
A read-only site that tells each project's story: one card per `projects/<name>/PROJECT.md` (frontmatter + `##`
sections), enriched with the project's best MLflow run. Two modes from one code base (D-1):
- **local live:** `npm run dev` — cards and metrics re-read on every request; links to MLflow shown;
- **showcase:** `npm run build` — static `dist/`, metrics frozen at build time, no links to 127.0.0.1 (D-14).
No server adapter, no LIVE switch (S-2). Before writing Astro APIs, check them with Context7 (`/withastro/docs`) —
the spike used `defineCollection` + `glob` loader + `getCollection`/`getEntry`/`render`.
**Invalid card policy (D-13):** any invalid card fails the build with a message naming the file and the problem.

## Files

#### `app/package.json` (NEW, from spike)
`"type": "module"`, `engines.node ">=22.22.0"`, deps pinned exactly: `astro` `7.4.1`; devDeps `@astrojs/check`,
`typescript`, **`@types/node` (22.x)** (without it `astro check` reports 4 errors on `process`, `node:test`,
`node:assert/strict` — verified) and **`yaml`** (the G-8 contract test parses the template card outside Astro); pin
versions published ≥ 2 weeks ago. Scripts: `dev` (`astro dev --host 127.0.0.1`), `build` (`astro build`), `check`
(`astro check`), `test` (`node --test --experimental-test-coverage --test-coverage-lines=70 'src/**/*.test.ts'` —
glob **quoted** so Node expands `**` itself; failing 70 % line floor on the tested modules). **No** `@astrojs/node`, no vitest (S-2, S-3).
Commit `package-lock.json`.

#### `app/tsconfig.json` (NEW)
`{"extends": "astro/tsconfigs/strict", "include": [".astro/types.d.ts", "**/*"], "exclude": ["dist"]}` — brings
`allowImportingTsExtensions` and `verbatimModuleSyntax`. **Every relative import between `.ts` files carries its
`.ts` extension** (`import { NAME_RE } from './name.ts'`) and type-only imports use `import type`: `node --test`
resolves no extensionless import (verified: `ERR_MODULE_NOT_FOUND`). Modules under test never import `astro:*`.

#### `app/astro.config.mjs` (NEW) — `defineConfig({ output: 'static', integrations: [exportGuard()] })`.

#### `app/src/lib/name.ts` (NEW)
`export const NAME_RE = /^[a-z][a-z0-9]*(-[a-z0-9]+)*$/;` — comment: "identical literal in
packages/datalab/src/datalab/project.py; vectors in contracts/name_vectors.json". `RESERVED = new Set(["test",
"datalab", "datalab-test", "template", "y", "n", "yes", "no", "on", "off", "true", "false", "null"])` (YAML 1.1
bool/null words: PyYAML reads `name: no` as `False`, the JS parser as `"no"` — reserving them keeps both sides
agreeing). `isValidName(s: unknown): boolean`.

#### `app/src/lib/card.ts` (NEW, pure) — `export const cardSchema` (zod from `astro/zod`)
`name` refined with `isValidName`; `title` string; `status` = `z.preprocess(s => typeof s === 'string' ?
s.normalize('NFC').trim() : s, z.enum(['idée','en cours','conclu','abandonné']))` (an NFD-typed `idée` passes);
`tags` string[] default `[]`; `data` optional string; `metric` optional `{ key: z.string().regex(/^[A-Za-z0-9_.\-/
]+$/), goal: z.enum(['max','min']) }` (F-7). `export type Card = z.infer<typeof cardSchema>`.

#### `app/src/content.config.ts` (NEW, from spike)
`glob({ base: process.env.DATALAB_PROJECTS_DIR ?? '../projects', pattern: '*/PROJECT.md', generateId: ({entry}) =>
entry.split('/')[0] })`, `schema: cardSchema`. Dot-dirs (e.g. `.x.tmp-…` from `datalab-new`) must not match: verify
the glob skips them, else exclude explicitly. `DATALAB_PROJECTS_DIR` exists only for the CI build fixtures below.

#### `app/src/lib/projects.ts` (NEW) — `loadProjects()`: `getCollection('projects')`; throw
`Error("<file>: name '<name>' must equal its folder '<id>'")` when `data.name !== id` (S-9, D-13); sorted by status
order (en cours, idée, conclu, abandonné) then title. Zero projects is valid (F-15).

#### `app/src/lib/completeness.ts` (NEW, from spike + U-9) — pure
`SECTIONS_BY_STATUS` as in the spike (idée: Objectif · en cours: + Approche · conclu/abandonné: + Enseignements,
Suite) and `Données` + `Métrique` required from `en cours`. `sections(body)`: ignore lines inside fenced code blocks
(U-9d); strip `<!-- … -->` before the emptiness check (U-9c); headings matched exactly after NFC + trim,
case-sensitive (U-9b); a heading present several times is filled if **any** occurrence has content (U-9a); unknown
sections ignored. `missing(card: Pick<Card,'status'|'data'|'metric'>, body: string): string[]`.

#### `app/src/lib/mlflow.ts` (NEW, from spike, reworked) — no `astro:*` import
- `export function mlflowUri(env: Record<string, string | undefined> = process.env): string` →
  `env.DATALAB_MLFLOW_TRACKING_URI ?? 'http://127.0.0.1:5050'`; the only place the URI is read; never read
  `MLFLOW_URL` / `MLFLOW_TRACKING_URI` (F-2). A function so tests pass an env object instead of re-importing.
- `export type BestRun = {kind:'ok', runName, value, runCount, experiment, runUrl} | {kind:'no-runs'} |
  {kind:'metric-not-logged', runCount} | {kind:'unavailable', reason}`. `metric-not-logged` = finished runs exist but
  none logs `metric.key` (a typo in the key must not look like "no runs", G-6).
- `warmUp(fetchImpl = fetch, budgetMs = 30_000): Promise<void>`: poll `GET /health` (1 s interval) until 200 or the
  budget is spent, once per process (memoised promise) (F-1). **Never rejects**: at the deadline it resolves, so a
  build without MLflow (CI) still renders cards as `unavailable` instead of crashing.
- `bestRun(project, metric, fetchImpl = fetch, env = process.env): Promise<BestRun>`: if `!isValidName(project)` it
  **throws** before any request (cannot happen after schema validation; programming error, D-13). Otherwise never
  throws: `experiments/search` with `filter: name LIKE '<project>%'`, then keep only `name === project ||
  name.startsWith(project + '/')` (U-7); `runs/search` with `filter: "tags.project = '<project>' AND
  attributes.status = 'FINISHED'"` (F-6, S-10), `order_by: ["metrics.\`<key>\` <DESC|ASC>", "attributes.start_time
  DESC"]`, `max_results: 1000`. First search retried once on timeout/5xx (F-1). Timeout 10 s per request.
  Shape-check responses (object; arrays where present), else `unavailable`. Selection delegated to `pickBest`.
  Every `unavailable` calls `reportUnavailable(project, reason)`.
- `pickBest(runs, metric): Pick | {kind:'no-runs'} | {kind:'metric-not-logged', runCount}` where `Pick = {kind:'picked',
  run, value, runCount}` (pure, exported; `bestRun` turns `picked` into `ok` by adding `experiment` name from its
  experiments map and `runUrl`): no runs → `no-runs`; runs but none carrying exactly
  `metric.key` → `metric-not-logged` (a pilot's `smoke_score` never stands in for `score`, D-15); keep values from
  `run.data.metrics` (latest, U-6) that are `Number.isFinite` (U-1), none finite → `no-runs`; order by value per
  goal, then `start_time` desc, then `run_id` asc (U-5).
- **Build report on `globalThis`, never a module variable:** during `astro build` the pages and the integration load
  separate module instances, so a module-level array stays empty in the hook (verified on the spike: module array
  `[]`, `globalThis` array filled). `reportUnavailable(project, reason)` sets into
  `globalThis.__datalabBuildReport ??= new Map<string,string>()` (one entry per project, deduped across pages);
  `readReport(): Map<string,string>`. Declare the global's type in `src/env.d.ts`.
- `runUrl`: `${mlflowUri(env)}/#/experiments/<id>/runs/<run_id>`.
- `metricState(card: Pick<Card,'name'|'metric'>, fetchImpl = fetch, env = process.env): Promise<BestRun | {kind:
  'no-metric'}>` — the one function pages/`Metric.astro` call: no `metric` → `{kind:'no-metric'}` **without any
  fetch** (U-8); else `await warmUp(fetchImpl)` then `bestRun(...)`.

#### `app/src/integrations/export-guard.ts` (NEW) — `exportGuard(env = process.env)` returns an Astro integration
whose `astro:build:done` hook logs one line per `readReport()` entry and, when `env.DATALAB_STRICT_EXPORT === '1'`
and the report is non-empty, throws (build fails) (F-1). Export the hook body as `checkReport(report, env)` (pure) so
it is testable without Astro. Verify the hook name with Context7.

#### `app/src/components/Metric.astro` (NEW, from spike) — receives a `metricState()` result. States: `no-metric` →
"Pas de métrique déclarée." (U-8); `no-runs` → "Aucun run MLflow pour l'instant."; `metric-not-logged` → "N runs, aucun
ne journalise `<key>`"; `unavailable` → "Métriques indisponibles (MLflow injoignable)"; `ok` → value (3 decimals),
"Meilleur de N runs", run name. **Only when `import.meta.env.DEV`** the run name links to `runUrl`; in the static
export it is plain text (D-14).

#### `app/src/layouts/Base.astro` (NEW, from spike) — mode label from `import.meta.env.DEV` ("en direct" /
"statique"), render time; the resolved `mlflowUri()` in the footer **in dev only** (F-2, D-14). Keep the spike's CSS
tokens incl. dark mode.

#### `app/src/pages/index.astro`, `app/src/pages/projects/[name].astro` (NEW, from spike)
As in the spike, using `loadProjects()`, `missing()`, `metricState()`; `getStaticPaths` from `loadProjects()`; no
404 branch (static only). Badge "À compléter : …" when `missing()` is non-empty. Empty state on the index when there
are no projects.

#### `app/test-fixtures/` (NEW) — `bad-name/x/PROJECT.md` (`name: y-z` in folder `x`), `crlf-bom/demo/PROJECT.md`
(UTF-8 BOM + CRLF, valid card). Used by CI build steps via `DATALAB_PROJECTS_DIR`.

#### `.github/workflows/ci.yml` (create if 2A has not yet, else append) — job `app`: setup-node from `.nvmrc`; `cd app && npm ci && npm run check
&& npm test && npm run build` (real `projects/`, may be empty; no MLflow in CI → "unavailable"; strict NOT set);
`DATALAB_PROJECTS_DIR=test-fixtures/crlf-bom npm run build` must succeed; `DATALAB_PROJECTS_DIR=test-fixtures/bad-name
npm run build` must **fail** (step asserts non-zero exit).

#### `README.md` (MODIFY) — "App" section: `nvm use`, `npm run dev`, `DATALAB_STRICT_EXPORT=1 npm run build` for a
showable export (fails if MLflow is down), what the badge means, invalid cards fail the build.
**`ARCHITECTURE.md` (MODIFY)** — app layer: extract of `pickBest`, the two modes, the "app never writes" rule, U-6
(latest value) contract, the `globalThis` build-report reason.

#### `spike-astro/` (DELETE) — `rm -rf` after the promotion is complete and tests pass (never committed).

## Tests — `app/src/**/*.test.ts` (`node:test` + `node:assert/strict`; fetch and env injected, no network)

| Test | Given → expected | Source |
|---|---|---|
| `name.test.ts` "F-12: should match the shared name vectors" | read `new URL('../../../contracts/name_vectors.json', import.meta.url)` (test file in `app/src/lib/` → repo root is 3 levels up; never resolve from cwd); accept → true, reject → false (incl. `no`, `yes`, `null`) | F-12, U-2, G-9 |
| `card.test.ts` "F-7: should reject a metric key containing a backtick" | `cardSchema` parse with `metric.key: "a\`b"` → fails | F-7 |
| "G-9: NFD status is accepted" | status `"idée"` → parsed `"idée"` | G-9 |
| "unknown status rejected" | status `"fini"` → fails | D-13 |
| `completeness.test.ts` status ladder | idée + Objectif filled → `[]`; conclu without Enseignements/Suite → `["Enseignements","Suite"]`; en cours without data/metric → includes `"Données"`, `"Métrique"` | card rules |
| "U-9a: duplicate heading is filled if any occurrence has content" | `## Approche\nx\n## Approche\n` → not missing | U-9a |
| "U-9b: lowercase heading counts as missing" | `## objectif\nx` at idée → `["Objectif"]` | U-9b |
| "U-9c: comment-only section counts as missing" | `## Objectif\n<!-- à remplir -->` → `["Objectif"]` | U-9c |
| "U-9d: heading inside a code fence is not a section" | fenced `## Objectif` only → `["Objectif"]` | U-9d |
| `mlflow.test.ts` "U-1: should ignore NaN/Infinity runs" | values `[NaN, Infinity]` → `no-runs`; `[NaN, 0.4]` → ok 0.4, runCount 1 | U-1 |
| "U-5: should pick the most recent run when metric values tie" | two runs 0.72, start_time 1 and 2 → the start_time 2 run | U-5 |
| "goal min" | values 0.3, 0.1, goal `min` → 0.1 | contract |
| "U-6: uses run.data.metrics value" | fixture value 0.5 → value 0.5 | U-6 |
| "G-6: runs exist but none logs the key" | 3 runs with only `accuracy`, key `score` → `{kind:"metric-not-logged", runCount:3}` | G-6 |
| "D-15: smoke_score never counts as score" | runs with only `smoke_score=1.0`, key `score` → `metric-not-logged` | D-15 |
| "F-6: should not pick a better run from a sibling-prefix experiment" | experiments `mini-rag`, `mini-rag-v2` → runs request lists only `mini-rag`'s id and contains `tags.project = 'mini-rag'` | F-6, U-7 |
| "U-7: should keep p/sub experiments" | `p`, `p/bm25`, `p-x` → ids of `p` and `p/bm25` only | U-7 |
| "F-1: should return ok when the first search times out and the retry succeeds" | fake fetch: abort once, then runs → `ok` | F-1 |
| "F-1: unavailable is reported once per project" | two failing `bestRun("p")` → `readReport().size === 1` | F-1 |
| "F-1: strict mode fails when any card is unavailable" | `checkReport(new Map([["p","x"]]), {DATALAB_STRICT_EXPORT:"1"})` throws; with `{}` → no throw | F-1 |
| "F-2: resolves to 127.0.0.1:5050 and ignores MLFLOW_URL" | `mlflowUri({})`, `mlflowUri({MLFLOW_URL:"http://x:5000"})` → `http://127.0.0.1:5050`; `{DATALAB_MLFLOW_TRACKING_URI:"http://h:1"}` → `http://h:1` | F-2 |
| "F-7: should throw before any request when project fails NAME_RE" | `bestRun("Bad_Name", …)` rejects; fetch never called | F-7, D-13 |
| "U-8: should not call MLflow when the card has no metric" | `metricState({name:"p"}, fetchSpy)` → `{kind:"no-metric"}`, `fetchSpy` never called | U-8 |
| "F-1: warmUp never rejects" | fetch always throws, `budgetMs: 50` → resolves; then `bestRun` → `unavailable` | F-1 |
| "pickBest returns the picked run" | values 0.2, 0.7 goal max → `{kind:"picked", value:0.7, runCount:2}` | contract |
| "G-10: app default matches .env.example" | parse `new URL('../../../.env.example', import.meta.url)` line `DATALAB_MLFLOW_TRACKING_URI=` → equals `mlflowUri({})` | G-10 |
| shape check | `{"experiments": {}}` → `unavailable` | resilience |
| CI build steps | empty `projects/` builds (F-15); `crlf-bom` fixture builds (F-11/G-9); `bad-name` fixture fails (S-9, D-13) | F-15, D-13 |

## Done when
`npm run check`, `npm test`, `npm run build` and the CI fixture builds behave as above; `npm run dev` against the
running data-lab MLflow renders cards with links; `DATALAB_STRICT_EXPORT=1 npm run build` fails when MLflow is
stopped; `spike-astro/` removed.

<!-- plan-validate: READY 2026-11-03 sha256:f7be2fb33e77 -->
