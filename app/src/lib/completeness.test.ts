import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { parse } from 'yaml';
import { cardSchema } from './card.ts';
import { missing, sections } from './completeness.ts';

const metric = { key: 'score', goal: 'max' } as const;
const full = '## Objectif\no\n## Approche\na\n';

test('status ladder: idée with Objectif filled is complete', () => {
  assert.deepEqual(missing({ status: 'idée' }, '## Objectif\nx\n'), []);
});

test('status ladder: conclu without Enseignements/Suite', () => {
  assert.deepEqual(missing({ status: 'conclu', data: 'd', metric }, full), ['Enseignements', 'Suite']);
});

test('status ladder: en cours without data/metric', () => {
  const gaps = missing({ status: 'en cours' }, full);
  assert.ok(gaps.includes('Données'));
  assert.ok(gaps.includes('Métrique'));
  assert.deepEqual(gaps, ['Données', 'Métrique']);
});

test('should require the conclu sections when status is abandonné', () => {
  assert.deepEqual(missing({ status: 'abandonné', data: 'd', metric }, full), ['Enseignements', 'Suite']);
});

test('should report Approche missing when status is en cours', () => {
  assert.deepEqual(missing({ status: 'en cours', data: 'd', metric }, '## Objectif\no\n'), ['Approche']);
});

test('U-9a: duplicate heading is filled if any occurrence has content', () => {
  const gaps = missing({ status: 'en cours', data: 'd', metric }, '## Objectif\no\n## Approche\nx\n## Approche\n');
  assert.deepEqual(gaps, []);
});

test('U-9b: lowercase heading counts as missing', () => {
  assert.deepEqual(missing({ status: 'idée' }, '## objectif\nx'), ['Objectif']);
});

test('U-9c: comment-only section counts as missing', () => {
  assert.deepEqual(missing({ status: 'idée' }, '## Objectif\n<!-- à remplir -->'), ['Objectif']);
});

test('U-9d: heading inside a code fence is not a section', () => {
  assert.deepEqual(missing({ status: 'idée' }, '```md\n## Objectif\nx\n```\n'), ['Objectif']);
});

test('should ignore a heading inside a ~~~ fence', () => {
  assert.deepEqual(missing({ status: 'idée' }, '~~~\n## Objectif\nx\n~~~\n'), ['Objectif']);
});

test('should keep a fence open until a closing fence at least as long', () => {
  // The three-backtick line does not close the four-backtick fence, so the second heading is still code.
  const body = '````\n## Objectif\nx\n```\n## Objectif\ny\n````\n';
  assert.deepEqual(missing({ status: 'idée' }, body), ['Objectif']);
});

test('should blank only its own section when a <!-- is never closed', () => {
  const body = '## Objectif\n<!-- never closed\n## Approche\na\n';
  assert.deepEqual(missing({ status: 'en cours', data: 'd', metric }, body), ['Objectif']);
});

test('should match an NFD heading against the NFC section name', () => {
  // No required section name has an accent, so this goes through sections() directly.
  const found = sections('## Re\u0301sume\u0301\nx\n');
  assert.equal(found.get('R\u00e9sum\u00e9'), true);
  assert.equal(found.has('Re\u0301sume\u0301'), false);
});

test('CRLF body is parsed', () => {
  assert.deepEqual(missing({ status: 'conclu', data: 'd', metric }, full + '## Enseignements\r\ne\r\n## Suite\r\ns\r\n'), []);
});

test('G-8: the template card is a valid idée card missing only Objectif', () => {
  // Repo root is 3 levels above app/src/lib/. datalab-new writes the title as a JSON (YAML double-quoted) string.
  const raw = readFileSync(new URL('../../../templates/project/PROJECT.md', import.meta.url), 'utf8')
    .replaceAll('__DATALAB_PROJECT__', 'demo')
    .replaceAll('__DATALAB_TITLE__', '"Demo"');
  const match = /^---\r?\n([\s\S]*?)\r?\n---\r?\n([\s\S]*)$/.exec(raw);
  assert.ok(match, 'template card has no frontmatter');
  const [, front, body] = match;
  assert.ok(front !== undefined && body !== undefined);
  const card = cardSchema.parse(parse(front));
  assert.equal(card.status, 'idée');
  assert.equal(card.title, 'Demo');
  assert.deepEqual(missing(card, body), ['Objectif']);
});
