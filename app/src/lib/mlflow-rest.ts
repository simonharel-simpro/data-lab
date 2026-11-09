// MLflow REST transport + response shape checks. Read-only: only `search` and `/health` endpoints are called.
import { z } from 'astro/zod';

const TIMEOUT_MS = 10_000;

const Experiment = z.object({ experiment_id: z.string(), name: z.string() });
const Metric = z.object({ key: z.string(), value: z.unknown() });
const Param = z.object({ key: z.string(), value: z.string() });
const Tag = z.object({ key: z.string(), value: z.string() });
const Run = z.object({
  info: z.object({
    run_id: z.string(),
    run_name: z.string().optional().catch(undefined),
    experiment_id: z.string(),
    start_time: z.coerce.number().catch(0),
    status: z.string().optional().catch(undefined),
  }),
  data: z
    .object({
      metrics: z.array(z.unknown()).default([]),
      params: z.array(z.unknown()).default([]),
      tags: z.array(z.unknown()).default([]),
    })
    .default({ metrics: [], params: [], tags: [] }),
});
// MLflow omits empty lists: an absent list means empty.
const ExperimentsResponse = z.object({ experiments: z.array(Experiment).default([]) });
const RunsResponse = z.object({ runs: z.array(Run).default([]), next_page_token: z.string().optional() });

export type MlflowExperiment = z.infer<typeof Experiment>;
export type MlflowMetric = z.infer<typeof Metric>;
export type MlflowParam = z.infer<typeof Param>;
export type MlflowTag = z.infer<typeof Tag>;
// `z.infer` alone would type metrics/params/tags as unknown[]: parseRunsPage narrows them.
export type MlflowRun = Omit<z.infer<typeof Run>, 'data'> & {
  data: { metrics: MlflowMetric[]; params: MlflowParam[]; tags: MlflowTag[] };
};

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
    throw new Error(`${path}: ${err instanceof Error ? err.message : String(err)}`, { cause: err });
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

function keep<T extends z.ZodType>(schema: T, items: readonly unknown[]): z.infer<T>[] {
  return items.flatMap((item) => {
    const r = schema.safeParse(item);
    return r.success ? [r.data] : [];
  });
}

/** Metrics without a string `key`, and params/tags without string `key`/`value`, are dropped, not fatal. */
export function parseRunsPage(res: unknown): { runs: MlflowRun[]; nextPageToken?: string } {
  const page = parse(RunsResponse, res);
  const runs = page.runs.map((run) => ({
    ...run,
    data: {
      metrics: keep(Metric, run.data.metrics),
      params: keep(Param, run.data.params),
      tags: keep(Tag, run.data.tags),
    },
  }));
  return page.next_page_token ? { runs, nextPageToken: page.next_page_token } : { runs };
}

export function parseRuns(res: unknown): MlflowRun[] {
  return parseRunsPage(res).runs;
}

/** Every page of `runs/search` for `body`; a repeated token or more than `maxPages` pages is an error (F-19). */
export async function searchAllRuns(
  base: string,
  body: Record<string, unknown>,
  fetchImpl: typeof fetch,
  maxPages = 50,
): Promise<MlflowRun[]> {
  const runs: MlflowRun[] = [];
  const seen = new Set<string>();
  let token: string | undefined;
  for (let page = 0; page < maxPages; page++) {
    const res = parseRunsPage(
      await post(base, 'runs/search', token ? { ...body, page_token: token } : body, fetchImpl),
    );
    runs.push(...res.runs);
    token = res.nextPageToken;
    if (!token) return runs;
    if (seen.has(token)) break;
    seen.add(token);
  }
  throw new Error('runs/search: pagination did not end');
}
