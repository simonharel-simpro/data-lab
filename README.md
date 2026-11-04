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

The fork lives in `tools/weavit-ui` — build and run it as described in [its README](tools/weavit-ui/README.md).

Create once a **local** connection profile named exactly **`data-lab`** with **HTTP port 8090 AND gRPC port
50052**, both filled in explicitly. An empty gRPC field falls back to 50051 — Demo-RAG's Weaviate — and you get a
split-brain view: REST on data-lab, gRPC on Demo-RAG (F-4).

## New project

_Added by Phase 2A (`datalab-new`)._

## App

_Added by Phase 2B (Astro presentation app)._

## Checks

```bash
pre-commit install --hook-type pre-commit --hook-type pre-push
pre-commit run --all-files
uvx pytest tests/        # compose port contract (needs docker on PATH)
```
