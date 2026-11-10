import { test } from 'node:test';
import assert from 'node:assert/strict';
import { bestFilter, eligibleForBest, type BestFilter } from './best.ts';
import type { LedgerState } from './ledger.ts';
import type { MlflowRun } from './mlflow-rest.ts';

const L: BestFilter = { kind: 'ledger', splitSha256: 'a'.repeat(64), dataSha256: 'b'.repeat(64) };
const legacy: BestFilter = { kind: 'legacy' };

function run(
  id: string,
  metrics: Record<string, number>,
  start = 1,
  exp = '1',
  params: Record<string, string> = {},
  tags: Record<string, string> = {},
  status = 'FINISHED',
): MlflowRun {
  const m = Object.entries(metrics).map(([key, value]) => ({ key, value }));
  const p = Object.entries(params).map(([key, value]) => ({ key, value }));
  const t = Object.entries(tags).map(([key, value]) => ({ key, value }));
  return {
    info: { run_id: id, run_name: `n-${id}`, experiment_id: exp, start_time: start, status },
    data: { metrics: m, params: p, tags: t },
  };
}
const child = (id: string, parent: string, score: number, tags: Record<string, string> = {}, status = 'FINISHED') =>
  run(id, { score }, 1, '1', {}, { 'mlflow.parentRunId': parent, ...tags }, status);
const ids = (runs: MlflowRun[]) => runs.map((r) => r.info.run_id);

test('U-9: child of a running parent never eligible', () => {
  const runs = [run('p', {}, 1, '1', {}, {}, 'RUNNING'), child('c', 'p', 0.9)];
  assert.deepEqual(ids(eligibleForBest(runs, legacy)), []);
});

test('U-9: an orphan child never counts', () => {
  assert.deepEqual(ids(eligibleForBest([child('c', 'gone', 0.9)], legacy)), []);
});

test('F-13: test-split run never eligible', () => {
  const runs = [run('p', {}), child('c1', 'p', 0.5), child('c2', 'p', 0.99, { split: 'test' })];
  assert.deepEqual(ids(eligibleForBest(runs, legacy)), ['p', 'c1']);
  const standalone = run('e', { test_score: 0.99 }, 1, '1', {}, { split: 'test' });
  assert.deepEqual(ids(eligibleForBest([standalone], legacy)), []);
});

test('U-27: ledger filter keeps the frozen split and full data only', () => {
  const runs = [
    run('pa', {}, 1, '1', {}, { split_sha256: 'a'.repeat(64), data_sha256: 'b'.repeat(64) }),
    child('ca', 'pa', 0.4),
    run('pc', {}, 1, '1', {}, { split_sha256: 'c'.repeat(64), data_sha256: 'b'.repeat(64) }),
    child('cc', 'pc', 0.9),
    run('pu', {}),
    child('cu', 'pu', 0.8),
  ];
  assert.deepEqual(ids(eligibleForBest(runs, L)), ['ca']);
});

test('U-27: null run.json hash or invalid ledger makes nothing eligible', () => {
  const runs = [
    run('pa', {}, 1, '1', {}, { split_sha256: 'a'.repeat(64), data_sha256: 'b'.repeat(64) }),
    child('ca', 'pa', 0.4),
  ];
  assert.deepEqual(eligibleForBest(runs, { ...L, kind: 'ledger', dataSha256: null }), []);
  assert.deepEqual(eligibleForBest(runs, { kind: 'none' }), []);
  assert.deepEqual(bestFilter({ kind: 'absent' }), { kind: 'legacy' });
  assert.deepEqual(bestFilter({ kind: 'invalid', reason: 'x' }), { kind: 'none' });
});

test('a parentless run counts only under legacy and only when FINISHED', () => {
  const runs = [run('f', { score: 0.6 }), run('x', { score: 0.7 }, 1, '1', {}, {}, 'FAILED')];
  assert.deepEqual(ids(eligibleForBest(runs, legacy)), ['f']);
  assert.deepEqual(ids(eligibleForBest(runs, L)), []);
});

test('bestFilter on an ok ledger carries the run.json hashes', () => {
  const f = bestFilter({
    kind: 'ok',
    ledgerKind: 'training',
    metric: 'm',
    steps: [],
    splitSha256: 'a'.repeat(64),
    dataSha256: null,
  });
  assert.deepEqual(f, { kind: 'ledger', splitSha256: 'a'.repeat(64), dataSha256: null });
});

test('D-6: an exploration ledger ranks its runs by the legacy rule; other kinds keep the ledger filter', () => {
  const state: Extract<LedgerState, { kind: 'ok' }> = {
    kind: 'ok',
    ledgerKind: 'exploration',
    metric: 'm',
    steps: [],
    splitSha256: null,
    dataSha256: null,
  };
  assert.deepEqual(bestFilter(state), { kind: 'legacy' });
  assert.deepEqual(bestFilter({ ...state, ledgerKind: 'comparison' }), {
    kind: 'ledger',
    splitSha256: null,
    dataSha256: null,
  });
});
