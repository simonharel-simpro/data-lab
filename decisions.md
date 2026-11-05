# Decisions

## 2026-11-03 — Astro for the presentation app

**Status:** accepted
**Context:** Each project needs a readable page (card + best MLflow run), live in dev and as a showable static
export, maintained by one person. A throwaway spike (`spike-astro/`) validated Astro content collections over
`projects/*/PROJECT.md` (glob loader), cards and metrics reloaded per request in dev, and metrics frozen at build in
a static export.
**Decision:** Astro 7, static output, no server adapter; the app calls the MLflow REST API directly (D-1).
**Alternatives considered:** Next.js (server runtime and framework weight unneeded for a read-only site);
Vite + React SPA (no build-time content collections, a static export would need hand-rolled data loading);
Streamlit (needs a running Python server, no static export, weak for long-form project narratives).
**Consequences:** A Node 22 toolchain lives beside Python. No server means no live mode outside `astro dev`; the
static export shows metrics as of build time.

## 2026-11-03 — Collection prefix + `project` tag over Weaviate multi-tenancy

**Status:** accepted
**Context:** Many projects share one Weaviate; their data must not mix, and each project's schema differs per
configuration (chunking, vectorizer, properties).
**Decision:** One collection per project configuration, named `<Pascal>_<parts>_<hash8>` with the hash over
`json.dumps([name, *parts])`; MLflow runs carry an exact `project` tag (D-2).
**Alternatives considered:** Weaviate multi-tenancy (one schema shared by all tenants of a collection — does not
fit per-config schemas); one Weaviate instance per project (the per-project stacks this repo replaces).
**Consequences:** Isolation is by convention, not enforced by Weaviate; the app and tests filter on exact names
and tags. Collection names are opaque, so tooling must derive them through `datalab`.

## 2026-11-03 — One env per project, shared package as a path dependency

**Status:** accepted
**Context:** Projects have conflicting dependencies (OCR stacks, RAG stacks, ontology tools), yet must share
settings, naming and tracking conventions.
**Decision:** Each `projects/<name>/` is its own uv project; `packages/datalab` is consumed as a path dependency.
No root Python project exists (root tooling is stdlib-only, run with `uvx`).
**Alternatives considered:** A single uv workspace (one lock forces one resolution for all projects); copying the
helpers into each project (drift).
**Consequences:** One `uv sync` per project; a `datalab` change reaches projects on their next sync. Root hooks
cannot `uv run`, so they call `python` directly.

## 2026-11-03 — Distinct fixed ports and a `DATALAB_` env prefix

**Status:** accepted
**Context:** Demo-RAG's stack already runs on 127.0.0.1:5000 / 8080 / 50051 and must keep running. A wrong port
silently sends runs or queries to the other stack — including a split-brain Weaviate (REST on one, gRPC on the
other, F-4) or runs logged through an inherited `MLFLOW_TRACKING_URI` (F-5).
**Decision:** data-lab publishes 5050 (MLflow), 8090 (Weaviate REST) and 50052 (Weaviate gRPC), all on 127.0.0.1;
every setting is read from `DATALAB_*` env vars (D-4). A compose test guards the mapping.
**Alternatives considered:** Dynamic ports (unpredictable for the Weavit profile and bookmarks); stopping
Demo-RAG (breaks ongoing work); unprefixed `MLFLOW_TRACKING_URI` (picked up from the shell by accident).
**Consequences:** Ports live in several places (compose, `.env.example`, Python settings, app, Weavit profile);
parity tests guard them (G-10).

## 2026-11-03 — Weavit UI as a "fork libre" submodule

**Status:** accepted
**Context:** Browsing the shared Weaviate needs a UI that auto-connects to the data-lab profile; upstream Weavit
has no such feature and an upstream release first would delay v1 (S-14, kept by the user).
**Decision:** Fork `weavit-ui` to `simonharel-simpro/weavit-ui`, attach it at `tools/weavit-ui` as a git submodule
(`push.recurseSubmodules check`), and patch the fork freely.
**Alternatives considered:** Upstream contribution first (slower); vendoring a copy (loses history and rebase
path); no UI (Weaviate has no built-in browser).
**Consequences:** Drift from upstream is accepted; periodic rebase is tracked in #5. Clones need
`--recurse-submodules`.

## 2026-11-03 — Embeddings by Weaviate `text2vec-transformers`, English-only in v1

**Status:** accepted
**Context:** Projects need vector search without each one running its own embedding service. The user approved
an English-only model for v1 (D-5, AskUserQuestion 2026-11-03); some projects are French.
**Decision:** Run `semitechnologies/transformers-inference:baai-bge-small-en-v1.5-1.13.3` (pinned, CPU) as the
Weaviate `text2vec-transformers` module; `DEFAULT_VECTORIZER_MODULE` stays `none` so collections opt in and
bring-your-own-vectors remains possible. The model id is part of the collection hash (U-13).
**Alternatives considered:** A multilingual model (larger, slower on CPU; tracked in #6); embedding client-side
in each project (duplicated code and models); a hosted embedding API (network dependency, cost, data leaves the
machine).
**Consequences:** French projects get weaker vector search or bring their own vectors. Changing the model means
new collections, not an in-place migration.

## 2026-11-05 — OpenRouter as the default LLM endpoint for mini-rag

**Status:** accepted
**Context:** The pilot depended on the user's LAN DGX, whose availability the user doubts. Runs must still be
reproducible and comparable with earlier DGX runs.
**Decision:** Default `MINI_RAG_LLM_BASE_URL` to `https://openrouter.ai/api` (OpenRouter's Anthropic Messages
endpoint, so the `anthropic` SDK and the generator are unchanged) with `deepseek/deepseek-v4-flash`, the same model
the DGX serves. `MINI_RAG_LLM_API_KEY` is required (`SecretStr`, from the gitignored `.env`); the DGX stays one
override away. The endpoint is logged as the `llm_base_url` param and is part of `config_hash`; the key never is.
**Alternatives considered:** Keep the DGX as default (the reliability problem stays); OpenRouter's
OpenAI-compatible API (a second SDK and a rewrite of the generator); `anthropic/claude-haiku-5.5` as default
(better answers, but no longer comparable with DGX runs).
**Consequences:** Questions and retrieved passages (a snapshot of this repo's public docs) leave the machine, and
runs cost OpenRouter credits (a few cents per sweep). OpenRouter may route to different upstream providers, so
determinism is weaker than on the DGX.
