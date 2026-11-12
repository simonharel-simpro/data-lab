# Fix Status — data-lab (REVIEW 2026-11-11)

**Last updated:** 2026-11-12
**Plan:** FIX_PLAN.md (multi-phase, 3 phases) · integration branch `fix/review-2026-11-11` → `develop` · driven by `/loop-fix` · tracker #55

## Progress Summary

| Phase | Theme | Severity | Status | Fix Units | Completion |
|-------|-------|----------|--------|-----------|------------|
| 1 | Resilience + test quality | 🟡 | ✅ Complete | 9/9 | 100% |
| 2 | Python lint, hooks & docs | 🟡 | ✅ Complete | 13/13 | 100% |
| 3 | App & CI gates | 🟡 | ⏳ Pending | 0/3 | 0% |

**Overall:** 22/25 fix units complete (88%)

---

## Phase 1 — Resilience + test quality

**Implemented:** 2026-11-11
**Branch:** fix-phase-1-resilience-tests
**Agent:** python-fastapi (two sequential dispatches)
**Tooling:** ✅ `pre-commit run --all-files --hook-stage pre-push` all hooks pass

### Completed
- ✅ Fix Unit 1.1: Bound MLflow HTTP retries on the read path — 5 files, grep 1→0
- ✅ Fix Unit 1.2: `run.json` writes refuse a stale base — 4 files, grep 1→0
- ✅ Fix Unit 1.3: Voice-arch budget counts a cost-unknown run at its estimate — 3 files, grep 2→0
- ✅ Fix Unit 1.4: Hashed files are byte-stable across platforms — 4 files + 3 new, grep 3→0
- ✅ Fix Unit 1.5: Ledger transition test uses an independent oracle — 1 file, grep 2→0
- ✅ Fix Unit 1.6: Invalid ledger vectors assert what they blame — 2 files, grep 1→0
- ✅ Fix Unit 1.7: Drop the redundant tag count — 1 file, grep 1→0
- ✅ Fix Unit 1.8: Outside-scaffold source test asserts behaviour — 1 file, grep 1→0
- ✅ Fix Unit 1.9: `close_runs` one behaviour per test + unreadable-run path — 1 file, grep 1→0

### Notes
- `test_decide_unreachable_mlflow_fails_fast` was not seen red as an assertion failure: on the unfixed code it hung past 120 s (the defect itself); it passes in ~5 s after the fix.
- `voice_arch.budget._has_no_cost` helper added to keep `_unmeasured_estimates` within the 30-line function cap.
- Template `eval.py` is at exactly 200 lines (the cap).
- `tests/TESTING_SCENARIOS.md` not updated for the three behaviour changes (decide fails fast when MLflow is down; a stale `run.json` write is refused; cost-unknown runs count at estimate) — follow-up with #53.

### Cross-phase Regressions
- none (first phase)

### Verification Checklist
| Item | Status |
|------|--------|
| All fix units processed | ✅ |
| All grep patterns clean (`fix_plan_gate.py assert-zero --phase 1`) | ✅ |
| Tooling clean | ✅ |
| No cross-phase regressions | ✅ |

---

## Phase 2 — Python lint, hooks & docs

**Implemented:** 2026-11-12
**Branch:** fix-phase-2-lint-hooks-docs
**Agent:** python-fastapi (three sequential dispatches)
**Tooling:** ✅ `pre-commit run --all-files --hook-stage pre-push` all hooks pass

### Completed
- ✅ Fix Unit 2.1a / 2.1b / 2.1c: every `# type: ignore[...]` / `# pyright: ignore[...]` carries a reason — 19 files, grep 14+10+5→0
- ✅ Fix Unit 2.2: `suppression-reason` pygrep hook (seen failing with one reason stripped)
- ✅ Fix Unit 2.4a: StrEnum value maps moved to `tools/pre_commit_checks/enum_maps.py`; `check_enum_discipline.py` 202→116 lines, hook output unchanged
- ✅ Fix Unit 2.4b: `file-size` + `check-function-length` cover `tools/` (vendored files excluded), 2 new tests — grep 2→0
- ✅ Fix Unit 2.3a / 2.3b / 2.3c: 8 internal exceptions renamed `…Error` — grep 17+22+11→0
- ✅ Fix Unit 2.3d: ruff `ANN`, `PGH`, `T20`, `N` + reasoned per-file ignores; scaffold-shaped copy passes — grep 1→0
- ✅ Fix Unit 2.3e: pyright strict on `tools/check_file_size.py`, `hydra_gate.py`, `enum_maps.py`
- ✅ Fix Unit 2.5: ARCHITECTURE.md lists `value_sets.json`, the pre_commit_checks files, `.ci-gate-exemptions.json`, the new hooks, project isolation
- ✅ Fix Unit 2.6: six ADRs dated 2026-11-11

### Notes
- The plan's `suppression-reason` hook `name:` was unquoted and broke YAML (`type: ignore` contains `: `); it is single-quoted, same text.
- `test_vendored_tools_files_are_out_of_scope` passes on the old code too (the old `_in_scope` rejected every `tools/` path); it guards the exclusions now that `tools/` is in scope.
- A bare `ruff format .` from the root rewrites python blocks inside Markdown (ARCHITECTURE.md, two archive files); the hook only formats `.py`. Do not run it bare.

### Cross-phase Regressions
- none (`fix_plan_gate.py assert-zero --done` OK)

### Verification Checklist
| Item | Status |
|------|--------|
| All fix units processed | ✅ |
| All grep patterns clean (`fix_plan_gate.py assert-zero --phase 2`) | ✅ |
| Tooling clean | ✅ |
| No cross-phase regressions | ✅ |

---

## Next Phase Preview

**Phase 3: App & CI gates** — 3 fix units, 🟡, depends on Phase 2 ✅
