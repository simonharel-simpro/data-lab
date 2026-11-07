import { test } from 'node:test';
import assert from 'node:assert/strict';
import { parseExperiments, parseRuns, searchAllRuns } from './mlflow-rest.ts';

const info = { run_id: 'r1', experiment_id: '1', start_time: 5 };

test('should leave run_name undefined when MLflow omits it', () => {
  const [run] = parseRuns({ runs: [{ info, data: { metrics: [] } }] });
  assert.ok(run);
  assert.equal(run.info.run_name, undefined);
  assert.equal(run.info.run_id, 'r1');
});

test('should read a non-numeric start_time as 0', () => {
  const [run] = parseRuns({ runs: [{ info: { ...info, start_time: 'soon' }, data: { metrics: [] } }] });
  assert.ok(run);
  assert.equal(run.info.start_time, 0);
});

test('should drop a metric without a string key', () => {
  const metrics = [{ key: 'score', value: 0.5 }, { key: 7, value: 1 }, { value: 2 }, 'junk'];
  const [run] = parseRuns({ runs: [{ info, data: { metrics } }] });
  assert.ok(run);
  assert.deepEqual(run.data.metrics, [{ key: 'score', value: 0.5 }]);
});

test('should read an absent runs list as empty', () => {
  assert.deepEqual(parseRuns({}), []);
});

test('should throw on a malformed run or experiment', () => {
  assert.throws(() => parseRuns({ runs: [{ info: { run_id: 1, experiment_id: '1' } }] }), /unexpected response/);
  assert.throws(() => parseExperiments({ experiments: [{ experiment_id: '1' }] }), /unexpected response/);
});

test('should keep string params and drop malformed ones', () => {
  const params = [{ key: 'collection', value: 'MiniRag_x' }, { key: 'k', value: 3 }, { value: 'v' }, 'junk'];
  const [run] = parseRuns({ runs: [{ info, data: { metrics: [], params } }] });
  assert.ok(run);
  assert.deepEqual(run.data.params, [{ key: 'collection', value: 'MiniRag_x' }]);
});

test('should read absent params as empty', () => {
  const [run] = parseRuns({ runs: [{ info, data: { metrics: [] } }] });
  assert.deepEqual(run?.data.params, []);
});

test('F-19: tags parsed, bad ones dropped', () => {
  const tags = [{ key: 'mlflow.parentRunId', value: 'p1' }, { key: 1 }];
  const [run, bare] = parseRuns({
    runs: [{ info: { ...info, status: 'FAILED' }, data: { metrics: [], tags } }, { info, data: { metrics: [] } }],
  });
  assert.deepEqual(run?.data.tags, [{ key: 'mlflow.parentRunId', value: 'p1' }]);
  assert.equal(run?.info.status, 'FAILED');
  assert.deepEqual(bare?.data.tags, []);
  assert.equal(bare?.info.status, undefined);
});

function pagedFetch(pages: (n: number) => unknown) {
  const bodies: Record<string, unknown>[] = [];
  const impl = (async (_url: string | URL, init?: RequestInit) => {
    bodies.push(JSON.parse(String(init?.body)));
    return new Response(JSON.stringify(pages(bodies.length)), { status: 200 });
  }) as typeof fetch;
  return { impl, bodies };
}

test('F-19: follows next_page_token', async () => {
  const a = { info: { ...info, run_id: 'a' } };
  const b = { info: { ...info, run_id: 'b' } };
  const f = pagedFetch((n) => (n === 1 ? { runs: [a], next_page_token: 't' } : { runs: [b] }));
  const runs = await searchAllRuns('http://h:1', { filter: 'x' }, f.impl);
  assert.deepEqual(runs.map((r) => r.info.run_id), ['a', 'b']);
  assert.equal(f.bodies.length, 2);
  assert.equal(f.bodies[0]?.page_token, undefined);
  assert.equal(f.bodies[1]?.page_token, 't');
  assert.equal(f.bodies[1]?.filter, 'x');
});

test('F-19: pagination that never ends throws', async () => {
  const f = pagedFetch(() => ({ runs: [], next_page_token: 't' }));
  await assert.rejects(searchAllRuns('http://h:1', {}, f.impl), /pagination did not end/);
  assert.equal(f.bodies.length, 2, 'a repeated token stops at once, not after maxPages');
  const g = pagedFetch((n) => ({ runs: [], next_page_token: `t${n}` }));
  await assert.rejects(searchAllRuns('http://h:1', {}, g.impl, 3), /pagination did not end/);
  assert.equal(g.bodies.length, 3);
});
