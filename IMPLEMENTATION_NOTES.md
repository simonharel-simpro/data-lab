# Implementation notes

## Phase 1 — MLflow `experiments/search` with an empty body

- Plan assumed: `curl -X POST 127.0.0.1:5050/api/2.0/mlflow/experiments/search -d '{}'` returns HTTP 200, and a non-200 would mean an allowed-hosts problem to fix in compose.
- Territory was: MLflow 3.17.2 answers 400 `INVALID_PARAMETER_VALUE: Invalid value 0 for parameter 'max_results'` to a POST without `max_results` (Demo-RAG's server on :5000 does the same). Hosts are fine: `{"max_results": 100}` → 200 on 127.0.0.1:5050, and a foreign `Host:` header → 403, so the host check is active and accepts the 5050→5000 mapping.
- I did: no compose change (no `--allowed-hosts` needed); smoke recorded with `{"max_results": 100}`.
- One-off or pattern?: likely recurs — every MLflow REST search (the 2B app's `experiments/search` / `runs/search`) must send an explicit positive `max_results`.

## Phase 2A — uv picks a managed Python 3.14 for `requires-python >= 3.12`

- Plan assumed: Python 3.12 (CI uses setup-python 3.12; pyright `pythonVersion = "3.12"`).
- Territory was: uv prefers its managed interpreters, so `uv sync` in `packages/datalab` built the env on CPython 3.14.3 (3.13 and 3.11 are installed too) while CI runs 3.12.
- I did: added `packages/datalab/.python-version` = `3.12`; the template keeps only `requires-python >= 3.12` as the plan says, so new projects may still get 3.14 locally.
- One-off or pattern?: likely recurs — every new project (3) gets the newest managed Python unless the template also ships a `.python-version`.

## Phase 2A — declared-deps hook needs cwd = the package, not `--project`

- Plan assumed: the recipe runs as `uv run --project packages/datalab python tools/pre_commit_checks/check_declared_dependencies.py`.
- Territory was: the recipe reads `pyproject.toml` / `uv.lock` and scans `src/` relative to the cwd; `--project` does not chdir, so from the repo root it finds no source root (prints "no source root found", exit 1) and never sees the package's manifest.
- I did: `uv run --locked --directory packages/datalab python ../../tools/pre_commit_checks/check_declared_dependencies.py` (`--locked`: lock drift fails instead of rewriting `uv.lock` mid-hook); proved it fails on an undeclared `import reportlab`.
- One-off or pattern?: likely recurs — any vendored layered-linter recipe in a repo with no root project needs `--directory <tree>`.

## Phase 2A — MLflow "delete experiment" is a soft delete

- Plan assumed: the integration test's experiment `datalab-test/<sub>` is "deleted by exact name after".
- Territory was: `delete_experiment` moves it to lifecycle `deleted`; it stays in the store (name reserved) until `mlflow gc`. Each integration run leaves one deleted `datalab-test/t<hex8>` experiment behind (default searches, `ACTIVE_ONLY`, do not return it).
- I did: kept the exact-name delete (no prefix, F-3); no `gc`.
- One-off or pattern?: one-off — the 2B app must keep the default `ACTIVE_ONLY` view so deleted experiments never show.

## Phase 2B — `node --test` coverage counts the test files themselves

- Plan assumed: `node --test --experimental-test-coverage --test-coverage-lines=70 'src/**/*.test.ts'` gates the tested modules at 70 %.
- Territory was: Node 22.23 includes every `*.test.ts` in the coverage table (each ~100 %), inflating the total; it also parses the threshold as an integer (`--test-coverage-lines=99.9` behaves as 99, verified: 99.40 % passed a "99.9" floor).
- I did: added `--test-coverage-exclude='src/**/*.test.ts'` (tightens the oracle, never loosens it); kept 70 (an integer, unaffected). Proven failing: a run covering 41 % exits 1 with "does not meet threshold of 70%".
- One-off or pattern?: likely recurs — every `node --test` coverage floor needs the test-file exclude.

## Phase 2B — `astro dev` detaches from a non-TTY shell

- Plan assumed: `nohup npm run dev & echo $!` gives the dev server's PID to kill.
- Territory was: Astro 7.4.1 daemonizes `astro dev` when stdout is not a TTY: `npm` exits at once and the server runs as a separate process whose PID is printed in the JSON log line ("Dev server running … (pid N)", plus `astro dev stop|status|logs`).
- I did: killed exactly the PID Astro printed (verified by its command line); README mentions `astro dev stop`.
- One-off or pattern?: likely recurs — any agent smoke test of `astro dev` must read the PID from the log, not `$!`.

## Phase 2B — a strict export failure still leaves `dist/` written

- Plan assumed: `DATALAB_STRICT_EXPORT=1 npm run build` "fails the build" when MLflow is down.
- Territory was: the check runs in `astro:build:done`, after the pages are written, so the command exits 1 but `app/dist/` holds the export with "Métriques indisponibles" cards.
- I did: kept the plan (exit code is the gate; the app never deletes files); a showable export is one whose strict build exited 0.
- One-off or pattern?: one-off — if shipping is ever automated, gate on the exit code (or clean `dist/` in the deploy step).

## Phase 2C — the fork's pnpm gate does not run as written under Node 22 / pnpm 11

- Plan assumed: `pnpm install && pnpm typecheck && pnpm test` is green in the fork with its existing scripts.
- Territory was: the fork needs Node >= 22; nvm's Node 22 resolves pnpm 11.1.3 via corepack, which (a) ignores build scripts (electron, esbuild, protobufjs) and writes an untracked `pnpm-workspace.yaml` with `allowBuilds:` placeholders, (b) refuses every `pnpm <script>` with ERR_PNPM_IGNORED_BUILDS (its pre-run deps check), and (c) leaves no Electron binary, so the 6 `src/main/weaviate/*.test.ts` files fail at import ("Electron failed to install correctly"). The lockfile itself is unchanged.
- I did: ran scripts with `pnpm --config.verify-deps-before-run=false <script>` and ran `node install.js` in `node_modules/electron` once (downloads the binary, no dependency or lockfile change) → 17/17 files, 275 tests green. Did not approve builds or commit `pnpm-workspace.yaml` (left untracked, to be excluded or deleted).
- One-off or pattern?: likely recurs — any agent running this fork's gate on Node 22 hits it; pin pnpm (`packageManager`) or document the flags.

## Phase 2C — a blank Host field is saved as `''`, not `undefined`

- Plan assumed: an "empty" `localHost` arrives as `undefined` (accepted, since `connectionManager.ts:86` maps it to `localhost`).
- Territory was: `ConnectionModal.tsx:169` binds the Host input with `set({ localHost: e.currentTarget.value })`, so clearing it persists `''`; `connectionManager.ts:86` (`||`) still treats `''` as `localhost`. Blank ports become `Number('') = 0`.
- I did: kept the plan literally — only `undefined`, `127.0.0.1` and `localhost` are accepted, so a UI profile with a cleared Host gets `skip/host` (safe direction: no auto-connect, never a wrong target). Blank ports (`0`) get `skip/ports` as intended.
- One-off or pattern?: one-off — if a cleared Host should auto-connect, add `''` to the accepted set (and a test); orchestrator's call.

## Phase 3 — Demo-RAG's `GEN_MODEL` is an OpenRouter id, not the DGX model

- Plan assumed: the DGX URL and model come from Demo-RAG's `.env` (`DGX_BASE_URL`, `GEN_MODEL`) into `MINI_RAG_*`.
- Territory was: that `.env` has `GEN_PROVIDER=openrouter` and `GEN_MODEL=deepseek/deepseek-v4.1-flash` (an OpenRouter model id); the DGX id is Demo-RAG's code default `deepseek-v4-flash`, which is also the plan's `gen_model` default.
- I did: copied only `DGX_BASE_URL` → `MINI_RAG_DGX_BASE_URL` in `projects/mini-rag/.env` (gitignored, verified with `git check-ignore`); kept the default `deepseek-v4-flash`. Not confirmed against the server: the DGX on :8000 refused connections during the whole phase.
- One-off or pattern?: likely recurs — any project porting Demo-RAG's LLM settings must read `GEN_PROVIDER` before trusting `GEN_MODEL`.

## Phase 3 — coverage floor in `addopts` breaks `pytest -m integration`

- Plan assumed: pytest `addopts` holds `--cov=mini_rag --cov-fail-under=70 -m 'not integration'`.
- Territory was: with the floor in `addopts`, `uv run pytest -m integration` (2 tests, a slice of the code) fails on coverage even when green; the orchestrator's verify commands (`pytest --cov`, `pytest -m integration`) follow `packages/datalab`'s layout instead.
- I did: same as datalab — `addopts = "-ra --strict-markers -m 'not integration'"`, `[tool.coverage.run] source = ["mini_rag"]`, `[tool.coverage.report] fail_under = 70`; the CI job `pilot` runs `uv run pytest --cov` (floor enforced, failing). Floor unchanged (70).
- One-off or pattern?: likely recurs — the template could carry this coverage block so every project gets the same split.

## Fix Phase 3 (review-2026-11-04) — `Base.astro` also imported `mlflowUri` from `mlflow.ts`

- Plan assumed: fix unit 3.3 touches `mlflow.ts`, `content.config.ts`, `export-guard.ts`, `mlflow.test.ts`; deleting `mlflowUri` from `mlflow.ts` with no re-export shim.
- Territory was: `app/src/layouts/Base.astro:2` imports `mlflowUri` from `../lib/mlflow.ts` (dev footer); deleting it without a shim breaks `astro check`.
- I did: repointed that import to `../lib/config.ts` (one line), honouring "no re-export shim"; `import.meta.env.DEV` there is untouched.
- One-off or pattern?: likely recurs — a planner's "Files" list built from `grep` over `.ts` misses `.astro` importers; include `src/**/*.astro` when listing callers.

## Fix Phase 3 (review-2026-11-04) — the verbatim `Run` schema is stricter than the old parser on `data`

- Plan assumed: the 3.2 zod schema keeps the old `parseRuns` behaviour ("existing tests pass unchanged").
- Territory was: the old parser read a run whose `data` was present but not an object (`null`, a string) as "no metrics"; `.default({ metrics: [] })` only covers an absent `data`, so such a run now throws `unexpected response` and the card shows `unavailable`. Also ±Infinity `start_time` (old `Number(x) || 0` kept it) now becomes 0. No test pinned either; real MLflow omits empty `data` rather than nulling it.
- I did: kept the spec's schema verbatim (fail-loud on a malformed run is the plan's stated direction); no test added for an unspecified behaviour.
- One-off or pattern?: one-off — if `data: null` should stay tolerated, `z.preprocess((d) => d ?? undefined, …)` on `data` plus a test; orchestrator's call.

## Fix Phase 5 (review-2026-11-04) — no section name has an accent, so `missing()` cannot observe NFC

- Plan assumed: 5.1.5 "match an NFD heading against the NFC section name" is observable through a required section.
- Territory was: `SECTIONS_BY_STATUS` names (Objectif, Approche, Enseignements, Suite) are pure ASCII; dropping `.normalize('NFC')` in `sections()` changes no `missing()` result.
- I did: tested the exported `sections()` directly with an NFD heading built from `\u0301` escapes, looked up under its NFC form (`\u00e9` escapes); it goes red when `.normalize('NFC')` is removed.
- One-off or pattern?: one-off.
