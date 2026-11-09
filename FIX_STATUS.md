# Fix Status — review 2026-11-08

Ledger written by `/loop-fix` (integration branch `fix/review-2026-11-08`, base `main`).
A phase is complete only when merged into the integration branch AND marked here.

**Execution order: 1 → 2 → 3 → 4 → 5 → 6 → 8 → 7** (FIX_PLAN Cross-phase Dependencies: 8.1 moves
`test_hydra_gate.py` and 7.1 documents the tree, so 8 lands before 7). A resume follows this order, not numeric order.

| Phase | Theme | Status | Branch | /check |
|-------|-------|--------|--------|--------|
| 1 | Run integrity: empty index, #12 build race, voice-arch budget | ✅ landed (4/4) | fix-phase-1-run-integrity | clean @ 2e50ef7 (1 fix-check iter) |
| 2 | Resilience at the trust boundaries | ✅ landed (7/7) | fix-phase-2-trust-boundaries | clean @ 2e1bc20 (1 fix-check iter) |
| 3 | Ledger contract, enum discipline & datalab test quality | ✅ landed (9/9) | fix-phase-3-ledger-enums | clean @ 95ea6d2 (first pass) |
| 4 | Signatures, settings & error-handling style | ✅ landed (10/10) | fix-phase-4-signatures-errors | clean @ fc8f158 (first pass) |
| 5 | pyright strict on `src/` (#14) | implemented (8/8 + 5.9), awaiting /check | fix-phase-5-pyright-strict | — |
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

## Phase 3 — Ledger contract, enum discipline & datalab test quality (🟡)

**Implemented:** 2026-11-08 · **Branch:** fix-phase-3-ledger-enums · **Agents:** python-fastapi ×3 (ledger / test quality / enums), general-purpose (3.3 TS) + 1 targeted retry (3.5 bench Component literals)
**Tooling:** ✅ pre-push exit 0 on the committed tree

- ✅ 3.1 `ledger_access.py` split (ledger_ops 166 lines), literals → enums / `DATASET`·`FEATURES`·`MODELING`·`AUDIT` — grep → 0
- ✅ 3.2 `contracts/value_sets.json` + Python pin · ✅ 3.3 TS pin + typed `SIGN` map — grep → 0
- ✅ 3.4 `TRANSITIONS` table + `_next`; tests in new `test_ledger_transitions.py`
- ✅ 3.5 `Goal`, `Component`, `_RUNNING`/`_FINISHED`, `AUDIT_EXPERIMENT` (in template `paths.py`) — grep → 0
- ✅ 3.6 ADR "Milestone ids stay data-driven strings" · ✅ 3.7 skip cites #8, issue #8 body updated (gh) · ✅ 3.8 match= + 6 rule cases + 256-case property (new `test_split_rules.py`) · ✅ 3.9 sequences pinned
- Red-first: `6c1eae6` (datalab collection errors, app 1 fail on old source) → fix `561de87`
- Low-stakes deviation: `_next` keeps the existing error wording (takes the milestone id) so existing tests stay unchanged.
- **Follow-up (pre-existing, found by 3.8):** a non-ISO `time_max` is rejected by `read_split`, but the message is the first pydantic union error ("valid array"), not the ISO rule — pick the best union error. Not in plan scope.
- Cross-phase regressions: none

## Phase 4 — Signatures, settings & error-handling style (🟡)

**Implemented:** 2026-11-08 · **Branch:** fix-phase-4-signatures-errors · **Agents:** python-fastapi ×2 (A: voice-arch structure 4.2–4.5; B: lint rules 4.1, 4.6–4.10, sole owner of ruff.toml)
**Tooling:** ✅ pre-push exit 0 on the committed tree · scaffold 1 passed · `uvx ruff check .` clean with BLE + PLR0913 on

- ✅ 4.1 BLE on; reasons on broad excepts (+ `livekit_env.py`, `tracking_outcome.py` surfaced by enabling BLE) — grep → 0
- ✅ 4.2 `load_settings()` — grep 1 (expected) · ✅ 4.3 `dump_empty_dir` setting, threaded via `audio.make_llm` — grep → 0
- ✅ 4.4 `run_sweep(env, SweepPlan, SweepContext)`; `Sweep` moved to new `voice_arch/sweep.py` (runner 112 lines) · ✅ 4.5 `build_result(CallIdentity, SessionOutcome, report_fn)`
- ✅ 4.6–4.8 seven `# noqa: PLR0913 … (#39)`, landed in the same commit as 4.10's rule enable
- ✅ 4.9 three functions ≤ 30 lines (`_params`, `_extra_body`, `_trial_tags`); `_layout.py` untouched (#41) · ✅ 4.10 annotations (`test_bench._corpus` returns `Callable[[], Awaitable[Corpus]]`)
- Red-first: `6653b52` (collection errors on old source) → fix `36b8620`
- Deviations (low-stakes): two noqa reasons shortened for the 120-col limit; `_trial_tags(tags)` takes only `tags`; test renamed `test_dump_is_off_without_a_directory` (trailer `Test-Change: #39`).
- Cross-phase regressions: none

## Phase 5 — pyright strict on `src/` (#14) (🟡)

**Implemented:** 2026-11-08 · **Branch:** fix-phase-5-pyright-strict · **Agents:** python-fastapi ×4 (datalab+template / mini-rag / voice-arch / 5.9 gate wiring)
**Tooling:** ✅ pre-push exit 0 · scaffold 1 passed · `pyright -p pyproject.toml` 0 errors in datalab, mini-rag, voice-arch · strict probe (`def f(x)`) → 4 errors (strict is live)

- ✅ 5.1 `strict = ["src"]` ×4, `py.typed` · ✅ 5.2/5.3 datalab (private cross-module names made public) · ✅ 5.4 mini-rag · ✅ 5.5–5.7 voice-arch full strict (casts at SDK boundaries, P-6) · ✅ 5.8 template strict via scaffold
- **⚠️ Finding (pre-existing, also on main):** the root `pyrightconfig.json` (0b5de8f) won pyright's config discovery, so every per-tree `uv run pyright` (pre-commit, CI, /check) checked only root `tools/`+`tests/` — the trees were never type-checked. The "pyright 0" rows in Phases 1–4 /check were vacuous for the trees.
- ✅ **5.9 (user-approved deviation, 2026-11-08):** hooks + CI + `wiring.gates_block` generator run `pyright -p pyproject.toml`; 15 basic-mode errors in tests/ fixed type-only.
- Commit: `d4345ea` (single commit: typing refactor, no behavioural tests; `Test-Change: #14`)
- Follow-ups: S-14 stale-cast risk on livekit upgrades (casts in llm_dump, llm_guard, worker, naturalness, agents/tools, agents/state); the plan's "every ignore has a reason" grep cannot fail (the `# pyright:` itself matches `  # `).
