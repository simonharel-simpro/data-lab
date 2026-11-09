// The only module that knows the app's env var names. Each reader takes `env`, so tests stay hermetic.
export type Env = Record<string, string | undefined>;

/** Never MLFLOW_URL / MLFLOW_TRACKING_URI (Demo-RAG's, F-2). */
export const mlflowUri = (env: Env = process.env): string => env.DATALAB_MLFLOW_TRACKING_URI ?? 'http://127.0.0.1:5050';
/** Exists only for the CI build fixtures (app/test-fixtures/*). */
export const projectsDir = (env: Env = process.env): string => env.DATALAB_PROJECTS_DIR ?? '../projects';
/** Weavit UI web mode (`pnpm web` in tools/weavit-ui). */
export const weavitUrl = (env: Env = process.env): string => env.DATALAB_WEAVIT_URL ?? 'http://127.0.0.1:3080';
export const isStrictExport = (env: Env = process.env): boolean => env.DATALAB_STRICT_EXPORT === '1';
