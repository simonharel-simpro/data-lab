# data-lab

A local data-science lab: one shared Weaviate (+ English vectorizer) and one MLflow, used by many projects
under `projects/<name>/`, each with its own Python env. A read-only Astro app tells each project's story, and
a Weavit UI fork (submodule) browses the shared Weaviate.

## Prerequisites

- Docker (with the `docker compose` plugin)
- [uv](https://docs.astral.sh/uv/) for Python
- Node 22 via nvm (`nvm use` reads `.nvmrc`)
- Keep the repo on the Linux filesystem (e.g. `~/projects/...`), not under `/mnt/c`: bind mounts, file watching
  and `uv`/`npm` installs are much slower and less reliable across the WSL boundary.

## Clone

```bash
git clone --recurse-submodules https://github.com/simonharel-simpro/data-lab.git
cd data-lab
git config push.recurseSubmodules check   # refuse to push a superproject that points at an unpushed fork commit
```

Already cloned without `--recurse-submodules`? Run `git submodule update --init`.

## Shared infra

```bash
docker compose up -d     # start Weaviate, the vectorizer and MLflow
docker compose ps        # all three should become "healthy" (the vectorizer takes ~30 s)
docker compose down      # stop; data is kept in named volumes
```

> **Warning:** `docker compose down -v` deletes the named volumes, i.e. the Weaviate collections and MLflow
> runs of **every** project. There is no undo.

Every port is bound to `127.0.0.1` only: the services are unauthenticated (auth deferred, #2).

| Service | Host address | Container port | Env var (`.env.example`) |
|---|---|---|---|
| MLflow | `http://127.0.0.1:5050` | 5000 | `DATALAB_MLFLOW_TRACKING_URI` |
| Weaviate REST | `127.0.0.1:8090` | 8080 | `DATALAB_WEAVIATE_HTTP_PORT` |
| Weaviate gRPC | `127.0.0.1:50052` | 50051 | `DATALAB_WEAVIATE_GRPC_PORT` |
| text2vec-transformers | not published | 8080 | — |

Why not 5000 / 8080 / 50051: the Demo-RAG stack already uses them and keeps running side by side (D-4). The
`DATALAB_` prefix keeps a stray `MLFLOW_TRACKING_URI` from sending runs to Demo-RAG.

## Weavit UI

The fork lives in `tools/weavit-ui`. It runs **in the browser** (web mode) or as the desktop app.

```bash
tools/weavit-web.sh              # http://127.0.0.1:3080 — node >= 22; builds on first run
tools/weavit-web.sh --rebuild    # after updating the submodule
```

Web mode creates the `data-lab` profile itself and auto-connects. In dev, each project page links its best run's
collection ("Ouvrir dans Weavit", via the run's `collection` param; `DATALAB_WEAVIT_URL` overrides the address).
The RAG tab's **OpenRouter (deepseek-v4-flash)** preset uses `OPENROUTER_API_KEY` from the root `.env`: the
launcher hands it to the local server, which keeps it in memory and sends it to Weaviate only as the
`X-OpenAI-Api-Key` header. The server listens on 127.0.0.1 only and refuses foreign `Host`/`Origin` headers: it can
delete collections.

Desktop app: build and run it as described in [its README](tools/weavit-ui/README.md), and create once a
**local** connection profile named exactly **`data-lab`** with **HTTP port 8090 AND gRPC port
50052**, both filled in explicitly. An empty gRPC field falls back to 50051 — Demo-RAG's Weaviate — and you get a
split-brain view: REST on data-lab, gRPC on Demo-RAG (F-4).

## New project

```bash
uv run --project packages/datalab datalab-new mini-rag --title "Mini RAG"   # from the repo root
# or install the command once (editable: it finds the repo from the package location)
uv tool install --editable packages/datalab && datalab-new mini-rag
cd projects/mini-rag && uv sync
```

Naming rules: lowercase letters and digits, single dashes between words (`^[a-z][a-z0-9]*(-[a-z0-9]+)*$`), not a
reserved word (`test`, `datalab`, `datalab-test`, `template`, and the YAML words `y n yes no on off true false
null`). An existing `projects/<name>` (even an empty folder or a file) is refused and nothing is written.

The template (`templates/project/`) gives: `PROJECT.md` (the card: `name`, `title`, `status: idée`, `tags`, four
sections to fill), a `pyproject.toml` named `proj-<name>` that depends on `packages/datalab` (editable path dep),
an empty `src/` for your package, `.env.example` and a short README. A non-editable install of `datalab` cannot find
the repo and refuses to run.

In code: `datalab.project.load()` (identity from `PROJECT.md`), `datalab.project.collection_name()` (Weaviate),
`datalab.tracking.tracked_run()` (MLflow run tagged `project=<name>`), `datalab.settings.Settings` (`DATALAB_*`).

## App

A read-only Astro site (`app/`): one page per `projects/<name>/PROJECT.md`, with the project's best MLflow run
(the card's `metric {key, goal}`, among FINISHED runs tagged exactly `project=<name>`). It never writes anything.

```bash
cd app && nvm use && npm ci
npm run dev                          # local live mode: http://127.0.0.1:4321, cards and metrics re-read per request
DATALAB_STRICT_EXPORT=1 npm run build   # showable static export in app/dist/ (fails if MLflow is down)
npm run check && npm test            # astro check + unit tests (line coverage floor 70 %)
```

- **Two modes.** `npm run dev` links run names to MLflow and shows the MLflow URI in the footer. `npm run build`
  freezes the metrics at build time and contains no link to `127.0.0.1` (D-14). Without `DATALAB_STRICT_EXPORT=1`
  a build with MLflow down still succeeds and shows "Métriques indisponibles" on cards with a metric (that is what
  CI does); use the strict flag for any export you show. Note: `astro dev` detaches from a non-interactive shell and
  prints its own PID; stop it with `astro dev stop` (from `app/`) or Ctrl-C in a terminal.
- **MLflow URI:** `DATALAB_MLFLOW_TRACKING_URI` (default `http://127.0.0.1:5050`); `MLFLOW_TRACKING_URI` is ignored.
- **Badge "À compléter : …"** lists what the card still lacks for its status: `idée` needs `## Objectif`;
  `en cours` adds `## Approche`, `data` and `metric`; `conclu`/`abandonné` add `## Enseignements` and `## Suite`.
  A section with only an HTML comment (as in the template) counts as empty.
- **Invalid cards fail the build** with the file named (D-13): unknown `status`, a `name` that breaks the naming
  rules or differs from its folder, a `metric.key` with characters outside `A-Z a-z 0-9 _ . - /`.

## Pilot

`projects/mini-rag` is the end-to-end example (BM25 and vector retrieval over a frozen snapshot of these docs,
answers from an LLM, OpenRouter by default). With the stack up (`docker compose up -d`):

```bash
cd projects/mini-rag && uv sync
echo 'MINI_RAG_LLM_API_KEY=<openrouter-key>' > .env          # gitignored; required (DGX: see .env.example)
for r in bm25 vector; do for k in 3 5; do uv run python -m mini_rag.run --retrieval $r --k $k; done; done
cd ../../app && npm run dev                                   # the mini-rag card: best `score` of the 4 runs
```

The runs land in MLflow under `mini-rag/retrieval` (tag `project=mini-rag`), the chunks in a Weaviate collection
prefixed `MiniRag_`. `--n N` runs the first N questions only: it logs `smoke_*` metrics and tag `smoke=true`, never
`score`, so a smoke run never becomes the card's best run (D-15). A perfect run scores 0.9: 2 of the 20 questions
are unanswerable and "I don't know" counts as missing (D-7).

## Checks

```bash
pre-commit install --hook-type pre-commit --hook-type pre-push
pre-commit run --all-files
uvx pytest tests/        # compose port contract (needs docker on PATH)
(cd packages/datalab && uv run pytest --cov=datalab)   # unit tests, coverage >= 70 %
(cd packages/datalab && uv run pytest -m integration)  # live stack (docker compose up -d)
(cd projects/mini-rag && uv run pytest --cov)         # pilot unit tests, coverage >= 70 %
```
