import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { isStrictExport, mlflowUri, projectsDir } from './config.ts';

test('projectsDir defaults to ../projects', () => {
  assert.equal(projectsDir({}), '../projects');
});

test('projectsDir reads DATALAB_PROJECTS_DIR', () => {
  assert.equal(projectsDir({ DATALAB_PROJECTS_DIR: 'x' }), 'x');
});

test('isStrictExport is true only for exactly 1', () => {
  assert.equal(isStrictExport({ DATALAB_STRICT_EXPORT: '1' }), true);
  assert.equal(isStrictExport({ DATALAB_STRICT_EXPORT: 'true' }), false);
});

test('F-2: resolves to 127.0.0.1:5050 and ignores MLFLOW_URL', () => {
  assert.equal(mlflowUri({}), 'http://127.0.0.1:5050');
  assert.equal(
    mlflowUri({ MLFLOW_URL: 'http://x:5000', MLFLOW_TRACKING_URI: 'http://x:5000' }),
    'http://127.0.0.1:5050',
  );
  assert.equal(mlflowUri({ DATALAB_MLFLOW_TRACKING_URI: 'http://h:1' }), 'http://h:1');
});

test('G-10: app default matches .env.example', () => {
  const text = readFileSync(new URL('../../../.env.example', import.meta.url), 'utf8');
  const line = text.split(/\r?\n/).find((l) => l.startsWith('DATALAB_MLFLOW_TRACKING_URI='));
  assert.equal(line?.slice('DATALAB_MLFLOW_TRACKING_URI='.length).trim(), mlflowUri({}));
});
