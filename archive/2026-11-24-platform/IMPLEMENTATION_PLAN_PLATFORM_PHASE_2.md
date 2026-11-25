# Phase 2 — Plugin `datalab` + marketplace, `/datalab:experiment` with portable paths

**Agent:** `general-purpose` (Markdown, JSON, one root pytest file, two string edits in Python). **Depends on:** Phase 1
— `python -m datalab.resources <contracts file>` (absolute path, rc 0; unknown name → rc 2), the root `datalab.toml`,
README §New project with the outside bootstrap `uvx --from "git+https://github.com/simonharel-simpro/data-lab#subdirectory=packages/datalab" datalab-new <name>`.
**Plan:** `IMPLEMENTATION_PLAN_PLATFORM.md`.

**Context.** `/experiment` lives in `.claude/skills/experiment/` (SKILL.md + `references/dispatch-briefs.md`,
`references/agent-overrides.md`) and only works inside data-lab: it runs `uv run --locked --project packages/datalab …`
(SKILL.md:31,39,54,73), reads `contracts/EXPERIMENT.md` and `contracts/milestones.json` by repo path (:23,94,133,
dispatch-briefs.md:3) and runs `python3 tools/pre_commit_checks/hydra_gate.py` (:105, agent-overrides.md:32). Goal: the
skill ships in a Claude Code plugin served by a marketplace at this repo's root, and runs in any workspace (a repo with
`datalab.toml` at its root and projects under `projects/<name>/`, each depending on `datalab`).

**Claude Code facts (docs, 2026-11-10).** Plugin = dir with `.claude-plugin/plugin.json` (only `name` required) and
`skills/<n>/SKILL.md` at the plugin root. Marketplace = `.claude-plugin/marketplace.json` with `name`, `owner.name`,
`plugins[{name, source}]`; a relative `source` ("./plugins/datalab") resolves from the marketplace root. Skills are
namespaced `/<plugin>:<skill>`. Installed plugins are copied to a cache, so links must not escape the plugin dir.
`claude plugin validate <path>`; `claude plugin marketplace add <owner/repo>`; `claude plugin install <p>@<m>`;
`claude --plugin-dir <dir>` loads a local plugin for one session.

**Decisions.** D-1: no trouvetou / ds-* agents in the plugin (#47); the skill keeps dispatching bare `ds-*` names, which
the user installs at user level — the README says so. D-5: plugin `datalab`, marketplace `data-lab`, skill
`/datalab:experiment`. S-13: `.claude/settings.json` is **not** changed. D-2: no Hydra gate outside data-lab (#48).

## Files

#### `.claude-plugin/marketplace.json` (NEW, repo root)
`{"name": "data-lab", "owner": {"name": "Simon Harel"}, "plugins": [{"name": "datalab", "source": "./plugins/datalab",
"description": "data-lab experiment methodology: /datalab:experiment (milestones, frozen split, ledger, MLflow)"}]}`

#### `plugins/datalab/.claude-plugin/plugin.json` (NEW)
`{"name": "datalab", "description": "<same sentence>"}` — **no `version`** (D-11: Claude Code then keys releases on
the git commit, so a push to `main` reaches users on `claude plugin marketplace update data-lab`).

#### `plugins/datalab/skills/experiment/**` (MOVE with `git mv` from `.claude/skills/experiment/`, then MODIFY)
Keep the skill `name: experiment` (namespacing makes it `/datalab:experiment`). Rewrite only the lines below; the
methodology text is unchanged.
- **Working directory rule** (new short paragraph near the top): every command runs from the workspace root (the folder
  holding `datalab.toml`); `projects/<name>` paths are relative to it. "Inside data-lab" = the workspace root holds
  `packages/datalab/` **and** `compose.yaml` (same predicate as `datalab.project.is_datalab_checkout`, U-17).
- **Ledger snippets** (:31, :39, :54): `uv run --locked --project projects/<name> python …` (the project env has
  `datalab`). Never `--project packages/datalab`.
- **Contracts** (:23, :94, :133, dispatch-briefs.md:3): read them through
  `uv run --project projects/<name> python -m datalab.resources EXPERIMENT.md` (resp. `milestones.json`), which prints
  the path. If that command fails with `No module named datalab.resources`, stop and tell the expert to run
  `uv lock --upgrade-package datalab` in the project (S-15). Before a project exists, the contract read waits until
  after `datalab-new`.
- **Missing project** (:73): "tell the expert to create it from the workspace root — see README §New project (inside
  data-lab: `uv run --project packages/datalab datalab-new <name>`; another workspace: the `uvx` bootstrap)". The only
  allowed `packages/datalab` mention is inside this sentence, marked as the inside-data-lab form.
- **Hydra gate** (:105, agent-overrides.md:32): "inside data-lab: `python3 tools/pre_commit_checks/hydra_gate.py
  projects/<name>` (mandatory; a missing script is an error). In another workspace: skip it and say `no Hydra gate
  outside data-lab (#48)`" (F-9).
- Milestone ids and sequences come only from `milestones.json` (read through `datalab.resources`); the skill text
  names no sequence of its own (U-12).
- **Agents:** one line: the `ds-*` specialists come from the user-level trouvetou install (#47).
- Links between skill files: relative and inside `plugins/datalab/` only (F-8).

#### `tests/test_plugin.py` (NEW, root tree; stdlib + pyyaml; run by `gates-root`)
| Test | Given → expected | Source |
|---|---|---|
| `test_marketplace_lists_existing_plugins` | `.claude-plugin/marketplace.json` → has `name`, `owner.name`; each `plugins[].source` dir exists and holds `.claude-plugin/plugin.json` whose `name` equals the entry name | D-5 |
| `test_skill_frontmatter` | every `plugins/*/skills/*/SKILL.md` → YAML frontmatter with non-empty `name` and `description` | docs |
| `test_skill_has_no_data_lab_paths` | all `plugins/datalab/**/*.md` → no `--project packages/datalab`, no bare `contracts/` path, `tools/` only on the Hydra-gate line; `packages/datalab` only inside the "inside data-lab" create sentence | S-1 |
| `test_skill_links_stay_in_plugin` | each relative Markdown link / backticked relative file path in `plugins/datalab/**/*.md` → `resolve().is_relative_to(plugins/datalab)` | F-8 |
| `test_skill_hydra_gate_guarded_by_checkout` | SKILL.md → the `hydra_gate.py` line sits under the "inside data-lab" condition, that condition names both `packages/datalab/` and `compose.yaml`, and the skip line names `#48` | F-9, U-17 |
| `test_skill_missing_project_points_to_readme` | SKILL.md names `datalab-new` and "README §New project"; `README.md` has a `## New project` heading | F-3 |
| `test_resources_module_referenced_exists` | SKILL.md uses `python -m datalab.resources`; `packages/datalab/src/datalab/resources.py` exists | U-4 |
| `test_old_skill_location_is_gone` | `.claude/skills/experiment` → does not exist | move |
| `test_plugin_json_has_no_version` | `plugins/datalab/.claude-plugin/plugin.json` → no `version` key | U-13 |
| `test_u11_skill_upgrade_command` | SKILL.md → the missing-module remedy is `uv lock --upgrade-package datalab` | U-11 |
| `test_readme_says_upgrade_after_plugin_update` | README §Claude Code → mentions `uv lock --upgrade-package datalab` after a plugin update | U-12 |

#### Rename `/experiment` → `/datalab:experiment` (MODIFY, exact strings)
- `packages/datalab/src/datalab/new_project.py` final `next:` line: `… uv sync, then run /datalab:experiment`.
- `packages/datalab/src/datalab/ledger_ops.py:103` comment.
- `templates/project/src/__DATALAB_PACKAGE__/eval.py:61` and `split.py:88` messages; `templates/project/tests/test_eval.py:52`
  asserts `"/datalab:experiment"` (the old substring check would not match the new text).
- `templates/project/README.md`, `contracts/EXPERIMENT.md:3`, `contracts/README.md:6`, `tests/TESTING_SCENARIOS.md`
  (EXP-26 and any other `/experiment` row), `ARCHITECTURE.md`.
- `grep -rn "/experiment\b" --include=*.md --include=*.py . | grep -v archive/ | grep -v datalab:experiment` → only
  URL paths like `#/experiments/` remain.

#### `README.md` (MODIFY, §Claude Code)
For any dev: `claude plugin marketplace add simonharel-simpro/data-lab` then `claude plugin install datalab@data-lab`
(needs read access to the private repo + git credentials; refresh with `claude plugin marketplace update data-lab`).
After a plugin update, run `uv lock --upgrade-package datalab` in each project so its contracts match the skill (U-12).
The skill dispatches the `ds-*` agents, installed separately via trouvetou (#47). In data-lab, test unpushed skill
edits with `claude --plugin-dir plugins/datalab` (disable the installed copy if both load).

#### `ARCHITECTURE.md` (MODIFY)
Project Structure gets `.claude-plugin/` and `plugins/datalab/`; a short "Claude plugin" layer: what it holds, what it
must not hold (data-lab-only paths, links outside the plugin), the portable command forms.

## Exit checks
- `pre-commit run --all-files --hook-stage pre-push` green (gates-root runs `tests/test_plugin.py`); template tests green.
- `claude plugin validate .` and `claude plugin validate plugins/datalab` exit 0 (record output in IMPLEMENTATION_STATUS).
- Manual: `claude --plugin-dir plugins/datalab` in data-lab → `/datalab:experiment` is listed; on a scratch project the
  first ledger snippet runs with `--project projects/<name>`.

<!-- plan-validate: READY 2026-11-10 sha256:8b8395802cd6 -->
