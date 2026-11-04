# Testing Scenarios

> Living document maintained by `/implement-phase`. QA uses this to know what to test.

**Last updated:** 2026-11-04 (Phase 2A)

## Shared infra

| ID | Scenario | Input | Expected Output | Status | Last Modified |
|----|----------|-------|-----------------|--------|---------------|
| INFRA-01 | Start the stack | `docker compose up -d` | weaviate, t2v-transformers, mlflow all `healthy` | 🆕 New | Phase 1 |
| INFRA-02 | Ports coexist with Demo-RAG | Demo-RAG on 5000/8080/50051 running | data-lab on 127.0.0.1:5050/8090/50052; Demo-RAG untouched | 🆕 New | Phase 1 |
| INFRA-03 | Loopback only | `docker compose config` | every published port has host_ip 127.0.0.1 (`tests/test_compose.py`) | 🆕 New | Phase 1 |
| INFRA-04 | Vectorizer loaded | `GET 127.0.0.1:8090/v1/meta` | modules lists `text2vec-transformers` | 🆕 New | Phase 1 |
| INFRA-05 | MLflow reachable | `POST /api/2.0/mlflow/experiments/search` with `{"max_results":10}` | HTTP 200 (an empty body gives 400: max_results required) | 🆕 New | Phase 1 |

## New project (`datalab-new`)

| ID | Scenario | Input | Expected Output | Status | Last Modified |
|----|----------|-------|-----------------|--------|---------------|
| NEW-01 | Create a project | `datalab-new demo --title "RAG: v2 # b"` | `projects/demo/` with PROJECT.md (title survives YAML), pyproject `name = "proj-demo"`; `uv sync` works | 🆕 New | Phase 2A |
| NEW-02 | Existing target | `projects/demo` exists (even empty dir/file) | exit 2, nothing written | 🆕 New | Phase 2A |
| NEW-03 | Bad / reserved / traversal name | `Bad`, `test`, `../escape` | exit 2, nothing written | 🆕 New | Phase 2A |
| NEW-04 | Package added after first sync | create `src/demo_pkg/` after `uv sync` | `import demo_pkg` works | 🆕 New | Phase 2A |

## Shared package (`datalab`)

| ID | Scenario | Input | Expected Output | Status | Last Modified |
|----|----------|-------|-----------------|--------|---------------|
| DL-01 | Tracked run | `tracked_run(project, settings, "r", sub="bm25")` | run in experiment `<name>/bm25`, tag `project=<name>`, FINISHED | 🆕 New | Phase 2A |
| DL-02 | Project tag override | `tags={"project": "x"}` | `ValueError` | 🆕 New | Phase 2A |
| DL-03 | Inherited MLFLOW_TRACKING_URI | env points at Demo-RAG :5000 | data-lab URI (5050) used | 🆕 New | Phase 2A |
| DL-04 | Card with BOM/CRLF | PROJECT.md saved on Windows | loads | 🆕 New | Phase 2A |
| DL-05 | MLflow down | `preflight` on unreachable URI | `TrackingUnavailable` | 🆕 New | Phase 2A |
