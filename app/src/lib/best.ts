// Which runs may stand as a project's best, and the pick among them. Pure; the leaf of the MLflow modules.
import type { Goal, Metric } from './card.ts';
import type { MlflowRun } from './mlflow-rest.ts';
import type { LedgerState } from './ledger.ts';
import { PARENT_RUN_ID, RUN_STATUS, TAGS, TEST_SPLIT } from './tags.ts';

// Sort direction per goal: a new Goal fails type-checking until it gets a sign.
const SIGN: Record<Goal, number> = { max: -1, min: 1 };

export type PickedRun = { kind: 'picked'; run: MlflowRun; value: number; runCount: number };

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
  const sign = SIGN[metric.goal];
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

export function tag(run: MlflowRun, key: string): string | undefined {
  return run.data.tags.find((t) => t.key === key)?.value;
}

/**
 * `legacy`: no run.json, today's rule. `ledger`: only children of a parent on run.json's frozen split and data.
 * `none`: run.json is invalid, so no run can be trusted to be on the frozen split.
 */
export type BestFilter =
  | { kind: 'legacy' }
  | { kind: 'ledger'; splitSha256: string | null; dataSha256: string | null }
  | { kind: 'none' };

export function bestFilter(state: LedgerState): BestFilter {
  if (state.kind === 'absent') return { kind: 'legacy' };
  if (state.kind === 'invalid') return { kind: 'none' };
  return { kind: 'ledger', splitSha256: state.splitSha256, dataSha256: state.dataSha256 };
}

const finished = (run: MlflowRun): boolean => run.info.status === RUN_STATUS.finished;

function parentMatches(parent: MlflowRun, filter: BestFilter): boolean {
  if (filter.kind !== 'ledger') return filter.kind === 'legacy';
  // A null run.json hash means nothing is frozen yet: no run can prove it scored on the frozen split (U-27).
  if (filter.splitSha256 === null || filter.dataSha256 === null) return false;
  return tag(parent, TAGS.split_sha256) === filter.splitSha256 && tag(parent, TAGS.data_sha256) === filter.dataSha256;
}

/** Test-split runs never (F-13); a child only if it and its parent FINISHED (U-9) and the parent matches (U-27). */
export function eligibleForBest(runs: readonly MlflowRun[], filter: BestFilter): MlflowRun[] {
  if (filter.kind === 'none') return [];
  const byId = new Map(runs.map((r) => [r.info.run_id, r]));
  return runs.filter((run) => {
    if (tag(run, TAGS.split) === TEST_SPLIT || !finished(run)) return false;
    const parentId = tag(run, PARENT_RUN_ID);
    if (parentId === undefined) return filter.kind === 'legacy';
    const parent = byId.get(parentId);
    return parent !== undefined && finished(parent) && parentMatches(parent, filter);
  });
}
