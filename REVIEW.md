# Architecture Review — data-lab

**Date:** 2026-11-04
**Last healed:** 2026-11-05 — 3/3 gaps resolved (F4.3/M1.7 numbers_equal table; F5.2/M0.7 pinned template dev deps + `datalab-new` runs `uv lock`; M1.4 scheme-grammar URL validators)
**Project type:** Python (generic, no FastAPI) — `packages/datalab`, `projects/mini-rag`, `templates/project`, root `tests/` + `tools/`; Astro 7 / TypeScript static app — `app/`. Out of scope: `tools/weavit-ui/` (vendored git submodule).
**Models:** `sonnet` (dimension agents 1–5), resilience-auditor, `/audit-ci --report-only`; orchestrator re-verified every 🔴/🟡 and every contested row.

## Executive Summary

| Category | Conformance | Critical | Warnings | Info |
|----------|------------|----------|----------|------|
| Architecture & SoC | High | 0 | 2 | 4 |
| Typing & Style | Medium | 0 | 3 | 3 |
| State & Enums | High | 0 | 0 | 4 |
| Testing | Medium | 0 | 14 | 6 |
| Documentation & Debt | High | 0 | 2 | 4 |
| Resilience & Failure Modes | Medium | 1 | 6 | 5 |
| CI Gate Surface | Medium | 0 | 5 | 4 |
| Simpro Cloud & AI | N/A (no `score.yaml`) | — | — | — |

Overall: a small (~2.5 k lines), well-layered, well-documented codebase. Layering contracts hold, no file > 200 lines, ARCHITECTURE.md is accurate, lockfiles are committed. The real gaps are **gates that are declared but never run** (import-linter, pyright, pip-audit, gitleaks in CI) and a few **silent-wrong-result paths** in the pilot.

### Top Critical Findings
1. **Run results live only in memory until the end of `run()`** — an MLflow outage (or kill) at `log_metrics`/`log_dict` loses every DGX answer of the run; MLflow's default 7×120 s retry policy can block ~15–20 min first (`projects/mini-rag/src/mini_rag/run.py:82-87`). 🔴
2. **Declared gates are never executed** — the two `[tool.importlinter]` contracts (`datalab.project` pure, `mini_rag.scoring` pure), pyright, `pip-audit` and `npm audit` appear in config/dev-deps but in no hook and no CI step (`grep lint-imports|pyright|pip-audit|npm audit .github .pre-commit-config.yaml` → 0 hits). False confidence: ARCHITECTURE.md cites those contracts as guarantees.
3. **gitleaks is a no-op in CI** — the hook scans `--staged`; `pre-commit run --all-files` on a fresh checkout has nothing staged. Secrets are enforced locally only.
4. **Stale index silently reused after a corpus edit** — the collection name hashes only embedder/size/overlap and reuse is `count == len(chunks)`; an edit that keeps the chunk count reuses old vectors and logs a FINISHED run with wrong metrics (`index.py:34-38,70-73`). Mitigated today only by the "frozen corpus" convention.
5. **Shared name contract diverges Python ↔ JS on a trailing newline** — `NAME_RE.match("mini-rag\n")` matches (Python `$`), the JS twin rejects; reproduced: `validate_name("mini-rag\n") → 'mini-rag\n'`, `experiment_name("mini-rag\n") → 'mini-rag\n'`. `contracts/name_vectors.json` has no such vector.

## Detailed Findings

### 1. Architecture & Separation of Concerns

| Severity | Finding | File(s) | Rule Violated | Recommendation |
|----------|---------|---------|---------------|----------------|
| 🟡 Warning | MLflow REST responses validated by hand-rolled guards, not zod: `const isObject = (v: unknown): v is Record<string, unknown> =>` (l.34), `typeof e.experiment_id !== 'string'` (l.47), `typeof info.run_id !== 'string'` (l.58); `MlflowRun`/`MlflowExperiment` are hand-written types while `card.ts` uses `astro/zod` | `app/src/lib/mlflow-rest.ts:34,47,58` | zod at boundaries, types via `z.infer` | zod schemas for experiment/run/metric; `safeParse` + `z.infer` |
| 🟡 Warning | Env read in 4 modules with no single config module: `base: process.env.DATALAB_PROJECTS_DIR ?? '../projects'`, `exportGuard(env: Env = process.env)`, `const linked = import.meta.env.DEV;`, `const dev = import.meta.env.DEV;` (plus `mlflowUri` in mlflow.ts) | `app/src/content.config.ts:9`, `app/src/integrations/export-guard.ts:15`, `app/src/components/Metric.astro:10`, `app/src/layouts/Base.astro:8`, `app/src/lib/mlflow.ts:22` | env access centralized | `src/lib/config.ts` as the single reader; keep the injectable `env` params |
| 🔵 Info | `mlflow-rest.ts` mixes transport (timeout, `TransientError`, retry class) with shape validation; `mlflow.ts` mixes env, warm-up polling, run picking and `metricState` | `app/src/lib/mlflow-rest.ts`, `app/src/lib/mlflow.ts` | pure logic separated from I/O | When adding zod, split transport vs pure `pickRun`/`metricState` |
| 🔵 Info | `datalab.settings` holds both `BaseSettings` and the I/O factory `connect_weaviate` (module-level `import weaviate`), so `datalab.tracking` pulls weaviate in transitively | `packages/datalab/src/datalab/settings.py:6,8,22` | config separated from I/O clients | Optional: move `connect_weaviate` to `datalab/weaviate.py` + a forbidden-import contract |
| 🔵 Info | `run()` calls `mlflow.log_params/log_metrics/log_dict` on the global active run; `answer`/`search` are injected (good) | `projects/mini-rag/src/mini_rag/run.py:83-86` | DI over module-level clients | Acceptable for a CLI pilot; inject a small logger if tests need it |
| 🔵 Info | Otherwise clean: `scoring.py` and `project.py` stdlib/yaml-only (contracts hold), settings via `BaseSettings` with env prefixes, no `os.environ` in Python, no cycles, Astro pages ≤ 32 lines | — | — | — |

### 2. Typing & Style

| Severity | Finding | File(s) | Rule Violated | Recommendation |
|----------|---------|---------|---------------|----------------|
| 🟡 Warning | `def run(project, settings, pilot, questions, *, retrieval, k, n, size, overlap, collection, answer, search) -> str:` — 12 parameters (only function > 5 in an AST scan of 35 files) | `projects/mini-rag/src/mini_rag/run.py:60-74` | max 5 function args | Group into frozen dataclasses (`ChunkingParams`, `RetrievalParams`, `Backends`) |
| 🟡 Warning | pyright `typeCheckingMode = "basic"` everywhere, and pyright is never executed by any gate (see §7); code already fully annotated, so strict is likely cheap | `pyrightconfig.json:3`, `packages/datalab/pyproject.toml:64`, `projects/mini-rag/pyproject.toml:75` | typing rigor | Wire pyright into pre-commit/CI; try `strict` on `src/` |
| 🟡 Warning | `"extends": "astro/tsconfigs/strict"` — that preset lacks `noUncheckedIndexedAccess` (only `strictest` sets it); records are indexed (`res[key]`, mlflow-rest.ts:41) | `app/tsconfig.json:2` | tsconfig strict + `noUncheckedIndexedAccess` | Extend `astro/tsconfigs/strictest` or add the flag |
| 🔵 Info | Unchecked casts in catch blocks: `(err as Error).message`, `(err as { name?: unknown }).name` | `app/src/lib/mlflow.ts:140`, `app/src/lib/mlflow-rest.ts:25,27` | no unchecked assertions | `err instanceof Error ? err.message : String(err)` |
| 🔵 Info | `print()` only in CLI entrypoints (`new_project.py:49,54,63,65` stderr/stdout; `run.py:114` summary) — acceptable | `packages/datalab/src/datalab/new_project.py`, `projects/mini-rag/src/mini_rag/run.py:114` | no print in library code | Move `run.py:114` into `main()` if `run()` becomes a library call |
| 🔵 Info | Zero hits for bare/`Exception` catches, wildcard/relative imports, `.format`/`%`, `== None`, untyped defs, `Any`, TS `any`/`@ts-ignore`/`require(`. (Agent 2 also reported "no `type: ignore`" — wrong, see §5.) | — | — | — |

### 3. State Management & Enums

| Severity | Finding | File(s) | Rule Violated | Recommendation |
|----------|---------|---------|---------------|----------------|
| 🔵 Info | Goal values compared as raw literals `metric.goal === 'max'`; inline `z.enum(['max','min'])`, no exported `GOALS as const` / `Goal` type (zod already narrows) | `app/src/lib/card.ts:12`, `app/src/lib/mlflow.ts:68,102` | fixed sets as typed unions | Export `GOALS` + `type Goal`; optional `Record<Goal, …>` for sign/order |
| 🔵 Info | `b.type == "text"` on an Anthropic SDK content block — external discriminator, acceptable | `projects/mini-rag/src/mini_rag/generate.py:70` | raw string comparison (borderline) | Optional `isinstance(b, TextBlock)` |
| 🔵 Info | Good: `Retrieval`/`Outcome` are `StrEnum` (`mode is Retrieval.BM25`, argparse `choices=list(Retrieval)`); `STATUSES as const` + `Record<Status, …>`; `MetricState` discriminated union; no TS `enum` | `projects/mini-rag/src/mini_rag/index.py:27`, `scoring.py:39`, `app/src/lib/card.ts:4`, `app/src/lib/completeness.ts` | — | — |
| 🔵 Info | Card `status` lifecycle is documented but has no in-code transition map; transitions are manual YAML edits, so no runtime transition exists to guard | `ARCHITECTURE.md:180-191`, `app/src/lib/completeness.ts` | FSM rule (N/A) | None unless transition validation is wanted |

### 4. Testing Quality

**Test-quality scorecard** (`test_quality_audit.py`, run per sub-root; percentages of active, non-skipped unit tests)

| Sub-project | Language | Test files | Tests | No-assertion % | Existence-only % | Interaction-only % | Skipped | Env-gated/e2e |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| app | ts | 5 | 44 | 0% | 0% | 0% | 0 | 0 |
| packages/datalab | python | 5 | 40 | 0% | 0% | 0% | 0 | 0 |
| projects/mini-rag | python | 8 | 37 | 0% | 0% | 0% | 0 | 1 |
| tests (root) | python | 1 | 1 | 0% | 0% | 0% | 0 | 0 |

Mechanical findings: 0 in all four roots. Id-literal cross-check (ports, tracking URI, experiment names, embedder tag, model default) against compose.yaml/.env.example/settings: no stale literal.

| Severity | Finding | File(s) | Rule Violated | Recommendation |
|----------|---------|---------|---------------|----------------|
| 🟡 Warning | Trailing newline accepted by Python, rejected by JS: `NAME_RE: Final = re.compile(r"^[a-z][a-z0-9]*(-[a-z0-9]+)*$")` with `.match` → `validate_name("mini-rag\n")` returns `'mini-rag\n'` (reproduced); `name_vectors.json` has no such vector, so both F-12 tests pass. Agent rated 🔴; downgraded — card loading is protected by `name == folder.name`, exposure is `datalab-new`/direct API calls | `packages/datalab/src/datalab/project.py:13,35,101,122`; `contracts/name_vectors.json`; `packages/datalab/tests/test_project.py:23` | MISSING BEHAVIOUR; TQ9 | Add `"a\n"`, `"mini-rag\n"`, `"a\r"` to `reject` first (red), then `fullmatch` |
| 🟡 Warning | `collection_name` hash is a persistent key but never pinned: tests only assert inequality + charset; `_check_name_shape` rejection and `experiment_name` bad-project untested | `packages/datalab/src/datalab/project.py:99-111`; `test_project.py:34-45` | MISSING BEHAVIOUR; TQ8 | One labelled golden value + determinism test + bad-project tests |
| ✅ Resolved (was 🟡 Warning) | `parse_number` / `normalize` / `contains_phrase` / `numbers_equal` covered only via `outcome()` with a few examples (`"1,200"` vs `"1200"`); no multiplier, unknown-unit, NFKC, empty-needle cases | `projects/mini-rag/src/mini_rag/scoring.py:62-100`; `tests/test_scoring.py` | TQ9; MISSING BEHAVIOUR | Parametrized tables + Hypothesis (idempotent `normalize`, symmetric `numbers_equal`) |
| 🟡 Warning | `metrics()` has one 6/2/2 example; no invariants (rates sum to 1, score ∈ [-1,1]) | `tests/test_scoring.py:34-42`; `scoring.py:111-125` | TQ9 | Property test over `lists(sampled_from(Outcome), min_size=1)` |
| 🟡 Warning | `main()` / `_args` untested: `--retrieval` choices, `--n`/`--k`, "config validated before any I/O (F-13)" | `projects/mini-rag/src/mini_rag/run.py:89-118`; `tests/test_run.py` | MISSING BEHAVIOUR | `main([...bogus])` → `SystemExit`; settings failure before I/O |
| 🟡 Warning | Partial assertions on run logging: only `retrieval`/`collection` params checked; artifact checked via `assert '"q4"' in text` / `assert '"hallucination"' in text`; `config_hash` not shown to vary with k/model/size | `projects/mini-rag/tests/test_run.py:56-72,99,117-121` | TQ3 partial assertions | Parse the JSON, assert per-question equality; vary hash inputs |
| 🟡 Warning | `index.search()` (BM25 + near_text) has no unit test — only the deselected integration test; the `failed_objects` warning branch is never reached (fake always `[]`) | `projects/mini-rag/src/mini_rag/index.py:55-58,83-92`; `tests/test_index.py:60-72` | MISSING BEHAVIOUR | Fake `collection.query`; add a failed-objects case |
| 🟡 Warning | Change detector on an unowned type: `fake.calls == [("delete", name), ("create", name), ("delete", name), ("create", name)]` against a hand-built Weaviate fake | `projects/mini-rag/tests/test_index.py:104,112` | TQ3; TQ4 | Assert outcome (name / `IndexBuildError`) + rebuild count only |
| 🟡 Warning | `monkeypatch.setattr(new_project, "_rewrite", broken)` patches a private helper of the unit under test; leftover-placeholder `ProjectError` and binary-file skip untested | `packages/datalab/tests/test_new_project.py:76-84`; `new_project.py:21-37` | TQ4; MISSING BEHAVIOUR | Trigger with a real condition (stray placeholder template) |
| 🟡 Warning | `load_corpus` "no *.md file" error untested; chunk boundaries (n = size, overlap = 0, empty doc, CRLF) absent; selector `"w150" in c.text.split() or "Section A" in c.text or …` hard to read | `projects/mini-rag/src/mini_rag/corpus.py:31-58`; `tests/test_corpus.py:11-24` | MISSING BEHAVIOUR; TQ9; TQ5 | Boundary table + coverage property; empty-folder test |
| 🟡 Warning | `completeness.ts`: status `abandonné` never tested, nor `~~~` fences, unterminated `<!--`, NFC heading normalisation | `app/src/lib/completeness.ts:13-35`; `completeness.test.ts` | MISSING BEHAVIOUR; TQ9 | Table-driven cases; fuzz `sections()` |
| 🟡 Warning | `mlflow.ts`/`mlflow-rest.ts` error paths untested: second failure after retry, `warmUps` memoisation, `poll` until deadline, `parseRuns` fallbacks, `METRIC_KEY_RE` other bad chars; `test('shape check')` holds two scenarios | `app/src/lib/mlflow.ts:33-48,66-80,122-140`; `mlflow-rest.ts:40-65`; `mlflow.test.ts:184` | MISSING BEHAVIOUR; TQ5 | Add cases; split into spec-named tests |
| 🟡 Warning | Build report stored on `globalThis`; only two tests call `readReport().clear()`; `'F-1: warmUp never rejects'` polls the real default `mlflowUri` | `app/src/lib/report.ts`; `app/src/lib/mlflow.test.ts:111-118,156-159` | SHARED STATE (TQ2) | `beforeEach(() => readReport().clear())`; pass `env` to `warmUp` |
| 🟡 Warning | Port parity checked only for the root `.env.example`; `templates/project/.env.example` (inherited by new projects) and `projects/mini-rag/.env.example` unchecked | `packages/datalab/tests/test_settings.py:57-79` | MISSING BEHAVIOUR | Parity test over all three copies |
| 🔵 Info | Duplicate compose-port coverage (`test_f_4_compose_maps_distinct_host_ports` and the compose half of `test_g_10`); g_10 skips after half its asserts ran | `tests/test_compose.py:25-54`; `packages/datalab/tests/test_settings.py:57-79` | TQ7; TQ5 | Keep one compose test; split env parity from the docker-gated part |
| 🔵 Info | `test_f_3_cleanup_deletes_only_created_names` tests a helper defined in the test file | `packages/datalab/tests/test_integration.py:50-57` | TQ7 | Label as a test-safety check |
| 🔵 Info | Oracle read from source: expects `PilotSettings.model_fields["gen_model"].default` | `projects/mini-rag/tests/test_settings.py:11-14` | TQ1 (weak) | Pin `deepseek-v4-flash` if contractual |
| 🔵 Info | Invisible NFD literal `'idée'` (e + U+0301) — correct but editor-fragile | `app/src/lib/card.test.ts:17-20` | TQ5 | Write as `'idée'` |
| 🔵 Info | Vague names (`'goal min'`, `'shape check'`, `'pickBest returns the picked run'`); data-guard tests (`len(questions) == 20`) unlabelled | `app/src/lib/mlflow.test.ts:55,60,184`; `projects/mini-rag/tests/test_questions.py:19-28` | TQ8; TQ7 | Spec-style names; label data guards |
| 🔵 Info | CRLF/BOM frontmatter covered in Python (`test_f_11`) and by CI build fixtures, but not by a TS unit test | `app/test-fixtures/`; `app/src/content.config.ts:7` | MISSING BEHAVIOUR (TS) | Add a TS unit test if TS parses it |

Calibration (script vs judgment): none — the script's 0 % rows agree with the reading; the gaps above are categories the script cannot see.

### 5. Documentation & Cognitive Debt

| Severity | Finding | File(s) | Rule Violated | Recommendation |
|----------|---------|---------|---------------|----------------|
| 🟡 Warning | Unbounded `>=` runtime deps: `"pydantic-settings>=2.6"`, `"pyyaml>=6.0"`, `"httpx>=0.27"` (datalab); `"pydantic-settings>=2.6"` (mini-rag); dev groups likewise (uv.lock mitigates) | `packages/datalab/pyproject.toml:7-11,19-24`; `projects/mini-rag/pyproject.toml:13,18-24` | dependency hygiene: floating versions | `~=` or exact pins, as already done for weaviate-client/mlflow/ruff |
| ✅ Resolved (was 🟡 Warning) | Template ships `dev = ["pytest>=8"]` and no lock/`.python-version` (IMPLEMENTATION_NOTES: uv then picks Python 3.14 locally while CI is 3.12) | `templates/project/pyproject.toml:5,9` | dependency hygiene (template) | Pin + ship `.python-version`; have `datalab-new` run `uv lock` |
| 🔵 Info | Bare `# type: ignore[...]` without reason, e.g. `PilotSettings(_env_file=None)  # type: ignore[call-arg]`, `tomllib = None  # type: ignore[assignment]` (others carry a reason) | `projects/mini-rag/tests/test_settings.py:28`; `projects/mini-rag/tests/test_run.py:34,35`; `projects/mini-rag/tests/test_integration.py:19`; `packages/datalab/tests/test_integration.py:103`; `tools/pre_commit_checks/_layout.py:35,61,95`; `tools/pre_commit_checks/check_declared_dependencies.py:33,40` | suppression without justification | Add reasons; a typed `settings()` factory in conftest removes most |
| 🔵 Info | `# noqa: S603` without justification on 3 test subprocess calls | `packages/datalab/tests/test_new_project.py:119`; `packages/datalab/tests/test_settings.py:27`; `tests/test_compose.py:28` | suppression without justification | `# noqa: S603  # fixed argv, no user input` |
| 🔵 Info | `api_key="not-needed",  # placeholder: the LAN DGX is unauthenticated` — documented placeholder, not a secret | `projects/mini-rag/src/mini_rag/generate.py:52` | hardcoded `api_key=` (accepted) | None |
| 🔵 Info | Clean: ARCHITECTURE.md has all 7 sections and matches code/versions; decisions.md in ADR format; no file > 200 lines; no utils catch-alls, TODO/FIXME, `shell=True`, `yaml.load`; `datalab-new` validates the name before building paths; all compose ports on 127.0.0.1; lockfiles committed; package.json exact pins | — | — | — |

### 6. Resilience & Failure Modes

| Severity | Finding | File(s) | Dimension | Status | Already tested? | Proposed test |
|----------|---------|---------|-----------|--------|-----------------|---------------|
| 🔴 Critical | Results held in memory until after `_answer_all`; `log_metrics`/`log_dict` failure (or kill) loses all DGX answers; MLflow default retries (7 × 120 s, backoff 2) block ~15–20 min; `end_run(FAILED)` hits the same outage → run stuck `RUNNING` (app filters `FINISHED`, so dashboard stays correct) | `projects/mini-rag/src/mini_rag/run.py:82-87`; `packages/datalab/src/datalab/tracking.py:52-54` | 4 partial failure / 1 I/O | CONFIRMED (code + retry config); duration inferred | No | `test_f_13_mlflow_failure_after_answers_keeps_results_locally` — monkeypatch `mlflow.log_metrics` to raise; assert a local per-question file holds every answer |
| 🟡 Warning | Stale index reused after a corpus edit: name hashes embedder/size/overlap only, reuse = `_count(...) == len(chunks)`; no corpus hash in params | `projects/mini-rag/src/mini_rag/index.py:34-38,70-73`; `run.py:78-80` | 7 state / contract drift | CONFIRMED | No | `test_corpus_content_change_with_same_count_rebuilds`; assert `corpus_hash` in params |
| 🟡 Warning | 200 with non-JSON or list body → raw `AttributeError` (`'str' object has no attribute 'content'`), not `GenerationError` | `projects/mini-rag/src/mini_rag/generate.py:59-70` | 1 / 10 | CONFIRMED (probe) | Partly | `MockTransport` → `Response(200, content=b"<html>")` / `json=[1,2]` → `pytest.raises(GenerationError)` |
| 🟡 Warning | `stop_reason` never checked: a `max_tokens` cut-off (likely with thinking + `max_tokens=512`) is scored as a complete answer | `projects/mini-rag/src/mini_rag/generate.py:70-73` | 1 partial response / 7 | CONFIRMED (code) | No | `stop_reason: "max_tokens"` → `GenerationError` (or flagged result — spec decides) |
| 🟡 Warning | All-empty corpus → `chunks == []`, `count 0 == len 0` treated as complete, FINISHED run with `missing=1.0` | `projects/mini-rag/src/mini_rag/corpus.py:51-58`; `index.py:71` | 7 empty set / 5 | CONFIRMED (code) | No | whitespace-only `a.md` → `pytest.raises(ValueError)` |
| 🟡 Warning | Concurrent runs race on delete → create → batch of a shared collection (no lock) | `projects/mini-rag/src/mini_rag/index.py:45-48,70-80` | 3 concurrency | SUSPECTED | No | Interleaved fake caller; integration two-process test |
| 🟡 Warning | `--k` unbounded; `k=0` → proto `limit=0` likely falls back to `QUERY_DEFAULTS_LIMIT=25` while `k=0` is logged | `projects/mini-rag/src/mini_rag/run.py:93`; `index.py:86-88` | 5 input | SUSPECTED | No | `_args([... "--k","0"])` → `SystemExit` |
| 🔵 Info | MLflow preflight: `/health` has 5 s timeout but `search_experiments` inherits the long retry policy | `packages/datalab/src/datalab/tracking.py:31-34` | 1 timeout | CONFIRMED (config) | No | Assert preflight caps `MLFLOW_HTTP_REQUEST_MAX_RETRIES`/`TIMEOUT` |
| 🔵 Info | No DGX preflight; `dgx_base_url: str` unvalidated (scheme-less URL → `Connection error` after index build + run opened) | `projects/mini-rag/src/mini_rag/settings.py:10`; `run.py:103-112` | 5 config / 1 | CONFIRMED (probe) | Missing-URL only | `PilotSettings(dgx_base_url="dgx.lan:8000")` → `ValidationError` (`HttpUrl`) |
| 🔵 Info | Scheme-less `DATALAB_MLFLOW_TRACKING_URI` gives a misleading "maintenance mode" filesystem-backend error | `packages/datalab/src/datalab/tracking.py:26-34`; `settings.py:18` | 5 / 10 | CONFIRMED / SUSPECTED | No | `Settings` with `127.0.0.1:5050` → `ValidationError` |
| 🔵 Info | `IndexBuildError` drops the batch failure reason (only logged as warning) | `projects/mini-rag/src/mini_rag/index.py:61-63,80` | 10 observability | CONFIRMED | No | `pytest.raises(IndexBuildError, match="t2v unreachable")` |
| 🔵 Info | Ctrl-C between `copytree` and `rename` leaves `projects/.<name>.tmp-*` (only `OSError`/`ProjectError` cleaned) | `packages/datalab/src/datalab/new_project.py:56-63` | 4 crash recovery | CONFIRMED | Partly (F-8) | `_rewrite` raising `KeyboardInterrupt` → no tmp dir left (`try/finally`) |

### 7. CI Gate Surface

Full matrix: [`CI_REVIEW_2026-11-04.md`](CI_REVIEW_2026-11-04.md). Script core verdict exit 0 **but blind to the three Python trees** (manifests at depth 2); they were audited by hand — core gates (pre-commit, unfiltered `ci.yml`, `fail_under = 70` with `--cov`) are present. No wholly ungated tree.

| Severity | Finding | File(s) | Rule Violated | Recommendation |
|----------|---------|---------|---------------|----------------|
| 🟡 Warning | gitleaks no-op in CI: hook runs `gitleaks git --pre-commit --staged`; `uvx pre-commit run --all-files` on a fresh checkout has nothing staged | `.pre-commit-config.yaml` (gitleaks), `.github/workflows/ci.yml` (`checks`) | secrets gate local↔CI parity | Add `gitleaks detect --source . --log-opts=HEAD` (or gitleaks-action) to CI |
| 🟡 Warning | import-linter contracts declared but never run: 0 hits for `lint-imports` in ci.yml / pre-commit | `packages/datalab/pyproject.toml` `[tool.importlinter]`, `projects/mini-rag/pyproject.toml` `[tool.importlinter]` | declared contract unenforced | `uv run lint-imports` in each Python CI job + pre-commit |
| 🟡 Warning | pyright never executed (dev dep + config only) | `pyrightconfig.json`, both pyprojects | lint+type gate | `uv run pyright` in CI + hook |
| 🟡 Warning | No dependency audit anywhere: `pip-audit` in dev deps but never run; no `npm audit` | `.github/workflows/ci.yml` | dep-audit gate | `uv run pip-audit` per tree; `npm audit --audit-level=moderate` in `app` |
| 🟡 Warning | `app/` has no format/lint/SAST and no local hook (ruff excludes it; no node hooks) — `astro check` + tests run in CI only | `app/`, `.pre-commit-config.yaml` | format · lint · local parity | Add a pre-commit/pre-push `npm run check && npm test` and a formatter |
| 🔵 Info | Tests run in CI only; `ci.yml` header claims "the same checks as the local pre-commit/pre-push hooks" but no pre-push hook exists | `.github/workflows/ci.yml:1` | local↔CI parity | Add pre-push `pytest` hooks or fix the comment |
| 🔵 Info | CI uses `uv sync` without `--locked` (hooks use `--locked`) — lock drift is rewritten silently in CI | `.github/workflows/ci.yml` (`checks`, `pilot`) | lockfile discipline | `uv sync --locked` |
| 🔵 Info | Template dev group is pytest-only: generated projects start without coverage floor, pyright, pip-audit, import-linter | `templates/project/pyproject.toml` | gate inheritance | Carry mini-rag's coverage/pyright/audit block into the template |
| 🔵 Info | `tools/pre_commit_checks/check_declared_dependencies.py` customised vs recipe v1 — review manually, don't auto-overwrite | `tools/pre_commit_checks/` | linter freshness | Manual diff on next recipe bump |

## Migration Plan

### Phase 0 — Quick Wins (mechanical, low risk)
- [ ] Add `"a\n"`, `"mini-rag\n"`, `"a\r"` to `contracts/name_vectors.json` reject list (red), then `NAME_RE.fullmatch` in `project.py` (3 call sites)
- [ ] `uv sync --locked` in CI; add `uv run lint-imports`, `uv run pyright`, `uv run pip-audit` to the `checks` and `pilot` jobs
- [ ] Add `gitleaks detect` step to CI; `npm audit --audit-level=moderate` to the `app` job
- [ ] `app/tsconfig.json` → `astro/tsconfigs/strictest` (or `noUncheckedIndexedAccess`)
- [ ] Justify bare `# type: ignore` / `# noqa: S603`; add a typed `settings()` conftest factory
- [ ] `beforeEach(() => readReport().clear())` in `mlflow.test.ts`; pass `env` to `warmUp`
- [x] Bound `>=` deps (`~=`), pin template dev deps, ship `templates/project/.python-version`

### Phase 1 — Structural Improvements (medium effort)
- [ ] `run()`: write `per_question.json` locally before MLflow logging; cap MLflow retries/timeout for the run
- [ ] Add a corpus content hash to `index_name` and run params
- [ ] `DgxGenerator.answer`: `GenerationError` on non-JSON/list 200 and on `stop_reason == "max_tokens"`
- [x] Fail fast: empty chunk list, `--k < 1`, `HttpUrl` for DGX / MLflow URIs
- [ ] zod schemas for MLflow REST (`z.infer` types); `src/lib/config.ts` as single env reader
- [ ] Group `run()` params into dataclasses
- [x] Fill the §4 test gaps (scoring tables + Hypothesis properties, `main()`, `search()`, completeness, mlflow error paths, golden `collection_name`, env parity)

### Phase 2 — Architectural Changes (higher effort)
- [ ] Lock or build-then-alias for shared Weaviate collections (concurrent runs)
- [ ] Optional: split `connect_weaviate` out of `datalab.settings`; split `mlflow.ts` transport vs pure picking
- [ ] pyright `strict` on `src/`

### Phase 3 — Ongoing Discipline
- [ ] Pre-push hook running each tree's tests (matches the ci.yml claim)
- [ ] Template carries the full gate block so every new project inherits it
- [ ] Re-run `/review-architecture` after the next project lands under `projects/`

## Implementation-Notes Promotion (tier-3 flywheel)

Deviations the plan-time passes missed → sharpenings so they're caught proactively next time.

| Deviation (from IMPLEMENTATION_NOTES.md) | Recurs? | Promote to | Action |
|---|---|---|---|
| MLflow REST search needs explicit positive `max_results` | likely (2B app hit it too) | resilience-auditor | add "MLflow REST: explicit `max_results`, `ACTIVE_ONLY` default" to the external-API emphasis rows |
| uv picks newest managed Python unless `.python-version` | likely; still open in template | spec-gap-auditor + this review (Phase 0) | add "interpreter pin vs CI version" to the Python env checklist |
| Vendored layered-linter recipe needs `--directory <tree>` in a rootless repo | likely | `/scaffold-linter` recipe docs | document `--directory` + `--locked` invocation for multi-tree repos |
| `node --test` coverage counts test files; integer threshold | likely | `/audit-ci` + CI recipes | add `--test-coverage-exclude` to the node recipe; this is also why `ci_gate_inventory` exempts app (#9) |
| `astro dev` daemonizes in a non-TTY shell | likely | `run` skill / agent smoke-test notes | read PID from the log; `astro dev stop` |
| Fork pnpm gate fails under Node 22 / pnpm 11 | likely | — (fork-specific) | pin `packageManager` in the fork; out of scope here |
| Demo-RAG `GEN_MODEL` is an OpenRouter id | likely | spec-gap-auditor | "check provider before trusting a model id" when porting settings |
| Coverage floor in pytest `addopts` breaks `-m integration` | likely | template (Phase 3) | carry the `[tool.coverage.report] fail_under` split into `templates/project` |
| MLflow delete is soft; strict export leaves `dist/`; blank Host `''` | one-off | — | note; watch for recurrence |

Once promoted (or dismissed), `IMPLEMENTATION_NOTES.md` is archived with this cycle via `/plan-archive`, so each deviation is reviewed exactly once.

## Linter Candidates (3+ occurrences)

| Pattern | Files | Scaffold Command | Fix First |
|---------|-------|------------------|-----------|
| Suppression (`# type: ignore` / `# noqa`) without a reason | 9 | `/scaffold-linter justified-suppressions` (generic grep: suppression must be followed by `# <reason>`) | Phase 0 |

No other pattern reaches 3 files.

## Harness Gaps (a mechanical gate should have caught this)

The cheap pre-commit gate let these reach this review — close the gate, not just the finding.

| Finding | Gap type | Action |
|---------|----------|--------|
| import-linter contracts declared, never executed | unguarded surface (contract exists, no runner) | wire `lint-imports` into hooks + CI; `/audit-ci` should flag "contract declared but no runner" |
| gitleaks `--staged` hook is a no-op under `pre-commit run --all-files` in CI | existing-check miss (gate present, scans nothing) | dedicated CI gitleaks step; teach `/audit-ci` to detect `--staged` hooks used as the CI secrets gate |
| `ci_gate_inventory.py` detects manifests at depth 0–1 only → 3 Python trees absent from the core verdict | existing-check miss (inventory blind spot) | extend detection to depth 2 (`packages/*`, `projects/*`) + fixture reproducing this layout |
| Python↔JS name contract divergence (`$` vs trailing `\n`) | unguarded surface (shared vectors lack edge cases) | add newline/CR vectors; regex recipe rule: Python `fullmatch`/`\Z`, never `$` with `.match` |

**Workflow:** run `/plan-fix`, fix violations per phase, then close each harness gap (scaffold/repair the check + fixture) so the same class can't recur.
