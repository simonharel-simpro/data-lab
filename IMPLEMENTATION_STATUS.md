# Implementation Status — data-lab

Integration branch: `feat/data-lab` (base `main`). Driven by `/loop-implement` (mode: checkpoint).

| Phase | Title | Status | Branch |
|-------|-------|--------|--------|
| 1 | Foundation (git, compose, tooling, submodule, docs) | ✅ landed 2026-11-04 (/check clean) | `phase-1-foundation` |
| 2A | `datalab` package + project template + `datalab-new` | ✅ landed 2026-11-04 (/check clean) | `phase-2a-datalab-package` |
| 2B | Astro presentation app | ✅ landed 2026-11-04 (/check clean) | `phase-2b-astro-app` |
| 2C | Weavit UI fork: auto-connect (`tools/weavit-ui`) | ✅ implemented 2026-11-04, awaiting /check — fork branch NOT pushed | `phase-2c-weavit-autoconnect` + fork `feat/autoconnect-data-lab` |
| 3 | Pilot project `mini-rag` | pending | — |

## Phase 1 — Foundation
**Implemented:** 2026-11-04 · **Agent:** general-purpose · **Tooling:** ✅ pytest 1 passed; pre-commit (pre-push stage) green
- Files: .gitignore, compose.yaml, .env.example, .nvmrc, contracts/{name_vectors.json,README.md}, projects/.gitkeep, ruff.toml, tools/check_file_size.py, .pre-commit-config.yaml, README.md, ARCHITECTURE.md, decisions.md (6 ADRs), tests/test_compose.py, submodule tools/weavit-ui (v1.2.0)
- Tests: `test_f_4_compose_maps_distinct_host_ports` proves F-4/D-4 — seen red 3 ways ✅
- Smoke: all 3 services healthy; /v1/meta lists text2vec-transformers; MLflow search 200 with `max_results` (see IMPLEMENTATION_NOTES.md)

## Phase 2A — datalab package, template, datalab-new, CI
**Implemented:** 2026-11-04 · **Agent:** general-purpose · **Tooling:** ✅ 40 unit passed (cov 95 %, floor 70), 2 integration passed, pyright 0, pre-commit pre-push green
- Files: packages/datalab/{pyproject.toml,uv.lock,.python-version,src/datalab/{project,settings,tracking,new_project}.py,tests/*}, templates/project/*, tools/pre_commit_checks/check_declared_dependencies.py (+_base,_layout), .github/workflows/ci.yml; modified .pre-commit-config.yaml, README.md, ARCHITECTURE.md, ruff.toml (`src=` for isort)
- Tests: all 31 planned rows implemented + 9 extra tied to plan sentences; each seen red (stubs, then targeted breakage)
- Notes: 3 IMPLEMENTATION_NOTES entries (Python 3.12 pin, hook --directory, MLflow soft delete). `Project.root` = project folder.

## Phase 2B — Astro presentation app
**Implemented:** 2026-11-04 · **Agent:** general-purpose · **Tooling:** ✅ astro check 0/0/0, 43/43 node tests, line coverage 99.4 % (failing floor 70), builds: empty projects ✅, crlf-bom ✅, bad-name fails (D-13) ✅, no loopback links in dist (D-14) ✅
- Files: app/{package.json,package-lock.json,tsconfig.json,astro.config.mjs}, app/src/{content.config.ts,env.d.ts,lib/*,integrations/export-guard.ts,components/Metric.astro,layouts/Base.astro,pages/*}, app/test-fixtures/*; ci.yml `app` job; README, ARCHITECTURE
- `spike-astro/` removed after promotion (plan step; never committed)
- Notes: 3 IMPLEMENTATION_NOTES entries (coverage exclude, `astro dev` detaches, strict build leaves dist/)

## Phase 2C — Weavit UI fork: auto-connect
**Implemented:** 2026-11-04 · **Agent:** general-purpose · **Tooling (fork):** ✅ typecheck 0 errors, vitest 275/275 (10 new)
- Fork files: src/renderer/src/features/connections/{autoConnect.ts,useAutoConnectOnLaunch.ts,autoConnect.test.ts}; App.tsx (+2); README "Fork notes"
- data-lab: submodule pointer → local fork commit (fork push pending user approval)
- Pending: 2 manual GUI checks (profile on 8090/50052 → connects; empty gRPC port → `skip: ports`); fork push + merge into fork main
- Notes: pnpm 11 under Node 22 needs `--config.verify-deps-before-run=false`; a cleared Host is saved as `''` → `skip/host` (fails safe)
