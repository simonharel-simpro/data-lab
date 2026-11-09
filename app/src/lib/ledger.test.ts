import { test, beforeEach } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { join } from 'node:path';
import {
  DECISIONS,
  KINDS,
  ledgerState,
  MILESTONES,
  parseLedger,
  readLedger,
  STATUSES,
  type LedgerFs,
  type LedgerState,
} from './ledger.ts';
import { readReport } from './report.ts';
import { checkReport } from '../integrations/export-guard.ts';

type Vector = { name: string; run: unknown; rule?: string; checked_by?: string[] };
const vectors = JSON.parse(
  readFileSync(new URL('../../../contracts/run_ledger_vectors.json', import.meta.url), 'utf8'),
) as { valid: Vector[]; invalid: (Vector & { rule: string; checked_by: string[] })[] };
const vector = (name: string): Vector => {
  const v = [...vectors.valid, ...vectors.invalid].find((x) => x.name === name);
  assert.ok(v, name);
  return v;
};
const contract = JSON.parse(
  readFileSync(new URL('../../../contracts/value_sets.json', import.meta.url), 'utf8'),
) as { statuses: string[]; decisions: string[]; kinds: string[] };
const PREFIX: Record<string, string> = { schema: 'schema:', 'U-13': 'unsupported schema (kind missing)', 'I-1': 'I-1:' };
const fixture = fileURLToPath(new URL('../../test-fixtures/ledger/valid', import.meta.url));

/** In-memory LedgerFs: `files` maps a path to its text, `links` maps a path to its real path. */
function fakeFs(files: Map<string, string>, links = new Map<string, string>()): LedgerFs {
  return {
    exists: (p) => files.has(p),
    read: (p) => files.get(p) ?? '',
    real: (p) => links.get(p) ?? p,
  };
}
function ok(state: LedgerState): Extract<LedgerState, { kind: 'ok' }> {
  assert.ok(state.kind === 'ok', JSON.stringify(state));
  return state;
}

beforeEach(() => readReport().clear());

test('F-18: valid vectors parse', () => {
  for (const v of vectors.valid) {
    const r = parseLedger(JSON.stringify(v.run));
    assert.equal(r.ok, true, `${v.name}: ${r.ok ? '' : r.reason}`);
  }
});

test('F-18: app-checked invalid vectors fail with their rule', () => {
  const checked = vectors.invalid.filter((v) => v.checked_by.includes('app'));
  assert.ok(checked.length > 0);
  for (const v of checked) {
    const r = parseLedger(JSON.stringify(v.run));
    const prefix = PREFIX[v.rule];
    assert.ok(prefix, `unknown app rule ${v.rule}`);
    assert.ok(!r.ok && r.reason.startsWith(prefix), `${v.name}: ${r.ok ? 'accepted' : r.reason}`);
  }
});

test('F-18: Python-only vectors are accepted by the app', () => {
  const pythonOnly = vectors.invalid.filter((v) => v.checked_by.length === 1 && v.checked_by[0] === 'python');
  assert.ok(pythonOnly.length > 0);
  for (const v of pythonOnly) {
    const r = parseLedger(JSON.stringify(v.run));
    assert.equal(r.ok, true, `${v.name}: ${r.ok ? '' : r.reason}`);
  }
});

test('F-18: milestones contract', () => {
  assert.equal(MILESTONES.sequences.training.length, 9);
  assert.equal(MILESTONES.sequences.comparison.length, 7);
  assert.equal(MILESTONES.freeze_after, 'dataset');
});

test('ledger value sets match contracts/value_sets.json', () => {
  assert.deepEqual([...STATUSES], contract.statuses);
  assert.deepEqual([...DECISIONS], contract.decisions);
  assert.deepEqual([...KINDS], contract.kinds);
});

test('F-20: missing run.json renders nothing', () => {
  assert.deepEqual(ledgerState('p', '/x/p', fakeFs(new Map())), { kind: 'absent' });
  assert.equal(readReport().size, 0);
});

test('F-20: invalid run.json is reported and strict export fails', (t) => {
  t.mock.method(console, 'warn', () => {});
  const state = ledgerState('p', '/x/p', fakeFs(new Map([['/x/p/run.json', '{"schema_version": 1,']])));
  assert.ok(state.kind === 'invalid' && state.reason.startsWith('invalid JSON:'), JSON.stringify(state));
  assert.ok(readReport().has('run.json:p'));
  assert.throws(() => checkReport(readReport(), { DATALAB_STRICT_EXPORT: '1' }, () => {}), /run\.json:p/);
});

test('F-20: a non-object document is a schema error, not U-13', () => {
  const r = parseLedger('[]');
  assert.ok(!r.ok && r.reason.startsWith('schema:'), JSON.stringify(r));
});

test('F-20: a half-valid document is a schema reason, never a throw', () => {
  const base = vector('training-mid-run').run as Record<string, unknown>;
  for (const patch of [{ kind: 'bogus' }, { milestones: undefined }, { milestones: 5 }, { milestones: { eda: 'x' } }]) {
    const r = parseLedger(JSON.stringify({ ...base, ...patch }));
    assert.ok(!r.ok && r.reason.startsWith('schema:'), `${JSON.stringify(patch)}: ${JSON.stringify(r)}`);
  }
});

test('BOM is stripped like Python', () => {
  const first = vectors.valid[0];
  assert.ok(first);
  assert.equal(parseLedger('﻿' + JSON.stringify(first.run)).ok, true);
});

test('U-15: missing artifact flagged, present one not', () => {
  const steps = ok(readLedger(fixture)).steps;
  const art = (id: string) => steps.find((s) => s.id === id)?.artifacts;
  assert.deepEqual(art('scoping'), [{ path: 'scope.md', exists: true }]);
  assert.deepEqual(art('cleaning'), [{ path: 'src/demo/data/clean.py', exists: false }]);
});

test('U-15: symlink escape is missing', () => {
  const text = JSON.stringify(vector('training-mid-run').run);
  const files = new Map([['/x/p/run.json', text], ['/x/p/scope.md', 'secret link']]);
  const fs = fakeFs(files, new Map([['/x/p/scope.md', '/etc/passwd']]));
  const scoping = ok(readLedger('/x/p', fs)).steps.find((s) => s.id === 'scoping');
  assert.deepEqual(scoping?.artifacts, [{ path: 'scope.md', exists: false }]);
});

test('U-15: an absolute or parent-relative artifact is missing even when the file exists', () => {
  const run = structuredClone(vector('training-mid-run').run) as { milestones: Record<string, { artifacts: string[] }> };
  const scoping = run.milestones.scoping;
  assert.ok(scoping);
  scoping.artifacts = ['/x/q/a.md', '../q/a.md'];
  const files = new Map([['/x/p/run.json', JSON.stringify(run)], ['/x/q/a.md', 'outside']]);
  const step = ok(readLedger('/x/p', fakeFs(files))).steps.find((s) => s.id === 'scoping');
  assert.deepEqual(step?.artifacts.map((a) => a.exists), [false, false]);
});

test('steps follow the kind sequence, mark current, carry notes', () => {
  const state = ok(readLedger(fixture));
  assert.deepEqual(state.steps.map((s) => s.id), MILESTONES.sequences.training);
  assert.deepEqual(state.steps.filter((s) => s.current).map((s) => s.id), ['eda']);
  assert.deepEqual(state.steps[0]?.notes, [{ decision: 'validate', note: 'ok' }]);
  assert.equal(state.steps[0]?.agent, 'ds-scoper');
  assert.equal(state.ledgerKind, 'training');
  assert.equal(state.splitSha256, 'a'.repeat(64));
  assert.equal(state.dataSha256, null);
});

test('no current step once all are validated', () => {
  const files = new Map([[join('/x/p', 'run.json'), JSON.stringify(vector('comparison-complete').run)]]);
  const state = ok(readLedger('/x/p', fakeFs(files)));
  assert.equal(state.steps.length, 7);
  assert.ok(state.steps.every((s) => !s.current));
});

test('an unreadable run.json is invalid, never a throw', () => {
  const fs: LedgerFs = {
    exists: () => true,
    read: () => { throw Object.assign(new Error('EACCES: permission denied, open /x/p/run.json'), { code: 'EACCES' }); },
    real: (p) => p,
  };
  assert.deepEqual(readLedger('/x/p', fs), { kind: 'invalid', reason: 'cannot read: EACCES' });
});
