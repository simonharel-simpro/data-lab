// Best MLflow run per project card. Read-only (never writes to MLflow); no `astro:*` import so node --test runs it.
import type { Card, Metric } from './card.ts';
import { METRIC_KEY_RE } from './card.ts';
import { isValidName } from './name.ts';
import { post, parseExperiments, parseRuns, TransientError, type MlflowExperiment, type MlflowRun } from './mlflow-rest.ts';
import { reportUnavailable } from './report.ts';
import { mlflowUri, type Env } from './config.ts';

export type { MlflowRun } from './mlflow-rest.ts';
export { readReport, reportUnavailable } from './report.ts';

export type BestRun =
  | { kind: 'ok'; runName: string; value: number; runCount: number; experiment: string; runUrl: string }
  | { kind: 'no-runs' }
  | { kind: 'metric-not-logged'; runCount: number }
  | { kind: 'unavailable'; reason: string };
export type MetricState = BestRun | { kind: 'no-metric' };
export type PickedRun = { kind: 'picked'; run: MlflowRun; value: number; runCount: number };

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

/** Latest finite value of exactly `metric.key` (U-6, U-1, D-15), best per goal, ties: newest, then run_id (U-5). */
export function pickBest(
  runs: readonly MlflowRun[],
  metric: Metric,
): PickedRun | { kind: 'no-runs' } | { kind: 'metric-not-logged'; runCount: number } {
  if (runs.length === 0) return { kind: 'no-runs' };
  const carrying = runs.flatMap((run) => {
    const m = run.data.metrics.find((x) => x.key === metric.key);
    return m ? [{ run, value: m.value }] : [];
  });
  if (carrying.length === 0) return { kind: 'metric-not-logged', runCount: runs.length };
  const finite = carrying.filter((c): c is { run: MlflowRun; value: number } => Number.isFinite(c.value));
  if (finite.length === 0) return { kind: 'no-runs' };
  const sign = metric.goal === 'max' ? -1 : 1;
  finite.sort(
    (a, b) =>
      sign * (a.value - b.value) ||
      b.run.info.start_time - a.run.info.start_time ||
      (a.run.info.run_id < b.run.info.run_id ? -1 : a.run.info.run_id > b.run.info.run_id ? 1 : 0),
  );
  const best = finite[0];
  if (!best) return { kind: 'no-runs' };
  return { kind: 'picked', run: best.run, value: best.value, runCount: finite.length };
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

async function searchRuns(
  base: string,
  project: string,
  metric: Metric,
  experimentIds: string[],
  fetchImpl: typeof fetch,
): Promise<MlflowRun[]> {
  return parseRuns(
    await post(base, 'runs/search', {
      experiment_ids: experimentIds,
      filter: `tags.project = '${project}' AND attributes.status = 'FINISHED'`,
      order_by: [`metrics.\`${metric.key}\` ${metric.goal === 'max' ? 'DESC' : 'ASC'}`, 'attributes.start_time DESC'],
      max_results: 1000,
      run_view_type: 'ACTIVE_ONLY',
    }, fetchImpl),
  );
}

function toOk(pick: PickedRun, experiments: readonly MlflowExperiment[], base: string): BestRun {
  const { run_id, run_name, experiment_id } = pick.run.info;
  return {
    kind: 'ok',
    runName: run_name ?? run_id,
    value: pick.value,
    runCount: pick.runCount,
    experiment: experiments.find((e) => e.experiment_id === experiment_id)?.name ?? experiment_id,
    runUrl: `${base}/#/experiments/${experiment_id}/runs/${run_id}`,
  };
}

/** Best finished run tagged exactly `project=<project>`. Throws only on a programming error (invalid input). */
export async function bestRun(
  project: string,
  metric: Metric,
  fetchImpl: typeof fetch = fetch,
  env: Env = process.env,
): Promise<BestRun> {
  // Both values are interpolated into MLflow filters: validation, not escaping, keeps them safe (F-7, D-13).
  if (!isValidName(project)) throw new Error(`bestRun: invalid project name ${JSON.stringify(project)}`);
  if (!METRIC_KEY_RE.test(metric.key)) throw new Error(`bestRun: invalid metric key ${JSON.stringify(metric.key)}`);
  const base = mlflowUri(env);
  try {
    const experiments = await projectExperiments(base, project, fetchImpl);
    if (experiments.length === 0) return { kind: 'no-runs' };
    const ids = experiments.map((e) => e.experiment_id);
    const pick = pickBest(await searchRuns(base, project, metric, ids, fetchImpl), metric);
    if (pick.kind !== 'picked') return pick;
    return toOk(pick, experiments, base);
  } catch (err) {
    const reason = (err as Error).message;
    reportUnavailable(project, reason);
    return { kind: 'unavailable', reason };
  }
}

/** The one call pages make: no `metric` → no MLflow request at all (U-8). */
export async function metricState(
  card: Pick<Card, 'name' | 'metric'>,
  fetchImpl: typeof fetch = fetch,
  env: Env = process.env,
): Promise<MetricState> {
  if (!card.metric) return { kind: 'no-metric' };
  await warmUp(fetchImpl, 30_000, env);
  return bestRun(card.name, card.metric, fetchImpl, env);
}
