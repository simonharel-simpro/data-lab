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
- **App:** Astro 7.4.1 on Node 22 (static output, no server adapter); zod via `astro/zod`; tests with `node --test`
  (type stripping, no vitest); dev deps `@astrojs/check`, `typescript`, `@types/node`, `yaml` (template contract test, Phase 3).
- **Weaviate browser:** Weavit UI fork (`tools/weavit-ui`, Electron/TS), auto-connect to the `data-lab` profile;
  web mode (`tools/weavit-web.sh` → `node:http` server on 127.0.0.1:3080 hosting the same handlers and renderer).
- **Voice stack (`projects/voice-arch`, own env):** self-hosted LiveKit server `livekit/livekit-server:v1.13.10`
  (compose profile `voice`, 127.0.0.1 only: 7880, 7881/tcp, 7882/udp), `livekit-agents` 1.8.8 with the `openai` and
  `silero` plugins, `livekit-api` 1.2.2; every STT / TTS / LLM call goes to OpenRouter (`/audio/transcriptions`,
  `/audio/speech`, `/chat/completions`). Browser smoke client: `livekit-client` 2.23.0 from jsDelivr.
- **Infra runtime:** Docker Compose (`compose.yaml`, project name `data-lab`).
- **Hooks:** pre-commit stage: ruff check/format (Python only), gitleaks (staged files), file-size, declared deps (`declared-deps-voice-arch` covers the voice-arch tree).
  Pre-push stage: `gates-datalab`, `gates-mini-rag`, `gates-voice-arch` (lint-imports + pyright + pytest with coverage per tree),
  `gates-app` (`npm run check && npm test`; needs node >=22.22 on PATH). `default_install_hook_types` wires both
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
contracts/              cross-side contracts (name_vectors.json) read by the Python and app test suites
packages/datalab/       shared Python package: settings, project naming, tracking (Phase 2A)
templates/project/      template copied by `datalab-new` (Phase 2A)
projects/<name>/        one project per folder: own env, PROJECT.md card (projects/.gitkeep: zero is valid)
projects/mini-rag/      the pilot (Phase 3): data/ (frozen corpus + questions), src/mini_rag/, tests/
projects/voice-arch/    voice-agent architecture experiment: src/voice_arch/ (settings, audio factories, stage-1 bench,
                        booking/ pure normalisers), web/ (smoke client), data/, tests/ (+ tests/integration, live)
app/                    read-only Astro presentation app (Phase 2B): src/lib (pure, node --test), src/pages,
                        src/integrations/export-guard.ts, test-fixtures/ (CI build fixtures)
tools/weavit-ui/        Weavit UI fork, git submodule (Phase 2C auto-connect; web mode, RAG OpenRouter preset)
tools/weavit-web.sh     Starts Weavit web mode on the data-lab stack (seeds the profile, passes OPENROUTER_API_KEY)
tools/check_file_size.py  pre-commit hook: Python modules under src/ <= 200 lines
tools/pre_commit_checks/   pre-commit hook (vendored recipe): every datalab import is a declared dependency
.github/workflows/ci.yml  every hook + the networked scans: pre-commit, full-history gitleaks, root compose test,
                        datalab gates + pip-audit (job `checks`); npm audit, app check, tests, builds incl.
                        fixtures (job `app`); mini-rag gates + pip-audit (job `pilot`); voice-arch gates + pip-audit (job `voice-arch`); Python gates `--locked`
tests/                  root tests (compose contract), run with `uvx pytest tests/`
ruff.toml               single ruff config for every Python tree
```

## Layer Responsibilities

### Infra (`compose.yaml`)
- **Does:** runs one Weaviate, one vectorizer and one MLflow for all projects, with named volumes and healthchecks.
- **Must NOT:** publish any port on anything but `127.0.0.1` (unauthenticated, #2); reuse Demo-RAG's ports
  5000 / 8080 / 50051 (D-4).

```yaml
    ports:
      - "127.0.0.1:8090:8080"
      - "127.0.0.1:50052:50051"
```

### Shared package (`packages/datalab`, Phase 2A)
- **Does:** reads `DATALAB_*` settings, validates project names (`NAME_RE`), builds collection names, wraps MLflow
  runs with the non-overridable `project` tag, scaffolds new projects (`datalab-new`).
- **Must NOT:** read unprefixed env vars such as `MLFLOW_TRACKING_URI` (F-5); validate the card beyond `name` (D-3).
- **Modules:** `project` (pure: `NAME_RE`, `load`, `repo_root`, naming), `settings` (`Settings`, `connect_weaviate`),
  `tracking` (`preflight`, `tracked_run`), `new_project` (`datalab-new`). Root found from the package file, so only
  editable installs work (F-10).

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

### App (`app/`, Phase 2B)
- **Does:** reads cards (content collection `projects`, glob `*/PROJECT.md`, schema `cardSchema`) and MLflow runs
  (REST, D-1), renders an index and one page per project.
- **Must NOT:** write anything — the app only calls MLflow's `experiments/search`, `runs/search` and `/health`; no
  Weaviate access, no card edits; never launch runs (#4). Pages never import MLflow code other than `metricState()`.
- **Two modes, one code base (no server adapter, S-2):** `astro dev` re-reads cards and metrics per request and
  links run names to MLflow; `astro build` is a static export with metrics frozen and no MLflow link or URI (D-14).
- **Modules:** `lib/name.ts` (`NAME_RE`, same literal as Python), `lib/card.ts` (zod schema, statuses),
  `lib/completeness.ts` (badge), `lib/mlflow.ts` + `lib/mlflow-rest.ts` (best run, zod-checked responses),
  `lib/report.ts` (build report), `lib/config.ts` (the only module that names the app's `DATALAB_*` env vars),
  `lib/projects.ts` (the only `astro:content` user besides the pages), `integrations/export-guard.ts`.
  Everything under `lib/` except `projects.ts` is pure TS imported with `.ts` extensions, so `node --test` runs it.
- **Invalid card = failed build (D-13):** schema errors come from Astro; `loadProjects()` adds `name` ≠ folder.
- **Metric value contract (U-6):** the value of a run is `run.data.metrics` — MLflow's *latest* value of the key,
  not the max over steps. Only exactly `metric.key` counts (a `smoke_score` never stands in for `score`, D-15).
- **Build report on `globalThis` (B-1):** during `astro build` the pages and the integration load separate module
  instances, so `reportUnavailable()` writes to `globalThis.__datalabBuildReport`; the `astro:build:done` hook logs
  it and, with `DATALAB_STRICT_EXPORT=1`, fails the build when any card's metrics were unavailable (F-1).

```ts
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
4. The app reads `projects/*/PROJECT.md`, queries MLflow for runs with exactly `tags.project = '<name>'`, picks the
   best run by the card's `metric {key, goal}` and renders it (links only in dev, D-14).

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
   collection, never stale vectors; the count check stays a completeness check, with one rebuild (F-13).
3. `run.run` takes a frozen `RunConfig` (retrieval, k, n, size, overlap, collection, corpus_hash), logged as params
   and covered by `config_hash`; it opens `tracked_run(..., sub="retrieval")` → experiment `mini-rag/retrieval`,
   tags `project`, `config_hash` (and `smoke=true` for `--n`); per question: `index.search` (`bm25` or
   `near_text`) → `generate.LlmGenerator.answer` (Anthropic Messages API, text blocks only, `<think>` stripped,
   temperature 0) → `scoring.outcome` (IDK → missing, token-boundary containment → correct, else hallucination).
   Each scored answer is appended as it is produced to `projects/<project>/results/<run_id>.jsonl` (gitignored
   crash copy), so a kill, a `GenerationError` or an MLflow outage keeps the answers computed so far.
4. Metrics and the artifact are logged only after every question is scored: `score = accuracy − hallucination`
   (or `smoke_*`) and `per_question.json` (the canonical artifact); a `GenerationError` leaves a FAILED run without
   metrics (F-13).
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
