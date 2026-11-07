# Implementation Status — data-lab

**v1 (Phases 1–3):** ✅ shipped (PR #11) · 📦 archived 2026-11-05 → [archive/2026-11-04-data-lab-v1/](archive/2026-11-04-data-lab-v1/INDEX.md)
**Review cycle review-2026-11-04 (5 fix phases):** ✅ shipped (PR #16) · 📦 archived 2026-11-05 →
[archive/2026-11-05-review-2026-11-04/](archive/2026-11-05-review-2026-11-04/INDEX.md)

Integration branch: `feat/data-lab` (base `main`). Driven by `/loop-implement` (mode: checkpoint).

| Phase | Title | Status | Branch |
|-------|-------|--------|--------|
| 1 | Foundation (git, compose, tooling, submodule, docs) | ✅ landed 2026-11-04 (/check clean) | `phase-1-foundation` |
| 2A | `datalab` package + project template + `datalab-new` | ✅ landed 2026-11-04 (/check clean) | `phase-2a-datalab-package` |
| 2B | Astro presentation app | ✅ landed 2026-11-04 (/check clean) | `phase-2b-astro-app` |
| 2C | Weavit UI fork: auto-connect (`tools/weavit-ui`) | ✅ landed locally 2026-11-04 (/check clean) — fork push + manual GUI checks pending | `phase-2c-weavit-autoconnect` + fork `feat/autoconnect-data-lab` |
| 3 | Pilot project `mini-rag` | ✅ landed 2026-11-04 (/check clean) — DGX acceptance pending | `phase-3-mini-rag-pilot` |

## Phase 1 — Foundation
**Implemented:** 2026-11-04 · **Agent:** general-purpose · **Tooling:** ✅ pytest 1 passed; pre-commit (pre-push stage) green
- Files: .gitignore, compose.yaml, .env.example, .nvmrc, contracts/{name_vectors.json,README.md}, projects/.gitkeep, ruff.toml, tools/check_file_size.py, .pre-commit-config.yaml, README.md, ARCHITECTURE.md, decisions.md (6 ADRs), tests/test_compose.py, submodule tools/weavit-ui (v1.2.0)
- Tests: `test_f_4_compose_maps_distinct_host_ports` proves F-4/D-4 — seen red 3 ways ✅
- Smoke: all 3 services healthy; /v1/meta lists text2vec-transformers; MLflow search 200 with `max_results` (see [IMPLEMENTATION_NOTES.md](archive/2026-11-05-review-2026-11-04/IMPLEMENTATION_NOTES.md))

## Phase 2A — datalab package, template, datalab-new, CI
**Implemented:** 2026-11-04 · **Agent:** general-purpose · **Tooling:** ✅ 40 unit passed (cov 95 %, floor 70), 2 integration passed, pyright 0, pre-commit pre-push green
- Files: packages/datalab/{pyproject.toml,uv.lock,.python-version,src/datalab/{project,settings,tracking,new_project}.py,tests/*}, templates/project/*, tools/pre_commit_checks/check_declared_dependencies.py (+_base,_layout), .github/workflows/ci.yml; modified .pre-commit-config.yaml, README.md, ARCHITECTURE.md, ruff.toml (`src=` for isort)
- Tests: all 31 planned rows implemented + 9 extra tied to plan sentences; each seen red (stubs, then targeted breakage)
- Notes: 3 [IMPLEMENTATION_NOTES](archive/2026-11-05-review-2026-11-04/IMPLEMENTATION_NOTES.md) entries (Python 3.12 pin, hook --directory, MLflow soft delete). `Project.root` = project folder.

## Phase 2B — Astro presentation app
**Implemented:** 2026-11-04 · **Agent:** general-purpose · **Tooling:** ✅ astro check 0/0/0, 43/43 node tests, line coverage 99.4 % (failing floor 70), builds: empty projects ✅, crlf-bom ✅, bad-name fails (D-13) ✅, no loopback links in dist (D-14) ✅
- Files: app/{package.json,package-lock.json,tsconfig.json,astro.config.mjs}, app/src/{content.config.ts,env.d.ts,lib/*,integrations/export-guard.ts,components/Metric.astro,layouts/Base.astro,pages/*}, app/test-fixtures/*; ci.yml `app` job; README, ARCHITECTURE
- `spike-astro/` removed after promotion (plan step; never committed)
- Notes: 3 [IMPLEMENTATION_NOTES](archive/2026-11-05-review-2026-11-04/IMPLEMENTATION_NOTES.md) entries (coverage exclude, `astro dev` detaches, strict build leaves dist/)

## Phase 2C — Weavit UI fork: auto-connect
**Implemented:** 2026-11-04 · **Agent:** general-purpose · **Tooling (fork):** ✅ typecheck 0 errors, vitest 275/275 (10 new)
- Fork files: src/renderer/src/features/connections/{autoConnect.ts,useAutoConnectOnLaunch.ts,autoConnect.test.ts}; App.tsx (+2); README "Fork notes"
- data-lab: submodule pointer → local fork commit (fork push pending user approval)
- Pending: 2 manual GUI checks (profile on 8090/50052 → connects; empty gRPC port → `skip: ports`); fork push + merge into fork main
- Notes: pnpm 11 under Node 22 needs `--config.verify-deps-before-run=false`; a cleared Host is saved as `''` → `skip/host` (fails safe)

## Phase 3 — Pilot project mini-rag
**Implemented:** 2026-11-04 · **Agent:** general-purpose · **Tooling:** ✅ 41 unit (cov 89.8 %, floor 70), 2 integration (bm25, vector) vs live Weaviate, pyright 0, ruff, pip-audit 0 vulns, pre-commit pre-push green
- Files: projects/mini-rag/{PROJECT.md,README.md,.env.example,pyproject.toml,uv.lock,data/corpus/*,data/questions.jsonl,src/mini_rag/*,tests/*}; ci.yml `pilot` job; declared-deps hook for mini-rag; README, ARCHITECTURE; app G-8 test
- **Acceptance pending:** the DGX LLM (port 8000) was down during the whole phase — the 4 real runs + card check are not done. One live FAILED run (`bm25-k3`, smoke) exists in MLflow `mini-rag/retrieval`; collection `MiniRag_t2v_bge_small_en_v1_5_w120o20_9e8526f5` built.
- To finish: `cd projects/mini-rag && for r in bm25 vector; do for k in 3 5; do uv run python -m mini_rag.run --retrieval $r --k $k; done; done`, then check the card in `npm run dev` and `npm run build`. Model id `deepseek-v4-flash` unconfirmed.

## Pending (carried over from the archived plans)

- **Phase 2C:** push the Weavit fork (`feat/autoconnect-data-lab`), merge it into the fork's `main`, and run the
  2 manual GUI checks (profile on 8090/50052 connects; an empty gRPC port gives `skip: ports`).
- **Phase 3:** the acceptance run on the DGX is replaced by OpenRouter (default since PR #17, ADR 2026-11-05). The
  smoke run `--n 1` was green on 2026-11-05; the full bm25/vector × k 3/5 sweep runs on OpenRouter.
- **Review cycle:** the validation reads GAPS FOUND only because bandit and radon are not installed (a decision
  still open); the deferred items are tracked in #12, #13 and #14.

# voice-arch — LiveKit voice-agent architecture experiment

Integration branch: `feat/voice-arch` (base `main`). Driven by `/loop-implement` (mode: autonomous, review chain: off).
Plan: `IMPLEMENTATION_PLAN.md` + `IMPLEMENTATION_PLAN_PHASE_{1,2,3}.md` (READY stamps).

| Phase | Title | Status | Branch |
|-------|-------|--------|--------|
| 1 | Infra, gates, OpenRouter audio, stage-1 bench | ✅ landed on feat/voice-arch @ fd114c3 (/check clean, fix-check 2 iter) | `phase-1-infra-bench` |
| 2 | Booking domain + architectures A/B/C + worker | ✅ landed on feat/voice-arch @ 7fbfe3b (/check clean, fix-check 1 iter) | `phase-2-booking-archs` |
| 3 | Simulated caller, sweep runner, scoring, decision | ✅ landed on feat/voice-arch @ 0e69038 (/check clean; live call ESC-3-2; sweeps await user) | `phase-3-caller-runner` |

## voice-arch Phase 1 — Infra, gates, OpenRouter audio, stage-1 bench
**Implemented:** 2026-11-06 · **Agent:** python-fastapi (3 dispatches: A scaffold/infra/core, B bench/tools/docs, C D-17 caller default)
**Tooling:** ruff ✅ · pyright 0 · lint-imports 1/1 kept · pytest 82 passed (3 integration deselected), coverage 88.3 % (floor 70) · pre-push hooks all pass · live spike 3/3
- Stage-1 bench (MLflow `voice-arch/bench`, 0.17 $): STT `assemblyai/universal-3-6-pro` (4/40 errors, p50 0.61 s), TTS `deepgram/aura-2` (TTFB p50 0.38 s), LLM `google/gemini-3.5-flash-lite` (20/20, TTFT 0.82 s); per-turn sum ≈ 2.3 s (> 1.2 s bar, as planned, #25)
- Escalations: ESC-1-1 resolved (plan scoring kept); ESC-1-2 open, reversible: caller model provisionally `anthropic/claude-haiku-5.5` (user to confirm)
- Deferred to the user (approved deviation): browser smoke (README runbook); LiveKit healthcheck unverified until first `--profile voice up`
- Deviations logged in IMPLEMENTATION_NOTES.md (fields punctuation fix, extra modules seams/candidates/bench_runs, direct mlflow/pydantic-settings pins)

## voice-arch Phase 2 — Booking domain + architectures A/B/C + worker

**Implemented:** 2026-11-06 · **Agent:** python-fastapi · **Tooling:** ✅ ruff, pyright, lint-imports, pytest 185 passed, pre-push hooks

- ✅ Pure domain `booking/` (record, calendar, actions, instructions); `arch.py`, `result.py`
- ✅ `agents/` (state, tools, arch_a orchestrator, arch_b TaskGroup, arch_c + call record, registry)
- ✅ `worker.py` (AgentServer, agent_name booking-agent) + pure `worker_logic.py`
- ✅ Live text-mode integration: A, B, C each pass the clean caller and U-18 slot change (6/6)
- ⏳ Browser call per arch — deferred to the user (recorded deviation, VA-16)

Open escalations: ESC-1-2 (caller model), ESC-2-1 (provider pin vs gemini-3.5-flash-lite; worker unpinned provisionally).
Deviations in IMPLEMENTATION_NOTES.md: worker_logic split, unpinned LLM, non-awaited step-task reply on a user-ended
context copy (Gemini 400), arch C slot updates via apply_choose_slot, caller must wait for the first task question.

## voice-arch Phase 3 — Simulated caller, sweep runner, scoring, decision, human ratings

**Implemented:** 2026-11-06 · **Agent:** python-fastapi · **Tooling:** ✅ pyright, ruff, lint-imports (2 contracts), pytest 272 passed, pre-push hooks, weak_tests 0

- ✅ personas (6, validated at load), caller (LiveKit AgentSession on a self-connected room), call + runner (one MLflow run per sweep, budget check, crash-copy JSONL), naturalness, scoring, decide (D-15 rule), rate
- ❌ Live call: 2 runs (arch A, self_correction) timed out after the address turn — the agent never replied (ESC-3-2); text-mode replay of the same turns works
- ⏳ Full sweeps, `decide` into PROJECT.md, human ratings — deferred to the user (approved)

Open escalations: ESC-3-1 (provider_error outcome counting), ESC-3-2 (live stall; likely coupled with ESC-2-1 unpinned route).

# experiment — trouvetou experiment methodology (`IMPLEMENTATION_PLAN_EXPERIMENT*.md`, loop on `feat/experiment`)

| Phase | Title | Status | Branch |
|---|---|---|---|
| 1 | Contract + ledger, split, tags, trial helpers | ✅ landed on feat/experiment (/check clean, fix-check 1 iter) | `phase-1-contract-ledger` |
| 2 | Hydra gate, ledger hook, wiring, CI matrix | ⏳ pending | — |
| 3 | Hydra template, package name, scaffold-and-gate | ⏳ pending | — |
| 4 | `/experiment` skill | ⏳ pending | — |
| 5 | App stepper + run groups + card best | ⏳ pending | — |

## experiment Phase 1 — Contract + ledger, split, tags, trial helpers

**Implemented:** 2026-11-06 · **Agent:** python-fastapi · **Tooling:** ✅ gate exit 0 (pre-push hooks, pyright 0, ruff, lint-imports 1 kept, pytest 174 passed, coverage 94 %)
- New: `contracts/{EXPERIMENT.md,milestones.json,mlflow_tags.json,run_ledger_vectors.json}`, `datalab/{split,ledger_model,ledger_rules,ledger_ops,ledger_checks,ledger,tags,tracking_queries}.py`, tests `test_split`, `test_ledger`, `test_ledger_io`, `ledger_support`.
- Modified: `datalab/{project,tracking}.py`, `pyproject.toml` (purity contract), tests `test_project`, `test_tracking`, ARCHITECTURE.md, decisions.md (ADR), contracts/README.md, .gitignore.
- Tests: every planned case seen red once (ModuleNotFoundError or a targeted mutation); one exception noted (F-7 double cost log by design).
- Deviations: see IMPLEMENTATION_NOTES.md "experiment Phase 1" (extra `ledger_checks.py`/test split for size, extra refusals, queries not HTTP-retry bounded, `test_tracking.py` 332 lines).
