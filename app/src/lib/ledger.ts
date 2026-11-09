// run.json reader for the stepper: the strict schema + I-1, in Python's check order (datalab.ledger.parse).
// I-2..I-15 and V-1..V-3 stay Python-only (the `ledger` hook and CI guard them). Read-only: never writes.
import { existsSync, readFileSync, realpathSync } from 'node:fs';
import { isAbsolute, join, relative, resolve } from 'node:path';
import { z } from 'astro/zod';
import milestonesJson from '../../../contracts/milestones.json' with { type: 'json' };
import { reportInvalidLedger } from './report.ts';

export const KINDS = ['training', 'comparison'] as const;
export const STATUSES = ['todo', 'produced', 'validated'] as const;
export const DECISIONS = ['validate', 'correct', 'redo'] as const;
export type Kind = (typeof KINDS)[number];
export type Status = (typeof STATUSES)[number];
export type Decision = (typeof DECISIONS)[number];

const RUN_JSON = 'run.json';
const BOM = '﻿';

const milestonesSchema = z
  .object({
    schema_version: z.literal(1),
    milestones: z.array(z.object({ id: z.string(), agent: z.string() }).strict()),
    sequences: z.object({ training: z.array(z.string()), comparison: z.array(z.string()) }).strict(),
    freeze_after: z.string(),
  })
  .strict();
const contract = milestonesSchema.parse(milestonesJson);
export const MILESTONES: {
  milestones: { id: string; agent: string }[];
  sequences: Record<Kind, string[]>;
  freeze_after: string;
} = { milestones: contract.milestones, sequences: contract.sequences, freeze_after: contract.freeze_after };

/** Each kind's sequence with its agents; a sequence id with no milestone entry is a broken contract (throws). */
const STEP_AGENTS = Object.fromEntries(
  KINDS.map((kind) => [
    kind,
    MILESTONES.sequences[kind].map((id) => {
      const m = MILESTONES.milestones.find((x) => x.id === id);
      if (!m) throw new Error(`contracts/milestones.json: ${kind} sequence names unknown milestone '${id}'`);
      return m;
    }),
  ]),
) as Record<Kind, { id: string; agent: string }[]>;

const sha = z.string().regex(/^[0-9a-f]{64}$/);
const nonEmpty = z.string().min(1);
const pyList = (xs: readonly string[]) => `[${xs.map((x) => `'${x}'`).join(', ')}]`;

export const runLedgerSchema = z
  .object({
    schema_version: z.literal(1),
    kind: z.enum(KINDS),
    current_milestone: z.string(),
    milestones: z.record(
      z.string(),
      z
        .object({ status: z.enum(STATUSES), artifacts: z.array(z.string()), decision: z.enum(DECISIONS).nullable() })
        .strict(),
    ),
    dataset: z.object({ id: nonEmpty, hash: nonEmpty }).strict().nullable(),
    metric: nonEmpty,
    split_summary: z.string().nullable(),
    split_sha256: sha.nullable(),
    data_sha256: sha.nullable(),
    features: z.array(z.string()).min(1).nullable(),
    winner: z.object({ candidate: nonEmpty, run_id: nonEmpty }).strict().nullable(),
    test_looks: z.array(z.object({ split_sha256: sha, run_id: nonEmpty, note: z.string() }).strict()),
    decisions_log: z.array(z.object({ milestone: z.string(), decision: z.enum(DECISIONS), note: nonEmpty }).strict()),
  })
  .strict()
  .superRefine((lg, ctx) => {
    const seq = MILESTONES.sequences[lg.kind];
    const keys = Object.keys(lg.milestones);
    if (keys.length !== seq.length || !seq.every((m) => keys.includes(m))) {
      const got = pyList([...keys].sort());
      ctx.addIssue({
        code: 'custom',
        message: `I-1: milestones must be exactly ${pyList(seq)} for a ${lg.kind} ledger, got ${got}`,
      });
    }
  });
export type RunLedger = z.infer<typeof runLedgerSchema>;

export type Step = {
  id: string;
  agent: string;
  status: Status;
  // `redo` is legal for the schema; only Python's I-3 rejects it on a milestone, so the app shows it as is.
  decision: Decision | null;
  current: boolean;
  artifacts: { path: string; exists: boolean }[];
  notes: { decision: Decision; note: string }[];
};
export type LedgerState =
  | { kind: 'absent' }
  | { kind: 'invalid'; reason: string }
  | {
      kind: 'ok';
      ledgerKind: Kind;
      metric: string;
      steps: Step[];
      splitSha256: string | null;
      dataSha256: string | null;
    };

function describe(issue: z.core.$ZodIssue): string {
  if (issue.code === 'custom') return issue.message;
  const path = [...issue.path, ...(issue.code === 'unrecognized_keys' ? issue.keys.slice(0, 1) : [])];
  return `schema: ${path.map(String).join('.')}: ${issue.message}`;
}

/** Check order (first failure wins): JSON, `kind` present (U-13), schema, then I-1. Never throws. */
export function parseLedger(text: string): { ok: true; ledger: RunLedger } | { ok: false; reason: string } {
  let doc: unknown;
  try {
    doc = JSON.parse(text.startsWith(BOM) ? text.slice(BOM.length) : text);
  } catch (err) {
    return { ok: false, reason: `invalid JSON: ${err instanceof Error ? err.message : String(err)}` };
  }
  if (typeof doc === 'object' && doc !== null && !Array.isArray(doc) && !('kind' in doc)) {
    return { ok: false, reason: 'unsupported schema (kind missing)' };
  }
  const r = runLedgerSchema.safeParse(doc);
  if (r.success) return { ok: true, ledger: r.data };
  const first = r.error.issues[0];
  return { ok: false, reason: first ? describe(first) : 'schema: invalid' };
}

export type LedgerFs = { exists(p: string): boolean; read(p: string): string; real(p: string): string };
const nodeFs: LedgerFs = { exists: existsSync, read: (p) => readFileSync(p, 'utf8'), real: realpathSync };

/** Exists only when the file exists and its real path stays strictly inside the project's real path (U-15). */
function artifactExists(projectDir: string, path: string, fs: LedgerFs): boolean {
  const target = resolve(projectDir, path);
  try {
    if (!fs.exists(target)) return false;
    const rel = relative(fs.real(projectDir), fs.real(target));
    return rel !== '' && !isAbsolute(rel) && rel.split(/[\\/]/)[0] !== '..';
  } catch {
    return false; // a dangling link or an unreadable parent: shown as missing, never a crash
  }
}

function toSteps(lg: RunLedger, projectDir: string, fs: LedgerFs): Step[] {
  return STEP_AGENTS[lg.kind].flatMap(({ id, agent }) => {
    const entry = lg.milestones[id];
    if (!entry) return []; // unreachable once I-1 holds; narrows the record lookup
    return [
      {
        id,
        agent,
        status: entry.status,
        decision: entry.decision,
        // The ledger keeps its pointer on the last milestone once all are validated (I-6): no step is current then.
        current: id === lg.current_milestone && entry.status !== 'validated',
        artifacts: entry.artifacts.map((path) => ({ path, exists: artifactExists(projectDir, path, fs) })),
        notes: lg.decisions_log.filter((l) => l.milestone === id).map(({ decision, note }) => ({ decision, note })),
      },
    ];
  });
}

export function readLedger(projectDir: string, fs: LedgerFs = nodeFs): LedgerState {
  const path = join(projectDir, RUN_JSON);
  if (!fs.exists(path)) return { kind: 'absent' };
  let text: string;
  try {
    text = fs.read(path);
  } catch (err) {
    // The code only: the message carries an absolute path that must not reach the static export.
    return { kind: 'invalid', reason: `cannot read: ${(err as NodeJS.ErrnoException).code ?? 'error'}` };
  }
  const r = parseLedger(text);
  if (!r.ok) return { kind: 'invalid', reason: r.reason };
  const lg = r.ledger;
  return {
    kind: 'ok',
    ledgerKind: lg.kind,
    metric: lg.metric,
    steps: toSteps(lg, projectDir, fs),
    splitSha256: lg.split_sha256,
    dataSha256: lg.data_sha256,
  };
}

/** `readLedger` + one build-report entry per invalid ledger (F-20: a strict export then fails). */
export function ledgerState(project: string, projectDir: string, fs?: LedgerFs): LedgerState {
  const state = readLedger(projectDir, fs);
  if (state.kind === 'invalid') reportInvalidLedger(project, state.reason);
  return state;
}
