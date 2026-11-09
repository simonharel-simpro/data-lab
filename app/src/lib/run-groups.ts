// A project's MLflow runs grouped parent → children for the project page (F-19, U-11, U-12). Pure.
import type { Metric } from './card.ts';
import type { MlflowExperiment, MlflowRun } from './mlflow-rest.ts';
import { eligibleForBest, pickBest, tag, type BestFilter } from './best.ts';
import { PARENT_RUN_ID, RUN_STATUS, TAGS } from './tags.ts';

export type RunGroup =
  | {
      kind: 'parent';
      experiment: string;
      parent: MlflowRun;
      children: MlflowRun[];
      finished: number;
      failed: number;
      best?: { run: MlflowRun; value: number };
    }
  | { kind: 'standalone'; experiment: string; run: MlflowRun }
  | { kind: 'orphans'; experiment: string; parentRunId: string; children: MlflowRun[] };

const byId = (a: string, b: string): number => (a < b ? -1 : a > b ? 1 : 0);

function parentGroup(
  parent: MlflowRun,
  children: MlflowRun[],
  experiment: string,
  metric: Metric | undefined,
  filter: BestFilter,
): RunGroup {
  const count = (status: string) => children.filter((c) => c.info.status === status).length;
  const group: RunGroup = {
    kind: 'parent',
    experiment,
    parent,
    children,
    finished: count(RUN_STATUS.finished),
    failed: count(RUN_STATUS.failed),
  };
  if (!metric) return group;
  const pick = pickBest(eligibleForBest([parent, ...children], filter), metric);
  return pick.kind === 'picked' ? { ...group, best: { run: pick.run, value: pick.value } } : group;
}

/** Orders groups: experiment name asc; inside one, newest top-level run first (then run_id), orphans last. */
function order(a: RunGroup, b: RunGroup): number {
  const exp = byId(a.experiment, b.experiment);
  if (exp !== 0) return exp;
  if (a.kind === 'orphans' || b.kind === 'orphans') {
    if (a.kind === 'orphans' && b.kind === 'orphans') return byId(a.parentRunId, b.parentRunId);
    return a.kind === 'orphans' ? 1 : -1;
  }
  const ra = a.kind === 'parent' ? a.parent : a.run;
  const rb = b.kind === 'parent' ? b.parent : b.run;
  return rb.info.start_time - ra.info.start_time || byId(ra.info.run_id, rb.info.run_id);
}

export function groupRuns(
  runs: readonly MlflowRun[],
  experiments: readonly MlflowExperiment[],
  metric: Metric | undefined,
  filter: BestFilter,
): RunGroup[] {
  const name = (id: string) => experiments.find((e) => e.experiment_id === id)?.name ?? id;
  const top: MlflowRun[] = [];
  const kids = new Map<string, MlflowRun[]>();
  for (const run of runs) {
    const parentId = tag(run, PARENT_RUN_ID);
    if (parentId === undefined) top.push(run);
    else kids.set(parentId, [...(kids.get(parentId) ?? []), run]);
  }
  const groups: RunGroup[] = top.map((run) => {
    const children = kids.get(run.info.run_id) ?? [];
    kids.delete(run.info.run_id);
    const experiment = name(run.info.experiment_id);
    const isParent =
      children.length > 0 || tag(run, TAGS.n_children) !== undefined || tag(run, TAGS.entry) !== undefined;
    return isParent ? parentGroup(run, children, experiment, metric, filter) : { kind: 'standalone', experiment, run };
  });
  // Children left over have no top-level parent in `runs`: shown, never hidden, never best (F-19).
  for (const [parentRunId, children] of kids) {
    const first = children[0];
    if (first) groups.push({ kind: 'orphans', experiment: name(first.info.experiment_id), parentRunId, children });
  }
  return groups.sort(order);
}
