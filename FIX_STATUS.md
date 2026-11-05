# Fix Status — review-2026-11-04

Ledger maintained by `/loop-fix` (integration branch `fix/review-2026-11-04` → `main`).
A phase is complete only when it is merged into `fix/review-2026-11-04` **and** marked here.

| Phase | Theme | Status | Branch | /check | Landed |
|-------|-------|--------|--------|--------|--------|
| 1 | Run integrity & resilience (pilot) | ✅ complete | fix-phase-1-run-integrity | clean @ d8284c5 (1 fix-check iter) | 2026-11-05 |
| 2 | Gates, input validation & dependency hygiene | ✅ complete | fix-phase-2-gates-validation-deps | clean @ da43950 (1 fix-check iter) | 2026-11-05 |
| 3 | App boundaries (TS) | ✅ complete | fix-phase-3-app-boundaries | clean @ f47e288 (1 fix-check iter) | 2026-11-05 |
| 4 | Test gaps — Python | ✅ complete | fix-phase-4-python-test-gaps | clean @ d0f4594 (1 fix-check iter) | 2026-11-05 |
| 5 | Test gaps — TS | ✅ complete | fix-phase-5-ts-test-gaps | clean @ b1c003c (0 fix-check iters; Test-Change #15) | 2026-11-05 |

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

## Phase 2 — Gates, input validation & dependency hygiene

**Implemented:** 2026-11-05 · **Branch:** fix-phase-2-gates-validation-deps · **Agents:** python-fastapi (2.1, 2.4, 2.5), general-purpose (2.2, 2.3)
**Tooling:** gate_runner exit 0 (with node 22 on PATH). The pre-push suite now runs gates-datalab, gates-mini-rag and gates-app, all passing. gitleaks full history: 25 commits, no leaks. pip-audit exit 0 in both trees.

- ✅ 2.1 `fullmatch` for project names. Red-first commit `bcd326e` was confirmed red by the orchestrator. grep 3→0
- ✅ 2.2 CI: full-history gitleaks, locked lint-imports/pyright/pip-audit/pytest, `npm audit`. grep 2→0
- ✅ 2.3 Local pre-push parity: three gate hooks, plus `default_install_hook_types`
- ✅ 2.4 Runtime specs bounded (`~=`). `uv.lock` changed only in specifier metadata; no version moved. grep 4→0
- ✅ 2.5 Template inherits the dev list, gates and `.python-version` 3.12. grep 1→0

Environment note: the gates-app hook needs node >=22.22 on PATH (`.nvmrc`). Under node 20 it fails loudly at `astro check`, and a one-line comment on the hook says so. `pre-commit install` has not been run; that is left to the user.
Cross-phase regressions: none (`assert-zero --done` OK).

## Phase 3 — App boundaries (TS)

**Implemented:** 2026-11-05 · **Branch:** fix-phase-3-app-boundaries · **Agent:** general-purpose (node 22)
**Tooling:** `npm test` 53/53 pass, 100% line / 93.02% branch coverage · `astro check` 0 errors · `tsc` 0 errors · `npm run build` OK · pre-push hooks all pass

- ✅ 3.1 `noUncheckedIndexedAccess` enabled; 10 → 0 errors. Existing tests were edited only to narrow types, with the same assertions and no `!`
- ✅ 3.2 zod-validated MLflow REST parsers + `mlflow-rest.test.ts` (5 tests, each seen red under a schema mutation). grep 3→0
- ✅ 3.3 `src/lib/config.ts` owns the env var names + `config.test.ts`. grep 3→0. Also `Base.astro` import repointed (outside the file list; recorded deviation)
- ✅ 3.4 Build report isolated by `beforeEach(clear)` + a new dedup test

Behaviour note for the PR: the verbatim `Run` schema is stricter than the old parser. `data: null` or a string run now throws, so the card shows `unavailable`; ±Infinity `start_time` → 0. See IMPLEMENTATION_NOTES.md.
Cross-phase regressions: none.

## Phase 4 — Test gaps (Python)

**Implemented:** 2026-11-05 · **Branch:** fix-phase-4-python-test-gaps · **Agent:** python-fastapi
**Tooling:** mini-rag 114 passed (96.49% cov) · datalab 56 passed · pyright 0 · ruff clean · pre-push hooks pass. Tests only; `src/` untouched.

- ✅ 4.1 golden `collection_name` + bad-project paths
- ✅ 4.2 tables for `parse_number`/`normalize`/`contains_phrase` (+ an extra `("", "")` row so the empty-needle guard is actually covered)
- ✅ 4.3 `metrics()` invariants, enumerated exhaustively for n=1..4
- ✅ 4.4 every logged param, the full per-question artifact, and config_hash sensitivity to k/model/size. grep 2→0
- ✅ 4.5 `index.search()` units + the failed-objects branch. grep 2→0
- ✅ 4.6 a real failure condition for `datalab-new` (no private-helper patch). grep 1→0
- ✅ 4.7 chunking boundaries + empty-folder error. grep 1→0
- ✅ 4.8 port parity across the three `.env.example` copies

Each new test pins existing behaviour. Each was seen red under a targeted source mutation. No source bugs found, so no xfail tests.
Gap: `corpus.py:21`'s `\r\n` replace is redundant, since `str.split()` already treats `\r` as whitespace. No test can kill that mutation.

## Phase 5 — Test gaps (TS)

**Implemented:** 2026-11-05 · **Branch:** fix-phase-5-ts-test-gaps · **Agent:** general-purpose (node 22)
**Tooling:** `npm test` 65/65 pass, 100% line / 93.18% branch coverage · `astro check` 0 errors · `tsc` 0 errors · pre-push hooks pass · weak_tests 0. Tests only.

- ✅ 5.1 `completeness.ts`: `abandonné`, `en cours`, `~~~` and long fences, an unterminated `<!--`, NFD→NFC headings (6 tests)
- ✅ 5.2 MLflow client error paths (retry fails too, warmUp dedup and non-200), `'shape check'` split in two (grep 1→0), `metric-not-logged` end to end, metric-key rejection table

Each new test pins existing behaviour and was seen red under a targeted source mutation. No `{ todo }` bugs.
