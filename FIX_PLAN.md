# Fix Plan — data-lab

**Date:** 2026-11-08
**Based on:** REVIEW.md dated 2026-11-08 (`main` @ `8f3add8`)
**Project type:** Python (generic, uv multi-tree: `packages/datalab`, `projects/mini-rag`, `projects/voice-arch`, `templates/project`, plus `tools/` + root `tests/`) + Astro 7 / TypeScript (`app/`)
**Output mode:** multi-phase (8 phases, 45 fix units). Every 🔴 and 🟡 row of REVIEW.md is either covered by a fix unit, tracked under **Deferred Items**, or waiting on a **Pending User Decision**. Backlog issues #12, #13 and #14 are fixed here and close in their phase. #8 stays open as a tracker; #7 is referenced.
**Status:** UNVALIDATED. Run `/plan-fix-validate` before `/implement-fix-phase 1`. The user answered P-1..P-11 on 2026-11-08 (AskUserQuestion, "Tout accepter"), picking the recommended option every time.

**Baseline measured before planning (2026-11-08, on `8f3add8`):**
- pyright **strict** over `src/` only, current code: datalab **38** errors in 10 files, mini-rag **20** in 6, voice-arch **142** in 28. Of these, 17 are `reportMissingTypeStubs` on `datalab.*`, because the package has no `py.typed`. The rest are mostly `reportUnknown*` from untyped livekit/mlflow returns.
- root `uvx pyright==1.1.414` (basic, `tools/` + `tests/`): 0 errors.
- ruff: `BLE001` 3 hits (`worker_logic.py:122`, template `eval.py:140`, `train.py:138`; all three already carry inline reasons); `PLR0913` 17 hits (9 src, 8 tests); `FA` 0 hits (it is a no-op at `target-version = py312`).
- #13 pins: each version was published before 2026-10-25, at least 14 days before 2026-11-08, checked on the npm registry: prettier 3.9.10 (10-10), prettier-plugin-astro 1.1.2 (10-23), eslint 10.13.0 (10-16), @eslint/js 10.0.1 (2026-02-06), eslint-plugin-astro 3.2.1 (09-17), typescript-eslint 8.72.0 (10-19). The peer ranges accept typescript 6.0.3 and node 22. Amendment 2026-11-09 (ESC-6-1): these pins fail `npm audit` through minimatch, so Phase 6 adds eight exact npm overrides: two are a dated exception to the 14-day rule (`minimatch` 11.0.1, `@isaacs/nonrecursive-glob-match` 1.0.1), and six pin older in-range transitives so the rest of the resolved tree meets it; see `FIX_PLAN_PHASE_6.md`.

## Phase Summary

| Phase | Theme | Severity | Fix Units | Files | Agent | Depends on |
|-------|-------|----------|-----------|-------|-------|------------|
| 1 | Run integrity: empty index, #12 build race, voice-arch budget | 🔴 | 4 | 9 | python-fastapi | — |
| 2 | Resilience at the trust boundaries (template, datalab tracking, voice-arch calls, weavit-web.sh) | 🟡 | 7 | 17 | python-fastapi | — |
| 3 | Ledger contract, enum discipline & datalab test quality (Python ↔ TS) | 🟡 | 9 | 23 | python-fastapi (all but 3.3), general-purpose (3.3, kept inside Phase 3) | Phase 2 (template `train.py`) |
| 4 | Signatures, settings & error-handling style | 🟡 | 10 | 24 | python-fastapi | Phases 1, 2 (`ensure_collection`, `runner.py`, `call.py`) |
| 5 | pyright strict on `src/` (#14) | 🟡 | 8 | 47 | python-fastapi | Phases 1–4 |
| 6 | App formatter + linter (#13) | 🟡 | 3 | 12 | general-purpose | Phase 3 (3.3 edits `app/src/lib`) |
| 7 | Docs & dependency hygiene | 🟡 | 2 | 6 | general-purpose | Phases 3, 4 (docs describe the new modules) |
| 8 | CI gates & tooling | 🟡 | 2 | 10 | python-fastapi | — |
| **Total** | | | **45** | | | |

File counts are per phase; a file edited in two phases is counted twice. Agent note: the project is generic Python, not FastAPI. `python-fastapi` is the only Python implementer agent, so its layering rules (routers/services/repositories) do **not** apply, and every dispatch prompt says so. There is no Astro agent, so TS units go to `general-purpose` with the `app/` conventions restated in their phase file.

## Simplicity Review

Reviewer: `simplicity-reviewer` (fable), 2026-11-08. Before: 9 phases / 44 units. **After: 8 phases / 45 units.** S-10 merged the former Phase 7 into Phase 3, S-13 added 5.8, and the unit S-5 would drop stays pending. I re-read the evidence for S-3, S-7 and S-8 in the code before applying them: `test_hydra_gate.py:14-21` loads the script in-process; `ledger_rules.py:98,118,134` hold raw milestone ids; `ledger_checks.check_split_hash` + template `eval.py:72-73` already exist.

| # | Item | Class | Disposition |
|---|---|---|---|
| S-1 | 4.6–4.8: "build P-5 option B until answered" | mechanism (default reverses the 2026-11-04 decision) | **Resolved by the user (P-5 = A, 2026-11-08):** 4.6–4.8 are now `noqa` + reason units (D-6, #39) |
| S-2 | 7.2: "build P-9 `==` until answered" | mechanism | **Resolved by the user (P-9 = A, 2026-11-08):** 7.2 is now the ADR only (D-7, #40) |
| S-3 | 8.1: coverage floor over subprocess-run tests | self-inflicted | **Applied:** in-process tests; the vendored `pre_commit_checks` modules are omitted from coverage, and their test was dropped |
| S-4 | 3.4: test that parses the ASCII diagram | gold plating | **Applied:** ARCHITECTURE.md quotes a 5-row table rendered from `TRANSITIONS`; the test is a string check |
| S-5 | 4.9: split the four 31–32-line functions | would leave finding partly unfixed | **Asked as P-11; the user chose to split the three first-party ones** (the vendored one stays: D-9, #41) |
| S-6 | 1.4: existing budget tests break (no `project` tag) | add | **Applied** in 1.4 step 1 |
| S-7 | 3.1: same literals in `ledger_rules.py` | add | **Applied:** file, step 4 and grep added |
| S-8 | 2.1: `check_frozen` rebuilds `check_split_hash` | reinvented wheel | **Applied:** train reuses `ledger.check_split_hash`; one data-hash helper shared with eval |
| S-9 | P-2 (R) adds a second query and counts a ≤ 1-call crash at $15 | comment | **Recorded** in the P-2 row; the user decides |
| S-10 | Phase 7 (test quality) as its own phase | phase bloat | **Applied:** now 3.7–3.9; old Phases 8/9 renumbered 7/8 |
| S-11 | 8.1 pins in two places | dual-site constant | **Applied:** the `gates-root` hook holds the command; CI runs that hook |
| S-12 | 2.7 install stamp | mechanism | **Applied:** always run the idempotent `pnpm install` |
| S-13 | 5.1 template strict with no unit owning its errors | add | **Applied:** unit 5.8 (measure via `pytest -m scaffold`, fix or stop) |
| S-14 | P-6 full strict = casts over an untyped SDK | comment | **Recorded** in the P-6 row |
| S-15 | Phase 1 notes: two step-0 `cost_usd` points, probe exception, lock-file lifetime | keep + notes | **Applied** in 1.3 and 1.4 |

## Scope Decisions

| # | Type | What | Tracker | Approved |
|---|------|------|---------|----------|
| D-1 | decision | voice-arch budget reuses `datalab.tracking_queries.project_spend` (every status, every `voice-arch/*` experiment) instead of patching `spent_so_far`'s status filter | — | — |
| D-2 | decision | #12: `fcntl.flock` per collection name around `ensure_collection`, plus a re-check once the lock is held (mechanism answer is P-1) | #12 | — |
| D-3 | decision | split leakage property: exhaustive enumeration over a small index domain instead of adding Hypothesis (same property, no new dependency) | — | — |
| D-4 | decision | a hung LiveKit step (dispatch / connect) aborts the sweep with a named error; cleanup steps are bounded and logged (behaviour answer is P-4) | — | — |
| D-5 | decision | project-card status stays a manual label: the doc says so, no FSM code (REVIEW §3's own recommendation) | — | — |
| D-6 | cut | `PLR0913`: group only `run_sweep` + `build_result`; the other 7 functions over 5 args keep their signatures with a `noqa: PLR0913` and a reason (P-5 option A) | #39 | user, AskUserQuestion 2026-11-08 |
| D-7 | cut | dev dependency specs stay `>=` (`uv.lock` + `--locked` is the pin) instead of `==` (P-9 option A; first accepted 2026-11-04) | #40 | user, AskUserQuestion 2026-11-08 |
| D-8 | decision | pyright strict in voice-arch is full strict: `cast`/annotations at the untyped SDK boundaries, no rule lowered (P-6, user 2026-11-08) | #14 | — |
| D-9 | cut | the vendored `tools/pre_commit_checks/_layout.run_layer_check` (31 lines) stays unsplit; the three first-party functions over 30 lines are split (P-11) | #41 | user, AskUserQuestion 2026-11-08 |

D-6, D-7 and D-9 are approved cuts, each tracked. D-8 became a decision: the user chose full scope.

## User Decisions (answered 2026-11-08)

The user answered all eleven on 2026-11-08 (AskUserQuestion, "Tout accepter"): the **R** column is the chosen answer for every row. The alternatives are kept for the record.

| # | Question | R (chosen by the user) | Alternatives (not chosen) | Units |
|---|---|---|---|---|
| P-1 | #12: how to serialize Weaviate index builds? | `fcntl.flock` on a per-collection lock file in the OS temp dir, then re-check under the lock (POSIX/WSL; no new dependency) | (b) the `filelock` package (works on Windows too; adds a dependency); (c) no lock: build into a uuid-suffixed collection, then point a Weaviate alias at it | 1.3 |
| P-2 | voice-arch: how does a run with **no** `cost_usd` (crashed before its first per-call log, or a bench run killed mid-measure) count against the budget? | Unless the run is FINISHED, count it at the estimate (`FALLBACK_ESTIMATE_USD` $15 for sweeps, bench `ESTIMATE_USD`) and log a warning naming it. Cost: a second MLflow query in `budget.py`, and a sweep that crashed during its first call (≤ $1 spent) counts as $15 (S-9) | (b) count it as 0, with a warning and the `cost_unknown` tag (no new query; a killed bench run's whole cost stays invisible); (c) refuse to start new runs while one exists, until `close_runs` (reuse `stale_runs`) | 1.4 |
| P-3 | voice-arch: the `/key` read fails at sweep start (REVIEW §6 🔵). Today the mid-sweep checks are off for that sweep (F-12: fail-open) | Keep fail-open, plus the `cost_unknown` tag from 1.4 | (b) abort the sweep after 3 unreadable reads in a row; (c) abort at once (fail closed) | 1.4 |
| P-4 | voice-arch: LiveKit accepts the connection but never answers `create_dispatch` / `connect` | Abort the sweep: raise `LiveKitUnresponsive` naming the step (run FAILED, rows so far kept) | (b) record the call as `AGENT_LOST` and continue; (c) add a new `Outcome.INFRA_FAULT` row and continue | 2.5 |
| P-5 | Functions with more than 5 params (9 in src) and ruff `PLR0913` | (A) group `run_sweep` and `build_result` (10 args each) into dataclasses; enable `PLR0913` with a `noqa` + reason on the other 7 (mini-rag `run()` was kept at 8–9 args by decision on 2026-11-04, S-10) | (B) group all 9 to 5 or fewer: about 10 new dataclasses over ~20 files, and a `decide()` API change the `/experiment` skill documents; (C) group the two only and leave `PLR0913` off | 4.6–4.8, 4.10 |
| P-6 | #14 in voice-arch: 142 strict errors in 28 files, mostly `reportUnknown*` from untyped livekit/mlflow | Full strict, as #14 asks (3 batches, `cast`/annotations at each SDK boundary). Cost: a `cast` is unchecked and can go stale if livekit changes (S-14) | (b) strict, with the three `reportUnknown*` rules as warnings in voice-arch only (cut D-8); (c) strict on datalab + mini-rag now, voice-arch on a new issue | 5.5–5.7 |
| P-7 | #14 for `templates/project/src` (the user's scope named datalab + `projects/*/src`; REVIEW §7 🔵 says fold the template in) | Strict on the template's `src/` too, so every generated project starts strict (5.8 measures it via the `scaffold` CI step) | (b) explicit `typeCheckingMode = "basic"` in the template, strict later on a new issue | 5.1, 5.8 |
| P-8 | `from __future__ import annotations` is missing in 79 modules | Record "py312+: exempt (PEP 604/585 native; ruff `UP` keeps the syntax modern)" in ARCHITECTURE.md | (b) enforce it with ruff `I002` + `lint.isort.required-imports`, auto-fixed in all 79 modules | 7.1 |
| P-9 | Floating dev dependency specs (`pytest>=8` …) in datalab and mini-rag (accepted on 2026-11-04; voice-arch has since pinned `==`) | (A) keep `>=` (accepted; `uv.lock` + `--locked` CI is the pin) and record it in decisions.md (cut D-7) | (B) pin `==` to the locked versions, like voice-arch and the template | 7.2 |
| P-10 | Milestone id is a plain `str` (REVIEW §3: low priority) | Named constants for the ids the code references (`MODELING`, `AUDIT`, `DATASET`, `FEATURES`), each tested to exist in `milestones.json` (built in 3.1); the rest stays data-driven, recorded as an ADR | (b) a generated `Literal` type plus a drift test on both sides; (c) accept as is (won't fix) | 3.6 |
| P-11 | Four functions at 31–32 lines that REVIEW calls marginal (`run.run`, `LlmGenerator.__init__`, `tracked_trial`, vendored `_layout.run_layer_check`) | Split the three first-party ones to ≤ 30 lines; leave the vendored `run_layer_check` to the harness recipe | (b) accept all four (cut D-9); (c) split all four, the vendored file included | 4.9 |

## Cross-phase Dependencies

- **Phase 1 → 4.** 1.3 adds the lock to `ensure_collection` before 4.6 groups its parameters. 1.4 edits `runner.py` before 4.4 regroups `run_sweep`.
- **Phase 2 → 3, 4.** 2.1 edits template `train.py` (196/200 lines) before 3.5 replaces its literals. 2.5/2.6 edit `call.py` before 4.8.
- **Phases 1–4 → 5.** Strict typing goes last among the code phases, so it types the final signatures. Re-measure the counts before each batch: earlier phases move code between files.
- **Phase 3 → 6.** 3.3 edits `app/src/lib/ledger.test.ts` before the one-time prettier rewrite (6.2).
- **Phase 8 → 7.** Neither strictly depends on the other; merge 8 first if both are ready, because 8.1 moves `test_hydra_gate.py` and 7.1 documents the tree.

## Recommended Execution Order

For each phase: branch → `/implement-fix-phase N` → `/check` → PR → CI → merge → next phase. Order: 1 → 2 → 3 → 4 → 5 → 6 → 7; 8 can merge any time.

All the answers are in, so no phase waits on a decision.

**Per-phase specs are in `FIX_PLAN_PHASE_N.md` files.** This overview is for navigation only.

## Recurring Patterns Worth Promoting to Linters

| Pattern | Fix units | Files affected | Recipe match | Scaffold command / when |
|---------|-----------|----------------|--------------|------------------|
| Functions with > 5 parameters | 4.4–4.8 | 7 src files | ruff built-in `PLR0913` | enabled in 4.10 (`max-args = 5`, tests exempt), after the 2 regroupings + 7 justified `noqa` (P-5 = A, #39) |
| `except Exception` with neither a re-raise nor a reason | 4.1 | 5 | ruff `BLE001` catches only 3 of the 5 (a handler that calls `logger.exception` passes it) | enabled in 4.1. The other two need the generic linter in the next row |
| Bare `pyright: ignore` / `noqa` without a reason | 4.1, 4.2 | 10+ | adaptable: python-fastapi-layered `any-justified` WHY linter | `/scaffold-linter justified-pragmas --recipe python-fastapi-layered`, after Phase 5 (strict changes the pragma set) |
| Raw literal equal to a declared StrEnum value | 3.1, 3.5 | 7 | adaptable: `python-fastapi-layered/check_enum_discipline.py` | `/scaffold-linter enum-discipline --recipe python-fastapi-layered/check_enum_discipline.py`, after Phase 3 |
| Function > 30 lines | 4.4, 4.5, 4.9 | 6 | `python-fastapi-layered/check_file_length.py` (function mode) | `/scaffold-linter function-length --recipe python-fastapi-layered/check_file_length.py`, after Phase 4 (the vendored `run_layer_check` stays at 31 lines, #41; exclude `tools/pre_commit_checks`) |

## Deferred Items

| Item | REVIEW ref | Reason | Tracker |
|---|---|---|---|
| Environment-dependent skips (uv / docker / stack down) | §6 🟡 "#8 still present" | CI has docker + uv; the skips only happen on a bare machine. 3.7 adds the platform-conditional category | #8 |
| `ci_gate_inventory.py` sees 1 of 5 trees | §7 🟡 row 1, Harness Gap 1 | The fix belongs in the harness (`_trees.py` depth-2 detection). Until then, keep the hand audit of the Python trees in every review | #37 |
| A `set_dataset` / `set_features` ledger op (the skill rebuilds the ledger via `ledger.parse`) | Implementation-Notes promotion row "Ledger op gap" | A backlog item, not a finding | #38 |

The `tools/` type + test gate (REVIEW §7 row 2, #7) is fixed in Phase 8 without a root uv project, so #7 stays open only for its original root-gate question.

**Not planned (🔵 Info rows):** REVIEW §1–§7 Info rows stay unplanned unless a unit folds them in. Folded in: `sweep_query` purity (7.1), the template pyright mode (5.1), the `bench.py` lambda (4.2), the three test-helper annotations (4.10), the app type-import + `as Error` casts (6.2), and the hydra-gate stderr + subprocess timeout (8.2). The Harness Gaps, the IMPLEMENTATION_NOTES promotion rows and the LiveKit quirks are harness / Panoramix work (`/harness-feedback`, `propose_learning`), not repo fixes. In-repo exceptions: the size-gate warn band (8.2), the ruff rules (4.1, 4.10) and the Python ↔ TS pin (3.2/3.3).
