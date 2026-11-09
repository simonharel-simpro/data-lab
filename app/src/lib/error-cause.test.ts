import { test } from 'node:test';
import assert from 'node:assert/strict';
import { post } from './mlflow-rest.ts';
import { bestRun } from './mlflow.ts';

const base = 'http://h:1';
const env = { DATALAB_MLFLOW_TRACKING_URI: base };
const score = { key: 'score', goal: 'max' } as const;

test('should attach the fetch error as cause when the request fails', async () => {
  const boom = new Error('boom');
  const fetchImpl = (() => Promise.reject(boom)) as typeof fetch;
  await assert.rejects(
    post(base, 'runs/search', {}, fetchImpl),
    (e) => e instanceof Error && e.message === 'runs/search: boom' && e.cause === boom,
  );
});

// post() wraps every fetch rejection in an Error, so a non-Error only reaches fetchProject from the body read.
test('should report a non-Error rejection as text when MLflow is unreachable', async () => {
  const fetchImpl = (async () =>
    Object.assign(new Response('{}', { status: 200 }), {
      json: () => Promise.reject('socket closed'),
    })) as typeof fetch;
  assert.deepEqual(await bestRun('proj', score, fetchImpl, env), { kind: 'unavailable', reason: 'socket closed' });
});
