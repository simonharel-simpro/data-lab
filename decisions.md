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

## 2026-11-06 — Experiment methodology: trouvetou in data-lab

**Status:** accepted
**Context:** voice-arch, built by an autonomous loop, tuned fixes on the eval persona, had a metric dominated by STT
garble, unlogged one-off calls, candidate names inside metric keys and knobs in code. Every data-lab experiment
should follow trouvetou's methodology instead.
**Decision:** Hydra in the template; shared MLflow on 5050, not trouvetou's per-project sqlite (D-1); metric and
`cost_usd` on children only (D-5); experiment `<project>/<experiment.name>`, eval in `<project>/audit`; the grid runs
in-process (D-4); `run.json` + PROJECT.md with strict milestone order, a `redo` that resets later milestones and no
`skipped` status; the test partition is gated and every look counted; the winner lives in run.json and the card's
best is ranked on the frozen split and full data; the budget is shown, not enforced (D-6); one sweep at a time per
server (F-16: parallel sweeps would race on one sqlite-backed MLflow, and a logging failure surfaces as a tracking
error); `project_spend` counts RUNNING runs, unlike `voice_arch/budget.py`, so a crashed sweep's money is not hidden.
**Alternatives considered:** a per-project sqlite store, a role tag instead of nested runs, a `ledger.md` instead of
`run.json`, `--multirun` with Postgres, a hard budget stop.
**Consequences:** one sweep per server at a time; legacy runs stay flat (no parent/child) and keep today's card rule.

## 2026-11-08 — Embedding projector: a Rust sidecar in the Weavit fork

**Status:** accepted (fork PR simonharel-simpro/weavit-ui#2, merged as `a45b206`)
**Context:** Weavit needs a Projection tab that lays out a collection's embeddings in 2D and 3D, with PCA and UMAP,
for up to 100 000 vectors. Measured on 6 cores (WSL), 100k × 384: umap-js takes 16 s for only 5k points; umap-learn
takes 35 s and needs a Python service; in Rust, the Weaviate cursor read takes 5.8 s, exact kNN on PCA-50 17.6 s and
umap-rs (200 epochs) 12–15 s. An HNSW kNN measured recall@15 of 0.36–0.73.
**Decision:** (D-1) The compute runs in a Rust binary, `weavit-projector` (`native/projector/`: umap-rs 0.4.5,
ndarray, rayon), spawned by the host as a sidecar. The host streams vectors to its stdin and reads NDJSON frames
back. (D-2) kNN is exact, by blocked GEMM on PCA-50 coords. (D-3) UMAP runs on PCA-50 and starts from the PCA
components. (D-16) The sidecar emits the PCA-50 coords once per run, so placing a query never projects the dataset
in the host.
**Alternatives considered:** umap-js in a worker (too slow); a umap-learn service (slower, and one more Python
service to run); HNSW (recall too low); a napi addon or WASM in the host (D-1 keeps the compute in a separate
process that the host can kill).
**Consequences:** Building needs a Rust toolchain; `tools/weavit-web.sh` builds the binary and starts the server
even without one. The fork drifts further from upstream (#5). Installers do not ship the binary yet (#29). Host
memory, worst case: about 400 MB of vectors (100 000 × 1024 f32); a second copy of the 100k × p PCA coords in the
placement context of each breadcrumb level; and the prefetched colour and label columns (D-21: every text, boolean,
int and number property, text capped at 200 chars), about 40 MB per text property at 100 000 rows (UTF-16) and
0.8 MB per number or boolean property. The dataset is released on the next read. A Chrome check on 2026-11-08
found two bugs (camera refit, lasso), fixed in fork commit `b027767`. Lasso in 3D is deferred (#31).

## 2026-11-08 — deck.gl for the projection canvas

**Status:** accepted (fork PR simonharel-simpro/weavit-ui#2)
**Context:** The Projection tab draws up to 100 000 points in 2D and in 3D, with picking, colour by property and a
lasso.
**Decision:** deck.gl, which does 2D and 3D in one library and takes binary attributes for 100k points. Exact pins:
`@deck.gl/{core,layers,react,widgets}` 9.3.11, `@luma.gl/core` and `@luma.gl/engine` 9.3.6, `@loaders.gl/core` 4.5.4.
9.3.12 was under two weeks old (`minimumReleaseAge`). `@loaders.gl/core` went from the planned 4.4.5 to 4.5.4 to
satisfy the `~4.5.0` peer of `@loaders.gl/images` 4.5.4, which `@deck.gl/layers` pulls in.
**Alternatives considered:** a 2D scatter library plus a separate 3D renderer (two code paths); hand-written WebGL.
**Consequences:** A large dependency family; the packages move together, so a bump touches every pin.

## 2026-11-08 — Filtered projections capped at the server's offset limit

**Status:** accepted
**Context:** A Weaviate cursor cannot carry a filter, so a filtered read pages by offset, and Weaviate refuses any
page past `QUERY_MAXIMUM_RESULTS` (10 000).
**Decision:** (D-10) A filtered run reads at most 10 000 objects and never requests a page past the offset limit.
The banner states the order basis: "first 10 000 in server order (server limit)". Unfiltered runs use the UUID
cursor and are capped at 100 000.
**Alternatives considered:** raising `QUERY_MAXIMUM_RESULTS` on the shared Weaviate (affects every client); reading
everything by cursor and filtering in the host (reads up to 100k objects to keep a few).
**Consequences:** A filter matching more than 10 000 objects shows only the first 10 000 in server order, not a
sample. Lifting the cap is tracked in #30.

## 2026-11-08 — Metric-aware projection

**Status:** accepted
**Context:** PCA and UMAP work in Euclidean space, but collections may be indexed for cosine, dot, l2-squared,
hamming or manhattan.
**Decision:** (D-19) The metric comes from the vector index config. Cosine collections are L2-normalised in the
host, rows and query vectors alike, before PCA/UMAP and placement; a zero vector is skipped and counted. Every other
metric (dot, hamming, manhattan and unknown strings, U-37) uses raw rows, with the notice "<metric> metric: Euclidean
layout" (none for l2-squared). Hit weights for placing a query: cosine `max(ε, 1 − d)`; otherwise the sign-safe
`(d_max − d) + ε` (U-32).
**Alternatives considered:** always raw rows (cosine layouts dominated by vector norm); a metric-specific UMAP
distance (umap-rs is Euclidean only).
**Consequences:** Non-cosine, non-Euclidean layouts are approximate, and the notice says so.

## 2026-11-08 — Local pre-push hooks in the Weavit fork

**Status:** accepted
**Context:** The fork had no local gate; Rust code arrives with the projector.
**Decision:** (D-17, revised) `.pre-commit-config.yaml` in the fork, at the pre-push stage: typecheck, vitest,
`cargo fmt --check`, `cargo clippy -D warnings`, `cargo xtask lint`. CI stays the gate.
**Alternatives considered:** CI only, the original D-17 (slow feedback on Rust lints).
**Consequences:** `pre-commit` must be installed to use the hooks (fork README). `cargo deny` passes locally with
`native/projector/deny.toml` but is not in the hooks or CI yet.

## 2026-11-08 — View-only colour and label; Run below the root

**Status:** accepted
**Context:** After a lasso, the user works on a breadcrumb level below the full collection. Making colour and label
run inputs would force a re-run to recolour, and editing a root input while below the root is ambiguous.
**Decision:** (D-21) The read prefetches every text, boolean, int and number property (text truncated at 200 chars,
arrays excluded), so Colour and Label are view-only: a change recolours or relabels at once, at any level, with no
spawn. The memory cost is in the sidecar ADR above. (D-20) If only method or dims were edited, Run re-runs the current
level on the same indices. If a root input was edited (filter, limit, vector, tenant), Run asks "this clears the
breadcrumb (N levels)" first; declining sends nothing.
**Alternatives considered:** colour and label as run inputs (a re-run per change); always clearing the breadcrumb
on Run (loses the lasso work).
**Consequences:** Reads carry more data than the layout needs. Text colours and labels are cut at 200 chars.

## 2026-11-08 — Weavit fork hygiene

**Status:** accepted (user decision 2026-11-07; part of fork PR simonharel-simpro/weavit-ui#2)
**Context:** Before adding the projector, `pnpm audit` on the fork reported 98 vulnerabilities, the pnpm 9 CI
install was broken, and the fork had no lint gate.
**Decision:** Electron 37 → 43.8.3 (39 still had 12 open advisories; 45 and later deprecate `safeStorage`, so they
are avoided), electron-builder 26.18.0, zod 4.6.7. An ESLint 10 flat-config gate (hook and CI step). 16 range
overrides kept identical in `pnpm-workspace.yaml` and `package.json#pnpm`, so pnpm 11 locally and pnpm 9 in CI agree.
`packages: ['.']`, which repaired the pnpm 9 CI install. `minimumReleaseAge` of 14 days.
**Alternatives considered:** Electron 39 (12 open advisories); Electron 45+ (`safeStorage` deprecated); auditing
without upgrading.
**Consequences:** `pnpm audit` goes from 98 vulnerabilities to 0, except 2 moderate GHSAs (minimatch, glob) ignored
until #34. The overrides live in two places and must change together. Locally, pnpm 11 needs
`pnpm_config_verify_deps_before_run=false` (`tools/weavit-web.sh` passes the same setting as a flag). A GUI smoke of
Electron 43 on a native display is still pending.

## 2026-11-08 — UMAP repulsion 0.5

**Status:** accepted (ESC-1-1, user 2026-11-08)
**Context:** umap-rs 0.4.5's `step_epochs` applies the "move other" half of each attraction step to a copy that is
dropped, so attraction is half of umap-learn's while repulsion is full. With the defaults, 3 clean blobs smear
together.
**Decision:** `repulsion_strength = 0.5` (`REPULSION_STRENGTH` in `native/projector/src/umap_run.rs`), which
restores the balance: the intra/inter cluster distance ratio is 0.26, against 0.73 with the defaults. The value
compensates for the defect; it was not tuned to pass the test.
**Alternatives considered:** the default 1.0 (smeared clusters); patching or forking umap-rs; another UMAP crate.
**Consequences:** Layouts depend on a workaround for a crate bug. Revisit it if umap-rs fixes `step_epochs` or is
replaced: the compensation would then halve repulsion for nothing.

## 2026-11-08 — Serialize Weaviate index builds with a host-local flock

**Status:** accepted (P-1, user 2026-11-08)
**Context:** Two concurrent mini-rag runs racing `ensure_collection` (#12): B saw A's partial object count as
"incomplete" and deleted A's collection mid-build.
**Decision:** `ensure_collection` runs entirely under `fcntl.flock(LOCK_EX)` on `<tmp>/datalab-index-locks/<name>.lock`,
one lock per collection name. Weaviate is local (127.0.0.1), so the host is the right scope. The reuse check runs
under the lock, so B waits, then sees A's complete collection and reuses it.
**Alternatives considered:** (b) the `filelock` package (also works on Windows; adds a dependency); (c) no lock:
build into a uuid-suffixed collection, then point a Weaviate alias at it.
**Consequences:** `fcntl` is POSIX-only, which is fine on Linux/WSL (ADR 3). Lock files in the OS temp dir are never
removed, which is fine for a local lab. A holder that dies releases the lock with its file descriptor.
