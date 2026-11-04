# Fix Plan — Phase 5: Test gaps — TS

**Severity:** 🟡
**Agent:** general-purpose. Brief it on `app/` conventions:
- tests are `src/**/*.test.ts` run by `node --test` with type stripping (`import { test } from 'node:test'`, `import assert from 'node:assert/strict'`);
- no `astro:*` import in `src/lib`;
- `npm test` enforces 70 % line coverage;
- `noUncheckedIndexedAccess` is on after Phase 3.1, so narrow with `assert.ok` and never use `!`.

**Depends on:** Phase 3 (zod parsers, `config.ts`, strict index access, isolated build report)
**Fix units:** 2
**Files affected:** 3

**Rules for every unit:**
- Tests only: no `src/` change. If a new test exposes a bug, mark it `{ todo: '<bug>' }`, list it in the PR body, and stop that unit.
- Expected values are hand-written literals.
- Spec-style names (`'should <behaviour> when <scenario>'`), keeping any F-/U- prefix.

## Within-phase Dependencies

The two units are independent.

## Fix Units

### Fix Unit 5.1: `completeness.ts`: `abandonné`, fences, unterminated comments, NFC headings
- **Files:** `app/src/lib/completeness.test.ts`
- **Violation pattern (Grep):** `N/A`
- **Expected after fix:** 0 matches
- **Reference example:** `app/src/lib/completeness.ts` (`SECTIONS_BY_STATUS`, `FENCE`, the comment regex with `|$`, `sections()` → `.normalize('NFC')`) and the existing `'status ladder: …'` tests
- **HOW TO FIX:**
  1. `'should require the conclu sections when status is abandonné'`: `abandonné` needs Objectif, Approche, Enseignements, Suite (`completeness.ts:4-9`) **and** is in `NEEDS_DATA_AND_METRIC` (`completeness.ts:10`). Build the card with `data` and `metric` set and Objectif/Approche filled; with Enseignements/Suite absent, exactly those two are reported missing.
  2. `'should report Approche missing when status is en cours'`.
  3. `'should ignore a heading inside a ~~~ fence'` and `'should keep a fence open until a closing fence at least as long'` (a four-backtick fence that only four backticks close).
  4. `'should blank only its own section when a <!-- is never closed'`: `sections()` splits on headings first, then strips `COMMENT` per section (`completeness.ts:14,22-38`). So a section whose body **starts with** the open `<!--` (no content before it) counts as missing, and the **next** `## X` section is unaffected (still filled).
  5. `'should match an NFD heading against the NFC section name'`: build it with `́` escapes, never an invisible literal (REVIEW §4 🔵).

### Fix Unit 5.2: MLflow client error paths; split `'shape check'`; metric-key table
- **Files:** `app/src/lib/mlflow.test.ts`, `app/src/lib/card.test.ts`
- **Violation pattern (Grep):** `^test\('shape check'`
- **Expected after fix:** 0 matches
- **Reference example:** the existing `fakeFetch` helper and `'F-1: …'` tests in `mlflow.test.ts`
- **HOW TO FIX:**
  1. Split `'shape check'` into two spec-named tests, one per scenario it holds today, with the same assertions.
  2. Add `'F-1: should report unavailable when the retry fails too'`: two consecutive timeouts or 5xx give `{ kind: 'unavailable' }`.
  3. Add `'F-1: warmUp polls once per fetch implementation'`: two `warmUp` calls with the same counting fake, a short `budgetMs` and an explicit `env` share one promise (`===`) and one poll sequence.
  4. Add `'F-1: warmUp resolves without rejecting when /health stays non-200'`: the fake always returns 503 and `budgetMs` is 50. Assert it resolves and makes **≥ 1** fetch call. No wall-clock assertion (the testing rule forbids them), and no "≥ 2 calls": with a 50 ms budget `poll` makes exactly one fetch, then sleeps out the deadline (`mlflow.ts:41-52`).
  5. Add `'U-6: should report metric-not-logged end to end'`, going through `bestRun`/`metricState`, not only `pickBest`.
  6. Metric-key rejection lives with the schema, so extend `card.test.ts`'s existing `METRIC_KEY_RE` cases with a quote, a space and `$` (backtick and `/.-_` are already covered at `card.test.ts:7-15`).

<!-- plan-validate: READY 2026-11-04 sha256:a448154c9965 -->
