# Review Validation Report — data-lab

**Date:** 2026-11-05 (re-validated after `/heal-review`, the same day)
**Review date:** 2026-11-04
**Project type:** generic Python (uv multi-tree: packages/datalab, projects/mini-rag, templates/project) + Astro 7 / TypeScript (app/)
**Validated ref:** `fix/review-2026-11-04` (PR #16, unmerged)

## Validation Summary

| Category | Findings Checked | ✅ Pass | ⚠️ Partial | ❌ Fail | ⏭️ Deferred | Completion* |
|---|---|---|---|---|---|---|
| Architecture & Separation of Concerns | 2 | 2 | 0 | 0 | 0 | 100% |
| Typing & Style | 3 | 2 | 0 | 0 | 1 | 100% |
| State Management & Enums | 0 | 0 | 0 | 0 | 0 | — |
| Testing Quality | 14 | 14 | 0 | 0 | 0 | 100% |
| Documentation & Cognitive Debt | 2 | 2 | 0 | 0 | 0 | 100% |
| Resilience & Failure Modes | 7 | 6 | 0 | 0 | 1 | 100% |
| CI Gate Surface | 5 | 4 | 0 | 0 | 1 | 100% |
| **Migration Plan** | 20 | 15 | 0 | 0 | 2 | 100% |
| **TOTAL** | 53 | 45 | 0 | 0 | 5 | **100%** |

*Completion % = Pass / (Pass + Partial + Fail). Deferred and skipped items are not counted in the denominator (3 ⏭️ SKIPPED: M0.5, M2.2, M3.3).

## Overall Verdict

- ⚠️ **GAPS FOUND**: every finding is resolved. The cap is tooling only: 2 review tools are not installed (bandit, radon). Run `/heal-review` only if you decide to add them as dev dependencies; there are no finding gaps left to heal.

Computed by `review_gate.py verdict --compute-only` after `/heal-review` (2026-11-05): **GAPS FOUND — completion 100%**. The reasons are `tool bandit: not-installed` and `tool radon: not-installed`. No finding is PARTIAL or FAIL. The 🔴 critical F6.1 is ✅ PASS. 5 items are ⏭️ DEFERRED with trackers (#12, #13, #14) and 3 are ⏭️ SKIPPED as out of scope.

## Detailed Results

### 1. Architecture & Separation of Concerns

| ID | Status | Original Finding | Scope Checked | Files Still Affected | Details |
|---|---|---|---|---|---|
| F1.1 | ✅ PASS | MLflow REST validated by hand-rolled guards | all app/src (.ts,.astro) | 0 | `mlflow-rest.ts:2` zod from `astro/zod`, `safeParse` :48-49, `z.infer` types :21-24; no `isObject` left |
| F1.2 | ✅ PASS | Env read in 4 modules | all app/src incl .astro | 0 | `config.ts:6-9` owns every `DATALAB_*`; elsewhere only `env = process.env` pass-through defaults |

### 2. Typing & Style

| ID | Status | Original Finding | Scope Checked | Files Still Affected | Details |
|---|---|---|---|---|---|
| F2.1 | ✅ PASS | `run()` had 12 params | run.py + callers + tests | 0 | 8 params grouped by role; frozen `RunConfig` at `run.py:39` (8 accepted by FIX_PLAN) |
| F2.2 | ⏭️ DEFERRED | pyright basic + never executed | ci.yml, pre-commit, 3 configs | pyrightconfig.json:3, both pyproject pyright blocks | Never-run half ✅: `ci.yml:38,92` + pre-push `.pre-commit-config.yaml:45,52`. Strict half deferred — #14 |
| F2.3 | ✅ PASS | no `noUncheckedIndexedAccess` | app/tsconfig.json + all app/src | 0 | flag on; `tsc --noEmit` 0 errors; no new `!` |

### 3. State Management & Enums

No actionable findings in this section.

### 4. Testing Quality

| ID | Status | Original Finding | Scope Checked | Files Still Affected | Details |
|---|---|---|---|---|---|
| F4.1 | ✅ PASS | Trailing newline accepted by Python | name_vectors.json, project.py | 0 | 4 terminator vectors in reject; `fullmatch` at project.py:36,102,124 |
| F4.2 | ✅ PASS | collection_name hash never pinned | test_project.py | 0 | `test_collection_name_golden_value` |
| F4.3 | ✅ PASS | scoring helpers only via outcome() | test_scoring.py | 0 | ✅ Healed 2026-11-05: `test_numbers_equal_table` (11 rows hand-worked against rel_tol=1e-9 / abs_tol=1e-12, including unparseable input on either side) goes red under the rel_tol, abs_tol and None-guard mutations. The parse_number/normalize/contains_phrase tables were already present |
| F4.4 | ✅ PASS | metrics() no invariants | test_scoring.py:111 | 0 | exhaustive `itertools.product` n=1..4: rates sum to 1, score ∈ [-1,1] |
| F4.5 | ✅ PASS | main()/_args untested | test_cli.py | 0 | k<1, bogus retrieval, missing k, valid parse; config-before-I/O test. (No positive `--n` parse — range covered in test_run) |
| F4.6 | ✅ PASS | partial run-logging asserts | test_run.py:67,155 | 0 | full params dict + full per_question artifact |
| F4.7 | ✅ PASS | index.search() untested | test_index.py | 0 | bm25 + near_text + failed-objects warning tests |
| F4.8 | ✅ PASS | call-order change detector | repo-wide grep | 0 | no `calls == [("delete"` remains |
| F4.9 | ✅ PASS | private `_rewrite` patched | test_new_project.py | 0 | real template failure (`__DATALAB_UNKNOWN__`) instead |
| F4.10 | ✅ PASS | load_corpus errors + boundaries | test_corpus.py | 0 | no-md error, n=size, overlap 0, empty doc, CRLF all tested |
| F4.11 | ✅ PASS | completeness.ts gaps | completeness.test.ts | 0 | abandonné, ~~~, long fence, unterminated `<!--`, NFC |
| F4.12 | ✅ PASS | mlflow error paths | mlflow.test.ts | 0 | retry-fails-too, warmUp memo, non-200 /health |
| F4.13 | ✅ PASS | globalThis build report leaks | mlflow.test.ts, export-guard.test.ts | 0 | `beforeEach(clear)` in both |
| F4.14 | ✅ PASS | port parity root-only | test_settings.py | 0 | `test_g_10_env_examples_agree` across 3 copies |

### 5. Documentation & Cognitive Debt

| ID | Status | Original Finding | Scope Checked | Files Still Affected | Details |
|---|---|---|---|---|---|
| F5.1 | ✅ PASS | unbounded `>=` runtime deps | both pyprojects, ci.yml | 0 | runtime `~=`/`==`; dev `>=` accepted (user decision, uv.lock + `--locked`) |
| F5.2 | ✅ PASS | template `pytest>=8`, no lock/.python-version | templates/project | 0 | ✅ Healed 2026-11-05: template dev deps exact-pinned to mini-rag's uv.lock (pytest==9.2.0, pytest-cov==7.1.0, pyright==1.1.414, ruff==0.17.3, pip-audit==2.10.1), guarded by `test_template_dev_deps_are_exact_pins`. `datalab-new` now runs `uv lock` in the temp dir before publishing. If uv is missing, exits non-zero or times out, it aborts with exit 1 and leaves nothing (user decision), covered by 4 new tests. `.python-version` is 3.12 |

### 6. Resilience & Failure Modes

| ID | Status | Original Finding | Scope Checked | Files Still Affected | Details |
|---|---|---|---|---|---|
| F6.1 | ✅ PASS | results in memory until end (🔴) | run.py, .gitignore, tests | 0 | per-answer append to `results/<run_id>.jsonl` inside the loop (run.py:77-84); 2 tests; gitignored |
| F6.2 | ✅ PASS | stale index after corpus edit | index.py, run.py | 0 | `c<corpus_hash>` in name, computed once in main(); same-count test |
| F6.3 | ✅ PASS | non-JSON/list 200 → AttributeError | generate.py:67 | 0 | isinstance Message → GenerationError; 3 tests |
| F6.4 | ✅ PASS | max_tokens cut-off scored | generate.py:69 | 0 | truncated → GenerationError; test |
| F6.5 | ✅ PASS | all-empty corpus accepted | corpus.py | 0 | ValueError; test |
| F6.6 | ⏭️ DEFERRED | concurrent runs race on collection | index.py | index.py `_build` | No lock; content-keyed names narrow only cross-corpus races — #12 |
| F6.7 | ✅ PASS | `--k` unbounded | run.py:121 | 0 | `_positive_int`; test_cli |

### 7. CI Gate Surface

| ID | Status | Original Finding | Scope Checked | Files Still Affected | Details |
|---|---|---|---|---|---|
| F7.1 | ✅ PASS | gitleaks no-op in CI | ci.yml | 0 | fetch-depth 0 + `gitleaks git` full history (ci.yml:19,26-30) |
| F7.2 | ✅ PASS | lint-imports never run | ci.yml, pre-commit | 0 | ci.yml:37,91; pre-push :45,52 |
| F7.3 | ✅ PASS | pyright never run | ci.yml, pre-commit | 0 | ci.yml:38,92; pre-push :45,52 |
| F7.4 | ✅ PASS | no dependency audit | ci.yml | 0 | pip-audit ci.yml:39,93; npm audit :58 |
| F7.5 | ⏭️ DEFERRED | app no format/lint/SAST, no local hook | pre-commit, app | app/package.json | Hook half ✅ (`gates-app` pre-push); types raised (3.1); prettier/eslint half deferred — #13 |

### 8. Simpro Cloud & AI Patterns

Not present in REVIEW.md.

### 9. Tooling Verification

`review_gate.py` reads one gate record, and the repo root has no uv project (#7, so the root `pytest` row is exempt). The record is therefore the **mini-rag sub-root** run, `REVIEW_GATE.json`. That run also executes the full repo pre-push suite: the datalab, mini-rag and app gates. The datalab sub-root run is kept as `REVIEW_GATE-datalab.json`. Both ran with node 22 on PATH.

**mini-rag** (`gate_runner.py python-fastapi --root projects/mini-rag --review`):

| Tool | Command | Exit | Status | Detail |
|------|---------|------|--------|--------|
| pre-commit pre-push | `pre-commit run --all-files --hook-stage pre-push` | 0 | ✅ PASS | app astro check + unit tests + coverage floor.........................................Passed |
| pyright | `uv run pyright` | 0 | ✅ PASS | 0 errors, 0 warnings, 0 informations |
| ruff | `uv run ruff check .` | 0 | ✅ PASS | All checks passed! |
| lint-imports | `uv run lint-imports` | 0 | ✅ PASS | Contracts: 1 kept, 0 broken. |
| pytest | `uv run pytest` | 0 | ✅ PASS | ================ 132 passed, 2 deselected, 1 warning in 35.41s ================= |
| bandit | `uv run bandit -r src/ -c pyproject.toml` | 2 | ⛔ NOT INSTALLED | Caused by: No such file or directory (os error 2) |
| radon | `uv run radon cc src/ -a -nc` | 2 | ⛔ NOT INSTALLED | Caused by: No such file or directory (os error 2) |
gate exit 2: a tool is NOT INSTALLED — gate incomplete

**datalab** (`--root packages/datalab --review`):

| Tool | Command | Exit | Status | Detail |
|------|---------|------|--------|--------|
| pre-commit pre-push | `pre-commit run --all-files --hook-stage pre-push` | 0 | ✅ PASS | app astro check + unit tests + coverage floor.........................................Passed |
| pyright | `uv run pyright` | 0 | ✅ PASS | 0 errors, 0 warnings, 0 informations |
| ruff | `uv run ruff check .` | 0 | ✅ PASS | All checks passed! |
| lint-imports | `uv run lint-imports` | 0 | ✅ PASS | Contracts: 1 kept, 0 broken. |
| pytest | `uv run pytest` | 0 | ✅ PASS | ================ 71 passed, 2 deselected, 2 warnings in 27.04s ================= |
| bandit | `uv run bandit -r src/ -c pyproject.toml` | 2 | ⛔ NOT INSTALLED | Caused by: No such file or directory (os error 2) |
| radon | `uv run radon cc src/ -a -nc` | 2 | ⛔ NOT INSTALLED | Caused by: No such file or directory (os error 2) |
gate exit 2: a tool is NOT INSTALLED — gate incomplete

`bandit` and `radon` (the review-only extras) are **⛔ NOT INSTALLED** in both trees. That is a real gap, and it caps the verdict. On the /check path, ruff's `S` rules (selected in `ruff.toml`) are the ADR-2026-09-29 SAST equivalent, and they pass. radon has no equivalent. Adding either tool as a dev dependency is a decision for the user. The app suite (65/65, 100% line coverage) runs inside the pre-push row.

### Test Coverage Matrix

| Source Module | Public functions | Directly tested | Happy | Error | Coverage |
|---|---|---|---|---|---|
| mini_rag/run.py | run, main | 2 | ✅ | ✅ (MLflow down, GenerationError, k<1, config-before-I/O) | ✅ |
| mini_rag/index.py | corpus_hash, index_name, ensure_collection, search | 4 | ✅ | ✅ (IndexBuildError, failed objects) | ✅ |
| mini_rag/generate.py | DgxGenerator.answer | 1 | ✅ | ✅ (4 malformed/truncated cases) | ✅ |
| mini_rag/scoring.py | parse_number, normalize, contains_phrase, numbers_equal, outcome, metrics | 6 of 6 | ✅ | ✅ (unparseable, tolerance edges) | ✅ |
| mini_rag/corpus.py | load_corpus, chunking | 2 | ✅ | ✅ | ✅ |
| datalab/project.py | validate_name, collection_name, experiment_name, load | 4 | ✅ | ✅ | ✅ |
| datalab/tracking.py | preflight, tracked_run | 2 | ✅ | ⚠️ retry bound asserted via preflight only | ⚠️ |
| app/src/lib/*.ts | mlflow, mlflow-rest, config, completeness, card | all | ✅ | ✅ | ✅ (100% lines) |

### 10. Migration Plan Items

| ID | Status | Phase | Item | Details |
|---|---|---|---|---|
| M0.1 | ✅ PASS | Phase 0 | name vectors + fullmatch | see F4.1 |
| M0.2 | ✅ PASS | Phase 0 | locked CI + lint-imports/pyright/pip-audit | ci.yml:36-39,90-93 |
| M0.3 | ✅ PASS | Phase 0 | gitleaks in CI + npm audit | ci.yml:26-30,58 |
| M0.4 | ✅ PASS | Phase 0 | tsconfig strictest or noUncheckedIndexedAccess | second option taken |
| M0.5 | ⏭️ SKIPPED | Phase 0 | justify bare suppressions + typed settings() factory | Not in scope: FIX_PLAN marks it 🔵 (not a fix unit; linter recommended after reasons are added). 16 suppressions still lack a reason; no factory |
| M0.6 | ✅ PASS | Phase 0 | beforeEach clear + env to warmUp | mlflow.test.ts:6,10 |
| M0.7 | ✅ PASS | Phase 0 | ~= bounds, pin template dev deps, .python-version | ~= bounds ✅, .python-version ✅, template dev deps exact-pinned ✅ (healed 2026-11-05; see F5.2) |
| M1.1 | ✅ PASS | Phase 1 | local results before MLflow; cap retries | run.py sink + tracking.py `_bound_http_retries` (2/30s) + tests |
| M1.2 | ✅ PASS | Phase 1 | corpus hash in index_name + params | see F6.2; params test |
| M1.3 | ✅ PASS | Phase 1 | GenerationError on bad 200 / max_tokens | see F6.3/F6.4 |
| M1.4 | ✅ PASS | Phase 1 | fail fast: empty chunks, k<1, HttpUrl URIs | ✅ Healed 2026-11-05: empty chunks ✅ and k<1 ✅. Both URL validators now use `re.fullmatch(r"[A-Za-z][A-Za-z0-9+.-]*://\S+", v)`. It rejects `http://`, `://`, `garbage://` and anything with whitespace, and still accepts `sqlite:////abs`, `sqlite:///rel.db`, `postgresql://`, `mysql://` and `http(s)://host`. Both trees gained negative and positive tables |
| M1.5 | ✅ PASS | Phase 1 | zod MLflow + config.ts | see F1.1/F1.2 |
| M1.6 | ✅ PASS | Phase 1 | run() params in dataclass | RunConfig |
| M1.7 | ✅ PASS | Phase 1 | fill §4 gaps (Hypothesis) | Enumeration replaces Hypothesis (no new dep) ✅; the `numbers_equal` gap was healed 2026-11-05 (F4.3) |
| M2.1 | ⏭️ DEFERRED | Phase 2 | lock/build-then-alias for shared collections | #12 |
| M2.2 | ⏭️ SKIPPED | Phase 2 | Optional: split connect_weaviate / mlflow transport | Marked Optional in REVIEW; out of FIX_PLAN scope (transport already split; connect_weaviate still in settings.py) |
| M2.3 | ⏭️ DEFERRED | Phase 2 | pyright strict on src/ | #14 |
| M3.1 | ✅ PASS | Phase 3 | pre-push hook runs each tree's tests | gates-datalab/mini-rag/app + default_install_hook_types |
| M3.2 | ✅ PASS | Phase 3 | template carries the full gate block | ruff extend (inherits root `S` via ruff.toml select), pytest markers/addopts, coverage 70, pyright, pip-audit. import-linter excluded by validated plan (empty contract fails `lint-imports`) |
| M3.3 | ⏭️ SKIPPED | Phase 3 | re-run /review-architecture after next project | Future trigger; only mini-rag exists — not applicable yet |

### 11. Security Confidence Challenge

| Finding | Fix Applied | Challenge Question | Answer | Confidence |
|---|---|---|---|---|
| F4.1 name bypass | `NAME_RE.fullmatch` + shared vectors | Unicode or line-terminator tricks? | The `[a-z0-9]` classes are explicit ASCII ranges. `\n`, `\r` and `\r\n` are now rejected by both the Python and JS twins through the shared vectors | ✅ High |
| F7.1 secrets scan | full-history `gitleaks git` in CI | Can the scanner itself be tampered with? | The release tarball is fetched over HTTPS at a pinned version, but **its checksum is not verified** | ⚠️ Medium |
| F7.4 dep audit | pip-audit per tree + `npm audit --audit-level=moderate` | Are all trees covered? | datalab and mini-rag yes. `tools/weavit-ui` (the fork) is excluded and tracked as #10 | ✅ High |
| M1.4 URL validation | Scheme-grammar fullmatch with a non-empty, whitespace-free remainder (healed) | Does malformed input still pass? | `http://`, `://`, `garbage://`, `x ://y` and `http:// host` are now rejected. A valid but unreachable host still fails loudly at first connect | ✅ High |
| F6.1 crash copy | per-answer JSONL append | Is the path user-controllable? | No: `run_id` comes from MLflow (hex), and `results_dir` is fixed to the project root. A kill can truncate the last line only | ✅ High |

## Remaining Gaps (for /heal-review)

All three gaps below were **healed on 2026-11-05** by `/heal-review` (uncommitted on `fix/review-2026-11-04`). Tooling gap still open: `bandit` / `radon` not installed (see §9) — a dev-dependency decision for the user.

### Gap 1 — ✅ RESOLVED (2026-11-05): `numbers_equal` has no direct test
- **Category:** Testing Quality (F4.3, M1.7)
- **Original finding:** scoring helpers are covered only through `outcome()`. `numbers_equal` is named in the finding.
- **Current state:** parse_number, normalize and contains_phrase have tables. `numbers_equal` is covered only by one `outcome("1,200","1200")` case.
- **Remaining work:** add a `@pytest.mark.parametrize` table for `numbers_equal` covering equal, within `rel_tol`/`abs_tol`, just outside tolerance, and None on either side, with hand-worked expected values. Tests only.
- **Files affected:** `projects/mini-rag/tests/test_scoring.py`

### Gap 2 — ✅ RESOLVED (2026-11-05): template dev deps unpinned, and `datalab-new` doesn't lock
- **Category:** Documentation & Cognitive Debt (F5.2, M0.7)
- **Original finding:** "Pin + ship `.python-version`; have `datalab-new` run `uv lock`".
- **Current state:** `.python-version` 3.12 and the full dev list ship. Only `ruff==0.17.3` is pinned, and a new project gets no `uv.lock`.
- **Remaining work:** either pin the template dev deps (`==`, mirroring mini-rag's lock) or have `datalab-new` run `uv lock` after copying, with a test in `test_new_project.py`. Needs a decision: running `uv lock` inside `datalab-new` adds a subprocess and network dependency to scaffolding.
- **Files affected:** `templates/project/pyproject.toml`, `packages/datalab/src/datalab/new_project.py`, `packages/datalab/tests/test_new_project.py`

### Gap 3 — ✅ RESOLVED (2026-11-05): URL validators are weaker than `HttpUrl`
- **Category:** Migration Plan (M1.4)
- **Original finding:** fail fast with `HttpUrl` for the DGX and MLflow URIs.
- **Current state:** `"://" in v` (FIX_PLAN chose this so `sqlite:///` and `postgresql://` stay valid). It accepts `http://`, `://` and `garbage://`.
- **Remaining work:** require a non-empty scheme of `[a-z][a-z0-9+.-]*` before `://` and something after it (for example `re.fullmatch(r"[a-z][a-z0-9+.-]*://.+", v)`). Keep `sqlite:////abs` valid. Add negative tests for `http://`, `://` and `garbage` and a positive test for sqlite.
- **Files affected:** `projects/mini-rag/src/mini_rag/settings.py`, `packages/datalab/src/datalab/settings.py`, their `test_settings.py` files

## Deferred Items (not in scope for /heal-review)

| Item | Tracker | Reason for Deferral |
|---|---|---|
| F6.6 / M2.1 — serialize index builds across concurrent runs | #12 | User decision 2026-11-04 (solo lab); race narrowed by Phase 1.3 |
| F7.5 — formatter + linter for app/ (the format/lint half; the hook half is done) | #13 | Adds 2+ dev deps and a style decision |
| F2.2 / M2.3 — pyright `strict` on src/ (the strict half; the never-run half is done) | #14 | REVIEW lists it as a Phase-2 architectural item |

