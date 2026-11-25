# Fix Plan — data-lab

**Date:** 2026-11-11
**Based on:** REVIEW.md dated 2026-11-11
**Project type:** Python (generic) uv monorepo + Astro/TypeScript app (`app/`) + Claude Code plugin
**Output mode:** multi-phase (3 phases, 25 fix units total)

## Phase Summary

| Phase | Theme | Severity | Fix Units | Files | Agent | Depends on |
|-------|-------|----------|-----------|-------|-------|------------|
| 1 | Resilience + test quality | 🟡 | 9 | 20 | python-fastapi | — |
| 2 | Python lint, hooks & docs | 🟡 | 13 | 40 | python-fastapi | Phase 1 |
| 3 | App & CI gates | 🟡 | 3 | 6 | general-purpose | Phase 2 |
| **Total** | | | **25** | **66** | | |

REVIEW.md has no 🔴 finding. 🔵 Info rows are not planned.

## Simplicity Review

Reviewer: `simplicity-reviewer` (fable). Before: 5 phases / 22 fix units. After review: 2 phases / 21. After `/plan-fix-validate` round 1 (old 2.3 split into renames + config + strict-own-files; App/CI moved to their own phase for stack coherence): 3 phases / 25.

| # | Item | Class | Disposition |
|---|------|-------|-------------|
| S-1 | 1.2 compare-and-swap via a `PrivateAttr` cannot work: ops rebuild through `revalidate` (`ledger_ops.py:31-35`) | mechanism | applied — explicit `write_atomic(..., base=)` compared in `_check_overwrite` |
| S-2 | "concurrent test look" test cannot go red (append-only rule already refuses it) | add | applied — test dropped; residual simultaneous window stated as accepted |
| S-3 | `_layout.py::run_layer_check` edit reopens decision #41 | drop/defer → #41 | applied — step removed; `_layout.py` excluded from the widened hooks |
| S-4 | gates-root pins requirements file + CI pip-audit | drop/defer | **user: close by ADR** — 2.6 item 4 |
| S-5 | app JS SAST → ADR instead | drop/defer | **user: keep code** — 3.3 |
| S-6 | drop ruff `T20` | drop/defer | **user: keep code** — 2.3d with CLI per-file ignores |
| S-7 | pyright strict on vendored tools | drop/defer | user first kept code; the validator measured 84 strict errors (47+ in vendored recipe scripts) → **user: strict on project-owned files only** (2.3e) + ADR (2.6 item 6) |
| S-8 | ruff `N` silently missing from the plan | add | applied — 2.3a–c rename 8 internal exceptions, 2.3d adds `N` (public `TrackingUnavailable`, the `__DATALAB_PACKAGE__` placeholder and the Weaviate-mirroring fakes keep reasoned ignores) |
| S-9 | claim "per-tree envs make cross-project imports fail" | keep | verified; 2.5 sentence + ADR (2.6 item 5) |
| S-10 | merge 3.1a/b/c into one unit | mechanism | **not applied** — 20 files exceed the 8-file batch limit; kept as 2.1a–c |
| S-11 | 5 phases → 2 | mechanism | applied |
| S-12 | scenario-id traceability | drop/defer | **user: defer** → #53 |
| S-13 | Hypothesis property tests | drop/defer | **user: defer** → #54 |
| S-14 | scaffold tests CI-only | drop/defer | **user: close by ADR** — 2.6 item 3 |
| S-15 | 1.1, 1.3, 1.4, test units, hooks, 5.1, 5.2 | keep | kept |

## REVIEW.md coverage (🟡 findings → fix unit)

| REVIEW finding | Covered by |
|---|---|
| §1 import boundary without contract | 2.5 + 2.6 item 5 (structural via per-tree envs) |
| §1 `value_sets.json` missing from ARCHITECTURE.md | 2.5 |
| §1 tools / `.ci-gate-exemptions.json` missing from ARCHITECTURE.md | 2.5 |
| §2 pyright basic outside src | 2.3e + 2.6 item 6 |
| §2 ruff select gaps | 2.3a, 2.3b, 2.3c, 2.3d |
| §3 card status without FSM | 2.6 item 1 |
| §3 card statuses not in value_sets | 2.6 item 1 |
| §4 TQ6 skips (2 rows) | Deferred → #8 |
| §4 scenario traceability | Deferred → #53 |
| §4 no property tests | Deferred → #54 |
| §4 TQ1 transitions oracle | 1.5 |
| §4 invalid vectors prefix-only | 1.6 |
| §4 `len(tags) == 11` | 1.7 |
| §4 `hits == 1` change detector | 1.8 |
| §4 `close_runs` unreadable path | 1.9 |
| §4 `close_runs` roulette | 1.9 |
| §5 unjustified suppressions | 2.1a, 2.1b, 2.1c, 2.2; `_layout.py:35,61,95` → #41 |
| §5 file-size hook scope | 2.4a, 2.4b, 2.6 item 2 |
| §5 function length | 2.4b, 2.6 item 2; `_layout.py::run_layer_check` → #41 |
| §6 MLflow retries | 1.1 |
| §6 `run.json` lost update | 1.2 |
| §6 budget under-count | 1.3 |
| §6 CRLF hashes | 1.4 |
| §7 inventory blind spot | 3.1 |
| §7 template scaffold tests CI-only | 2.6 item 3 |
| §7 app build parity | 3.2 |
| §7 root dep audit | 2.6 item 4 |
| §7 app JS SAST | 3.3 |

## Cross-phase Dependencies

- Phase 2 after Phase 1: both touch test files, and 2.3d turns on `ANN`/`PGH`/`T20`/`N`, so Phase 1's new code must already comply.
- Phase 3 after Phase 2: 2.2 and 2.4b edit `.pre-commit-config.yaml`, which 3.2 also edits.

## Recommended Execution Order

For each phase: branch → `/implement-fix-phase N` → `/check` → PR → CI → merge → next phase.

**Per-phase specs are in `FIX_PLAN_PHASE_N.md` files.** This overview is for navigation only.

## Recurring Patterns Worth Promoting to Linters

| Pattern | Fix units | Files affected | Recipe match | Scaffold command |
|---------|-----------|----------------|--------------|------------------|
| `# type: ignore[...]` / `# pyright: ignore[...]` with no `# why` | 2.1a–c | 19 | none needed — pre-commit `language: pygrep` | added directly by 2.2 (no `/scaffold-linter`) |
| File > 200 lines outside `src/` | 2.4a | 1 | existing `tools/check_file_size.py` + vendored `check_function_length.py` | scope widened by 2.4b (no new linter) |

Both are mechanized inside Phase 2 itself, so no `/scaffold-linter` run is needed afterwards.

## Deferred Items

- **§4 TQ6 — 3 `skipif(sys.platform == "win32")` tests** (`test_new_project.py:221`, `test_new_project_outside.py:154,166`) → **#8** (environment-dependent skips; the `uv` stub is a `#!/bin/sh` script).
- **§4 scenario-id traceability** (88 catalogue ids in `tests/TESTING_SCENARIOS.md`) → **#53**.
- **§4 TQ9 property-based tests** (Hypothesis) → **#54**.
- **§5 `tools/pre_commit_checks/_layout.py`** — `run_layer_check` (31 lines) and its 3 unjustified suppressions (lines 35, 61, 95) → **#41** (vendored recipe left to the harness; scope widened in an issue comment 2026-11-11; the file is excluded from the widened size hooks and the `suppression-reason` hook).
