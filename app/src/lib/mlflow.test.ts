import { test, beforeEach } from 'node:test';
import assert from 'node:assert/strict';
import {
  bestRun,
  metricState,
  pickBest,
  projectView,
  readReport,
  reportUnavailable,
  warmUp,
  type MlflowRun,
} from './mlflow.ts';
import type { BestFilter } from './best.ts';

type Call = { path: string; body: Record<string, unknown> };
type Reply = unknown | Error | ((n: number) => unknown);
const env = { DATALAB_MLFLOW_TRACKING_URI: 'http://h:1' };
const score = { key: 'score', goal: 'max' } as const;

beforeEach(() => readReport().clear());

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

/** Fake MLflow: route by REST path; an Error reply is thrown, a function gets the call count for that path. */
function fakeFetch(routes: Record<string, Reply>) {
  const calls: Call[] = [];
  const counts = new Map<string, number>();
  const impl = (async (url: string | URL, init?: RequestInit) => {
    const path = String(url)
      .replace(/^.*\/api\/2\.0\/mlflow\//, '')
      .replace(/^https?:\/\/[^/]+\//, '');
    const n = (counts.get(path) ?? 0) + 1;
    counts.set(path, n);
    calls.push({ path, body: init?.body ? JSON.parse(String(init.body)) : {} });
    let reply = routes[path];
    if (typeof reply === 'function') reply = (reply as (n: number) => unknown)(n);
    if (reply instanceof Error) throw reply;
    if (reply instanceof Response) return reply;
    return new Response(JSON.stringify(reply ?? {}), { status: 200 });
  }) as typeof fetch;
  return { impl, calls };
}

const exps = (...names: string[]) => ({
  experiments: names.map((name, i) => ({ experiment_id: String(i + 1), name })),
});

test('U-1: should ignore NaN/Infinity runs', () => {
  assert.deepEqual(pickBest([run('a', { score: NaN }), run('b', { score: Infinity })], score), { kind: 'no-runs' });
  const r = pickBest([run('a', { score: NaN }), run('b', { score: 0.4 })], score);
  assert.equal(r.kind, 'picked');
  assert.equal(r.kind === 'picked' && r.value, 0.4);
  assert.equal(r.kind === 'picked' && r.runCount, 1);
});

test('U-5: should pick the most recent run when metric values tie', () => {
  const r = pickBest([run('old', { score: 0.72 }, 1), run('new', { score: 0.72 }, 2)], score);
  assert.equal(r.kind === 'picked' && r.run.info.run_id, 'new');
});

test('U-5: equal value and start_time fall back to run_id ascending', () => {
  const r = pickBest([run('b', { score: 0.5 }, 1), run('a', { score: 0.5 }, 1)], score);
  assert.equal(r.kind === 'picked' && r.run.info.run_id, 'a');
});

test('goal min', () => {
  const r = pickBest([run('a', { score: 0.3 }), run('b', { score: 0.1 })], { key: 'score', goal: 'min' });
  assert.equal(r.kind === 'picked' && r.value, 0.1);
});

test('U-6: uses run.data.metrics value', () => {
  const r = pickBest([run('a', { score: 0.5 })], score);
  assert.equal(r.kind === 'picked' && r.value, 0.5);
});

test('G-6: runs exist but none logs the key', () => {
  const runs = ['a', 'b', 'c'].map((id) => run(id, { accuracy: 0.9 }));
  assert.deepEqual(pickBest(runs, score), { kind: 'metric-not-logged', runCount: 3 });
});

test('D-15: smoke_score never counts as score', () => {
  assert.deepEqual(pickBest([run('a', { smoke_score: 1.0 })], score), { kind: 'metric-not-logged', runCount: 1 });
});

test('pickBest returns the picked run', () => {
  const r = pickBest([run('a', { score: 0.2 }), run('b', { score: 0.7 })], score);
  assert.equal(r.kind, 'picked');
  assert.equal(r.kind === 'picked' && r.value, 0.7);
  assert.equal(r.kind === 'picked' && r.runCount, 2);
});

test('no runs at all → no-runs', () => {
  assert.deepEqual(pickBest([], score), { kind: 'no-runs' });
});

test('F-6: should not pick a better run from a sibling-prefix experiment', async () => {
  const f = fakeFetch({
    'experiments/search': exps('mini-rag', 'mini-rag-v2'),
    'runs/search': { runs: [run('r', { score: 1 })] },
  });
  const r = await bestRun('mini-rag', score, f.impl, env);
  const runsCall = f.calls.find((c) => c.path === 'runs/search');
  assert.deepEqual(runsCall?.body.experiment_ids, ['1']);
  assert.match(String(runsCall?.body.filter), /tags\.project = 'mini-rag'/);
  assert.equal(r.kind, 'ok');
});

test('U-7: should keep p/sub experiments', async () => {
  const f = fakeFetch({ 'experiments/search': exps('p', 'p/bm25', 'p-x'), 'runs/search': {} });
  await bestRun('p', score, f.impl, env);
  assert.deepEqual(f.calls.find((c) => c.path === 'runs/search')?.body.experiment_ids, ['1', '2']);
});

test('ok result carries experiment name and run URL; requests are well-formed', async () => {
  const f = fakeFetch({ 'experiments/search': exps('p'), 'runs/search': { runs: [run('r9', { score: 0.8 })] } });
  const r = await bestRun('p', score, f.impl, env);
  assert.deepEqual(r, {
    kind: 'ok',
    runName: 'n-r9',
    value: 0.8,
    runCount: 1,
    experiment: 'p',
    runUrl: 'http://h:1/#/experiments/1/runs/r9',
  });
  for (const c of f.calls) assert.ok(Number(c.body.max_results) > 0, `${c.path} max_results`);
  const [expCall, runsCall] = f.calls;
  assert.ok(expCall && runsCall);
  assert.equal(expCall.body.view_type, 'ACTIVE_ONLY');
  assert.deepEqual(runsCall.body.order_by, ['attributes.start_time DESC']);
});

test('no matching experiment → no-runs without searching runs', async () => {
  const f = fakeFetch({ 'experiments/search': exps('p-x') });
  assert.deepEqual(await bestRun('p', score, f.impl, env), { kind: 'no-runs' });
  assert.equal(f.calls.length, 1);
});

test('F-1: should return ok when the first search times out and the retry succeeds', async () => {
  const timeout = new DOMException('timed out', 'TimeoutError');
  const f = fakeFetch({
    'experiments/search': (n: number) => (n === 1 ? timeout : exps('p')),
    'runs/search': { runs: [run('r', { score: 1 })] },
  });
  const r = await bestRun('p', score, f.impl, env);
  assert.equal(r.kind, 'ok');
});

test('F-1: a 5xx on the first search is retried once', async () => {
  const f = fakeFetch({
    'experiments/search': (n: number) => (n === 1 ? new Response('', { status: 503 }) : exps('p')),
    'runs/search': {},
  });
  assert.equal((await bestRun('p', score, f.impl, env)).kind, 'no-runs');
});

test('F-1: unavailable is reported once per project', async () => {
  const f = fakeFetch({ 'experiments/search': new TypeError('fetch failed') });
  const a = await bestRun('p', score, f.impl, env);
  await bestRun('p', score, f.impl, env);
  assert.equal(a.kind, 'unavailable');
  assert.equal(readReport().size, 1);
  assert.ok(readReport().has('p'));
});

test('a 4xx on runs/search → unavailable', async () => {
  const f = fakeFetch({ 'experiments/search': exps('p'), 'runs/search': new Response('', { status: 400 }) });
  assert.equal((await bestRun('p', score, f.impl, env)).kind, 'unavailable');
});

test('F-7: should throw before any request when project fails NAME_RE', async () => {
  const f = fakeFetch({});
  await assert.rejects(bestRun('Bad_Name', score, f.impl, env));
  await assert.rejects(bestRun('p', { key: 'a`b', goal: 'max' }, f.impl, env));
  assert.equal(f.calls.length, 0);
});

test('U-8: should not call MLflow when the card has no metric', async () => {
  const f = fakeFetch({});
  assert.deepEqual(await metricState({ name: 'p' }, f.impl, env), { kind: 'no-metric' });
  assert.equal(f.calls.length, 0);
});

test('metricState warms up then returns the best run', async () => {
  const f = fakeFetch({
    health: 'OK',
    'experiments/search': exps('p'),
    'runs/search': { runs: [run('r', { score: 0.3 })] },
  });
  const r = await metricState({ name: 'p', metric: score }, f.impl, env);
  assert.equal(r.kind === 'ok' && r.value, 0.3);
  const first = f.calls.at(0);
  assert.ok(first);
  assert.equal(first.path, 'health');
});

test('F-1: warmUp never rejects', async () => {
  const f = fakeFetch({ health: new TypeError('fetch failed'), 'experiments/search': new TypeError('fetch failed') });
  await warmUp(f.impl, 50, env);
  assert.equal((await bestRun('p', score, f.impl, env)).kind, 'unavailable');
});

test('should report unavailable when experiments/search returns a malformed experiments list', async () => {
  const f = fakeFetch({ 'experiments/search': { experiments: {} } });
  assert.equal((await bestRun('p', score, f.impl, env)).kind, 'unavailable');
});

test('should report unavailable when runs/search returns a malformed run', async () => {
  const g = fakeFetch({ 'experiments/search': exps('p'), 'runs/search': { runs: [{ info: 'x' }] } });
  assert.equal((await bestRun('p', score, g.impl, env)).kind, 'unavailable');
});

test('F-1: should report unavailable when the retry fails too', async () => {
  const timeout = new DOMException('timed out', 'TimeoutError');
  for (const reply of [() => timeout, () => new Response('', { status: 503 })]) {
    const f = fakeFetch({ 'experiments/search': reply });
    assert.equal((await bestRun('p', score, f.impl, env)).kind, 'unavailable');
    assert.equal(f.calls.filter((c) => c.path === 'experiments/search').length, 2);
  }
});

test('F-1: warmUp polls once per fetch implementation', async () => {
  const f = fakeFetch({ health: 'OK' });
  const a = warmUp(f.impl, 50, env);
  const b = warmUp(f.impl, 50, env);
  assert.equal(a, b);
  await b;
  assert.equal(f.calls.filter((c) => c.path === 'health').length, 1);
});

test('F-1: warmUp resolves without rejecting when /health stays non-200', async () => {
  const f = fakeFetch({ health: () => new Response('', { status: 503 }) });
  await assert.doesNotReject(warmUp(f.impl, 50, env));
  assert.ok(f.calls.filter((c) => c.path === 'health').length >= 1);
});

test('U-6: should report metric-not-logged end to end', async () => {
  const runs = [run('a', { accuracy: 0.9 }), run('b', { smoke_score: 1 })];
  const f = fakeFetch({ health: 'OK', 'experiments/search': exps('p'), 'runs/search': { runs } });
  assert.deepEqual(await metricState({ name: 'p', metric: score }, f.impl, env), {
    kind: 'metric-not-logged',
    runCount: 2,
  });
});

test('should warn once per project when the same reason repeats', (t) => {
  const warn = t.mock.method(console, 'warn', () => {});
  reportUnavailable('p', 'r');
  reportUnavailable('p', 'r');
  assert.equal(warn.mock.callCount(), 1);
  reportUnavailable('p', 'r2');
  assert.equal(warn.mock.callCount(), 2);
});

test("ok result carries the best run's Weaviate collection when it logged a valid one", async () => {
  const runs = [
    run('r1', { score: 0.9 }, 1, '1', { collection: 'MiniRag_x_6f5bda78' }),
    run('r2', { score: 0.1 }, 1, '1', { collection: 'Other' }),
  ];
  const f = fakeFetch({ 'experiments/search': exps('p'), 'runs/search': { runs } });
  const r = await bestRun('p', score, f.impl, env);
  assert.equal(r.kind === 'ok' && r.collection, 'MiniRag_x_6f5bda78');
});

test('ok result has no collection when the param is absent or not a collection name', async () => {
  const cases: Record<string, string>[] = [{}, { collection: 'mini rag' }, { collection: '<script>' }];
  for (const params of cases) {
    const f = fakeFetch({
      'experiments/search': exps('p'),
      'runs/search': { runs: [run('r', { score: 1 }, 1, '1', params)] },
    });
    const r = await bestRun('p', score, f.impl, env);
    assert.equal(r.kind, 'ok');
    assert.ok(!('collection' in r), JSON.stringify(params));
  }
});

const L: BestFilter = { kind: 'ledger', splitSha256: 'a'.repeat(64), dataSha256: 'b'.repeat(64) };
const child = (id: string, parent: string, value: number, tags: Record<string, string> = {}) =>
  run(id, { score: value }, 1, '1', {}, { 'mlflow.parentRunId': parent, ...tags });

test('F-19: all-status query', async () => {
  const f = fakeFetch({ 'experiments/search': exps('p'), 'runs/search': {} });
  await bestRun('p', score, f.impl, env);
  const filter = String(f.calls.find((c) => c.path === 'runs/search')?.body.filter);
  assert.equal(filter, "tags.project = 'p'");
  assert.doesNotMatch(filter, /attributes\.status/);
});

test('U-8: projectView without metric makes no request', async () => {
  const f = fakeFetch({});
  assert.deepEqual(await projectView({ name: 'p' }, { kind: 'legacy' }, f.impl, env), {
    state: { kind: 'no-metric' },
    groups: [],
  });
  assert.equal(f.calls.length, 0);
});

test('F-13 / U-9: card best ignores test runs and unfinished parents', async () => {
  const runs = [
    run('ok', {}, 1, '1', {}, { n_children: '2' }),
    child('c1', 'ok', 0.5),
    child('c2', 'ok', 0.99, { split: 'test' }),
    run('bad', {}, 1, '1', {}, { n_children: '1' }, 'FAILED'),
    child('c3', 'bad', 0.9),
  ];
  const f = fakeFetch({ health: 'OK', 'experiments/search': exps('p'), 'runs/search': { runs } });
  const r = await bestRun('p', score, f.impl, env);
  assert.equal(r.kind === 'ok' && r.value, 0.5);
  assert.equal(r.kind === 'ok' && r.runCount, 1);
});

test('U-27: projectView with a ledger filter ranks only matching parents', async () => {
  const runs = [
    run('pa', {}, 1, '1', {}, { split_sha256: 'a'.repeat(64), data_sha256: 'b'.repeat(64) }),
    child('ca', 'pa', 0.4),
    run('pc', {}, 2, '1', {}, { split_sha256: 'c'.repeat(64), data_sha256: 'b'.repeat(64) }),
    child('cc', 'pc', 0.9),
  ];
  const f = fakeFetch({ health: 'OK', 'experiments/search': exps('p'), 'runs/search': { runs } });
  const view = await projectView({ name: 'p', metric: score }, L, f.impl, env);
  assert.equal(view.state.kind === 'ok' && view.state.value, 0.4);
  assert.deepEqual(
    view.groups.map((g) => (g.kind === 'parent' ? g.best?.value : g.kind)),
    [undefined, 0.4],
  );
  assert.equal(f.calls.filter((c) => c.path === 'runs/search').length, 1);
});

test('legacy parentless FINISHED run still counts', async () => {
  const f = fakeFetch({
    health: 'OK',
    'experiments/search': exps('p'),
    'runs/search': { runs: [run('r', { score: 0.6 })] },
  });
  const r = await metricState({ name: 'p', metric: score }, f.impl, env);
  assert.equal(r.kind === 'ok' && r.value, 0.6);
});

test('projectView unavailable → no groups', async () => {
  const f = fakeFetch({ health: 'OK', 'experiments/search': new TypeError('fetch failed') });
  const view = await projectView({ name: 'p', metric: score }, { kind: 'legacy' }, f.impl, env);
  assert.equal(view.state.kind, 'unavailable');
  assert.deepEqual(view.groups, []);
});
