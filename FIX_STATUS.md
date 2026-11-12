# Fix Status — data-lab (REVIEW 2026-11-11)

**Last updated:** 2026-11-11
**Plan:** FIX_PLAN.md (multi-phase, 3 phases) · integration branch `fix/review-2026-11-11` → `develop` · driven by `/loop-fix` · tracker #55

## Progress Summary

| Phase | Theme | Severity | Status | Fix Units | Completion |
|-------|-------|----------|--------|-----------|------------|
| 1 | Resilience + test quality | 🟡 | ✅ Complete | 9/9 | 100% |
| 2 | Python lint, hooks & docs | 🟡 | ⏳ Pending | 0/13 | 0% |
| 3 | App & CI gates | 🟡 | ⏳ Pending | 0/3 | 0% |

**Overall:** 9/25 fix units complete (36%)

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

## Next Phase Preview

**Phase 2: Python lint, hooks & docs** — 13 fix units, 🟡, depends on Phase 1 ✅
