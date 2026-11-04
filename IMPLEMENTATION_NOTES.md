# Implementation notes

## Phase 1 — MLflow `experiments/search` with an empty body

- Plan assumed: `curl -X POST 127.0.0.1:5050/api/2.0/mlflow/experiments/search -d '{}'` returns HTTP 200, and a non-200 would mean an allowed-hosts problem to fix in compose.
- Territory was: MLflow 3.17.2 answers 400 `INVALID_PARAMETER_VALUE: Invalid value 0 for parameter 'max_results'` to a POST without `max_results` (Demo-RAG's server on :5000 does the same). Hosts are fine: `{"max_results": 100}` → 200 on 127.0.0.1:5050, and a foreign `Host:` header → 403, so the host check is active and accepts the 5050→5000 mapping.
- I did: no compose change (no `--allowed-hosts` needed); smoke recorded with `{"max_results": 100}`.
- One-off or pattern?: likely recurs — every MLflow REST search (the 2B app's `experiments/search` / `runs/search`) must send an explicit positive `max_results`.
