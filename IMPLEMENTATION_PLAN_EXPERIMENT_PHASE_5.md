# Phase 5 — App stepper + run groups (read-only)

**Agent:** `general-purpose` (Astro 7 / TypeScript in `app/`, `node --test`) · **Depends on:** Phase 1 (contracts only) ·
**Plan:** `IMPLEMENTATION_PLAN_EXPERIMENT.md`

**Acceptance:** `cd app && npm run check && npm test` green (line coverage floor 70 %, `app/package.json` `test` script
`--test-coverage-lines=70`, a failing floor); the new CI build steps pass; F-13 (app), F-18 (app), F-19, F-20, U-9, U-11,
U-12, U-13, U-15 (app), U-27 (card best) handled and tested. The app stays read-only: it never writes to MLflow or run.json.

**What the app checks (explicit):** run.json is parsed by a strict zod schema plus **I-1** (milestone keys == the kind's
sequence, which also orders the stepper), with the same reason prefixes and check order as Python. I-2…I-15 and
V-1…V-3 stay **Python-only**, guarded by the `ledger` pre-commit hook and the CI `projects` matrix step
(`datalab.ledger validate`); a ledger that breaks only those renders as valid here. The shared vectors say which rules
the app checks (`checked_by`).

Already exists from Phase 1 (read, never modify):
- `contracts/milestones.json` — `{"schema_version": 1, "milestones": [{"id", "agent"} × 9], "sequences": {"training":
  [9 ids], "comparison": ["scoping", "dataset", "eda", "modeling", "audit", "tracking", "report"]}, "freeze_after": "dataset"}`.
- `contracts/mlflow_tags.json` — `{"schema_version": 1, "tags": [11 names: candidate, split, entry, n_children, n_failed,
  failed_candidates, test_look, split_sha256, data_sha256, score_on, config_sha256]}`.
- `contracts/run_ledger_vectors.json` — `{"valid": [{"name", "run"}], "invalid": [{"name", "rule", "checked_by", "run"}]}`;
  `checked_by` is `["python", "app"]` for rules `schema`, `U-13`, `I-1`, else `["python"]`; includes `training-mid-run`
  (valid) and `trouvetou-format` (invalid, no `kind`).
- run.json schema (Python `RunLedger`, strict, `extra="forbid"`, no field optional; key order): `schema_version: 1`
  (not `true`), `kind: training|comparison`, `current_milestone: string`, `milestones: {id: {status:
  todo|produced|validated, artifacts: string[], decision: validate|correct|redo|null}}`, `dataset: {id: string(≥1),
  hash: string(≥1)}|null`, `metric: string(≥1)`, `split_summary: string|null`, `split_sha256`, `data_sha256`:
  `/^[0-9a-f]{64}$/|null`, `features: string[](≥1)|null`, `winner: {candidate: string(≥1), run_id: string(≥1)}|null`,
  `test_looks: [{split_sha256: /^[0-9a-f]{64}$/, run_id: string(≥1), note: string}]`, `decisions_log: [{milestone:
  string, decision: validate|correct|redo, note: string(≥1)}]`.
- Check order (first failure wins): `invalid JSON: <msg>` → `unsupported schema (kind missing)` (U-13) →
  `schema: <path>: <msg>` (first zod issue; the zod object declares keys in the order above) → `I-1: …`.
- MLflow contract: parent per invocation (no `metric.key`, no `cost_usd`; tags `entry`, `n_children`, `n_failed`,
  `failed_candidates`, `split_sha256`, `data_sha256`, `score_on`); one child per grid combination (`mlflow.parentRunId`,
  `candidate`, `config_sha256`; logs `metric.key` + `cost_usd`); eval runs in `<project>/audit`, tagged `split=test`,
  `test_look`, log `test_<key>`; tag `project` on every run.
Existing app code (a2e1201): `lib/mlflow-rest.ts:9-19` `Run` zod (no tags/status), `:21-22` responses, `:33-50` `post`,
`:52-56` `parse`, `:63-77` `parseRuns`; `lib/mlflow.ts:60-82` `pickBest`, `:85-95` `projectExperiments`, `:97-113`
`searchRuns` (FINISHED only), `:130-152` `bestRun`, `:155-163` `metricState`; `lib/mlflow.test.ts:3` imports `pickBest`
from `./mlflow.ts`, `:12-16` `run()`, `:19-34` `fakeFetch`; `lib/card.ts:8` `METRIC_KEY_RE`; `lib/report.ts:5-13`;
`integrations/export-guard.ts:6-12` `checkReport`; `components/Metric.astro:10-11` (links only in dev); zod is
`astro/zod`; contracts read like `lib/name.test.ts:7-9`; page `pages/projects/[name].astro:18` calls `metricState`.

## Files (30)
New (17): `app/src/lib/{ledger,ledger.test,run-groups,run-groups.test,best,best.test,tags,tags.test}.ts`,
`app/src/components/{Stepper,RunGroups}.astro`, `app/test-fixtures/ledger/valid/{PROJECT.md,run.json,scope.md,
dataset.md,eda.md}`, `app/test-fixtures/ledger/invalid/{PROJECT.md,run.json}`.
Modified (13): `app/src/lib/{mlflow-rest,mlflow-rest.test,mlflow,mlflow.test,report,card.test}.ts`,
`app/src/integrations/{export-guard,export-guard.test}.ts`, `app/src/pages/{index,projects/[name]}.astro`,
`.pre-commit-config.yaml`, `.github/workflows/ci.yml`, `ARCHITECTURE.md`.
Import graph (no cycle): `best.ts` → `mlflow-rest.ts`, `card.ts`, `tags.ts`; `run-groups.ts` → `best.ts`, `tags.ts`;
`mlflow.ts` → `best.ts`, `run-groups.ts` (and re-exports `pickBest`, so `mlflow.test.ts:3` keeps working).

### `app/src/lib/tags.ts` (new)
`export const TAGS = { candidate: 'candidate', split: 'split', entry: 'entry', n_children: 'n_children', n_failed:
'n_failed', failed_candidates: 'failed_candidates', test_look: 'test_look', split_sha256: 'split_sha256', data_sha256:
'data_sha256', score_on: 'score_on', config_sha256: 'config_sha256' } as const;` plus `PARENT_RUN_ID = 'mlflow.parentRunId'`.
Every tag read in `best.ts` / `run-groups.ts` goes through `TAGS`.

### `app/src/lib/best.ts` (new, leaf)
- `pickBest` moved verbatim from `mlflow.ts:59-82` (with `PickedRun`).
- `export function tag(run: MlflowRun, key: string): string | undefined`.
- `export type BestFilter = { kind: 'legacy' } | { kind: 'ledger'; splitSha256: string | null; dataSha256: string | null } | { kind: 'none' }`
  and `export function bestFilter(state: LedgerState): BestFilter` — `absent` → `legacy`; `invalid` → `none`; `ok` →
  `ledger` with the run.json hashes.
- `export function eligibleForBest(runs: readonly MlflowRun[], filter: BestFilter): MlflowRun[]` — drops tag
  `split=test` (F-13); `none` → `[]`; a child (`mlflow.parentRunId`) counts only if FINISHED and its parent (in `runs`)
  FINISHED (U-9; orphans never count) and, under `ledger`, the parent's `split_sha256` and `data_sha256` tags equal the
  run.json values (a null run.json value → nothing counts; U-27); a parentless run counts only under `legacy` and only
  if FINISHED (today's rule; new parents carry no `metric.key`).

### `app/src/lib/ledger.ts` (new)
Parse run.json like Python for what the app checks, and turn it into stepper steps. No `astro:*` import; ≤ 200 lines; no
`any`; never throws on bad input (throws only if `milestones.json` itself is invalid).
- `import milestonesJson from '../../../contracts/milestones.json' with { type: 'json' };` parsed once by a strict zod
  schema into `export const MILESTONES: { milestones: { id: string; agent: string }[]; sequences: Record<Kind, string[]>; freeze_after: string }`.
- `KINDS`, `STATUSES`, `DECISIONS` `as const` tuples and their types.
- `export const runLedgerSchema` — `z.object({...}).strict()` in the key order above (nested objects `.strict()`,
  nullable fields stay required keys, `z.literal(1)` for `schema_version`), `.superRefine` = I-1 only, message `I-1: …`.
- `export type Step = { id: string; agent: string; status: Status; decision: 'validate' | 'correct' | null; current: boolean; artifacts: { path: string; exists: boolean }[]; notes: { decision: Decision; note: string }[] }`.
- `export type LedgerState = { kind: 'absent' } | { kind: 'invalid'; reason: string } | { kind: 'ok'; ledgerKind: Kind; metric: string; steps: Step[]; splitSha256: string | null; dataSha256: string | null }`.
- `export function parseLedger(text: string): { ok: true; ledger: RunLedger } | { ok: false; reason: string }` — strips
  one leading U+FEFF, then the check order above.
- `export type LedgerFs = { exists(p: string): boolean; read(p: string): string; real(p: string): string }` (default
  `existsSync`, `readFileSync(p, 'utf8')`, `realpathSync`).
- `export function readLedger(projectDir: string, fs: LedgerFs = nodeFs): LedgerState` — no run.json → `absent`;
  invalid → `invalid`; ok → steps in sequence order; `current` = `id === current_milestone && status !== 'validated'`
  (the ledger keeps its pointer on the last milestone, I-6; the stepper shows **no** current step once all are validated);
  `notes` = that milestone's `decisions_log` entries in order; an artifact `exists` only when the file exists and its
  real path stays inside `projectDir` (U-15).
- `export function ledgerState(project: string, projectDir: string, fs?: LedgerFs): LedgerState` — `readLedger` +
  `reportInvalidLedger(project, reason)` when invalid (F-20).
**Reference:** `lib/card.ts:10-24` (zod style), `lib/mlflow-rest.ts:52-56`.

### `app/src/lib/run-groups.ts` (new)
Group a project's runs parent → children. Pure.
- `export type RunGroup = { kind: 'parent'; experiment: string; parent: MlflowRun; children: MlflowRun[]; finished: number; failed: number; best?: { run: MlflowRun; value: number } } | { kind: 'standalone'; experiment: string; run: MlflowRun } | { kind: 'orphans'; experiment: string; parentRunId: string; children: MlflowRun[] }`.
- `export function groupRuns(runs, experiments, metric: Metric | undefined, filter: BestFilter): RunGroup[]` — a
  parentless run is a `parent` when it has children in `runs` or a tag `n_children` or `entry`, else `standalone`
  (legacy, e.g. `projects/mini-rag/src/mini_rag/run.py:104`); children whose parent is absent → one `orphans` group per
  parent id (F-19); `finished` = FINISHED children (U-11), `failed` = FAILED (counted, never best); `best` =
  `pickBest(eligibleForBest(...))` over the group when a metric is given; experiments by name asc; inside one,
  parents/standalone by `start_time` desc then `run_id` (U-12), orphans last.

### `app/src/lib/mlflow-rest.ts` (modify)
`Run.info` gains `status: z.string().optional().catch(undefined)`; `Run.data` gains `tags: z.array(z.unknown()).default([])`
(the `.default({...})` adds `tags: []`); `RunsResponse` gains `next_page_token: z.string().optional()`; `MlflowRun.data`
gains `tags: MlflowTag[]` (`const Tag = z.object({ key: z.string(), value: z.string() })`, bad tags dropped like params);
`export function parseRunsPage(res: unknown): { runs: MlflowRun[]; nextPageToken?: string }` (`parseRuns` returns its
`runs`); `export async function searchAllRuns(base, body: Record<string, unknown>, fetchImpl: typeof fetch, maxPages =
50): Promise<MlflowRun[]>` — posts `runs/search` with `page_token` until no/empty token; a repeated token or more than
`maxPages` pages → `Error('runs/search: pagination did not end')`.

### `app/src/lib/mlflow.ts` (modify)
`pickBest` moves to `best.ts` (re-exported here). `searchRuns` → `searchAllRuns`, filter `tags.project = '<project>'` (no
status clause, F-19), `order_by: ['attributes.start_time DESC']`, `max_results: 1000`, `run_view_type: 'ACTIVE_ONLY'`;
`bestRun(project, metric, fetchImpl = fetch, env = process.env, filter: BestFilter = { kind: 'legacy' })` (filter
**last**, so every existing call — `mlflow.ts:162` and the `mlflow.test.ts` calls such as `:103` — stays valid) picks with `pickBest(
eligibleForBest(runs, filter), metric)`; new `export async function projectView(card: Pick<Card, 'name' | 'metric'>,
filter: BestFilter, fetchImpl = fetch, env: Env = process.env): Promise<{ state: MetricState; groups: RunGroup[] }>` —
with a metric it first `await warmUp(fetchImpl, 30_000, env)` exactly as `metricState` does today (`mlflow.ts:161`),
then one experiments + runs fetch serves both; no metric → `{ state: { kind: 'no-metric' }, groups: [] }`, no request;
unavailable → `groups: []`. `metricState(card, fetchImpl, env, filter = { kind: 'legacy' })` = `(await projectView(card, filter, fetchImpl,
env)).state`. The existing test `ok result carries experiment name and run URL; requests are well-formed`
(`mlflow.test.ts:101-110`) asserts at `:109` `` order_by == ['metrics.`score` DESC', 'attributes.start_time DESC'] ``:
update it to `['attributes.start_time DESC']`. The existing `metricState warms up then returns the best run`
(`mlflow.test.ts:157`, first call `/health`) must keep passing unchanged. ≤ 200 lines.

### `app/src/lib/report.ts`, `app/src/integrations/export-guard.ts` (modify)
`reportInvalidLedger(project, reason)` — same map, key `run.json:<project>` (never overwrites an MLflow entry), same
dedupe, `console.warn('[ledger] <project>: <reason>')`. `checkReport`: a `run.json:` key logs `run.json invalid for
'<project>': <reason>`, others keep `metrics unavailable for '<project>': <reason>`; strict mode still throws on a
non-empty report, listing every key.

### `app/src/components/Stepper.astro`, `RunGroups.astro` (new); `pages/projects/[name].astro` (modify)
- `Stepper` props `{ state: LedgerState }`: `absent` → nothing; `invalid` → `<p class="badge">run.json : {state.reason}</p>`
  (page still renders); `ok` → `<ol class="stepper">`, one `<li>` per step: id, agent, status, decision when set,
  `aria-current="step"` only on a `current` step, the step's notes as a `<ul>` of `decision — note`; artifacts as
  `<code>{path}</code>`, a missing one followed by an unlinked `missing` badge (U-15); no hyperlinks (the export has no
  route to `projects/` files; `Metric.astro:10`).
- `RunGroups` props `{ groups: RunGroup[]; metricKey?: string }`; `linked = import.meta.env.DEV` (`Metric.astro:11`); per
  experiment a heading; a `parent` row: run name, `{finished} children ({failed} failed)`, best child name and
  `value.toFixed(3)`, or `0 children, no best` (never hidden, U-11); `standalone` rows; `orphans`: "children of a missing
  parent" + id. Run links only when `linked`.
- Index `pages/index.astro:12`: `state: (await projectView(e.data, bestFilter(ledgerState(e.id, join(projectsDir(),
  e.id))))).state` replaces `metricState(e.data)`, so the index card and the project page show the same best (the
  report dedupes the ledger warning across both pages).
- Page: `const ledger = ledgerState(entry.id, join(projectsDir(), entry.id))`; `const view = await
  projectView(entry.data, bestFilter(ledger))` replaces `metricState` (`:18`); `<Stepper>` after the `<h1>`, `<Metric
  state={view.state} …/>` as today, `<RunGroups groups={view.groups} metricKey={entry.data.metric?.key} />` after it.

### `.pre-commit-config.yaml` (modify)
`gates-app` `files` (`:77`) becomes `^(app/|contracts/|\.env\.example$|packages/datalab/src/datalab/project\.py$)` (the
`card.test.ts` guard reads `project.py`'s `METRIC_KEY_RE`).

### `app/test-fixtures/ledger/` (new)
`valid/PROJECT.md`: `name: valid`, `title: Ledger valide`, `status: idée`, no `metric` (no MLflow call: a strict build
fails only on the ledger), a filled `## Objectif`; `valid/run.json`: vector `training-mid-run` byte for byte with a
UTF-8 BOM (F-20); `valid/{scope,dataset,eda}.md` exist; `src/demo/data/clean.py` absent (shows `missing`).
`invalid/PROJECT.md` (same shape, `name: invalid`); `invalid/run.json`: vector `trouvetou-format`.

### `.github/workflows/ci.yml` (modify — job `app`, after the bad-name step)
`- name: ledger fixtures build (valid + invalid run.json, F-20)` → `npm run build` with `DATALAB_PROJECTS_DIR:
test-fixtures/ledger`, then `grep -q 'class="stepper"' dist/projects/valid/index.html && grep -q 'unsupported schema
(kind missing)' dist/projects/invalid/index.html`; `- name: invalid run.json fails a strict export (F-20)` →
`"! npm run build"` with `DATALAB_PROJECTS_DIR: test-fixtures/ledger`, `DATALAB_STRICT_EXPORT: "1"`.

### `ARCHITECTURE.md` (modify)
Layer Responsibilities (app): `ledger.ts` (run.json reader: schema + I-1, no writes), `best.ts`, `run-groups.ts`,
`tags.ts`; Data Flow: project page = card + run.json + MLflow runs grouped parent → children, best on the frozen split.

### Test files
`fakeFetch` and `run()` from `lib/mlflow.test.ts:12-34`; `run()` gets `tags: Record<string, string> = {}` and `status =
'FINISHED'` and emits `data.tags`. Contracts read with `readFileSync(new URL('../../../contracts/<file>',
import.meta.url), 'utf8')`. Fake `LedgerFs` = a `Map`. `L = { kind: 'ledger', splitSha256: 'a'.repeat(64), dataSha256: 'b'.repeat(64) }`.

| File · Test | Given → expected | Source |
|---|---|---|
| `ledger.test` · `F-18: valid vectors parse` | each `valid` → `ok: true` | F-18 |
| `ledger.test` · `F-18: app-checked invalid vectors fail with their rule` | each `invalid` with `checked_by` ∋ `app` → `ok: false`, reason starts with `rule` (`schema` → `schema:`, `U-13` → `unsupported schema (kind missing)`, `I-1` → `I-1:`) | F-18 |
| `ledger.test` · `F-18: Python-only vectors are accepted by the app` | each `invalid` with `checked_by` = `["python"]` → `ok: true` (the documented gap; hook + CI guard them) | F-18 |
| `ledger.test` · `F-18: milestones contract` | `sequences.training.length === 9`, comparison 7, `freeze_after === 'dataset'` | F-18 |
| `ledger.test` · `F-20: missing run.json renders nothing` | no file → `{ kind: 'absent' }`, report empty | F-20 |
| `ledger.test` · `F-20: invalid run.json is reported and strict export fails` | `{"schema_version": 1,` → reason starts `invalid JSON:`; report has `run.json:p`; `checkReport(report, {DATALAB_STRICT_EXPORT: '1'})` throws `/run.json:p/` | F-20 |
| `ledger.test` · `BOM is stripped like Python` | `'﻿' + JSON.stringify(valid[0].run)` → `ok: true` | F-20 |
| `ledger.test` · `U-15: missing artifact flagged, present one not` · `U-15: symlink escape is missing` | `training-mid-run`, `scope.md` present, `clean.py` absent → `exists` true / false · `real()` outside → `false` | U-15 |
| `ledger.test` · `steps follow the kind sequence, mark current, carry notes` | `training-mid-run` → 9 steps in order, only `eda` current; scoping notes `[{validate, 'ok'}]` | default |
| `ledger.test` · `no current step once all are validated` | vector `comparison-complete` → every `current` false | default |
| `tags.test` · `tag names match the contract` | `Object.values(TAGS)` sorted == `mlflow_tags.json` `tags` sorted | F-18 |
| `card.test` · `METRIC_KEY_RE matches the Python literal` | `packages/datalab/src/datalab/project.py` captured `METRIC_KEY_RE: Final = re.compile(r"(.+)")` == `METRIC_KEY_RE.source` | F-18 |
| `best.test` · `U-9: child of a running parent never eligible` | parent RUNNING, child FINISHED 0.9 → `eligibleForBest(.., legacy)` excludes it | U-9 |
| `best.test` · `F-13: test-split run never eligible` | children 0.5 and `split=test` 0.99 → only 0.5 | F-13 |
| `best.test` · `U-27: ledger filter keeps the frozen split and full data only` | `L`; parent tags `a…`/`b…` child 0.4, parent `c…`/`b…` child 0.9, untagged parent child 0.8 → `[0.4 child]` | U-27 |
| `best.test` · `U-27: null run.json hash or invalid ledger makes nothing eligible` | `L` with `dataSha256: null` → `[]`; `{kind: 'none'}` → `[]`; `bestFilter({kind: 'absent'})` → legacy | U-27 |
| `run-groups.test` · `U-11: parent with no children shows zero, no best` · `U-11: template parent before any child` | parent `n_children "0"` → `finished 0`, no best · tag `entry: train`, no children → `parent`, `finished 0` | U-11 |
| `run-groups.test` · `U-11: counts finished and failed children` | 2 FINISHED (0.4, 0.7) + 1 FAILED (0.9) → `finished 2`, `failed 1`, best 0.7 | U-11 |
| `run-groups.test` · `U-12: parentless runs by start_time desc` · `U-12: legacy run stays standalone` | start 1, 3, 2 → 3, 2, 1 · FINISHED `score` 0.6, no `n_children`/`entry` → one `standalone` | U-12 |
| `run-groups.test` · `F-19: orphans form their own group` | child with `mlflow.parentRunId 'gone'` → one `orphans` group, last | F-19 |
| `mlflow-rest.test` · `F-19: tags parsed, bad ones dropped` · `F-19: follows next_page_token` | `[{key:'mlflow.parentRunId', value:'p1'}, {key: 1}]` → one tag; absent → `[]`; `status` read · page 1 `{runs:[a], next_page_token:'t'}`, page 2 `{runs:[b]}` → `[a, b]`, 2nd body `page_token: 't'` | F-19 |
| `mlflow-rest.test` · `pagination that never ends throws` | every page returns `'t'` → rejects `/pagination did not end/` | F-19 |
| `mlflow.test` · `F-19: all-status query` · `projectView without metric makes no request` | body filter `tags.project = 'p'`, no `attributes.status` · no metric → 0 fetch calls, `groups: []` | F-19, U-8 |
| `mlflow.test` · `F-13 / U-9: card best ignores test runs and unfinished parents` | FINISHED parent: children 0.5 + `split=test` 0.99; FAILED parent child 0.9 → `value 0.5`, `runCount 1` | F-13, U-9 |
| `mlflow.test` · `U-27: projectView with a ledger filter ranks only matching parents` | `L`; matching parent child 0.4, other split child 0.9 → `state.value === 0.4` | U-27 |
| `mlflow.test` · `legacy parentless FINISHED run still counts` | no run.json (`legacy`), one parentless run 0.6 → 0.6 | default |
| `export-guard.test` · `ledger entries get their own line` | report `run.json:p` → `run.json invalid for 'p': x` | F-20 |

<!-- plan-validate: READY 2026-11-06 sha256:898b16d0fb0a -->
