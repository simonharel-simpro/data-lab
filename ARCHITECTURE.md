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
- **App:** Astro 7 on Node 22 (static output, no server adapter).
- **Weaviate browser:** Weavit UI fork (`tools/weavit-ui`, Electron/TS), auto-connect to the `data-lab` profile.
- **Infra runtime:** Docker Compose (`compose.yaml`, project name `data-lab`).
- **Hooks:** pre-commit (ruff check/format, gitleaks, file-size).

## Project Structure

```
compose.yaml            shared infra: weaviate, t2v-transformers, mlflow (127.0.0.1 only)
.env.example            DATALAB_* connection settings (ports, tracking URI)
contracts/              cross-side contracts (name_vectors.json) read by the Python and app test suites
packages/datalab/       shared Python package: settings, project naming, tracking (Phase 2A)
templates/project/      template copied by `datalab-new` (Phase 2A)
projects/<name>/        one project per folder: own env, PROJECT.md card (projects/.gitkeep: zero is valid)
app/                    read-only Astro presentation app (Phase 2B)
tools/weavit-ui/        Weavit UI fork, git submodule (Phase 2C patches it)
tools/check_file_size.py  pre-commit hook: Python modules under src/ <= 200 lines
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

### Project (`projects/<name>/`)
- **Does:** owns its data, code, env and `PROJECT.md` card; talks to the infra only through `datalab`.
- **Must NOT:** hardcode ports or URIs; write into another project's collections or experiments.

### App (`app/`, Phase 2B)
- **Does:** reads cards and MLflow runs (REST, D-1), renders project pages; dev mode and static export.
- **Must NOT:** write anything — no MLflow writes, no Weaviate access, no card edits; launch runs (#4).

## Data Flow

1. A project script calls `datalab` → settings resolve `DATALAB_WEAVIATE_*` / `DATALAB_MLFLOW_TRACKING_URI`
   (defaults 127.0.0.1:8090 / 50052 / 5050).
2. Ingest: documents go to a collection named `<Pascal>_<parts>_<hash8>`; Weaviate calls `t2v-transformers` to
   embed them when the collection opts in to the module.
3. Experiments: each run is logged to the experiment `<name>` or `<name>/<sub>` with tag `project=<name>`.
4. The app reads `projects/*/PROJECT.md`, queries MLflow for runs with exactly `tags.project = '<name>'`, picks the
   best run by the card's `metric {key, goal}` and renders it (links only in dev, D-14).

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
