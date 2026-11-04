# Testing Scenarios

> Living document maintained by `/implement-phase`. QA uses this to know what to test.

**Last updated:** 2026-11-04 (Phase 1)

## Shared infra

| ID | Scenario | Input | Expected Output | Status | Last Modified |
|----|----------|-------|-----------------|--------|---------------|
| INFRA-01 | Start the stack | `docker compose up -d` | weaviate, t2v-transformers, mlflow all `healthy` | 🆕 New | Phase 1 |
| INFRA-02 | Ports coexist with Demo-RAG | Demo-RAG on 5000/8080/50051 running | data-lab on 127.0.0.1:5050/8090/50052; Demo-RAG untouched | 🆕 New | Phase 1 |
| INFRA-03 | Loopback only | `docker compose config` | every published port has host_ip 127.0.0.1 (`tests/test_compose.py`) | 🆕 New | Phase 1 |
| INFRA-04 | Vectorizer loaded | `GET 127.0.0.1:8090/v1/meta` | modules lists `text2vec-transformers` | 🆕 New | Phase 1 |
| INFRA-05 | MLflow reachable | `POST /api/2.0/mlflow/experiments/search` with `{"max_results":10}` | HTTP 200 (an empty body gives 400: max_results required) | 🆕 New | Phase 1 |
