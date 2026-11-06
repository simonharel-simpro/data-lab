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

## 2026-11-05 — Weavit UI in the browser: a web mode in the fork

**Status:** accepted
**Context:** The user wants the app to link straight to a project's Weaviate collection. Weavit UI is an Electron
app, so it has no URL. No maintained self-hosted web UI for Weaviate fits: the closest (a Streamlit app) can only
auto-connect to Weaviate Cloud, defaults to Demo-RAG's ports and ships delete buttons.
**Decision:** Add a web mode to the fork. The renderer only reaches the backend through `window.api` and the main
process touches Electron in three places, so `buildApi(invoke)`, `registerHandlers(register)` and a `StoreHost`
let one `node:http` server (no new dependency) host the same handlers and renderer. It binds 127.0.0.1, checks
`Host`/`Origin`, requires a custom header on every call, and keeps API keys in memory. `?collection=` opens a
collection; the app links to it from the best run's `collection` param, in dev only (D-14). The RAG tab gets an
OpenRouter preset (Weaviate's OpenAI module; the Anthropic module drops a reasoning model's answer), with the key
injected by the server from `OPENROUTER_API_KEY`. The same session upgrades the fork's build to Vite 8.
**Alternatives considered:** Rebuild a browser in the Astro app (a new product to maintain, read-only at first);
the Streamlit app in compose (manual connection every session, third-party code, no deep link); a `weavit://`
protocol handler (fragile under WSL, where the browser and the app run on different sides).
**Consequences:** The fork drifts further from upstream (#5), in a few contained files. Anything on the machine can
reach 127.0.0.1:3080; the header and host checks stop other web pages, not local processes. With the OpenRouter key
loaded, every Weaviate call carries it, so a query using the plain OpenAI provider would send it to OpenAI.

## 2026-11-06 — mini-rag on OpenRouter: an fp8 provider allow-list, endpoint checks at startup

**Status:** accepted (amends 2026-11-05 "OpenRouter as the default LLM endpoint for mini-rag")
**Context:** A code review of the OpenRouter switch found that OpenRouter routes `deepseek/deepseek-v4-flash`
to about fifteen upstream providers running fp4, fp8 or mxfp4 weights, so two runs with the same config could
meet different models. Old DGX `.env` files kept `MINI_RAG_DGX_BASE_URL`, which was silently ignored, so those
runs went to OpenRouter.
**Decision:** On OpenRouter, every request allows only `provider.order=MINI_RAG_OPENROUTER_PROVIDERS` (default
`deepinfra,gmicloud,parasail`) at `quantizations=[MINI_RAG_OPENROUTER_QUANTIZATION]` (default `fp8`), with
`allow_fallbacks=false`. The allow-list is logged as `llm_providers`. OpenRouter's `provider` response field,
counted per answer, becomes the run tag `llm_served_by`. `llm_base_url` is logged without userinfo, query or
fragment. Validation errors hide their input, so the key never shows in a traceback.
Startup refuses three setups, before any I/O: the legacy variable, an OpenRouter URL without a key, and any
other endpoint left on OpenRouter's default model id. The DGX needs no key.
**Alternatives considered:** Letting OpenRouter route (cheapest, not reproducible); a single pinned provider
(tried first: DeepInfra was rate-limited the same day, so every run would have failed); the `quantizations`
filter alone (any fp8 provider, unbounded).
**Consequences:** `config_hash` covers `llm_base_url` and `llm_provider`, so runs from before 2026-11-05 never
share a hash with later ones, even on the same endpoint. "Comparable with DGX runs" means the same model, not the
same config hash. Answers in one run can come from different listed providers; `llm_served_by` shows it, and
a strict comparison filters on it. If all three providers are down, OpenRouter runs fail.

## 2026-11-05 — voice-arch: self-hosted LiveKit + OpenRouter audio

**Status:** accepted
**Context:** `projects/voice-arch` compares three control architectures for an English phone booking agent. It needs
a realtime media server, STT, TTS and an LLM, a budget of 50 $, and it must not disturb the default stack (which
has no LiveKit keys).
**Decision:** (D-1) Every model call goes through OpenRouter with the existing root key `OPENROUTER_API_KEY`,
shared with other tools (500 $ limit); the 50 $ experiment budget is enforced in software (`budget.py`: the sum of
`cost_usd` over the bench and conversation runs in MLflow, a run refuses to start when `spent + estimate >= budget`),
and cost attribution is the key's usage delta around a run, so the key must not be used elsewhere during a run.
(D-2) LiveKit runs self-hosted in the data-lab compose, WebRTC only, every port on 127.0.0.1. (D-19) The service is
under compose profile `voice`: the default `docker compose up -d` is unchanged and needs no LiveKit keys (the key
interpolation uses `:-`, so a missing key never breaks another compose command; the server refuses empty keys at start).
(D-4) Audio goes through the LiveKit `openai` plugins with `base_url` = OpenRouter. The phase-1 spike passed live, so
the planned fallback adapter (`openrouter_adapters.py`) was not written. Per-turn estimate: end-of-turn 0.5 s + STT
0.6 s + LLM 0.45 s + TTS 0.7 s, about 2.2 s, so the 1.2 s latency bar is expected to fail on non-streaming OpenRouter
audio; latency is then reported comparatively, and (#25) tracks a direct streaming STT.
**Alternatives considered:** a dedicated OpenRouter key with a hard limit (cleaner cost attribution, one more secret
to manage; the user chose the shared key); LiveKit Cloud (needs an account and breaks the 127.0.0.1 rule); a custom
httpx adapter for audio from the start (more code than the plugins' `base_url`).
**Consequences:** Cost figures include any concurrent use of the shared key, so they are upper bounds. The
software budget only counts MLflow runs that logged `cost_usd`; a crashed process that never logged is invisible to
it. Stage-2 latency is the sum of four network round trips per turn.
