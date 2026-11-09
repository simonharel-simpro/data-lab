# Fix Status — review 2026-11-08

Ledger written by `/loop-fix` (integration branch `fix/review-2026-11-08`, base `main`).
A phase is complete only when merged into the integration branch AND marked here.

**Execution order: 1 → 2 → 3 → 4 → 5 → 6 → 8 → 7** (FIX_PLAN Cross-phase Dependencies: 8.1 moves
`test_hydra_gate.py` and 7.1 documents the tree, so 8 lands before 7). A resume follows this order, not numeric order.

| Phase | Theme | Status | Branch | /check |
|-------|-------|--------|--------|--------|
| 1 | Run integrity: empty index, #12 build race, voice-arch budget | ✅ landed (4/4) | fix-phase-1-run-integrity | clean @ 2e50ef7 (1 fix-check iter) |
| 2 | Resilience at the trust boundaries | ✅ landed (7/7) | fix-phase-2-trust-boundaries | clean @ 2e1bc20 (1 fix-check iter) |
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

## Phase 2 — Resilience at the trust boundaries (🟡)

**Implemented:** 2026-11-08 · **Branch:** fix-phase-2-trust-boundaries · **Agent:** python-fastapi (×3: template+datalab / voice-arch / weavit-web.sh)
**Tooling:** ✅ pre-push exit 0 on the committed tree · `pytest -m scaffold` 1 passed · root `uvx pytest tests/` 11 passed

- ✅ 2.1 train refuses a moved split/data hash — via new `prepare.frozen_score_on` (train.py stayed ≤200); `check_split_hash` exported from `datalab.ledger`
- ✅ 2.2 eval names a missing/deleted winner (and parent) run, exit 2
- ✅ 2.3 `split.check_time_kinds` → SplitError before any test look (called after the index/group branches in `_pick`)
- ✅ 2.4 body error kept, cleanup failure added as a note; helpers moved to new `datalab/tracking_outcome.py`
- ✅ 2.5 LiveKit steps bounded (`STEP_TIMEOUT_S`, `LiveKitUnresponsive`) — grep 2.5 → 0
- ✅ 2.6 interjection on an unstarted caller → CALLER_FAULT
- ✅ 2.7 weavit-web.sh `read_env_key`, submodule guard, always `pnpm install` — grep 2.7 → 0
- Red-first: `035e8e0` (datalab 2 failed, voice-arch collection error, root 9 failed on old source; template red shown by subagent mutation runs) → fix `3d7114e`
- Low-stakes deviations: a failed `handle.close()` now logs WARNING (was `logger.exception`/ERROR); new test files `templates/project/tests/test_train_frozen.py` (test_train.py at 274/300); trial note reads "logging the trial cost failed".
- Cross-phase regressions: none (`assert-zero --done` OK)
