import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { cardSchema, GOALS, METRIC_KEY_RE } from './card.ts';

const base = { name: 'p', title: 'T', status: 'idée' };

test('F-7: should reject a metric key containing a backtick', () => {
  const r = cardSchema.safeParse({ ...base, metric: { key: 'a`b', goal: 'max' } });
  assert.equal(r.success, false);
});

test('F-7: should reject a metric key containing a quote, a space or a dollar sign', () => {
  for (const key of ['a"b', "a'b", 'a b', 'a$b']) {
    const r = cardSchema.safeParse({ ...base, metric: { key, goal: 'max' } });
    assert.equal(r.success, false, key);
  }
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

test('F-18: METRIC_KEY_RE matches the Python literal', () => {
  const py = readFileSync(new URL('../../../packages/datalab/src/datalab/project.py', import.meta.url), 'utf8');
  const m = /METRIC_KEY_RE: Final = re\.compile\(r"(.+)"\)/.exec(py);
  assert.ok(m, 'METRIC_KEY_RE literal not found in project.py');
  assert.equal(m[1], METRIC_KEY_RE.source);
});

test('goal value set matches contracts/value_sets.json', () => {
  const contract = JSON.parse(
    readFileSync(new URL('../../../contracts/value_sets.json', import.meta.url), 'utf8'),
  ) as { goals: string[] };
  assert.deepEqual([...GOALS], contract.goals);
});
