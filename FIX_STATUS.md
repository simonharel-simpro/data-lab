# Fix Status — review 2026-11-08

Ledger written by `/loop-fix` (integration branch `fix/review-2026-11-08`, base `main`).
A phase is complete only when merged into the integration branch AND marked here.

**Execution order: 1 → 2 → 3 → 4 → 5 → 6 → 8 → 7** (FIX_PLAN Cross-phase Dependencies: 8.1 moves
`test_hydra_gate.py` and 7.1 documents the tree, so 8 lands before 7). A resume follows this order, not numeric order.

| Phase | Theme | Status | Branch | /check |
|-------|-------|--------|--------|--------|
| 1 | Run integrity: empty index, #12 build race, voice-arch budget | ✅ landed (4/4) | fix-phase-1-run-integrity | clean @ 2e50ef7 (1 fix-check iter) |
| 2 | Resilience at the trust boundaries | pending | — | — |
| 3 | Ledger contract, enum discipline & datalab test quality | pending | — | — |
| 4 | Signatures, settings & error-handling style | pending | — | — |
| 5 | pyright strict on `src/` (#14) | pending | — | — |
| 6 | App formatter + linter (#13) | pending | — | — |
| 7 | Docs & dependency hygiene | pending | — | — |
| 8 | CI gates & tooling | pending | — | — |

## Phase 1 — Run integrity (🔴)

**Implemented:** 2026-11-08 · **Branch:** fix-phase-1-run-integrity · **Agent:** python-fastapi (×2, mini-rag / voice-arch)
**Tooling:** ✅ `pre-commit run --all-files --hook-stage pre-push` exit 0 on the committed tree

- ✅ 1.1 vector-probe reuse — grep 1→0
- ✅ 1.2 EmptyRetrieval fails the run — N/A pattern; red test added
- ✅ 1.3 #12 per-collection flock + ADR — N/A pattern; concurrency test in new `tests/test_index_concurrency.py` (300-line test limit)
- ✅ 1.4 budget = project_spend + per-call cost + cost_unknown + P-2 estimates — grep 2→0
- Red-first: `936d378` (tests fail on old src: ImportError) → fix `8db8134`
- Deviations (subagent, low-stakes): fake uses `empty_probes: int` instead of `near_text_hits`; `_complete` logs a warning instead of putting the count in the error. Extra test `test_ensure_collection_without_chunks_is_refused`.
- Cross-phase regressions: none (first phase)
