# Implementation Plan — platform split, steps 1 + 2 (standalone `datalab` + Claude plugin)

**Date:** 2026-11-10 · **Phases:** 2 · **Base:** `develop` @ `f005eda` · **Integration branch:** `feat/platform`
**Source:** conversation 2026-11-10 (platform vs experiments), simplicity review (fable), resilience + spec-gap audits.

> ℹ️ 1 feature cycle shipped since the last architecture review (2026-11-08): exploration (PR #44). Consider
> `/review-architecture` soon.

**Goal:** a second developer runs experiments in their **own repo** (a *workspace*), outside data-lab, reusing the
`datalab` package (installed from git) and the `/experiment` skill (a Claude Code plugin served by a marketplace in
this repo). Simon keeps working inside data-lab unchanged.

Per-file specs live in `IMPLEMENTATION_PLAN_PLATFORM_PHASE_{1,2}.md`; each is self-contained.

| Phase | Title | Agent | Depends on | Files (new / modified) |
|---|---|---|---|---|
| 1 | Standalone `datalab`: workspace marker, packaged resources, `datalab-new` outside data-lab | `python-fastapi` | — | 3 / ~12 |
| 2 | Plugin `datalab` + marketplace, `/datalab:experiment` with portable paths | `general-purpose` | 1 (`python -m datalab.resources`, `datalab.toml`) | 4 / ~14 |

Order: the skill rewrite calls `python -m datalab.resources`, which Phase 1 creates, so the package ships first.

## Scope Analysis

| Feature | Layers touched | New files | Modified files |
|---|---|---|---|
| Standalone datalab | `datalab` package (project, new_project, ledger_model), hatch build, template docs | `datalab/resources.py`, `datalab.toml`, `tests/test_resources.py` | `project.py`, `new_project.py`, `ledger_model.py`, `pyproject.toml`, tests, template `README.md`, `ARCHITECTURE.md`, `decisions.md` |
| Plugin | Claude assets, docs, user-facing strings | `.claude-plugin/marketplace.json`, `plugins/datalab/.claude-plugin/plugin.json`, `tests/test_plugin.py` | skill moved + rewritten, `README.md`, contracts docs, template strings + test, `new_project.py` message, `ARCHITECTURE.md` |

## Scope Decisions

| # | Type | What | Tracker | Approved |
|---|------|------|---------|----------|
| D-1 | defer | trouvetou and the 9 ds-* agents stay out of the plugin until the user reviews trouvetou; the skill keeps dispatching the bare `ds-*` names installed at user level | #47 | user, AskUserQuestion 2026-11-10 |
| D-2 | defer | reusable hooks + CI for outside workspaces: outside data-lab `datalab-new` skips wiring and says so | #48 | — |
| D-3 | defer | workspace template repo and moving mini-rag / voice-arch out | #49 | — |
| D-4 | decision | the repo stays private at `https://github.com/simonharel-simpro/data-lab` (the dev is added as collaborator); the URL is one constant `DATALAB_GIT_URL` | — | user, AskUserQuestion 2026-11-10 |
| D-5 | decision | plugin `datalab`, marketplace `data-lab`; the skill becomes `/datalab:experiment` and every in-repo mention follows | — | — |
| D-6 | decision | infra stays local: the second dev clones data-lab and runs `docker compose up -d` there | — | — |
| D-7 | decision | release channel = `main` (GitHub default branch); `develop` is integration only. Outside projects pin the installed datalab commit, else `branch = "main"` | — | — |
| D-8 | decision | contracts and template stay at the repo root (single source); the wheel carries copies via hatch `force-include`; `datalab.resources` picks the checkout for editable installs, the packaged copy otherwise | — | — |
| D-9 | decision | workspace = nearest regular file `datalab.toml` walking up from the start path; "inside data-lab" = that workspace holds `packages/datalab/` + `compose.yaml` (never the install mode) | — | — |

## Existing Equivalents

| Mechanism | Existing code | Plan |
|---|---|---|
| Claude skill | `.claude/skills/experiment/{SKILL.md,references/*}` | moved into `plugins/datalab/skills/experiment/` |
| Distribution of Claude assets | trouvetou `team/install.sh` + granby copy into `~/.claude` | not reused: the plugin is the native channel |
| Checkout root | `datalab.project.repo_root()` (package-file walk, F-10) — also `projects/voice-arch/src/voice_arch/settings.py:20` | kept; `workspace_root(start)` added beside it |
| Contract loading | `ledger_model.contract()` → `repo_root()/contracts/milestones.json` | via `datalab.resources.contract_path` |
| Template copy | `new_project._build` → `root/templates/project` | via `datalab.resources.template_dir` |
| Non-interactive subprocess | `new_project._uv_lock` (no shell, timeout 300 s, captured output) | hardened: stdin closed, git prompts off |
| Root tests gate | `.pre-commit-config.yaml` `gates-root` (pre-push, no `files:` filter) + `ci.yml` | hosts `tests/test_plugin.py` |

## Simplicity Review

Before → after: 2 phases → 2 phases (reordered) · 11 mechanisms → 8 (reviewer: fable, 2026-11-10)

| # | Action | Class | What | Disposition |
|---|--------|-------|------|-------------|
| S-1 | add | — | the skill hard-codes `packages/datalab`, `tools/`, `contracts/`: rewrite to project-env + `datalab.resources` | applied, Phase 2 |
| S-2 | add | — | wheel test must use `uv build --wheel` (plain `uv build` fails via sdist) | applied, Phase 1 |
| S-4 | keep | — | two-way resource lookup beats physically moving contracts/template | applied (D-8) |
| S-5 | add | — | keep `repo_root()`; add `workspace_root()` | applied (D-9) |
| S-6 | add | — | marker walk starts at `start`, not cwd | applied, Phase 1 |
| S-8 | add | — | outside-scaffold test injects `lock`; never the GitHub URL in tests | applied, Phase 1 |
| S-9 | simplify | mechanism | one `<ws>/ruff.toml` written if absent instead of a per-project copy | applied |
| S-10 | simplify | mechanism | no release tag / version bump; outside source pins the installed commit (F-2) | applied (D-7) |
| S-11 | drop | mechanism | no `claude plugin validate` CI step; Phase 2 exit check runs it once | applied |
| S-12 | simplify | mechanism | trimmed root plugin test | applied, Phase 2 |
| S-13 | add | — | data-lab's `.claude/settings.json` unchanged; README documents install + `--plugin-dir` | applied, Phase 2 |
| S-14 | add | — | missed `/experiment` mentions (contracts README, ledger_ops comment, template test) | applied, Phase 2 |
| S-15 | simplify | mechanism | F-6 contract-version handshake replaced by the skill's "update datalab" message on a missing module | applied, Phase 2 |

## Cross-phase dependencies

Phase 1 produces, Phase 2 consumes: `python -m datalab.resources <contracts file>` (absolute path, rc 0; unknown → rc 2),
the root `datalab.toml`, the outside bootstrap command (README §Create a project, written in Phase 1), and
`datalab-new`'s final message (Phase 2 only renames `/experiment` in it).

## Mechanical Rules to Enforce

No new linter. The one portable-skill rule (no `packages/datalab`, `tools/`, bare `contracts/` path; links stay inside
the plugin) is mechanical but repo-specific: it ships as `tests/test_plugin.py` in Phase 2, run by `gates-root`.

## CI Gate Surface

| Gate | Laid by | At phase |
|---|---|---|
| Hook runner + format/lint/type + secrets + dep-audit + CI parity | existing (`.pre-commit-config.yaml`, `ci.yml`) | already present |
| datalab tests + coverage floor 70 | existing `gates-datalab` / CI `checks` | Phase 1 extends it (new tests) |
| Network tests (`-m scaffold`: wheel build, real lock) | existing CI `checks` scaffold step | Phase 1 adds the wheel test there |
| `plugins/` + `.claude-plugin/` (JSON/Markdown) | existing `gates-root` (pytest `tests/`) | Phase 2 (`tests/test_plugin.py`) |

No new language tree. **Verification at release:** `/loop-implement` Step 10 runs the gate inventory before the PR.

## Failure Modes (resilience)

Trust boundaries crossed: filesystem · subprocess (`uv lock`, `uv build`) · network (private git repo) · package data.

| # | Failure mode | Dimension | Required handling | Required test | Phase |
|---|---|---|---|---|---|
| F-1 | `uv lock` on the private git dep waits on a credential prompt | auth / subprocess | `stdin=DEVNULL`, env `GIT_TERMINAL_PROMPT=0`, `GCM_INTERACTIVE=never`; auth-looking stderr → `ProjectError` naming the URL + `gh auth setup-git` | `test_f1_uv_lock_runs_non_interactive`, `test_f1_auth_failure_is_classified` | 1 |
| F-2 | outside lock takes data-lab HEAD while the template came from the installed commit | contract | render `rev = <commit_id>` from the installed dist's `direct_url.json`; none → `branch = "main"` + stderr notice | `test_f2_outside_source_pins_installed_commit`, `test_f2_no_direct_url_uses_main_and_warns` | 1 |
| F-3 | no runnable "create a project" step outside data-lab | config | README bootstrap `uvx --from "git+<URL>#subdirectory=packages/datalab" datalab-new <name>`; the skill points to it | `test_f3_readme_has_outside_bootstrap` (P1), `test_skill_missing_project_points_to_readme` (P2) | 1, 2 |
| F-4 | wiring reads/rewrites a foreign workspace's CI files or aborts on their absence | partial failure | outside: neither `wiring.plan` nor `wiring.apply`; print the #48 notice; exit 0 | `test_f4_outside_scaffold_never_touches_user_ci`, `test_f4_outside_without_ci_files_succeeds` | 1 |
| F-5 | marker walk picks a stray marker, a directory, or never ends | input / fs | regular files only, from `start.resolve()` to `/`; none → `ProjectError` naming start; success message names the workspace | `test_f5_nearest_marker_wins`, `test_f5_marker_dir_ignored`, `test_f5_no_marker_raises`, `test_f5_success_message_names_workspace` | 1 |
| F-7 | editable install reads a stale packaged contract copy | state | checkout first when `repo_root()` succeeds, else package data; missing file → error, no cross-fallback | `test_f7_editable_prefers_checkout`, `test_f7_wheel_layout_uses_package_data`, `test_f7_missing_file_raises` | 1 |
| F-8 | skill link escapes the plugin dir (breaks once installed in the plugin cache) | config | every relative link resolves inside `plugins/datalab`; contracts only via `datalab.resources` | `test_skill_links_stay_in_plugin` | 2 |
| F-9 | Hydra gate silently skipped inside data-lab | observability | skill runs from the workspace root; inside data-lab the gate is mandatory, outside it is skipped with the #48 notice | `test_skill_hydra_gate_guarded_by_checkout` | 2 |
| F-10 | `<ws>/ruff.toml` written before a failed lock or clobbering a user file | partial failure | written only after the rename, with exclusive create; existing file kept and reported | `test_f10_failed_lock_leaves_no_ruff_toml`, `test_f10_existing_ruff_toml_untouched` | 1 |

Each mode above is a phase acceptance criterion: its handling AND its test ship in the named phase.

## Unspecified Behaviors (spec-gap)

Decision points: workspace resolution · inside/outside detection · resource precedence · ruff.toml creation · skill paths.

| # | Behavior (was unstated) | Decided resolution | Required test | Phase |
|---|---|---|---|---|
| U-1 | inside/outside follows the install or the workspace? | the workspace (D-9), one function `is_datalab_checkout(root)` for dependency, ruff, wiring | `test_u1_inside_decided_by_workspace_not_install` | 1 |
| U-2 | which ref outside projects and the plugin follow | `main` (D-7); exact commit when known (F-2) | `test_f2_*` (above) | 1 |
| U-4 | Phase-1-only skill would call a missing module | skill rewrite lands in Phase 2 only | Phase 2 `test_resources_module_referenced_exists` | 2 |
| U-5 | stray `src/datalab/{contracts,template}` hides the real ones | must never exist in the source tree | `test_u5_source_tree_has_no_packaged_copies` | 1 |
| U-6 | the wheel's template ships `.venv`, caches, `uv.lock` | wheel holds git-tracked files only | `test_u6_wheel_matches_git_ls_files` (scaffold marker) | 1 |
| U-7 | `<ws>/ruff.toml` exists / differs; inside data-lab | kept untouched with a notice; never written inside | `test_f10_existing_ruff_toml_untouched`, `test_u1_*` | 1 |
| U-8 | empty or garbage marker | content ignored | `test_u8_empty_and_garbage_marker_accepted` | 1 |
| U-9 | `load(start)` while cwd is in another workspace | walk from `start`; cwd only as the default | `test_u9_workspace_from_start_not_cwd` | 1 |
| U-10 | `python -m datalab.resources` input/output | bare contracts file name only; absolute path + rc 0; unknown/`../x` → names listed on stderr, rc 2 | `test_u10_resources_cli` | 1 |
