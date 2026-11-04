import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { isValidName } from './name.ts';

// Repo root is 3 levels up from app/src/lib/; never resolve from the cwd.
const vectors = JSON.parse(
  readFileSync(new URL('../../../contracts/name_vectors.json', import.meta.url), 'utf8'),
) as { accept: string[]; reject: string[] };

test('F-12: should match the shared name vectors', () => {
  for (const name of vectors.accept) assert.equal(isValidName(name), true, `accept ${name}`);
  for (const name of vectors.reject) assert.equal(isValidName(name), false, `reject ${name}`);
  for (const word of ['no', 'yes', 'null']) assert.ok(vectors.reject.includes(word), `vectors reject ${word}`);
});

test('non-string names are invalid', () => {
  assert.equal(isValidName(false), false);
  assert.equal(isValidName(undefined), false);
});
