import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { TAGS } from './tags.ts';

const contract = JSON.parse(
  readFileSync(new URL('../../../contracts/mlflow_tags.json', import.meta.url), 'utf8'),
) as { tags: string[] };

test('F-18: tag names match the contract', () => {
  assert.deepEqual(Object.values(TAGS).sort(), [...contract.tags].sort());
});
