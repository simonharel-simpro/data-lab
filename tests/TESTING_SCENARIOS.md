# Testing Scenarios

> Living document maintained by `/implement-phase`. QA uses this to know what to test.

**Last updated:** 2026-11-04 (Phase 3)

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

## Presentation app (`app/`)

| ID | Scenario | Input | Expected Output | Status | Last Modified |
|----|----------|-------|-----------------|--------|---------------|
| APP-01 | Zero projects | `projects/` holds only `.gitkeep` | build OK, index shows the empty state | 🆕 New | Phase 2B |
| APP-02 | Card + best run | card with `metric: {key, goal}`, runs tagged `project=<name>` | best finite value shown (tie → latest start_time, then run_id) | 🆕 New | Phase 2B |
| APP-03 | Invalid card | `name` ≠ folder | build fails naming the file (D-13) | 🆕 New | Phase 2B |
| APP-04 | MLflow down | `npm run build` | cards show "Métriques indisponibles"; with `DATALAB_STRICT_EXPORT=1` the build fails | 🆕 New | Phase 2B |
| APP-05 | Static export links | `npm run build` | no 127.0.0.1/localhost in `dist/` (D-14); dev mode links to MLflow | 🆕 New | Phase 2B |
| APP-06 | Card saved on Windows | BOM + CRLF | parses, title renders | 🆕 New | Phase 2B |

## Weavit UI auto-connect (fork)

| ID | Scenario | Input | Expected Output | Status | Last Modified |
|----|----------|-------|-----------------|--------|---------------|
| WUI-01 | Eligible profile | local profile `data-lab`, 127.0.0.1, 8090/50052, stack up | connected on launch without a click | 🆕 New | Phase 2C |
| WUI-02 | Empty gRPC port | same profile, gRPC blank | no auto-connect, console `autoconnect skip: ports` | 🆕 New | Phase 2C |
| WUI-03 | Two `data-lab` profiles | duplicates | no auto-connect (`ambiguous`) | 🆕 New | Phase 2C |
| WUI-04 | Stack down | eligible profile, Weaviate stopped | normal UI with `error` status, no retry, no other profile | 🆕 New | Phase 2C |

## Pilot mini-rag

| ID | Scenario | Input | Expected Output | Status | Last Modified |
|----|----------|-------|-----------------|--------|---------------|
| PIL-01 | Full run | `--retrieval bm25 --k 3`, OpenRouter key set (or DGX up with `MINI_RAG_LLM_BASE_URL` + `MINI_RAG_GEN_MODEL`) | FINISHED run in `mini-rag/retrieval`, tag `project=mini-rag`, metrics accuracy/hallucination/score | 🆕 New | Phase 3 |
| PIL-02 | 4 configs | bm25/vector × k 3/5 | 4 runs; app card "score = …, Meilleur de 4 runs" | 🆕 New | Phase 3 |
| PIL-03 | LLM endpoint down | any config, endpoint unreachable | run FAILED, no metrics logged | 🆕 New | Phase 3 |
| PIL-06 | OpenRouter refuses | bad key (401), no credits (402), rate-limited (429) | run FAILED; the error carries OpenRouter's reason | 🆕 New | 2026-11-06 |
| PIL-07 | Misconfigured endpoint | no key for OpenRouter; DGX URL without `MINI_RAG_GEN_MODEL`; legacy `MINI_RAG_DGX_BASE_URL` | refused at startup, before any I/O, with the fix in the message | 🆕 New | 2026-11-06 |
| PIL-08 | Reproducible routing | OpenRouter run | request allows only `provider.order=[deepinfra,gmicloud,parasail]`, `quantizations=[fp8]`, `allow_fallbacks=false`; params `llm_providers`, credential-free `llm_base_url`; tag `llm_served_by` counts the provider of each answer | 🆕 New | 2026-11-06 |
| PIL-04 | Smoke run | `--n 1` | `smoke_*` metrics + tag `smoke=true`, never counted as best | 🆕 New | Phase 3 |
| PIL-05 | Unanswerable question | answer `null` | IDK counts correct; any answer = hallucination | 🆕 New | Phase 3 |
