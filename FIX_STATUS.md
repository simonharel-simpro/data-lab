# Fix Status — review-2026-11-04

Ledger maintained by `/loop-fix` (integration branch `fix/review-2026-11-04` → `main`).
A phase is complete only when it is merged into `fix/review-2026-11-04` **and** marked here.

| Phase | Theme | Status | Branch | /check | Landed |
|-------|-------|--------|--------|--------|--------|
| 1 | Run integrity & resilience (pilot) | implemented (awaiting /check) | fix-phase-1-run-integrity | — | — |
| 2 | Gates, input validation & dependency hygiene | pending | — | — | — |
| 3 | App boundaries (TS) | pending | — | — | — |
| 4 | Test gaps — Python | pending | — | — | — |
| 5 | Test gaps — TS | pending | — | — | — |

## Phase 1 — Run integrity & resilience (pilot)

**Implemented:** 2026-11-05 · **Branch:** fix-phase-1-run-integrity · **Agent:** python-fastapi
**Tooling (tree-level):** mini-rag pytest 55 passed, 92.27% cov · datalab pytest 44 passed, 95.40% cov · pyright 0 · ruff clean · lint-imports 1/1 kept (both trees)

- ✅ 1.1 Crash-copy JSONL + `RunConfig` — grep 1→0 (logged params unchanged except the new `corpus_hash`; the orchestrator checked this against the diff)
- ✅ 1.2 Bounded MLflow HTTP retries — behavioural (2 tests)
- ✅ 1.3 Index keyed on corpus content — grep 2→0; call-order detectors replaced by outcome checks
- ✅ 1.4 Truncated / non-Message DGX response → GenerationError — behavioural (3 tests)
- ✅ 1.5 Fail fast on bad input + `tests/test_cli.py` — grep 1→0

Existing-test edit: `datalab/tests/test_settings.py::test_f_5_settings_ignores_bare_mlflow_tracking_uri` input `"x"` → `"http://x:1"`, because 1.5 now refuses a scheme-less URI by design. The test means the same thing.
Cross-phase regressions: none (first phase).
