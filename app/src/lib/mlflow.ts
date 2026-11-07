// Best MLflow run per project card. Read-only (never writes to MLflow); no `astro:*` import so node --test runs it.
import type { Card, Metric } from './card.ts';
import { METRIC_KEY_RE } from './card.ts';
import { isValidName } from './name.ts';
import { post, parseExperiments, searchAllRuns, TransientError, type MlflowExperiment, type MlflowRun } from './mlflow-rest.ts';
import { reportUnavailable } from './report.ts';
import { mlflowUri, type Env } from './config.ts';
import { runCollection } from './weavit.ts';
import { eligibleForBest, pickBest, type BestFilter, type PickedRun } from './best.ts';
import { groupRuns, type RunGroup } from './run-groups.ts';

export type { MlflowRun } from './mlflow-rest.ts';
export { readReport, reportUnavailable } from './report.ts';
export { pickBest } from './best.ts';

export type BestRun =
  | {
      kind: 'ok';
      runName: string;
      value: number;
      runCount: number;
      experiment: string;
      runUrl: string;
      /** The Weaviate collection the best run used, when it logged a valid `collection` param. */
      collection?: string;
    }
  | { kind: 'no-runs' }
  | { kind: 'metric-not-logged'; runCount: number }
  | { kind: 'unavailable'; reason: string };
export type MetricState = BestRun | { kind: 'no-metric' };
export type ProjectView = { state: MetricState; groups: RunGroup[] };

const warmUps = new WeakMap<typeof fetch, Promise<void>>();

/**
 * Poll `/health` until 200 or the budget is spent, once per process and fetch implementation (F-1: a cold MLflow
 * must not freeze "unavailable" into the export). Never rejects: a build without MLflow still renders.
 */
export function warmUp(fetchImpl: typeof fetch = fetch, budgetMs = 30_000, env: Env = process.env): Promise<void> {
  let p = warmUps.get(fetchImpl);
  if (!p) {
    p = poll(`${mlflowUri(env)}/health`, fetchImpl, Date.now() + budgetMs);
    warmUps.set(fetchImpl, p);
  }
  return p;
}

async function poll(url: string, fetchImpl: typeof fetch, deadline: number): Promise<void> {
  for (;;) {
    const left = deadline - Date.now();
    if (left <= 0) return;
    try {
      const res = await fetchImpl(url, { signal: AbortSignal.timeout(Math.max(1, Math.min(left, 10_000))) });
      if (res.status === 200) return;
    } catch {
      // not up yet: keep polling until the deadline
    }
    await new Promise((r) => setTimeout(r, Math.max(0, Math.min(1000, deadline - Date.now()))));
  }
}

/** Experiments `<project>` and `<project>/<sub>`; the first search is retried once on timeout/5xx (F-1). */
async function projectExperiments(base: string, project: string, fetchImpl: typeof fetch): Promise<MlflowExperiment[]> {
  // Default view_type is active-only: soft-deleted experiments (datalab-test/*) never show.
  const search = { filter: `name LIKE '${project}%'`, max_results: 1000, view_type: 'ACTIVE_ONLY' };
  const first = () => post(base, 'experiments/search', search, fetchImpl);
  const raw = await first().catch((err: unknown) => {
    if (err instanceof TransientError) return first();
    throw err;
  });
  // LIKE 'p%' also matches siblings such as p-x: keep `p` and `p/<sub>` only (U-7, F-6).
  return parseExperiments(raw).filter((e) => e.name === project || e.name.startsWith(`${project}/`));
}

/** Every run tagged `project=<project>`, any status (F-19: unfinished parents and children are shown too). */
function searchRuns(base: string, project: string, experimentIds: string[], fetchImpl: typeof fetch): Promise<MlflowRun[]> {
  return searchAllRuns(base, {
    experiment_ids: experimentIds,
    filter: `tags.project = '${project}'`,
    order_by: ['attributes.start_time DESC'],
    max_results: 1000,
    run_view_type: 'ACTIVE_ONLY',
  }, fetchImpl);
}

function toOk(pick: PickedRun, experiments: readonly MlflowExperiment[], base: string): BestRun {
  const { run_id, run_name, experiment_id } = pick.run.info;
  const collection = runCollection(pick.run.data.params);
  return {
    kind: 'ok',
    runName: run_name ?? run_id,
    value: pick.value,
    runCount: pick.runCount,
    experiment: experiments.find((e) => e.experiment_id === experiment_id)?.name ?? experiment_id,
    runUrl: `${base}/#/experiments/${experiment_id}/runs/${run_id}`,
    ...(collection ? { collection } : {}),
  };
}

type Fetched = { kind: 'fetched'; experiments: MlflowExperiment[]; runs: MlflowRun[] };

/** One experiments + runs fetch for both the card best and the run groups; failures are reported, never thrown. */
async function fetchProject(
  project: string,
  metric: Metric,
  fetchImpl: typeof fetch,
  env: Env,
): Promise<Fetched | { kind: 'no-runs' } | { kind: 'unavailable'; reason: string }> {
  // Both values are interpolated into MLflow filters: validation, not escaping, keeps them safe (F-7, D-13).
  if (!isValidName(project)) throw new Error(`bestRun: invalid project name ${JSON.stringify(project)}`);
  if (!METRIC_KEY_RE.test(metric.key)) throw new Error(`bestRun: invalid metric key ${JSON.stringify(metric.key)}`);
  const base = mlflowUri(env);
  try {
    const experiments = await projectExperiments(base, project, fetchImpl);
    if (experiments.length === 0) return { kind: 'no-runs' };
    const runs = await searchRuns(base, project, experiments.map((e) => e.experiment_id), fetchImpl);
    return { kind: 'fetched', experiments, runs };
  } catch (err) {
    const reason = (err as Error).message;
    reportUnavailable(project, reason);
    return { kind: 'unavailable', reason };
  }
}

function bestOf(fetched: Fetched, metric: Metric, filter: BestFilter, env: Env): BestRun {
  const pick = pickBest(eligibleForBest(fetched.runs, filter), metric);
  return pick.kind === 'picked' ? toOk(pick, fetched.experiments, mlflowUri(env)) : pick;
}

/** Best eligible run tagged exactly `project=<project>` (see `eligibleForBest`). Throws only on invalid input. */
export async function bestRun(
  project: string,
  metric: Metric,
  fetchImpl: typeof fetch = fetch,
  env: Env = process.env,
  filter: BestFilter = { kind: 'legacy' },
): Promise<BestRun> {
  const fetched = await fetchProject(project, metric, fetchImpl, env);
  return fetched.kind === 'fetched' ? bestOf(fetched, metric, filter, env) : fetched;
}

/** What a page shows for a card: the best run and the run groups. No `metric` → no MLflow request at all (U-8). */
export async function projectView(
  card: Pick<Card, 'name' | 'metric'>,
  filter: BestFilter,
  fetchImpl: typeof fetch = fetch,
  env: Env = process.env,
): Promise<ProjectView> {
  if (!card.metric) return { state: { kind: 'no-metric' }, groups: [] };
  await warmUp(fetchImpl, 30_000, env);
  const fetched = await fetchProject(card.name, card.metric, fetchImpl, env);
  if (fetched.kind !== 'fetched') return { state: fetched, groups: [] };
  return {
    state: bestOf(fetched, card.metric, filter, env),
    groups: groupRuns(fetched.runs, fetched.experiments, card.metric, filter),
  };
}

export async function metricState(
  card: Pick<Card, 'name' | 'metric'>,
  fetchImpl: typeof fetch = fetch,
  env: Env = process.env,
  filter: BestFilter = { kind: 'legacy' },
): Promise<MetricState> {
  return (await projectView(card, filter, fetchImpl, env)).state;
}
