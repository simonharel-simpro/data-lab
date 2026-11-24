# Architecture

## Overview

data-lab is a solo user's local data-science lab. One shared infra stack (Weaviate with a vectorizer module,
and MLflow) serves many independent projects under `projects/<name>/`, each with its own Python env. A shared
Python package (`datalab`) gives every project the same settings, naming and tracking conventions; a read-only
Astro app reads each project's card (`PROJECT.md`) and its MLflow runs to tell the project's story, in dev or as
a static export. A fork of Weavit UI (git submodule) browses the shared Weaviate.

## Tech Stack

- **Vector store:** Weaviate 1.40.2 with the `text2vec-transformers` module, model `baai-bge-small-en-v1.5`
  (inference image `1.13.3`, English-only in v1, D-5 / #6). Default vectorizer `none`: collections opt in.
- **Experiment tracking:** MLflow 3.17.2, SQLite backend, artifacts served by the tracking server.
- **Python:** 3.12, managed with uv; one env per project; ruff (single root `ruff.toml`), pytest.
  py312+: `from __future__ import annotations` is not required; PEP 604/585 syntax is native and ruff `UP` keeps it
  modern (decisions.md, 2026-11-09).
- **App:** Astro 7.4.13 on Node 22 (>=22.23.4) (static output, no server adapter); zod via `astro/zod`; tests with `node --test`
  (type stripping, no vitest); dev deps `@astrojs/check`, `typescript`, `@types/node`, `yaml` (template contract test, Phase 3).
  Lint + format (#13): eslint 10 flat config (`@eslint/js` + `typescript-eslint` `recommended` + `eslint-plugin-astro`
  `flat/recommended`) and prettier 3 with `prettier-plugin-astro`; scripts `lint`, `format`, `format:check`; eight exact
  npm `overrides` (decisions.md, 2026-11-09).
- **Weaviate browser:** Weavit UI fork (`tools/weavit-ui`, Electron/TS), auto-connect to the `data-lab` profile;
  web mode (`tools/weavit-web.sh` → `node:http` server on 127.0.0.1:3080 hosting the same handlers and renderer).
  Projection tab: `weavit-projector` Rust sidecar (umap-rs 0.4.5, ndarray, rayon), deck.gl 9.3.11 canvas; Rust gates
  `cargo xtask lint` (pre-push + CI) and `deny.toml` (`cargo deny` local only, not yet in CI).
- **Voice stack (`projects/voice-arch`, own env):** self-hosted LiveKit server `livekit/livekit-server:v1.13.10`
  (compose profile `voice`, 127.0.0.1 only: 7880, 7881/tcp, 7882/udp), `livekit-agents` 1.8.8 with the `openai` and
  `silero` plugins, `livekit-api` 1.2.2; every STT / TTS / LLM call goes to OpenRouter (`/audio/transcriptions`,
  `/audio/speech`, `/chat/completions`). Browser smoke client: `livekit-client` 2.23.0 from jsDelivr.
- **Infra runtime:** Docker Compose (`compose.yaml`, project name `data-lab`).
- **Hooks:** pre-commit stage: ruff check/format (Python only), gitleaks (staged files), file-size, declared deps (`declared-deps-voice-arch` covers the voice-arch tree).
  `enum-discipline` (+ `-mini-rag`, `-voice-arch`, one per tree): no raw string compared to a declared StrEnum value.
  Pre-push stage: `gates-root` (pyright + pytest + coverage >= 70 on `tools/` + root `tests/`, one ad-hoc
  `uv run --no-project` env, #7), `gates-datalab`, `gates-mini-rag`, `gates-voice-arch` (lint-imports + pyright + pytest with coverage per tree),
  `gates-app` (`npm run lint && npm run format:check && npm run check && npm test`; needs node >=22.23.4 on PATH). `default_install_hook_types` wires both
  stages via `pre-commit install`. CI runs all of it plus the networked scans the hooks skip (full-history
  gitleaks, `pip-audit` per tree, `npm audit --audit-level=moderate`); its Python gates run `--locked`.
- **Pilot deps (`projects/mini-rag`, own env):** anthropic 2.3.0 + httpx2 2.16.0 (LLM over the Anthropic
  Messages API: OpenRouter by default, the LAN DGX by override; httpx2 is the SDK's HTTP client and gives the tests `MockTransport`), weaviate-client, mlflow,
  pydantic-settings, `datalab` (editable path dep).
- **Shared package deps:** pydantic-settings, PyYAML (`safe_load` only), weaviate-client 4.24.1 (as Demo-RAG),
  mlflow 3.17.2 (as the server image; its sqlite store backs the tests), httpx (MLflow `/health` preflight).

## Project Structure

```
compose.yaml            shared infra: weaviate, t2v-transformers, mlflow, livekit (profile `voice`; 127.0.0.1 only)
infra/livekit.yaml      LiveKit server config (ports, node_ip 127.0.0.1; no keys: `LIVEKIT_KEYS` from the env)
.env.example            DATALAB_* connection settings (ports, tracking URI)
contracts/              cross-side contracts read by the Python and app test suites: name_vectors.json, EXPERIMENT.md,
                        milestones.json, run_ledger_vectors.json, mlflow_tags.json
packages/datalab/       shared Python package: settings, project naming, tracking (Phase 2A); experiment ledger:
                        split, ledger_model/_rules/_ops/_access/_checks/ledger (run.json), tags, tracking_queries,
                        tracking_outcome,
                        wiring (text-level hook + CI matrix wiring for `datalab-new`)
                        wiring_parity (test-time check that every projects/* has its hook stanzas + CI matrix entry)
templates/project/      template copied by `datalab-new` (Phase 2A; Hydra experiment code since experiment Phase 3):
                        configs/{train,eval}.yaml + groups paths/ data/ model/ experiment/ (hparams_search/ optional),
                        src/__DATALAB_PACKAGE__/{paths,candidates,split,scoring,grid,prepare,train,eval}.py (renamed to
                        the project's package), tests/ (+ fixtures/), .gitignore, PROJECT.md, README.md
projects/<name>/        one project per folder: own env, PROJECT.md card (projects/.gitkeep: zero is valid)
projects/mini-rag/      the pilot (Phase 3): data/ (frozen corpus + questions), src/mini_rag/, tests/
projects/voice-arch/    voice-agent architecture experiment: src/voice_arch/ (settings, audio factories, stage-1 bench,
                        booking/ pure domain, agents/ LiveKit layer for archs A/B/C, worker, result, simulated
                        caller + sweep runner + scoring + decide; module -> layer table under "Voice modules"),
                        web/ (smoke client), data/ (incl. personas), tests/ (+ tests/integration, live)
app/                    read-only Astro presentation app (Phase 2B): src/lib (pure, node --test), src/pages,
                        src/integrations/export-guard.ts, test-fixtures/ (CI build fixtures)
tools/weavit-ui/        Weavit UI fork, git submodule (Phase 2C auto-connect; web mode, RAG OpenRouter preset)
tools/weavit-ui/native/projector/  `weavit-projector` Rust sidecar (PCA, exact kNN, UMAP; NDJSON on stdout)
tools/weavit-web.sh     Starts Weavit web mode on the data-lab stack (seeds the profile, passes OPENROUTER_API_KEY,
                        builds the projector incrementally; serves even if cargo is missing or the build fails)
tools/check_file_size.py  pre-commit hook: Python modules under src/ of packages/, projects/ and templates/ <= 200 lines (warns from 190)
tools/pre_commit_checks/   pre-commit hook (vendored recipe): every datalab import is a declared dependency;
                        hydra_gate.py maps changed paths to project roots and runs the vendored gate once per root;
                        check_enum_discipline.py (hooks `enum-discipline`, `-mini-rag`, `-voice-arch`, one per tree):
                        no raw string compared to a declared StrEnum value
tools/check_hydra_project.py  vendored verbatim from trouvetou (sha256 in its header): Hydra is wired, not just shaped
.github/workflows/ci.yml  every hook + the networked scans: pre-commit, full-history gitleaks, root compose test,
                        datalab gates + pip-audit (job `checks`); npm audit, app check, tests, builds incl.
                        fixtures (job `app`); one matrix job `projects` (fail-fast off; mini-rag, voice-arch): gates + pip-audit, Hydra gate, ledger
                        validate; Python gates `--locked`
tests/                  root tests (compose contract, check_file_size, hydra_gate, weavit-web, plugin), run by the `gates-root`
                        pre-push hook (coverage >= 70 on `tools/`)
.claude-plugin/marketplace.json  the `data-lab` Claude Code marketplace: lists the `datalab` plugin (./plugins/datalab)
plugins/datalab/        the `datalab` Claude Code plugin: .claude-plugin/plugin.json (no `version`: releases follow the
                        commit) + skills/experiment/ (the `/datalab:experiment` skill: SKILL.md,
                        references/agent-overrides.md, references/dispatch-briefs.md); contracts read via datalab.resources
.claude/hooks/          Claude Code hooks: loop guards (loop-git-guard.sh, loop-compaction-flag.sh), statusline-meter.sh
ruff.toml               single ruff config for every Python tree
```

## Layer Responsibilities

### Infra (`compose.yaml`)
- **Does:** runs one Weaviate, one vectorizer and one MLflow for all projects, with named volumes and healthchecks.
- **Must NOT:** publish any port on anything but `127.0.0.1` (unauthenticated, #2); reuse Demo-RAG's ports
  5000 / 8080 / 50051 (D-4).
- `stop_grace_period: 60s` on Weaviate (#36) lets it flush the HNSW commit log on an orderly stop. A hard kill
  (`wsl --shutdown`, a Docker Desktop restart, OOM) can still lose it; mini-rag's reuse check probes vector search for
  that reason (Phase 1.1).

```yaml
    ports:
      - "127.0.0.1:8090:8080"
      - "127.0.0.1:50052:50051"
```

### Shared package (`packages/datalab`, Phase 2A)
- **Does:** reads `DATALAB_*` settings, validates project names (`NAME_RE`), builds collection names, wraps MLflow
  runs with the non-overridable `project` tag, scaffolds new projects (`datalab-new`); holds the experiment ledger
  (`run.json`: model, rules, ops, test-access rules, cross-checks, `python -m datalab.ledger validate`), the frozen
  split (`split.json` and its hash), and the hook + CI wiring of new projects (`wiring`, checked by `wiring_parity`).
- **Must NOT:** read unprefixed env vars such as `MLFLOW_TRACKING_URI` (F-5); validate the card beyond `name` (D-3).
- **Modules** (*pure* = in the import-linter contract "pure modules stay pure (no weaviate/mlflow)"): `project`
  (*pure*: `NAME_RE`, `load`, `repo_root`, `workspace_root`, `is_datalab_checkout`, naming), `resources`
  (*pure*: `contract_path`, `template_dir`, `ruff_toml`, `python -m datalab.resources <file>`), `settings` (`Settings`, `connect_weaviate`), `tracking`
  (`preflight`, `tracked_run`, `tracked_trial`), `tracking_outcome` (per-parent tally of trial outcomes),
  `tracking_queries` (`project_spend`), `new_project` (`datalab-new`), `ledger` (*pure*, facade + `validate` CLI),
  `ledger_model` (*pure*, `RunLedger`, `TRANSITIONS`), `ledger_rules` (*pure*, I-1..I-15), `ledger_ops` (*pure*),
  `ledger_access` (*pure*, test-partition access, test looks), `ledger_checks` (*pure*, V-1..V-3), `split` (*pure*),
  `tags` (*pure*, `Tag`), `wiring` (text-level hook + CI matrix wiring), `wiring_parity` (test-time check).
  `repo_root` is found from the package file (F-10) and only works for editable installs.
- **Workspace (ADR 2026-11-10):** a workspace is the nearest folder above the start path with a regular file
  `datalab.toml` (content ignored); `load()` and `datalab-new` use it. "Inside data-lab" means the workspace holds
  `packages/datalab/` and `compose.yaml` (`is_datalab_checkout`), never the install mode. Inside: path dependency,
  hook + CI wiring. Outside: git dependency (`branch = "main"`, `uv.lock` pins the commit), `<ws>/ruff.toml` written
  once, no wiring (#48). `resources` reads the checkout's contracts/template when `repo_root()` succeeds, else the
  copies the wheel force-includes (git-tracked files only); no fallback between the two.

```python
def collection_name(project: str, *parts: str) -> str:
    """`<Pascal(project)>_<parts>_<hash8>`; the hash covers the raw name and part boundaries (U-2, U-3)."""
    _check_name_shape(project)
    bad = [p for p in parts if not isinstance(p, str)]
    if bad:
        raise TypeError(f"collection name parts must be str, got {bad!r}")
    pascal = "".join(word.capitalize() for word in project.split("-"))
    digest = hashlib.sha256(json.dumps([project, *parts]).encode("utf-8")).hexdigest()[:8]
    return "_".join([_UNSAFE.sub("_", "_".join([pascal, *parts])), digest])
```

```python
    extra = dict(tags or {})
    if "project" in extra:
        raise ValueError("tags may not override 'project': it always equals the project name")
    # Set explicitly, so a project that skips preflight never logs through an inherited MLFLOW_TRACKING_URI (F-5).
    mlflow.set_tracking_uri(settings.mlflow_tracking_uri)
    mlflow.set_experiment(experiment_name(project.name, sub))
    with mlflow.start_run(run_name=run_name) as run:
        mlflow.set_tags({"project": project.name} | extra)
        yield run.info.run_id
```

### Project (`projects/<name>/`)
- **Does:** owns its data, code, env and `PROJECT.md` card; talks to the infra only through `datalab`.
- **Must NOT:** hardcode ports or URIs; write into another project's collections or experiments.

### Project template (`templates/project`, experiment Phase 3)
- **Does:** `train` and `eval` (`python -m <pkg>.train|eval`, each `@hydra.main`) own all I/O: config, split.json,
  data file, MLflow. `scoring`, `candidates`, `grid` are pure (an import-linter contract forbids mlflow, datalab, hydra,
  omegaconf there); `split` cuts the data by the frozen split and refuses the test partition unless `eval` opts in;
  `prepare` holds the pre-run checks. `<pkg>` is `package_name(name)`: the dashed name with underscores, refused when
  it shadows a keyword, a stdlib module or an installed import name.
- **Must NOT:** log `metric.key` or `cost_usd` on a parent run; read the test partition from `train`; run
  `--multirun` (the grid runs in-process, D-4); use `${oc.env:...}` or JSON in `configs/`.
- **`train.run` order:** (1) project + card metric, (2) experiment name (`audit` reserved), (3) resolve the config,
  (4) ledger and `score_on`, (5) candidates, grid and one composed model per combination (config_sha256), (6) rows,
  split, scored partition, hashes; steps 1-6 end in exit 2 with no MLflow run. (7) settings + preflight, (8) one
  parent run, one child per combination (a failing candidate fails its child only; an MLflow error aborts),
  (9) metric-key rules over the finished children, (10) exit 1 if a child failed.
- **`datalab-new` generates and gates it:** `test_f_3_scaffolded_project_passes_its_gates` (marker `scaffold`, network,
  run by the CI `checks` job) scaffolds a project with a real lock and runs its gates.

```python
@hydra.main(version_base=None, config_path="../../configs", config_name="train")
def main(cfg: DictConfig) -> None:
    refuse_multirun("train")
    code = run(cfg, tuple(HydraConfig.get().overrides.task))
    if code:
        raise SystemExit(code)
```

### Voice architectures (`projects/voice-arch`, Phase 2)
- **Does:** books a US service appointment by voice (name, phone, address, problem type, slot, read-back) in three
  control structures that share the same LLM, audio, instructions and tools: **A** one `Agent` with every tool,
  **B** a `TaskGroup` of one `AgentTask` per step (regression allowed), **C** B plus the call record rendered into
  each task's instructions.
- **Layers:** `booking/` is pure (import-linter contract "booking stays pure": no livekit, mlflow, datalab, httpx):
  `record` (`BookingRecord`, `ExpectedRecord`, `is_exact`), `calendar` (the fixed 12 slots, never `today`),
  `actions` (the only code writing the record; returns the reply the LLM sees), `instructions` (shared strings).
  `arch.py` (`Arch`, `parse_arch`) and `result.py` (`CallResult`, `RESULT_TOPIC`) are LiveKit-free too. `agents/`
  holds `state` (`BookingState`), `tools` (`@function_tool` wrappers over `booking.actions`), `arch_a/b/c`,
  `registry.build_agent`. `worker_logic.py` is the testable half of the worker (metadata, pinned
  `TURN_HANDLING` / `MAX_TOOL_STEPS`, `build_result`); `worker.py` builds the `AgentServer` from the settings.
  The agent LLM is pinned to Google's OpenRouter providers (`google-vertex,google-ai-studio`, no fallback, no
  quantization filter: their endpoints report "unknown"; ESC-2-1) and wrapped by `llm_guard.retry_on_empty_completion`
  (Gemini sometimes ends a stream with zero tokens, which LiveKit treats as a finished, silent turn; ESC-3-2).
  The simulated caller's LLM is unpinned. Preemptive generation is explicitly off in `TURN_HANDLING`.
  The agent LLM (`audio.make_agent_llm`) also sends `reasoning_effort=low`: without it Gemini answers most tool turns
  with `MALFORMED_FUNCTION_CALL`, the "empty completion" above. `SessionWatch` ends the call on the first
  unrecoverable LLM error (the `CallResult` carries it), and `confirm_booking` refuses until the caller has spoken
  after the last record write (`BookingState.caller_replied_since_write`).
- **Must NOT:** let `booking/` import LiveKit; write the record anywhere but `booking.actions`; default an unknown
  `arch` (F-9); write files from the worker (the result goes to the room).
- **Pattern (a tool completes the step that owns the written field):**
```python
def complete_current_task(ctx: Ctx, field: str) -> None:
    agent = ctx.session.current_agent
    if isinstance(agent, AgentTask) and not agent.done() and getattr(agent, "FIELD", None) == field:
        agent.complete(None)
```
- **Data flow:** `python -m voice_arch.dispatch --arch b --room R` creates an agent dispatch with metadata
  `{"arch": "b"}` -> the worker (`agent_name="booking-agent"`) parses it (`UnknownArchError` -> error `CallResult`),
  builds the session (STT/LLM/TTS via OpenRouter, Silero VAD, `userdata=BookingState`), starts `build_agent(arch)`
  in the room, waits for the session `close`, then sends one `CallResult` (record + session report + close reason +
  error counts) on the room text topic `voice-arch.result` before returning.
- **State:** the booking record is the only stateful entity; its `confirmed` flag resets on any write (U-2), so it
  has no FSM beyond that flag. The TaskGroup walks name -> phone -> address -> problem -> slot -> confirm, and
  `out_of_scope` (added by LiveKit to every task after the first) regresses to an earlier step.

### Voice sweeps (`projects/voice-arch`, Phase 3)
- **Does:** measures each architecture against a simulated caller: one sweep = one arch x 6 personas x N reps = one
  MLflow run in `voice-arch/conversations` (metric `exact_rate`), then `decide` picks the architecture (D-15) and
  `rate` logs human ratings (reported, never ranking).
- **Layers:** LiveKit-free (import-linter contract "scoring and decision stay LiveKit-free"): `personas`
  (`load_personas`, `PersonaError`), `naturalness` (counters from `SessionReport.to_dict()`), `scoring`
  (`aggregate`, `cost_per_call`), `decide` (`pick_arch` on integers; reads runs through `sweep_query`, so it imports
  `mlflow` and is not pure), `call` (`run_one_call` -> `CallRow`, the F-* classification), `call_env` (the `CallEnv` /
  `CallerHandle` protocols the tests fake). Runs side: `sweep` (one sweep's per-call loop), `sweep_log` (JSONL rows,
  MLflow params), `sweep_query` (reads the sweep runs). LiveKit side: `caller` (`CallerAgent`, `make_caller_session`), `live_caller` (the live `CallerHandle`),
  `livekit_env` (`LiveKitCallEnv`). `runner` wires settings, budget gate, MLflow run and spend tracker; `rate` is a
  small CLI.
- **Must NOT:** let `call.py` or the scoring modules import LiveKit; start a sweep without the budget gate (F-4b);
  count a `caller_fault` in `exact_rate` (F-6); let a smoke run log unprefixed metrics (U-1).
- **Pattern (a call is classified in a fixed order; auth failures stop the sweep before anything else):**
```python
_stop_on_auth(handle, result)                       # 401/402 on either side -> ProviderAuthStop
return _row(persona, rep, room, _classify(handle, result), result)
```
- **Data flow:** `runner.main()` loads settings/personas, then `run_sweep` checks the budget, opens the run and the
  spend tracker, and for each persona x rep calls `run_one_call`: dispatch the booking agent, connect the caller
  (it joins the room and starts listening; B and C only after the agent's greeting, see `LiveCaller`), wait for the
  agent's `CallResult` on `voice-arch.result` (firing the persona's interjections while the agent talks), classify,
  delete the room. Rows are appended to `results/<run_id>.jsonl`; metrics, params and `per_conversation.json` are
  logged at the end. `cost_usd` (caller included) is the key's cumulative usage: logged after every call
  (`step=index`, so a killed sweep loses at most one call) and once more on tracker exit (`step=len(rows)`), even for
  a FAILED run; an unreadable key tags the run `cost_unknown=true` and the sweep carries on (F-12).
- **Budget:** `budget.spent_so_far` is `datalab.tracking_queries.project_spend("voice-arch")` (every run, whatever its
  status, RUNNING included) plus P-2: a `voice-arch/<sub>` run that is not FINISHED and logged no `cost_usd` counts
  at `ESTIMATES_USD[sub]` (conversations 15 $, bench 2 $), with a warning.
- **State:** a call row has an `Outcome` (scored, timeout, agent_lost, caller_fault, provider_error); there is no
  transition model, each call is classified once from what the handle reports.

### Voice modules (`projects/voice-arch/src/voice_arch/`, module -> layer)

Measured 2026-11-09 with `grep -lE '^(import|from) (mlflow|datalab|httpx|livekit)'`, then checked transitively by
import-linter. The **pure** row is exactly the contract "pure modules stay MLflow-free" (no mlflow, datalab, httpx,
livekit, even through another module); `booking/` has its own contract "booking stays pure".

| Layer | Modules |
|---|---|
| pure | `arch`, `call`, `call_env`, `candidates`, `fields`, `naturalness`, `personas`, `result`, `scoring`, `winners`, the `booking` package |
| MLflow / runs | `bench`, `bench_record`, `budget`, `decide` (imports `mlflow`), `rate`, `runner`, `sweep`, `sweep_log` (no direct import, but reaches `datalab` via `settings` and `livekit` via `worker_logic`), `sweep_query` |
| IO adapters / LiveKit | `audio`, `bench_runs`, `caller`, `corpus`, `dispatch`, `live_caller`, `livekit_env`, `llm_dump`, `llm_guard`, `openrouter_key`, `seams`, `settings`, `token`, `tool_schemas`, `worker_logic`, the `agents` package |
| entry points | `worker`, `smoke_agent` (and the `main()` of `runner`, `bench`, `decide`, `rate`) |

### Claude plugin (`plugins/datalab`, served by `.claude-plugin/marketplace.json`, platform Phase 2)
- **Does:** ships the `/datalab:experiment` skill to any workspace (a root with `datalab.toml`, projects under
  `projects/<name>/`). Commands run from the workspace root in portable forms: the ledger through
  `uv run --locked --project projects/<name> python …`, the contracts through
  `uv run --project projects/<name> python -m datalab.resources EXPERIMENT.md|milestones.json` (prints the path), a
  missing project through README §New project. Only steps gated on the `is_datalab_checkout` predicate
  (`packages/datalab/` and `compose.yaml` at the root) differ: the Hydra gate runs inside data-lab and is skipped
  elsewhere (#48).
- **Must NOT:** name data-lab-only paths (`--project packages/datalab`, `contracts/…`, `tools/…`) outside those gated
  sentences; link outside `plugins/datalab/` (installs are copied to a cache); ship the `ds-*` agents (user-level
  trouvetou install, #47); hardcode a milestone sequence (only `milestones.json`). `tests/test_plugin.py` guards it.

### Projection (Weavit fork, `tools/weavit-ui`)
- **Does:** the host reads vectors (lean cursor loop, `src/main/projection/readVectors.ts`) → sidecar stdin →
  NDJSON frames → one session slot, polled by the renderer's Projection tab.
- **Must NOT:** read through `exportObjects`; import `child_process` outside `src/main/projection/sidecar.ts`.

### App (`app/`, Phase 2B)
- **Does:** reads cards (content collection `projects`, glob `*/PROJECT.md`, schema `cardSchema`), each project's
  `run.json` (optional) and MLflow runs (REST, D-1), renders an index and one page per project.
- **Must NOT:** write anything — the app only calls MLflow's `experiments/search`, `runs/search` and `/health`; no
  Weaviate access, no card edits, no run.json writes; never launch runs (#4). Pages never import MLflow code other
  than `projectView()` (`metricState()` stays for callers that only need the card best).
- **Two modes, one code base (no server adapter, S-2):** `astro dev` re-reads cards and metrics per request and
  links run names to MLflow; `astro build` is a static export with metrics frozen and no MLflow link or URI (D-14).
- **Modules:** `lib/name.ts` (`NAME_RE`, same literal as Python), `lib/card.ts` (zod schema, statuses),
  `lib/completeness.ts` (badge), `lib/mlflow.ts` (`projectView`: one experiments + runs fetch → card best + run
  groups) + `lib/mlflow-rest.ts` (zod-checked responses, `runs/search` pagination), `lib/best.ts` (`pickBest`,
  `eligibleForBest`, `bestFilter`), `lib/run-groups.ts` (parent → children, orphans, counts), `lib/tags.ts` (the
  `mlflow_tags.json` names), `lib/ledger.ts` (run.json reader: strict schema + I-1 in Python's check order, stepper
  steps, artifact containment; no writes), `lib/report.ts` (build report), `lib/config.ts` (the only module that names the app's `DATALAB_*` env vars),
  `lib/projects.ts` (the only `astro:content` user besides the pages), `integrations/export-guard.ts`.
  Everything under `lib/` except `projects.ts` is pure TS imported with `.ts` extensions, so `node --test` runs it.
- **Lint + format (#13):** `npm run lint` (`eslint.config.js`: `recommended` rule sets plus
  `@typescript-eslint/no-explicit-any` and `consistent-type-imports`, both `error`), `npm run format:check`
  (`.prettierrc.json`: width 120, single quotes, trailing commas; `npm run format` rewrites). Both run in CI and in
  `gates-app`. A caught error rethrown with a new message keeps it as `{ cause: err }` (`preserve-caught-error`).
- **Invalid card = failed build (D-13):** schema errors come from Astro; `loadProjects()` adds `name` ≠ folder.
- **Metric value contract (U-6):** the value of a run is `run.data.metrics` — MLflow's *latest* value of the key,
  not the max over steps. Only exactly `metric.key` counts (a `smoke_score` never stands in for `score`, D-15).
- **Build report on `globalThis` (B-1):** during `astro build` the pages and the integration load separate module
  instances, so `reportUnavailable()` writes to `globalThis.__datalabBuildReport`; the `astro:build:done` hook logs
  it and, with `DATALAB_STRICT_EXPORT=1`, fails the build when any card's metrics were unavailable (F-1) or its
  run.json is invalid (key `run.json:<project>`, F-20).
- **run.json in the app (F-18):** checked are the schema, U-13 (`kind` missing) and I-1 (milestone keys = the kind's
  sequence, which also orders the stepper); I-2..I-15 and V-1..V-3 are Python-only (the `ledger` hook and the CI
  `projects` step), so a ledger that breaks only those renders as valid. `checked_by` in the shared vectors says
  which side checks what. An artifact shows `missing` unless it exists inside the project's real path (U-15).
- **Card best (F-13, U-9, U-27):** `eligibleForBest` drops `split=test` runs; a child counts only if it and its
  parent FINISHED; with a run.json the parent's `split_sha256`/`data_sha256` tags must equal the ledger's (a null
  ledger hash → no best); without one a parentless FINISHED run still counts (legacy); an invalid run.json → no best.
  The index card and the project page use the same filter, so they show the same best.

```ts
// lib/best.ts
export function pickBest(runs: readonly MlflowRun[], metric: Metric) {
  if (runs.length === 0) return { kind: 'no-runs' };
  const carrying = runs.flatMap((run) => {
    const m = run.data.metrics.find((x) => x.key === metric.key);
    return m ? [{ run, value: m.value }] : [];
  });
  if (carrying.length === 0) return { kind: 'metric-not-logged', runCount: runs.length };
  const finite = carrying.filter((c): c is { run: MlflowRun; value: number } => Number.isFinite(c.value));
  if (finite.length === 0) return { kind: 'no-runs' };
  const sign = metric.goal === 'max' ? -1 : 1;
  finite.sort(
    (a, b) =>
      sign * (a.value - b.value) ||
      b.run.info.start_time - a.run.info.start_time ||
      (a.run.info.run_id < b.run.info.run_id ? -1 : a.run.info.run_id > b.run.info.run_id ? 1 : 0),
  );
  const best = finite[0];
  if (!best) return { kind: 'no-runs' };
  return { kind: 'picked', run: best.run, value: best.value, runCount: finite.length };
}
```

## Data Flow

1. A project script calls `datalab` → settings resolve `DATALAB_WEAVIATE_*` / `DATALAB_MLFLOW_TRACKING_URI`
   (defaults 127.0.0.1:8090 / 50052 / 5050).
2. Ingest: documents go to a collection named `<Pascal>_<parts>_<hash8>`; Weaviate calls `t2v-transformers` to
   embed them when the collection opts in to the module.
3. Experiments: each run is logged to the experiment `<name>` or `<name>/<sub>` with tag `project=<name>`.
4. The app reads `projects/*/PROJECT.md` and `projects/<name>/run.json` (stepper), queries MLflow for runs of any
   status with exactly `tags.project = '<name>'` (all pages), groups them parent → children, picks the best eligible
   run by the card's `metric {key, goal}` — on the frozen split when a run.json exists — and renders it (links only
   in dev, D-14).
5. `datalab-new <name>` copies the template, locks it, then `wiring.plan` computes the new text of
   `.pre-commit-config.yaml` (declared-deps + gates stanzas) and `ci.yml` (matrix entry) between the
   `# >>> datalab-new` markers; both are written only after the project folder is published, and
   `wiring_parity.parity_problems` (a test) fails if any project is unwired.
6. Experiment (template project): `train` logs one parent run (tags `entry`, `split_sha256`, `data_sha256`,
   `score_on`; no metric) and one child per candidate x grid combination (`metric.key`, `cost_usd`, tags `candidate`,
   `config_sha256`); the expert validates modeling with a winner child in `run.json`. At the audit `eval` checks
   run.json (`test_access_problem`), the data hash, that the winner's parent was trained on the frozen split and data,
   and that the composed model hashes to the winner's `config_sha256`; it then records the test look in run.json
   and logs `test_<metric.key>` on a child of `<project>/audit`.

### Concrete example: the `mini-rag` pilot (Phase 3)

`uv run python -m mini_rag.run --retrieval bm25 --k 3` in `projects/mini-rag`:

1. `datalab.project.load()` reads `PROJECT.md` (name `mini-rag`); `PilotSettings` (`MINI_RAG_*`, the LLM API key is
   required; base URL defaults to OpenRouter) and `Settings` (`DATALAB_*`) are validated before any I/O; `preflight` checks MLflow. `preflight` and
   `tracked_run` bound MLflow HTTP retries (`MLFLOW_HTTP_REQUEST_MAX_RETRIES=2`, `MLFLOW_HTTP_REQUEST_TIMEOUT=30`
   via `setdefault`; a user value wins), so an outage fails fast instead of hanging.
2. `corpus.load_corpus` chunks the frozen snapshot `data/corpus/*.md` (by `##` section, then 120 words with a
   20-word overlap); `main()` computes `index.corpus_hash` once; `index.ensure_collection` reuses or builds
   `MiniRag_t2v_bge_small_en_v1_5_w120o20_c<corpus_hash12>_<hash8>` (vectorizer `text2vec-transformers`, embedder
   id and corpus hash in the hashed parts, U-13): reuse is keyed on corpus content, so a corpus edit gets a new
   collection, never stale vectors; a collection is reused only if its count matches AND a `near_text` probe answers
   (an index that holds objects but answers nothing is rebuilt), with one rebuild, then `IndexBuildError` (F-13).
   Index builds are serialized per collection by a host-local file lock, #12.
3. `run.run` takes a frozen `RunConfig` (retrieval, k, n, size, overlap, collection, corpus_hash), logged as params
   and covered by `config_hash`; it opens `tracked_run(..., sub="retrieval")` → experiment `mini-rag/retrieval`,
   tags `project`, `config_hash` (and `smoke=true` for `--n`); per question: `index.search` (`bm25` or
   `near_text`) → `generate.LlmGenerator.answer` (Anthropic Messages API, text blocks only, `<think>` stripped,
   temperature 0) → `scoring.outcome` (IDK → missing, token-boundary containment → correct, else hallucination).
   Each scored answer is appended as it is produced to `projects/<project>/results/<run_id>.jsonl` (gitignored
   crash copy), so a kill, a `GenerationError` or an MLflow outage keeps the answers computed so far.
4. Metrics and the artifact are logged only after every question is scored: `score = accuracy − hallucination`
   (or `smoke_*`) and `per_question.json` (the canonical artifact); a `GenerationError`, or a question whose search
   returns no passages (`EmptyRetrieval`), leaves a FAILED run without metrics (F-13).
5. The app shows the card with the best FINISHED run by `score` (`max`).

```python
    with tracked_run(project, settings, run_name=name, sub="retrieval", tags=tags) as run_id:
        mlflow.log_params(params)
        sink = results_dir / f"{run_id}.jsonl"
        results = _answer_all(selected, config.retrieval, config.k, answer, search, sink)
        mlflow.log_metrics(metrics([r.outcome for r in results]).as_dict(prefix="smoke_" if partial else ""))
        mlflow.log_dict({"results": [asdict(r) for r in results]}, "per_question.json")
```

## Key Domain Concepts

- **Project** — a folder `projects/<name>/` whose name matches `NAME_RE` and is not reserved; owns one env.
- **Card** — `projects/<name>/PROJECT.md`: YAML frontmatter (`name`, `title`, `status`, `tags`, `data`,
  `metric {key, goal}`) plus `##` sections. Schema single-sourced in the app (D-3).
- **Run** — an MLflow run tagged `project=<name>` in experiment `<name>` or `<name>/<sub>`.
- **Experiment ledger** — `projects/<name>/run.json` (a `RunLedger`, kind `training|comparison|exploration`): one
  status per milestone, the expert's decisions log, the frozen `split_sha256`, the winner and the test looks. Guarded
  by invariants I-1..I-15 (`datalab.ledger_rules`) and checks V-1..V-3; `split.json` is its frozen split. An
  `exploration` (scoping → eda → report) has no dataset step, split, modeling, audit or tracking: the fields those
  milestones own stay null (`ledger_rules._absent`). Its runs, if any, are logged from project code via
  `datalab.tracking`; the template train/eval refuse it, and the card ranks it by the legacy rule (decisions.md,
  2026-11-09).
  Milestone ids are data from `contracts/milestones.json`; only the ids the code names are `Final` constants
  (`DATASET`, `FEATURES`, `MODELING`, `AUDIT`), tested to exist in the contract (decisions.md, 2026-11-08).
- **Collection** — a Weaviate collection named from the project name + parts, hashed to avoid collisions.

## State Machines

### Project `status` (card frontmatter)

```
idée ──► en cours ──► conclu
  │         │
  └─────────┴──────► abandonné      (any state → abandonné)
```

Valid transitions: `idée → en cours`, `en cours → conclu`, any → `abandonné`. The required card sections grow with
the status (enforced by the app, Phase 2B).

The status is a hand-edited label. The diagram is the intended workflow, and nothing enforces the transitions. The
app only checks that the value is one of `STATUSES` (`app/src/lib/card.ts`) and that the required sections for that
status are present (`app/src/lib/completeness.ts`).

### Experiment milestone (`run.json`, per milestone)

```
todo ──► produced ──► validated
   ▲        │  ▲
   │        └──┘  correct          (produced → produced, decision `correct`)
   └─────────┘ redo                (produced → todo, decision `redo`)
```

`produce` moves the current milestone `todo → produced`; `decide` validates it (current advances), corrects it or
redoes it. Order is strict (a milestone starts only after every earlier one is validated) and there is no `skipped`
status. The log and test looks are append-only. The five legal transitions, one line per row of the table:

```
todo + produce → produced
produced + produce → produced
produced + correct → produced
produced + validate → validated
produced + redo → todo
```

`redo(m)` (any started status, VALIDATED included) → TODO for m and every later milestone, and clears the fields they
fed (split, dataset, features, winner, data hash); a separate op, not a table row. Transitions:
`datalab.ledger_model.TRANSITIONS`, checked against this table by `test_transitions_table_matches_architecture_md`.

## Cross-phase contracts

- **Project name** `NAME_RE = ^[a-z][a-z0-9]*(-[a-z0-9]+)*$`, reserved `{test, datalab, datalab-test, template, y, n, yes, no, on, off, true, false, null}` (the YAML 1.1 bool/null words because PyYAML reads `name: no` as `False` while the JS YAML parser reads `"no"`).
  Identical literal in `packages/datalab/src/datalab/project.py` (2A) and `app/src/lib/name.ts` (2B); both test
  suites read `contracts/name_vectors.json` (created in 1).
- **Project card** `projects/<name>/PROJECT.md`: frontmatter `name` (== folder), `title`, `status`
  (`idée|en cours|conclu|abandonné`), `tags`, `data`, `metric {key, goal: max|min}` + `##` sections. Full schema
  lives once, in the app (2B); Python validates `name` only (2A).
- **MLflow:** experiments named `<name>` or `<name>/<sub>`; every run carries non-overridable tag `project=<name>`
  (2A writes, 2B and 3 read). Env var `DATALAB_MLFLOW_TRACKING_URI`, default `http://127.0.0.1:5050` (both sides).
- **Weaviate:** collections `<Pascal>_<parts>_<hash8>`, hash over `json.dumps([name, *parts])` (2A → 3).
  Ports 127.0.0.1:8090 (HTTP) / 50052 (gRPC); vectorizer module `text2vec-transformers` (1 → 3).
- **Weavit profile** named exactly `data-lab`, HTTP 8090 + gRPC 50052 (README in 1, auto-connect in 2C).
- **Dual-site constants and their guards:** NAME_RE + reserved names → `contracts/name_vectors.json` read by both test
  suites; ports → G-10 parity test (`.env.example` = Python `Settings` = compose) + an app test (`.env.example` =
  `mlflowUri({})`); the fork's `DATALAB_PORTS` (another repo) has no copy-check on purpose: drift fails safe (the
  profile is refused with `skip: ports`, nothing connects to the wrong Weaviate).
- **Experiment methodology** (`contracts/EXPERIMENT.md`): `run.json` + `split.json` per project, validated by
  `python -m datalab.ledger validate PATH...`. Three JSON contracts: `milestones.json` (ids, sequences, `freeze_after`),
  `run_ledger_vectors.json` (shared valid/invalid cases) and `mlflow_tags.json` (the 11 tag names). Check order: JSON,
  `kind` present, field errors, I-1..I-15. MLflow: one parent per invocation, one nested child per grid combination
  via `tracked_trial` (the parent's experiment, tags `project` and `candidate` not overridable, one open trial at a
  time); only children log `metric.key` and `cost_usd`; parents get `n_children`, `n_failed`, `failed_candidates`
  from the `_OUTCOMES` registry. Naming: experiment `<project>/<experiment.name>`, eval in `<project>/audit`. The
  budget (`project_spend`, RUNNING included) is shown, never enforced.
