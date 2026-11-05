// MLflow REST transport + response shape checks. Read-only: only `search` and `/health` endpoints are called.
import { z } from 'astro/zod';

const TIMEOUT_MS = 10_000;

const Experiment = z.object({ experiment_id: z.string(), name: z.string() });
const Metric = z.object({ key: z.string(), value: z.unknown() });
const Param = z.object({ key: z.string(), value: z.string() });
const Run = z.object({
  info: z.object({
    run_id: z.string(),
    run_name: z.string().optional().catch(undefined),
    experiment_id: z.string(),
    start_time: z.coerce.number().catch(0),
  }),
  data: z
    .object({ metrics: z.array(z.unknown()).default([]), params: z.array(z.unknown()).default([]) })
    .default({ metrics: [], params: [] }),
});
// MLflow omits empty lists: an absent list means empty.
const ExperimentsResponse = z.object({ experiments: z.array(Experiment).default([]) });
const RunsResponse = z.object({ runs: z.array(Run).default([]) });

export type MlflowExperiment = z.infer<typeof Experiment>;
export type MlflowMetric = z.infer<typeof Metric>;
export type MlflowParam = z.infer<typeof Param>;
// `z.infer` alone would type metrics/params as unknown[]: parseRuns narrows them.
export type MlflowRun = Omit<z.infer<typeof Run>, 'data'> & { data: { metrics: MlflowMetric[]; params: MlflowParam[] } };

/** An HTTP or transport failure worth one retry (timeout or 5xx, F-1). */
export class TransientError extends Error {}

export async function post(base: string, path: string, body: unknown, fetchImpl: typeof fetch): Promise<unknown> {
  let res: Response;
  try {
    res = await fetchImpl(`${base}/api/2.0/mlflow/${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(TIMEOUT_MS),
    });
  } catch (err) {
    const name = err instanceof Error ? err.name : undefined;
    if (name === 'TimeoutError' || name === 'AbortError') throw new TransientError(`${path}: timed out`);
    throw new Error(`${path}: ${err instanceof Error ? err.message : String(err)}`);
  }
  if (res.status >= 500) throw new TransientError(`${path}: HTTP ${res.status}`);
  if (!res.ok) throw new Error(`${path}: HTTP ${res.status}`);
  return res.json();
}

function parse<T extends z.ZodType>(schema: T, res: unknown): z.infer<T> {
  const r = schema.safeParse(res);
  if (!r.success) throw new Error(`unexpected response: ${r.error.issues[0]?.message ?? 'shape'}`);
  return r.data;
}

export function parseExperiments(res: unknown): MlflowExperiment[] {
  return parse(ExperimentsResponse, res).experiments;
}

/** Metrics without a string `key`, and params without string `key`/`value`, are dropped, not fatal. */
export function parseRuns(res: unknown): MlflowRun[] {
  return parse(RunsResponse, res).runs.map((run) => ({
    ...run,
    data: {
      metrics: run.data.metrics.flatMap((m) => {
        const r = Metric.safeParse(m);
        return r.success ? [r.data] : [];
      }),
      params: run.data.params.flatMap((p) => {
        const r = Param.safeParse(p);
        return r.success ? [r.data] : [];
      }),
    },
  }));
}
