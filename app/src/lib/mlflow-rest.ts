// MLflow REST transport + response shape checks. Read-only: only `search` and `/health` endpoints are called.

const TIMEOUT_MS = 10_000;

export type MlflowMetric = { key: string; value: unknown };
export type MlflowRun = {
  info: { run_id: string; run_name?: string; experiment_id: string; start_time: number };
  data: { metrics: MlflowMetric[] };
};
export type MlflowExperiment = { experiment_id: string; name: string };

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
    const name = (err as { name?: unknown }).name;
    if (name === 'TimeoutError' || name === 'AbortError') throw new TransientError(`${path}: timed out`);
    throw new Error(`${path}: ${(err as Error).message}`);
  }
  if (res.status >= 500) throw new TransientError(`${path}: HTTP ${res.status}`);
  if (!res.ok) throw new Error(`${path}: HTTP ${res.status}`);
  return res.json();
}

const isObject = (v: unknown): v is Record<string, unknown> => typeof v === 'object' && v !== null && !Array.isArray(v);

/** The array under `key` of an object response; absent means empty (MLflow omits empty lists). */
function listOf(res: unknown, key: string): unknown[] {
  if (!isObject(res)) throw new Error(`unexpected response: not an object`);
  const v = res[key];
  if (v === undefined) return [];
  if (!Array.isArray(v)) throw new Error(`unexpected response: '${key}' is not an array`);
  return v;
}

export function parseExperiments(res: unknown): MlflowExperiment[] {
  return listOf(res, 'experiments').map((e) => {
    if (!isObject(e) || typeof e.experiment_id !== 'string' || typeof e.name !== 'string') {
      throw new Error('unexpected response: malformed experiment');
    }
    return { experiment_id: e.experiment_id, name: e.name };
  });
}

export function parseRuns(res: unknown): MlflowRun[] {
  return listOf(res, 'runs').map((r) => {
    const info = isObject(r) ? r.info : undefined;
    const data = isObject(r) && isObject(r.data) ? r.data : {};
    if (!isObject(info) || typeof info.run_id !== 'string' || typeof info.experiment_id !== 'string') {
      throw new Error('unexpected response: malformed run');
    }
    const metrics = listOf(data, 'metrics').filter(
      (m): m is MlflowMetric => isObject(m) && typeof m.key === 'string',
    );
    return {
      info: {
        run_id: info.run_id,
        run_name: typeof info.run_name === 'string' ? info.run_name : undefined,
        experiment_id: info.experiment_id,
        start_time: Number(info.start_time) || 0,
      },
      data: { metrics },
    };
  });
}
