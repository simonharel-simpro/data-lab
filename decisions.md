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

## 2026-11-08 — Milestone ids stay data-driven strings

**Status:** accepted (P-10, user 2026-11-08)
**Context:** Milestone ids come from `contracts/milestones.json`, per experiment kind, and both the Python ledger and
the TS app read that file. Python code names a few of them (`dataset`, `features`, `modeling`, `audit`).
**Decision:** The ids the code names are `Final` constants in `datalab.ledger_model` (`DATASET`, `FEATURES`,
`MODELING`, `AUDIT`), tested to exist in the contract. Any other id is validated at runtime by `_require_current` and,
in the app, by the `superRefine` check I-1.
**Alternatives considered:** A generated `Literal` plus drift tests on both sides; won't fix (raw literals).
**Consequences:** A new or renamed milestone in the contract is caught by tests and runtime checks, not by the type
checker. No code generation step to maintain.

## 2026-11-09 — No `from __future__ import annotations` on py312+

**Status:** accepted (P-8, user 2026-11-08)
**Context:** REVIEW 2026-11-08 (§2) found 79 non-test modules without the import and 3 with it, and asked for one
decision (ruff `FA`/`I002`, or a py312+ exemption). Every tree requires Python 3.12, where PEP 604 (`X | None`) and
PEP 585 (`list[int]`) syntax is native in annotations.
**Decision:** The import is not required and new code does not add it. ruff `UP` (selected in the root `ruff.toml`)
keeps annotations in the modern syntax.
**Alternatives considered:** Require it everywhere with ruff `FA`/`I002` (a per-file rule with no benefit on 3.12);
strip the 3 existing imports (churn for no behaviour change).
**Consequences:** Annotations are evaluated at definition time, so a forward reference needs quotes. Existing imports
are harmless and may stay.

## 2026-11-09 — Dev dependency specs stay `>=`; `uv.lock` + `uv sync --locked` is the pin

**Status:** accepted (P-9, user 2026-11-04, confirmed 2026-11-08; #40)
**Context:** REVIEW 2026-11-04 and REVIEW 2026-11-08 (§5) flag the 12 `>=` dev-group specs in
`packages/datalab/pyproject.toml`, `projects/mini-rag/pyproject.toml` and `projects/voice-arch/pyproject.toml`
(`import-linter`). The user decided on 2026-11-04 to keep them and confirmed it on 2026-11-08. Tracker: #40.
**Decision:** Keep the `>=` specs. The pin is each tree's `uv.lock`; the hooks and CI run `uv run --locked` /
`uv sync --locked`, so an unlocked resolution fails instead of drifting.
**Alternatives considered:** `==` like voice-arch's other dev pins.
**Consequences:** `uv lock --upgrade` keeps working without editing the specs. The installed versions are whatever the
lock says, so a reader checks `uv.lock`, not `pyproject.toml`.

## 2026-11-09 — App formatter + linter: prettier + eslint flat config

**Status:** accepted (Fix Phase 6, #13; overrides per ESC-6-1, decided 2026-11-08/09)
**Context:** #13: the Astro app (`app/`) had no formatter and no linter, so style and the "no `any`" / type-import
conventions were enforced by review only.
**Decision:** Six exact dev pins: `eslint` 10.13.0, `@eslint/js` 10.0.1, `typescript-eslint` 8.72.0,
`eslint-plugin-astro` 3.2.1, `prettier` 3.9.10, `prettier-plugin-astro` 1.1.2. `eslint.config.js` (flat config):
`@eslint/js` `recommended` + typescript-eslint `recommended` + `@typescript-eslint/no-explicit-any` and
`@typescript-eslint/consistent-type-imports` (inline `type` specifiers accepted) + eslint-plugin-astro
`flat/recommended`; no rule disabled or overridden. `.prettierrc.json` matches the existing style (width 120, single
quotes, trailing commas, astro parser for `*.astro`). Scripts `lint`, `format`, `format:check`; `lint` and
`format:check` run in the CI `app` job (after `npm audit`) and in the `gates-app` pre-push hook.
Eight exact npm `overrides` (ESC-6-1):

| Package | Override | Published | Why |
|---|---|---|---|
| `minimatch` | 11.0.1 | 2026-10-27 | Fixes GHSA-g3hv-75wg-m249. Exempt from the 14-day rule (ESC-6-1); crosses the dependents' `^10` range |
| `@isaacs/nonrecursive-glob-match` | 1.0.1 | 2026-10-27 | New dependency of minimatch 11.0.1 (oldest release its `^1.0.1` accepts). Exempt (ESC-6-1) |
| `@eslint-community/regexpp` | 4.12.2 | 2025-10-22 | in range; 14-day rule (4.12.3 is 2026-11-08) |
| `globals` | 17.13.0 | 2026-10-01 | in range; 14-day rule (17.14.0 is 2026-11-01) |
| `postcss-selector-parser` | 7.1.7 | 2026-10-20 | in range; 14-day rule (7.2.0 is 2026-11-08) |
| `@typescript-eslint/scope-manager` | 8.72.0 | 2026-10-19 | in range; 14-day rule (8.72.1 is 2026-10-26); same version `typescript-eslint` pins |
| `@typescript-eslint/types` | 8.72.0 | 2026-10-19 | same |
| `@typescript-eslint/visitor-keys` | 8.72.0 | 2026-10-19 | same |

The two exceptions are a dated exception to the 14-day release-age rule (decided 2026-11-08/09; both releases pass
14 days on 2026-11-10): the only minimatch release with the GHSA-g3hv-75wg-m249 fix is newer than 14 days, and
`npm audit --audit-level=moderate` fails without it. The `minimatch` override crosses the `^10` range its dependents
declare. The six in-range overrides keep the whole resolved tree under the 14-day rule.
**Removal condition:** once eslint and typescript-eslint ship releases that depend on a fixed minimatch and are at
least 14 days old, re-pin to them and drop every override whose package is then at least 14 days old in its natural
resolution.
**Alternatives considered:** Biome (no Astro template support at the pinned date); no formatter (lint only, style
stays a review concern).
**Consequences:** One whole-app rewrite commit (`a7e35ab`, prettier `--write`), listed in `.git-blame-ignore-revs`
(`git config blame.ignoreRevsFile .git-blame-ignore-revs`). Land the PR with a merge commit (not squash/rebase) so the
blame-ignore hash survives. The overrides are maintenance debt until the removal condition holds.

## 2026-11-09 — Split leakage property: exhaustive enumeration instead of Hypothesis

**Status:** accepted (user, 2026-11-09)
**Context:** REVIEW 2026-11-08 §4 / migration M1.4 asked for one Hypothesis property on `datalab.split`.
**Decision:** `packages/datalab/tests/test_split_rules.py` enumerates all 4^4 index assignments over a small domain.
The property: a split is accepted iff train and test are both non-empty.
**Alternatives considered:** Hypothesis (a new dev dependency); random sampling of the same small domain.
**Consequences:** No new dependency, and the domain is small enough to be exhaustive rather than sampled. Revisit if
the split rules grow beyond what enumeration covers.

## 2026-11-09 — Experiment kind `exploration` (scoping → eda → report)

**Status:** accepted (user asked for flexible, non-training experiments, 2026-11-09)
**Context:** Experiments in data-lab are often not model training: dataset exploration, an architecture trial, a
benchmark. The ledger only had `training` and `comparison`, both of which require a dataset step, a frozen split,
modeling and an audit, and there is no `skipped` status (U-18).
**Decision:** A third kind, `exploration`, with sequence `scoping, eda, report` (`contracts/milestones.json`). The user
said that a dataset step is not required. The invariants that index a named milestone (I-7, I-10, I-11, I-13, I-14,
I-15) now first check whether that milestone is in the kind's sequence. When it is absent, its fields must be null
(`test_looks` empty). No new invariant ids are added. An exploration may log MLflow runs from project code through
`datalab.tracking`. The template `train`/`eval` refuse an exploration ledger, because they need a frozen split. The
card ranks an exploration's runs by the legacy rule (`app/src/lib/best.ts`). `metric` stays required for every kind.
**Alternatives considered:** optional milestones chosen at scoping (reverses U-18 and weakens I-5/I-6); a
developer-chosen sequence (the contract would guarantee almost nothing); `metric` optional for exploration (a schema
change on both sides plus V-3).
**Consequences:** The I-7 message for a comparison changes wording ("features is not in the comparison sequence, so
features must be null"); only the `I-7:` prefix is pinned. A future kind that drops a milestone gets the same guards
for free. Plan: `archive/2026-11-10-exploration/IMPLEMENTATION_PLAN_EXPLORATION_PHASE_1.md`.

## 2026-11-10 — Standalone datalab: workspace marker + packaged resources

**Status:** accepted
**Context:** A second developer must scaffold and run experiments in their own repo, outside data-lab. `datalab` only
worked as an editable install: `repo_root()` walks up from the package file, and the contracts and the project
template were read from that checkout.
**Decision:** A workspace is the nearest folder with a regular file `datalab.toml` (D-9); inside data-lab means that
workspace holds `packages/datalab/` and `compose.yaml`. Contracts, template and `ruff.toml` stay at the repo root
(single source); the wheel carries copies through hatch `force-include`, and `datalab.resources` reads the checkout for
editable installs and the packaged copy otherwise, with no fallback between them (D-8). Outside projects depend on
datalab by git with `branch = "main"`; their `uv.lock` pins the commit and `uv lock --upgrade-package datalab` upgrades
it (D-7). Hook and CI wiring is skipped outside data-lab (#48).
**Alternatives considered:** moving contracts and template physically into `src/datalab` (rejected: the app imports
them from the repo root, and the template's own gate would then run under datalab's strict pyright); the nearest
`projects/` folder as the workspace (rejected: it matches `~/projects`); a release tag per version (rejected: it
forces relocks and a tag ritual).
**Consequences:** `datalab.toml` must exist at a workspace root. An outside project follows `main` until it upgrades.
A wheel built from a dirty tree must still hold only git-tracked template files (checked by a scaffold test).
Plan: `IMPLEMENTATION_PLAN_PLATFORM_PHASE_1.md`.

## 2026-11-11 — Claude plugin `datalab` + marketplace `data-lab`

**Status:** accepted
**Context:** The `/experiment` skill lived in `.claude/skills/experiment/` and only worked inside data-lab (repo paths
to `packages/datalab`, `contracts/`, `tools/`). A second developer works in their own workspace.
**Decision:** The skill ships in the Claude Code plugin `datalab` (`plugins/datalab/`), served by the marketplace
`data-lab` at the repo root (`.claude-plugin/marketplace.json`), and runs as `/datalab:experiment` (D-5).
`plugin.json` has no `version`: releases are keyed on the git commit, so `claude plugin marketplace update data-lab`
picks up every push to `main` (D-11). The `ds-*` agents stay out of the plugin; users install them at user level via
trouvetou (D-1, #47). No Hydra gate outside data-lab (D-2, #48). `.claude/settings.json` is unchanged; unpushed skill
edits are tested with `claude --plugin-dir plugins/datalab` (S-13).
**Alternatives considered:** copying the skill with an install script like trouvetou's `team/install.sh` (rejected:
the plugin is the native channel and updates come from git); a semver `version` (rejected: it needs a bump per
release, and users miss pushes that skip it).
**Consequences:** The skill text must stay portable, enforced by `tests/test_plugin.py`. Contracts are read through
`python -m datalab.resources`. Projects run `uv lock --upgrade-package datalab` after a plugin update so their
contracts match the skill. Plan: `IMPLEMENTATION_PLAN_PLATFORM_PHASE_2.md`.

## 2026-11-11 — Project-card status is a hand-edited label, not an FSM

**Status:** accepted
**Context:** The card `status` (`idée|en cours|conclu|abandonné`) has no transition map, and ARCHITECTURE.md §State
Machines already says nothing enforces the transitions. Python never reads the field, so it is not in
`contracts/value_sets.json`.
**Decision:** Keep a validated label: membership is checked in `app/src/lib/card.ts`, with no transition map and no
`value_sets.json` entry until a Python reader exists.
**Alternatives considered:** a `TRANSITIONS` const plus a git-diff CI check of card edits; a `card_statuses` entry in
`value_sets.json`.
**Consequences:** Any status change is allowed. Revisit this if a Python tool starts reading the status.

## 2026-11-11 — Size hooks exclude test files and non-Python files

**Status:** accepted
**Context:** 17 test files are over 200 lines and test helpers pass 30 lines. The `file-size` and
`check-function-length` hooks cover only `*/src/` and `tools/` Python. The app `.ts` / `.astro` sources are all under
200 lines, and four small tracked `.sh` scripts exist.
**Decision:** Tests and non-Python files stay out of the size hooks: parametrised scenario tables and fixtures read
better together.
**Alternatives considered:** a higher cap for tests; a size rule for JS/TS sources.
**Consequences:** Those files can grow unbounded and are reviewed by hand.

## 2026-11-11 — Scaffold tests run in CI only

**Status:** accepted
**Context:** `pytest -m scaffold` needs the network (`uv lock` against GitHub and PyPI), so it is deselected locally
(`addopts` in `packages/datalab/pyproject.toml`).
**Decision:** Keep it CI-only. When touching the template, run `pytest -m scaffold` by hand.
**Alternatives considered:** a manual pre-push stage hook that runs it.
**Consequences:** A template break is caught in CI, not at push.

## 2026-11-11 — `gates-root` dev pins have no separate audit

**Status:** accepted
**Context:** `gates-root` pins pyright, pytest, pytest-cov and pyyaml inline in its ad-hoc env, and no `pip-audit`
covers that env.
**Decision:** Accept it. The same four versions are in `packages/datalab/uv.lock`, which CI audits (`ci.yml` pip-audit
step), and these are dev tools only.
**Alternatives considered:** a requirements file for the pins plus a CI pip-audit step.
**Consequences:** If datalab's dev group (`>=`) drifts from the inline pins, the inline ones lose coverage: re-check
when bumping the pins.

## 2026-11-11 — Project isolation is enforced by per-tree envs, not import-linter

**Status:** accepted
**Context:** REVIEW §1 asked for forbidden import-linter contracts (datalab must not import projects, a project must
not import another project).
**Decision:** No contract. Each tree's env holds only itself plus datalab (pyright `venv = ".venv"`, no extra paths;
verified with `find_spec`), so such an import fails pyright, the tests and the declared-deps hook.
**Alternatives considered:** per-tree `forbidden` contracts naming every other project, to be updated on every new
project.
**Consequences:** `templates/project` has no local env, so only the CI scaffold test exercises it.

## 2026-11-11 — Pyright strict covers project-owned tools only

**Status:** accepted
**Context:** Strict mode on all of `tools/` gives about 84 errors, most in vendored harness-recipe scripts
(`check_declared_dependencies.py`, `check_function_length.py`, `check_enum_discipline.py`, `_layout.py`).
**Decision:** Strict on `tools/check_file_size.py`, `hydra_gate.py` and `enum_maps.py` (the `strict` list in
`pyrightconfig.json`). The recipe scripts stay at `basic` so they keep matching their recipes (same reasoning as #41).
Test code (root `tests/` and each tree's `tests/`) also stays at `basic`: tests use fakes and fixtures that strict mode
would force into casts.
**Alternatives considered:** fixing all 84 errors (recipe drift); strict on tests.
**Consequences:** Vendored scripts and tests get basic checking only. Typing fixes for the recipes go upstream.
