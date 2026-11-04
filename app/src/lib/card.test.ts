import { test } from 'node:test';
import assert from 'node:assert/strict';
import { cardSchema } from './card.ts';

const base = { name: 'p', title: 'T', status: 'idée' };

test('F-7: should reject a metric key containing a backtick', () => {
  const r = cardSchema.safeParse({ ...base, metric: { key: 'a`b', goal: 'max' } });
  assert.equal(r.success, false);
});

test('a plain metric key is accepted', () => {
  const r = cardSchema.safeParse({ ...base, metric: { key: 'eval/score_v1.2-x', goal: 'min' } });
  assert.equal(r.success, true);
});

test('G-9: NFD status is accepted', () => {
  const r = cardSchema.parse({ ...base, status: 'idée' });
  assert.equal(r.status, 'idée');
  assert.deepEqual(r.tags, []);
});

test('unknown status rejected', () => {
  assert.equal(cardSchema.safeParse({ ...base, status: 'fini' }).success, false);
});

test('reserved or malformed name rejected', () => {
  assert.equal(cardSchema.safeParse({ ...base, name: 'no' }).success, false);
  assert.equal(cardSchema.safeParse({ ...base, name: 'Bad_Name' }).success, false);
});
