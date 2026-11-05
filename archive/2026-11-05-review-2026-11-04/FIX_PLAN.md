# Fix Plan — data-lab

**Date:** 2026-11-04
**Based on:** REVIEW.md dated 2026-11-04
**Project type:** Python (generic, uv multi-tree: `packages/datalab`, `projects/mini-rag`, `templates/project`) + Astro 7 / TypeScript (`app/`)
**Output mode:** multi-phase (5 phases, 24 fix units total). Every 🔴 and 🟡 finding in REVIEW.md is covered, explicitly deferred, or accepted below. 🔵 rows are out of scope unless folded into a unit.

**Baseline measured before planning:**
- `lint-imports`: 1/1 contract kept in each tree.
- `pyright` (basic): 0 errors in both trees.
- `pip-audit`: no known vulnerabilities (local dists skipped).
- `npm audit`: 0.
- `tsc --noUncheckedIndexedAccess`: **10 errors** in 7 files.

Wiring the Python and npm gates needs no code fix. The TS flag does (3.1).

## Phase Summary

| Phase | Theme | Severity | Fix Units | Files | Agent | Depends on |
|-------|-------|----------|-----------|-------|-------|------------|
| 1 | Run integrity & resilience (pilot) | 🔴 | 5 | 16 | python-fastapi | — |
| 2 | Gates, input validation & dependency hygiene | 🟡 | 5 | 10 | python-fastapi (2.1, 2.4, 2.5), general-purpose (2.2, 2.3) | — |
| 3 | App boundaries (TS) | 🟡 | 4 | 12 | general-purpose | Phase 2 (preferred) |
| 4 | Test gaps — Python | 🟡 | 8 | 7 | python-fastapi | Phases 1, 2 |
| 5 | Test gaps — TS | 🟡 | 2 | 3 | general-purpose | Phase 3 |
| **Total** | | | **24** | | | |

Agent note: the project is generic Python, not FastAPI. `python-fastapi` is the only Python implementer agent, so its layered-FastAPI rules (routers/services/repositories) do **not** apply, and every dispatch prompt says so. There is no Astro agent: TS units go to `general-purpose`, briefed with the `app/` conventions written at the top of each TS phase file.

## Simplicity Review

Reviewer: `simplicity-reviewer` (fable), 2026-11-04. Before: 7 phases / 29 units. **After: 5 phases / 24 units.** I re-checked each row against the code; S-3 was confirmed (`projects/mini-rag/.env` exists and sets `MINI_RAG_DGX_BASE_URL`) and so was S-9 (`_isolated` already clears `MLFLOW_*`).

| # | Item | Class | Disposition |
|---|---|---|---|
| S-1 | 1.6 fcntl index build lock (SUSPECTED race) | would leave finding unfixed | **Deferred by user** → issue #12 |
| S-2 | 7 phases, files edited in several phases | mechanism | **Applied**: old Phases 2+3+5 merged into Phase 2. `run()` grouping folded into 1.1, call-order detector into 1.3, CLI tests into 1.5, report isolation and parser tests into Phase 3. Some test files are still edited in two phases (`test_run.py`, `test_index.py`, `test_corpus.py`, datalab `test_settings.py`, `test_new_project.py`, `mlflow.test.ts`, `completeness.test.ts`); the phase dependencies below order those edits |
| S-3 | `main()` config-before-I/O test would fail locally (real `.env`) | add | **Applied** in 1.5: monkeypatch `load()` and never chdir into the real tree |
| S-4 | warmUp test "≥ 2 calls in 50 ms" cannot pass | add | **Applied** in 5.2: assert ≥ 1 call, resolves, elapsed ≥ budget |
| S-5 | 🔴 fix only saved results after all generations | mechanism | **Applied** in 1.1: JSONL appended per answer inside the loop; no temp/rename helper |
| S-6 | `config.ts` `processEnv()` indirection and re-export shim | mechanism | **Applied** in 3.3: the readers keep `= process.env` defaults; only var names centralise; grep is `DATALAB_` |
| S-7 | Exact-pinning dev tools | mechanism / partial | **User: runtime only** (2.4). Dev `>=` accepted, see below |
| S-8 | TQ7 noise tests (determinism, `isclose` symmetry, `count/n` re-implementation, `chmod 000`, a duplicate key table) | mechanism | **Applied**: dropped; the metric-key cases moved to `card.test.ts` |
| S-9 | 1.2 retry bounds in `datalab.tracking` | keep | Kept; removed the moot fixture step |
| S-10 | `Backends` wrapper dataclass | mechanism | **Applied**: only `RunConfig` (what `config_hash` covers); 8 keyword-grouped params |
| S-11 | MLflow URI scheme allowlist would refuse `postgresql://` etc. | mechanism | **Applied** in 1.5: one "has a scheme" validator on both URL fields |
| S-12 | Double `corpus_hash`; catching `AttributeError` | mechanism | **Applied**: hash computed once in `main()`; `isinstance(message, anthropic.types.Message)` |

## Cross-phase Dependencies

- **Phase 1 → 4.** Phase 4's `run()` tests target the `RunConfig`/`corpus_hash` signature that Phase 1 creates.
- **Phase 2 → 4.** 4.1 tests `"mini-rag\n"` rejection (2.1).
- **Phase 3 → 5.** The TS tests rely on 3.1's strict index access, 3.2's zod parsers and 3.4's isolated build report.
- Phases 1 and 2 are independent of each other; merge them in either order.

## Recommended Execution Order

For each phase: branch → `/implement-fix-phase N` → `/check` → PR → CI → merge → next phase. Order: 1 → 2 → 3 → 4 → 5.

**Per-phase specs are in `FIX_PLAN_PHASE_N.md` files.** This overview is for navigation only.

## Recurring Patterns Worth Promoting to Linters

| Pattern | Fix units | Files affected | Recipe match | Scaffold command |
|---------|-----------|----------------|--------------|------------------|
| `# type: ignore[...]` / `# noqa` with no reason after the code | REVIEW §5 🔵 (not a fix unit) | 9 | adaptable: python-fastapi-layered `any-justified` WHY linter (`rules/python-fastapi/tooling.md:174`) | `/scaffold-linter justified-suppressions --recipe python-fastapi-layered`, after first adding the reasons (a small follow-up PR) |

The `.match` + `$` validation regex (2.1) appears in one file only, so it is below the bar. It is tracked as harness issue 4 in HARNESS_FEEDBACK.md.

## Deferred Items

| Item | REVIEW ref | Reason | Tracker |
|---|---|---|---|
| Serialize index builds across concurrent runs (fcntl lock or build-then-alias) | §6 🟡 (SUSPECTED) | User decision 2026-11-04 (S-1): solo lab; the race is narrowed by 1.3 | #12 |
| Formatter + linter for `app/` (prettier/eslint) | §7 🟡 "app has no format/lint/SAST" (format/lint half; the local-hook half is fixed in 2.3, types in 3.1) | Adds 2+ dev deps and a style decision | #13 |
| pyright `strict` on `src/` | §2 🟡 (the strict half; the "never runs" half is fixed in 2.2/2.3) | REVIEW lists it as a Phase-2 architectural item | #14 |

**Accepted (won't fix):**
- Dev-group `>=` specs (REVIEW §5 🟡, dev half). User decision 2026-11-04: `uv.lock` is the pin, CI runs `--locked`, and `uv lock --upgrade` keeps working.
- `run()` keeps 8 parameters, not 5 (REVIEW §2 🟡). Simplicity review S-10: the hashed config is grouped into `RunConfig` (1.1); `answer`, `search` and `results_dir` share nothing, and a wrapper just to hit the count is worse. 12 → 8, grouped by role. The private `_answer_all` helper has 6.
- `datalab-new` running `uv lock` for the new project (REVIEW §5 template row, a suggestion). 2.5 ships the pinned dev group and `.python-version`; the first `uv sync` writes the lock.
**Out of scope (🔵):** `IndexBuildError` dropping the batch reason, the DGX preflight, the misleading MLflow error message, the Ctrl-C temp dir, and the other §1–§7 Info rows.
