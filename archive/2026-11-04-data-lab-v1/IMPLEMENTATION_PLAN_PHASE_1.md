# Phase 1 — Repo foundation, shared infra, Weavit fork attached

**Depends on:** nothing. **Agent:** `general-purpose`. **Repo root:** `/home/simon/projects/data-science/data-lab`
(currently: only `spike-astro/` + `IMPLEMENTATION_PLAN*.md`; no git yet).
**Remote:** `https://github.com/simonharel-simpro/data-lab.git` (private, empty).
**Preconditions (check first, stop and report if missing):** the user's fork
`https://github.com/simonharel-simpro/weavit-ui` exists (`gh repo view simonharel-simpro/weavit-ui`); Docker running.

## Context
data-lab is a solo user's local data-science lab: one shared Weaviate (+ vectorizer) and one MLflow, used by many
projects under `projects/<name>/`, each with its own Python env. A Demo-RAG stack already runs on
127.0.0.1:5000 / 8080 / 50051 and must keep running: data-lab uses **5050 / 8090 / 50052** (decision D-4).
Services are unauthenticated, so every port binds to 127.0.0.1 only (auth deferred: #2).

## Files

#### `.gitignore` (NEW)
**Content:** `.venv/`, `__pycache__/`, `.pytest_cache/`, `.ruff_cache/`, `.coverage`, `.env`, `node_modules/`,
`/app/dist/`, `/app/.astro/`, `*.log`, and `spike-astro/` (throwaway prototype: never committed; Phase 2B
promotes it then `rm -rf`s it). Keep `.env.example` tracked.

#### `compose.yaml` (NEW) — the shared infra
**Reference:** `/home/simon/projects/data-science/Demo-RAG-crag-dataset/docker-compose.yml` (copy its structure,
images, healthchecks, named volumes, sqlite MLflow backend with `--serve-artifacts`).
**Changes vs reference:**
- top-level `name: data-lab` (volume/network names must not depend on the folder name).
- `weaviate` (`cr.weaviate.io/semitechnologies/weaviate:1.40.2`): ports `127.0.0.1:8090:8080` and
  `127.0.0.1:50052:50051`; `ENABLE_MODULES: text2vec-transformers`; `TRANSFORMERS_INFERENCE_API: http://t2v-transformers:8080`;
  `DEFAULT_VECTORIZER_MODULE: none` (collections opt in; bring-your-own-vectors stays possible); `depends_on`
  `t2v-transformers` with `condition: service_healthy`.
- `t2v-transformers` (NEW service): image `semitechnologies/transformers-inference:baai-bge-small-en-v1.5-1.13.3`
  (pinned; English-only by user decision D-5, multilingual tracked in #6), `ENABLE_CUDA: "0"`, no host port.
  Healthcheck with Python, not wget/curl (the slim inference image may lack them), same form as the reference
  mlflow healthcheck: `["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8080/.well-known/ready', timeout=4)"]`
  (verify the ready path in the image docs; fall back to `/meta`).
- `mlflow` (`ghcr.io/mlflow/mlflow:v3.17.2`): port `127.0.0.1:5050:5000`.
**Constraints:** a comment at the top stating the 127.0.0.1-only rule and the reason (unauthenticated, #2).
`docker compose down -v` wipes every project's data: say so in a comment.

#### `.env.example` (NEW)
`DATALAB_WEAVIATE_HOST=127.0.0.1`, `DATALAB_WEAVIATE_HTTP_PORT=8090`, `DATALAB_WEAVIATE_GRPC_PORT=50052`,
`DATALAB_MLFLOW_TRACKING_URI=http://127.0.0.1:5050`, each with a one-line comment. No secrets.

#### `contracts/name_vectors.json` (NEW) — consumed by 2A and 2B tests
```json
{"accept": ["a", "mini-rag", "ocr2", "a-b-c"],
 "reject": ["", "1a", "A", "a_b", "-a", "a-", "a--b", "mini--rag", "a b", "a/b", "test", "datalab", "datalab-test", "template", "no", "yes", "on", "off", "true", "false", "null", "y", "n"]}
```
Plus a sibling `contracts/README.md` (5 lines): the rule `^[a-z][a-z0-9]*(-[a-z0-9]+)*$`, the reserved names, and
the two files that must use the identical literal (`packages/datalab/src/datalab/project.py`, `app/src/lib/name.ts`).

#### `projects/.gitkeep` (NEW) — the app must build with zero projects (F-15)

#### `ruff.toml` (NEW) — single source for every Python tree
**Reference:** `[tool.ruff]` of the Demo-RAG `pyproject.toml`: `line-length = 120`, `target-version = "py312"`,
lint select `["E","F","W","I","B","UP","S","SIM","RUF"]`, per-file-ignores `"**/tests/**" = ["S101","S105","S106"]`.
Exclude `tools/weavit-ui`, `spike-astro`, `app`.

#### `tools/check_file_size.py` (NEW)
Copy `/home/simon/projects/data-science/Demo-RAG-crag-dataset/tools/check_file_size.py` (≤ 200 lines per
module); widen its filter to any `.py` under `packages/*/src/` and `projects/*/src/`. Or scaffold it with
`/scaffold-linter file-length --recipe python-fastapi-layered/check_file_length.py` if that gives the same rule.

#### `.pre-commit-config.yaml` (NEW)
**Reference:** Demo-RAG `.pre-commit-config.yaml` (ruff-pre-commit `v0.17.3` check `--fix` + format, gitleaks
`v8.30.1`). File-size hook: `language: python`, `entry: python tools/check_file_size.py` (no root uv project
exists, so no `uv run`). Exclude `^tools/weavit-ui/`.

#### `.nvmrc` (NEW) — content `22` (Astro 7 needs Node ≥ 22.22)

#### `.gitmodules` + `tools/weavit-ui` (NEW, via command)
`git submodule add https://github.com/simonharel-simpro/weavit-ui.git tools/weavit-ui`, then
`git config push.recurseSubmodules check` (documented in README too).

#### `README.md` (NEW)
Sections: what data-lab is (3 lines); prerequisites (Docker, uv, Node 22 via nvm, keep the repo on the Linux
filesystem, not `/mnt/c`); `git clone --recurse-submodules`; start/stop infra (`docker compose up -d`, `ps`, `down`;
warning on `down -v`); ports table (5050/8090/50052, and why not 5000/8080/50051); Weavit UI: build/run from
`tools/weavit-ui` (link to its README) and **create once a local profile named exactly `data-lab` with HTTP port
8090 AND gRPC port 50052** (both explicit: an empty gRPC field falls back to Demo-RAG's 50051, F-4);
placeholders for "New project" (2A) and "App" (2B) sections.

#### `ARCHITECTURE.md` (NEW) — all sections mandated by `rules/shared/documentation.md`
Overview; Tech stack (Weaviate 1.40.2 + text2vec-transformers bge-small-en-v1.5, MLflow 3.17.2 sqlite, Python 3.12
+ uv, Astro 7, Node 22, Weavit fork); Project structure (`compose.yaml`, `contracts/`, `packages/datalab/` (2A),
`templates/project/` (2A), `projects/<name>/`, `app/` (2B), `tools/weavit-ui/`); Layer responsibilities (infra /
shared package / project / app — what each must NOT do: the app never writes, projects never hardcode ports);
Data flow (project → datalab → Weaviate/MLflow → app); Key domain concepts (project, card, run, collection);
State machines: project `status` idée → en cours → conclu | abandonné (any → abandonné), and the cross-side
contracts copied from `IMPLEMENTATION_PLAN.md`. Later phases append code extracts.

#### `decisions.md` (NEW) — ADR format from `rules/shared/documentation.md`, dated 2026-11-03
ADRs: (1) Astro over Next.js / Vite+React / Streamlit for the app (spike results); (2) collection prefix + `project`
tag over Weaviate multi-tenancy (schemas differ per config); (3) one env per project + shared package as a path
dependency (projects have conflicting deps); (4) distinct fixed ports to coexist with Demo-RAG + `DATALAB_` env
prefix; (5) Weavit UI as a "fork libre" submodule (drift accepted, #5); (6) embeddings by the Weaviate
`text2vec-transformers` module, English-only model in v1 (user-approved cut D-5; multilingual tracked in #6). Each with Context / Decision / Alternatives / Consequences.

## Tests (Phase 1 acceptance)

| Test | Given → expected | Source |
|---|---|---|
| `tests/test_compose.py::test_f_4_compose_maps_distinct_host_ports` (pytest, stdlib + subprocess `docker compose config --format json`) | parsed config → weaviate publishes 127.0.0.1:8090→8080 and 127.0.0.1:50052→50051, mlflow 127.0.0.1:5050→5000, no other host port, every `host_ip == "127.0.0.1"` | F-4, D-4 |
| Smoke (manual, record output in the report) | `docker compose up -d` → all healthy; `curl -s -X POST 127.0.0.1:5050/api/2.0/mlflow/experiments/search -d '{}'` → HTTP 200 JSON (settles MLflow allowed-hosts); `curl 127.0.0.1:8090/v1/meta` lists `text2vec-transformers` | F-4, U-13 |
| `pre-commit run --all-files` | passes on the new tree | CI gate |

`tests/test_compose.py` has no project env: run it with `uvx pytest tests/` (stdlib only besides pytest); skip
with a clear reason if `docker` is not on PATH. Phase 2A adds this same command to the CI `checks` job.

## Git
`git init -b main`, add the remote, commit the foundation in one commit (message: why — shared base replacing
per-project stacks). Do not push without the user's go-ahead in the session.

## Done when
All files exist; compose test passes; smoke output recorded; pre-commit green; the submodule resolves
(`git submodule status` shows no leading `-`/`+`).

<!-- plan-validate: READY 2026-11-03 sha256:acfc37875b9e -->
