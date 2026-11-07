import { test } from 'node:test';
import assert from 'node:assert/strict';
import { groupRuns, type RunGroup } from './run-groups.ts';
import type { BestFilter } from './best.ts';
import type { MlflowRun } from './mlflow-rest.ts';

const legacy: BestFilter = { kind: 'legacy' };
const score = { key: 'score', goal: 'max' } as const;
const exps = [{ experiment_id: '1', name: 'p' }];

function run(id: string, metrics: Record<string, number>, start = 1, exp = '1', params: Record<string, string> = {}, tags: Record<string, string> = {}, status = 'FINISHED'): MlflowRun {
  const m = Object.entries(metrics).map(([key, value]) => ({ key, value }));
  const p = Object.entries(params).map(([key, value]) => ({ key, value }));
  const t = Object.entries(tags).map(([key, value]) => ({ key, value }));
  return { info: { run_id: id, run_name: `n-${id}`, experiment_id: exp, start_time: start, status }, data: { metrics: m, params: p, tags: t } };
}
const child = (id: string, parent: string, value: number, status = 'FINISHED') =>
  run(id, { score: value }, 1, '1', {}, { 'mlflow.parentRunId': parent }, status);

function only<K extends RunGroup['kind']>(groups: RunGroup[], kind: K): Extract<RunGroup, { kind: K }> {
  assert.equal(groups.length, 1);
  const g = groups[0];
  assert.ok(g && g.kind === kind, `expected one ${kind} group`);
  return g as Extract<RunGroup, { kind: K }>;
}

test('U-11: parent with no children shows zero, no best', () => {
  const g = only(groupRuns([run('p', {}, 1, '1', {}, { n_children: '0' })], exps, score, legacy), 'parent');
  assert.equal(g.finished, 0);
  assert.equal(g.failed, 0);
  assert.equal(g.best, undefined);
  assert.equal(g.experiment, 'p');
});

test('U-11: template parent before any child', () => {
  const g = only(groupRuns([run('p', {}, 1, '1', {}, { entry: 'train' }, 'RUNNING')], exps, score, legacy), 'parent');
  assert.equal(g.finished, 0);
  assert.deepEqual(g.children, []);
});

test('U-11: counts finished and failed children', () => {
  const runs = [run('p', {}, 1, '1', {}, { n_children: '3' }), child('a', 'p', 0.4), child('b', 'p', 0.7), child('c', 'p', 0.9, 'FAILED')];
  const g = only(groupRuns(runs, exps, score, legacy), 'parent');
  assert.equal(g.finished, 2);
  assert.equal(g.failed, 1);
  assert.equal(g.best?.value, 0.7);
  assert.equal(g.best?.run.info.run_id, 'b');
});

test('U-12: parentless runs by start_time desc', () => {
  const runs = [run('one', { score: 1 }, 1), run('three', { score: 1 }, 3), run('two', { score: 1 }, 2)];
  const groups = groupRuns(runs, exps, score, legacy);
  assert.deepEqual(groups.map((g) => (g.kind === 'standalone' ? g.run.info.run_id : g.kind)), ['three', 'two', 'one']);
});

test('U-12: legacy run stays standalone', () => {
  const g = only(groupRuns([run('r', { score: 0.6 })], exps, score, legacy), 'standalone');
  assert.equal(g.run.info.run_id, 'r');
});

test('F-19: orphans form their own group', () => {
  const runs = [child('c', 'gone', 0.5), run('s', { score: 0.1 }, 9)];
  const groups = groupRuns(runs, exps, score, legacy);
  assert.equal(groups.length, 2);
  const last = groups.at(-1);
  assert.ok(last && last.kind === 'orphans');
  assert.equal(last.parentRunId, 'gone');
  assert.deepEqual(last.children.map((r) => r.info.run_id), ['c']);
});

test('experiments by name ascending; no metric means no best', () => {
  const runs = [run('x', {}, 1, '2', {}, { entry: 'train' }), child('c', 'x', 0.5), run('y', { score: 1 }, 1, '1')];
  const groups = groupRuns(runs, [{ experiment_id: '1', name: 'p/z' }, { experiment_id: '2', name: 'p/a' }], undefined, legacy);
  assert.deepEqual(groups.map((g) => g.experiment), ['p/a', 'p/z']);
  const first = groups[0];
  assert.ok(first && first.kind === 'parent');
  assert.equal(first.best, undefined);
});
