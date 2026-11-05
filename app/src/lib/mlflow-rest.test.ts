import { test } from 'node:test';
import assert from 'node:assert/strict';
import { parseExperiments, parseRuns } from './mlflow-rest.ts';

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
