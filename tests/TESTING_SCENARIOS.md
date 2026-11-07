# Testing Scenarios

> Living document maintained by `/implement-phase`. QA uses this to know what to test.

**Last updated:** 2026-11-04 (Phase 3)

## Shared infra

| ID | Scenario | Input | Expected Output | Status | Last Modified |
|----|----------|-------|-----------------|--------|---------------|
| INFRA-01 | Start the stack | `docker compose up -d` | weaviate, t2v-transformers, mlflow all `healthy` | 🆕 New | Phase 1 |
| INFRA-02 | Ports coexist with Demo-RAG | Demo-RAG on 5000/8080/50051 running | data-lab on 127.0.0.1:5050/8090/50052; Demo-RAG untouched | 🆕 New | Phase 1 |
| INFRA-03 | Loopback only | `docker compose config` | every published port has host_ip 127.0.0.1 (`tests/test_compose.py`) | 🆕 New | Phase 1 |
| INFRA-04 | Vectorizer loaded | `GET 127.0.0.1:8090/v1/meta` | modules lists `text2vec-transformers` | 🆕 New | Phase 1 |
| INFRA-05 | MLflow reachable | `POST /api/2.0/mlflow/experiments/search` with `{"max_results":10}` | HTTP 200 (an empty body gives 400: max_results required) | 🆕 New | Phase 1 |

## New project (`datalab-new`)

| ID | Scenario | Input | Expected Output | Status | Last Modified |
|----|----------|-------|-----------------|--------|---------------|
| NEW-01 | Create a project | `datalab-new demo --title "RAG: v2 # b"` | `projects/demo/` with PROJECT.md (title survives YAML), pyproject `name = "proj-demo"`; `uv sync` works | 🆕 New | Phase 2A |
| NEW-02 | Existing target | `projects/demo` exists (even empty dir/file) | exit 2, nothing written | 🆕 New | Phase 2A |
| NEW-03 | Bad / reserved / traversal name | `Bad`, `test`, `../escape` | exit 2, nothing written | 🆕 New | Phase 2A |
| NEW-04 | Package added after first sync | create `src/demo_pkg/` after `uv sync` | `import demo_pkg` works | 🆕 New | Phase 2A |

## Shared package (`datalab`)

| ID | Scenario | Input | Expected Output | Status | Last Modified |
|----|----------|-------|-----------------|--------|---------------|
| DL-01 | Tracked run | `tracked_run(project, settings, "r", sub="bm25")` | run in experiment `<name>/bm25`, tag `project=<name>`, FINISHED | 🆕 New | Phase 2A |
| DL-02 | Project tag override | `tags={"project": "x"}` | `ValueError` | 🆕 New | Phase 2A |
| DL-03 | Inherited MLFLOW_TRACKING_URI | env points at Demo-RAG :5000 | data-lab URI (5050) used | 🆕 New | Phase 2A |
| DL-04 | Card with BOM/CRLF | PROJECT.md saved on Windows | loads | 🆕 New | Phase 2A |
| DL-05 | MLflow down | `preflight` on unreachable URI | `TrackingUnavailable` | 🆕 New | Phase 2A |

## Presentation app (`app/`)

| ID | Scenario | Input | Expected Output | Status | Last Modified |
|----|----------|-------|-----------------|--------|---------------|
| APP-01 | Zero projects | `projects/` holds only `.gitkeep` | build OK, index shows the empty state | 🆕 New | Phase 2B |
| APP-02 | Card + best run | card with `metric: {key, goal}`, runs tagged `project=<name>` | best finite value shown (tie → latest start_time, then run_id) | 🆕 New | Phase 2B |
| APP-03 | Invalid card | `name` ≠ folder | build fails naming the file (D-13) | 🆕 New | Phase 2B |
| APP-04 | MLflow down | `npm run build` | cards show "Métriques indisponibles"; with `DATALAB_STRICT_EXPORT=1` the build fails | 🆕 New | Phase 2B |
| APP-05 | Static export links | `npm run build` | no 127.0.0.1/localhost in `dist/` (D-14); dev mode links to MLflow | 🆕 New | Phase 2B |
| APP-06 | Card saved on Windows | BOM + CRLF | parses, title renders | 🆕 New | Phase 2B |

## Weavit UI auto-connect (fork)

| ID | Scenario | Input | Expected Output | Status | Last Modified |
|----|----------|-------|-----------------|--------|---------------|
| WUI-01 | Eligible profile | local profile `data-lab`, 127.0.0.1, 8090/50052, stack up | connected on launch without a click | 🆕 New | Phase 2C |
| WUI-02 | Empty gRPC port | same profile, gRPC blank | no auto-connect, console `autoconnect skip: ports` | 🆕 New | Phase 2C |
| WUI-03 | Two `data-lab` profiles | duplicates | no auto-connect (`ambiguous`) | 🆕 New | Phase 2C |
| WUI-04 | Stack down | eligible profile, Weaviate stopped | normal UI with `error` status, no retry, no other profile | 🆕 New | Phase 2C |

## Pilot mini-rag

| ID | Scenario | Input | Expected Output | Status | Last Modified |
|----|----------|-------|-----------------|--------|---------------|
| PIL-01 | Full run | `--retrieval bm25 --k 3`, OpenRouter key set (or DGX up with `MINI_RAG_LLM_BASE_URL` + `MINI_RAG_GEN_MODEL`) | FINISHED run in `mini-rag/retrieval`, tag `project=mini-rag`, metrics accuracy/hallucination/score | 🆕 New | Phase 3 |
| PIL-02 | 4 configs | bm25/vector × k 3/5 | 4 runs; app card "score = …, Meilleur de 4 runs" | 🆕 New | Phase 3 |
| PIL-03 | LLM endpoint down | any config, endpoint unreachable | run FAILED, no metrics logged | 🆕 New | Phase 3 |
| PIL-06 | OpenRouter refuses | bad key (401), no credits (402), rate-limited (429) | run FAILED; the error carries OpenRouter's reason | 🆕 New | 2026-11-06 |
| PIL-07 | Misconfigured endpoint | no key for OpenRouter; DGX URL without `MINI_RAG_GEN_MODEL`; legacy `MINI_RAG_DGX_BASE_URL` | refused at startup, before any I/O, with the fix in the message | 🆕 New | 2026-11-06 |
| PIL-08 | Reproducible routing | OpenRouter run | request allows only `provider.order=[deepinfra,gmicloud,parasail]`, `quantizations=[fp8]`, `allow_fallbacks=false`; params `llm_providers`, credential-free `llm_base_url`; tag `llm_served_by` counts the provider of each answer | 🆕 New | 2026-11-06 |
| PIL-04 | Smoke run | `--n 1` | `smoke_*` metrics + tag `smoke=true`, never counted as best | 🆕 New | Phase 3 |
| PIL-05 | Unanswerable question | answer `null` | IDK counts correct; any answer = hallucination | 🆕 New | Phase 3 |

## voice-arch — stage-1 bench (Phase 1), booking archs + worker (Phase 2)

| ID | Scenario | Input | Expected Output | Status | Last Modified |
|----|----------|-------|-----------------|--------|---------------|
| VA-01 | STT bench | `python -m voice_arch.bench --component stt` | run FINISHED in `voice-arch/bench`, per-model errors + p50, tag `winner`, `cost_usd` | 🆕 New | voice-arch P1 |
| VA-02 | Budget reached | spent ≥ 50 $ in voice-arch runs | bench refuses before any model call | 🆕 New | voice-arch P1 |
| VA-03 | OpenRouter 402/401 | key out of credit / revoked | bench run FAILED, later candidates not called, cost still logged | 🆕 New | voice-arch P1 |
| VA-04 | Stale corpus cache | other TTS voice / edited text | wavs re-synthesised | 🆕 New | voice-arch P1 |
| VA-05 | Browser smoke | Windows browser on `web/index.html` + token | audio both ways, UDP/TCP noted, e2e offset logged | 🆕 New (user) | voice-arch P1 |
| VA-06 | Default stack untouched | `docker compose up -d` without LiveKit keys | starts, no `livekit` service | 🆕 New | voice-arch P1 |
| VA-07 | Booked slot offered | caller picks `ST_20261109_0900` (booked) | reply "taken", record unchanged, agent offers another | 🆕 New | voice-arch P2 |
| VA-08 | Non-ISO day in `check_slots` | day "next tuesday" | reply "Use a date like 2026-11-10." | 🆕 New | voice-arch P2 |
| VA-09 | Record edited after confirm | `set_field` on a confirmed record | `confirmed` back to False, field logged in `corrections` | 🆕 New | voice-arch P2 |
| VA-10 | Unknown dispatch arch | metadata `""`, `{x`, no `arch`, `"A"` | error `CallResult` on `voice-arch.result`, no session started | 🆕 New | voice-arch P2 |
| VA-11 | Clean caller, text mode | `pytest -m integration tests/integration/test_arch_text.py` | each of A, B, C ends with an exact, confirmed record | 🆕 New | voice-arch P2 |
| VA-12 | Slot change during read-back | "actually Thursday at 2 PM" before the yes | final slot `ST_20261112_1400`, confirmed, old slot released (A, B, C) | 🆕 New | voice-arch P2 |
| VA-13 | Correction of another field | task = slot, caller fixes the phone | phone updated, the slot task stays open | 🆕 New | voice-arch P2 |
| VA-14 | Session report fails | `make_session_report` raises | `CallResult.report` None, `error` carries the message, record kept | 🆕 New | voice-arch P2 |
| VA-15 | Result send after room deleted | `send_text` raises | logged, the job still returns | 🆕 New | voice-arch P2 |
| VA-16 | Browser call per arch | `voice_arch.worker dev`, token with `--agent booking-agent`, `dispatch --arch a/b/c` | a booking completes by voice, the agent hangs up after the goodbye | 🆕 New (user) | voice-arch P2 |
| VA-17 | Persona data validated | personas.jsonl with an unknown/booked slot, a bad problem type, an extra key, a duplicate id | `PersonaError` naming the line and the cause | 🆕 New | voice-arch P3 |
| VA-18 | Agent never joins | dispatch accepted, no worker | `AgentNeverJoined` after `agent_join_timeout_s`, sweep run FAILED, one room | 🆕 New | voice-arch P3 |
| VA-19 | OpenRouter 401/402 on either side | agent result or caller session reports 402 | `ProviderAuthStop`, run FAILED, no further room, `cost_usd` still logged | 🆕 New | voice-arch P3 |
| VA-20 | Caller fails | caller TTS/LLM error closes its session, result arrives | row `caller_fault`, excluded from `exact_rate`; > 10 % of rows -> run FAILED after logging | 🆕 New | voice-arch P3 |
| VA-21 | Call never ends / agent leaves without result | no result by `call_timeout_s` / participant left | `timeout` / `agent_lost`, counted as a miss in `exact_rate` | 🆕 New | voice-arch P3 |
| VA-22 | Budget | `spent` + estimate >= 50 $ / key usage reaches the budget mid-sweep | refused before any room / stopped before the next call, FAILED run keeps rows and `cost_usd` | 🆕 New | voice-arch P3 |
| VA-23 | Smoke sweep | 1 persona x 1 rep | every metric `smoke_*`, tag `full=false`, run not used by `decide` | 🆕 New | voice-arch P3 |
| VA-24 | Naturalness counters | gap 2.0 s vs 2.01 s; interrupted reply repeated vs new | not long vs long; barge-in unhandled vs handled | 🆕 New | voice-arch P3 |
| VA-25 | Decision rule | archs 1 or 2 exact calls apart vs 3 | tie -> lowest latency p50; beyond the margin -> most exact; flag `production_ready` only at >= 90 % and p50 < 1.2 s | 🆕 New | voice-arch P3 |
| VA-26 | Human rating | `rate --rating 0` / `6`; `--rating 4` | refused before MLflow; run `voice-arch/human` with `human_rating`, never `exact_rate` | 🆕 New | voice-arch P3 |
| VA-27 | One live call | worker + LiveKit up, `self_correction`, arch A | one `CallRow` (scored or timeout); the report holds the keys `naturalness` reads | 🆕 New | voice-arch P3 |
| VA-28 | Full sweeps (user) | `runner --arch` a, b, c | three FINISHED full runs, `decide` table in PROJECT.md, app card shows `exact_rate` | 🆕 New (user) | voice-arch P3 |

## Experiment methodology — ledger, split, trials (experiment Phase 1)

| ID | Scenario | Input | Expected Output | Status | Last Modified |
|----|----------|-------|-----------------|--------|---------------|
| EXP-01 | Valid ledger at scoping | `new_ledger(kind=comparison, metric="score (max)")` then `python -m datalab.ledger validate projects/<p>` | exit 0, every milestone `todo`, dataset/split_summary `null` | 🆕 New | exp Phase 1 |
| EXP-02 | Milestone produced before its predecessor is validated | hand-edited run.json, `eda: produced` while `dataset: todo` | validate exits 1, message starts `I-` (strict order) | 🆕 New | exp Phase 1 |
| EXP-03 | Redo resets later milestones | `decide(eda, redo)` with modeling validated | eda and every later milestone back to `todo`, decision logged | 🆕 New | exp Phase 1 |
| EXP-04 | Frozen split edited after the freeze | change one index in split.json after modeling produced | validate exits 1 (split_sha256 mismatch) | 🆕 New | exp Phase 1 |
| EXP-05 | Overlapping split partitions | same group in train and test | `SplitError` | 🆕 New | exp Phase 1 |
| EXP-06 | Trouvetou-format run.json | run.json without `kind` | validate exits 1, `schema` rule | 🆕 New | exp Phase 1 |
| EXP-07 | Nested trial runs | parent `tracked_run` + 2 `tracked_trial` children, one failing | children in the parent's experiment, failed child still logs `cost_usd`, parent tags `n_children`, `n_failed`, `failed_candidates` | 🆕 New | exp Phase 1 |
| EXP-08 | Trial without a parent / inside a trial | `tracked_trial` with no active run, or nested | `TrialError` | 🆕 New | exp Phase 1 |
| EXP-09 | Project spend | runs of every status incl. RUNNING in `<p>/*` | `project_spend` sums all `cost_usd`; no experiment → 0.0 | 🆕 New | exp Phase 1 |

#### Test Data Dependencies
- `contracts/run_ledger_vectors.json` (valid + invalid run.json cases), `contracts/milestones.json`, `contracts/mlflow_tags.json`; MLflow through the `sqlite_uri` fixture (no server).

## Experiment methodology — gates and wiring (experiment Phase 2)

| ID | Scenario | Input | Expected Output | Status | Last Modified |
|----|----------|-------|-----------------|--------|---------------|
| EXP-10 | New project is wired automatically | `datalab-new foo` | `.pre-commit-config.yaml` gains `declared-deps-foo` + `gates-foo` between the `# >>> datalab-new` markers, ci.yml matrix gains `foo`; parity check passes | 🆕 New | exp Phase 2 |
| EXP-11 | Wiring is idempotent and keeps comments | run the wiring twice | files byte-identical after the 2nd run; YAML comments preserved | 🆕 New | exp Phase 2 |
| EXP-12 | Hydra gate on a half-migrated project | project with `configs/` but no `@hydra.main` | hydra hook fails (exit non-zero) | 🆕 New | exp Phase 2 |
| EXP-13 | Legacy project without configs | mini-rag / voice-arch | Hydra gate skips them; ledger hook finds no run.json | 🆕 New | exp Phase 2 |
| EXP-14 | Secret interpolation in a config | `${oc.env:X}` in a YAML under configs/ | hydra hook fails | 🆕 New | exp Phase 2 |
| EXP-15 | CI matrix covers every project | parity check on ci.yml | `fail-fast: false`, one matrix entry per `projects/*`, ledger-validate + Hydra steps present | 🆕 New | exp Phase 2 |
| EXP-16 | Fresh project is green on its gates | `datalab-new demo-app` | `uv sync --locked`, lint-imports, pyright, pytest --cov ≥ 70, pip-audit, ruff, Hydra gate all pass | 🆕 New | exp Phase 3 |
| EXP-17 | Package name collides | `datalab-new json` / `hydra` / `class` | exit 2, nothing written, config files untouched | 🆕 New | exp Phase 3 |
| EXP-18 | Grid search | `train hparams_search=g` with 3 values | one parent, 3 children `dummy-0..2`, distinct `config_sha256` | 🆕 New | exp Phase 3 |
| EXP-19 | Grid names an unknown candidate or param | `{ghost: …}` / `{dummy: {offset: …}}` | exit 2 before any MLflow run | 🆕 New | exp Phase 3 |
| EXP-20 | One candidate crashes | candidates `[dummy, boom]` | exit 1, `boom-0` FAILED, parent lists it | 🆕 New | exp Phase 3 |
| EXP-21 | `--multirun` | `train --multirun` | exit 2, no run | 🆕 New | exp Phase 3 |
| EXP-22 | Eval outside the audit | no run.json / before audit / audit validated | exit 2, no MLflow run | 🆕 New | exp Phase 3 |
| EXP-23 | Second test look | eval twice on one split | 2nd needs `look_note`; tagged `test_look=2`; 2 looks in run.json | 🆕 New | exp Phase 3 |
| EXP-24 | Eval with a different model config | `eval model.value=0.5` | exit 2, hint `model=<family> model.<k>=<v>` | 🆕 New | exp Phase 3 |
| EXP-25 | Split or data changed since modeling | edit split.json / append data | eval exit 2 | 🆕 New | exp Phase 3 |
| EXP-26 | Milestone stop | `/experiment` on a new project | each milestone ends at ⏸️ with validate / correct / redo; the metric is restated | 🆕 New | exp Phase 4 |
| EXP-27 | Redo demotes downstream | redo at eda | eda…report back to todo, split + dataset kept | 🆕 New | exp Phase 4 |
| EXP-28 | Kind change | expert switches training → comparison after scoping | run.json + split.json archived, new ledger at scoping | 🆕 New | exp Phase 4 |
| EXP-29 | Hydra not wired at the BOX | gate fails | modeling redone, BOX re-runs | 🆕 New | exp Phase 4 |
| EXP-30 | Stale RUNNING runs | crashed runs older than N days | listed; only the ones the expert names are closed | 🆕 New | exp Phase 4 |
| EXP-31 | Stepper renders a ledger | project with a valid run.json | steps in kind order, current marked, decision notes shown | 🆕 New | exp Phase 5 |
| EXP-32 | Invalid run.json | trouvetou-format ledger | reported in the build report; strict export fails | 🆕 New | exp Phase 5 |
| EXP-33 | Missing artifact | run.json lists a file that is absent, or `../` | flagged missing | 🆕 New | exp Phase 5 |
| EXP-34 | Run groups | parents with FINISHED/FAILED children, orphans, legacy runs | counts per parent, orphans grouped, legacy standalone | 🆕 New | exp Phase 5 |
| EXP-35 | Card best | test-split runs, running parents, another split | none eligible; only children of the frozen split + data count | 🆕 New | exp Phase 5 |

> ⚠️ After merge: required CI checks are renamed `project (mini-rag)` / `project (voice-arch)` (were `pilot` / `voice-arch`) — update branch protection.
