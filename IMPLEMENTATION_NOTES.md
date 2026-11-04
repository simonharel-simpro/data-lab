# Implementation notes

## Phase 1 — MLflow `experiments/search` with an empty body

- Plan assumed: `curl -X POST 127.0.0.1:5050/api/2.0/mlflow/experiments/search -d '{}'` returns HTTP 200, and a non-200 would mean an allowed-hosts problem to fix in compose.
- Territory was: MLflow 3.17.2 answers 400 `INVALID_PARAMETER_VALUE: Invalid value 0 for parameter 'max_results'` to a POST without `max_results` (Demo-RAG's server on :5000 does the same). Hosts are fine: `{"max_results": 100}` → 200 on 127.0.0.1:5050, and a foreign `Host:` header → 403, so the host check is active and accepts the 5050→5000 mapping.
- I did: no compose change (no `--allowed-hosts` needed); smoke recorded with `{"max_results": 100}`.
- One-off or pattern?: likely recurs — every MLflow REST search (the 2B app's `experiments/search` / `runs/search`) must send an explicit positive `max_results`.

## Phase 2A — uv picks a managed Python 3.14 for `requires-python >= 3.12`

- Plan assumed: Python 3.12 (CI uses setup-python 3.12; pyright `pythonVersion = "3.12"`).
- Territory was: uv prefers its managed interpreters, so `uv sync` in `packages/datalab` built the env on CPython 3.14.3 (3.13 and 3.11 are installed too) while CI runs 3.12.
- I did: added `packages/datalab/.python-version` = `3.12`; the template keeps only `requires-python >= 3.12` as the plan says, so new projects may still get 3.14 locally.
- One-off or pattern?: likely recurs — every new project (3) gets the newest managed Python unless the template also ships a `.python-version`.

## Phase 2A — declared-deps hook needs cwd = the package, not `--project`

- Plan assumed: the recipe runs as `uv run --project packages/datalab python tools/pre_commit_checks/check_declared_dependencies.py`.
- Territory was: the recipe reads `pyproject.toml` / `uv.lock` and scans `src/` relative to the cwd; `--project` does not chdir, so from the repo root it finds no source root (prints "no source root found", exit 1) and never sees the package's manifest.
- I did: `uv run --locked --directory packages/datalab python ../../tools/pre_commit_checks/check_declared_dependencies.py` (`--locked`: lock drift fails instead of rewriting `uv.lock` mid-hook); proved it fails on an undeclared `import reportlab`.
- One-off or pattern?: likely recurs — any vendored layered-linter recipe in a repo with no root project needs `--directory <tree>`.

## Phase 2A — MLflow "delete experiment" is a soft delete

- Plan assumed: the integration test's experiment `datalab-test/<sub>` is "deleted by exact name after".
- Territory was: `delete_experiment` moves it to lifecycle `deleted`; it stays in the store (name reserved) until `mlflow gc`. Each integration run leaves one deleted `datalab-test/t<hex8>` experiment behind (default searches, `ACTIVE_ONLY`, do not return it).
- I did: kept the exact-name delete (no prefix, F-3); no `gc`.
- One-off or pattern?: one-off — the 2B app must keep the default `ACTIVE_ONLY` view so deleted experiments never show.
