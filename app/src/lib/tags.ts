// MLflow tag names the app reads (contracts/mlflow_tags.json; tags.test.ts keeps the two in sync).
export const TAGS = {
  candidate: 'candidate',
  split: 'split',
  entry: 'entry',
  n_children: 'n_children',
  n_failed: 'n_failed',
  failed_candidates: 'failed_candidates',
  test_look: 'test_look',
  split_sha256: 'split_sha256',
  data_sha256: 'data_sha256',
  score_on: 'score_on',
  config_sha256: 'config_sha256',
} as const;

/** Set by MLflow itself on a nested run; not one of the project's contract tags. */
export const PARENT_RUN_ID = 'mlflow.parentRunId';

/** MLflow run statuses the app distinguishes; any other (RUNNING, SCHEDULED, KILLED, absent) counts as neither. */
export const RUN_STATUS = { finished: 'FINISHED', failed: 'FAILED' } as const;

/** The `split` tag value of an evaluation run on the frozen test split (F-13). */
export const TEST_SPLIT = 'test';
