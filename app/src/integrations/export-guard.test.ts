import { test, beforeEach } from 'node:test';
import assert from 'node:assert/strict';
import { readReport } from '../lib/report.ts';
import { checkReport } from './export-guard.ts';

beforeEach(() => readReport().clear());

const quiet = () => {};

test('F-1: strict mode fails when any card is unavailable', () => {
  assert.throws(() => checkReport(new Map([['p', 'x']]), { DATALAB_STRICT_EXPORT: '1' }, quiet), /p/);
  assert.doesNotThrow(() => checkReport(new Map([['p', 'x']]), {}, quiet));
});

test('strict mode passes when the report is empty', () => {
  assert.doesNotThrow(() => checkReport(new Map(), { DATALAB_STRICT_EXPORT: '1' }, quiet));
});

test('one log line per unavailable project', () => {
  const lines: string[] = [];
  checkReport(new Map([['a', 'r1'], ['b', 'r2']]), {}, (l) => lines.push(l));
  assert.equal(lines.length, 2);
  const first = lines[0];
  assert.ok(first !== undefined);
  assert.match(first, /a.*r1/);
});

test('F-1: the astro:build:done hook reads the shared build report', async () => {
  const { exportGuard } = await import('./export-guard.ts');
  readReport().set('p', 'down');
  const warned: string[] = [];
  const logger = { warn: (l: string) => warned.push(l) } as never;
  const hook = exportGuard({ DATALAB_STRICT_EXPORT: '1' }).hooks['astro:build:done'];
  assert.throws(() => hook?.({ logger } as never), /p/);
  assert.deepEqual(warned, ["metrics unavailable for 'p': down"]);
});
