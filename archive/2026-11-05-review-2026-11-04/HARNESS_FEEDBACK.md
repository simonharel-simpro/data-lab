# Harness Feedback — data-lab

**Source:** `REVIEW.md` (2026-11-04) + `CI_REVIEW_2026-11-04.md` + `IMPLEMENTATION_NOTES.md`
**Stacks:** Python (generic, uv multi-tree), Astro/TypeScript
**Mode:** dry (no `--repo`) — dedup against open harness issues **not run**; statuses below are "new" pending that check.
**Harness vetted against:** `~/.claude/` (deployed copy).

| # | Bucket | Title | Target file | Status |
|---|--------|-------|-------------|--------|
| 1 | Detect — continuous gate | Flag inert gates in the CI gate inventory: tools configured but never invoked, and `--staged` gitleaks as the CI secrets gate | `recipes/ci/gate-inventory/_gates.py`, `commands/audit-ci.md`, `recipes/ci/python-fastapi/github-ci.yml` | 📝 new (dedup pending) |
| 2 | Detect — continuous gate | Gate inventory: list undeclared depth-2 trees when depth 0–1 already has a manifest | `recipes/ci/gate-inventory/_trees.py` (+ fixture) | 📝 new (dedup pending) |
| 3 | Prevent — plan-time auditor | Sharpen resilience-auditor's RAG/data row: content-keyed derived artifacts, persist-before-remote-log, LLM truncation | `agents/resilience-auditor.md` | 📝 new (dedup pending) |
| 4 | New rule (on-demand) | Python validation regexes: `fullmatch`/`\Z`, never `^…$` with `.match`; cross-language contract vectors carry line-terminator cases | `rules/python-fastapi/security.md` (Input Validation) | 📝 new (dedup pending) |
| 5 | Detect — mechanical gate | Mechanize the documented "max 5 function args" rule with ruff `PLR0913` in the Python baseline | `recipes/linters/python-fastapi-layered/README.md` (ruff baseline) | 📝 new (dedup pending) |

---

## Issue 1 — Flag inert gates in the CI gate inventory: tools configured but never invoked, and `--staged` gitleaks as the CI secrets gate

## What happened
In data-lab, `/audit-ci --report-only` returned **core verdict exit 0**, but several gates are configured and never run:
- Both `packages/datalab/pyproject.toml` and `projects/mini-rag/pyproject.toml` declare `[tool.importlinter]` contracts (`datalab.project` pure, `mini_rag.scoring` pure). `ARCHITECTURE.md` cites them as guarantees. `grep -rn "lint-imports" .github .pre-commit-config.yaml` → **0 hits**.
- `pyright` (config in `pyrightconfig.json` + `[tool.pyright]`) and `pip-audit` (in both dev groups) have **0 invocations** in hooks or CI.
- gitleaks runs as the pre-commit hook `gitleaks git --pre-commit --redact --staged`. CI runs it via `uvx pre-commit run --all-files` on a fresh checkout with **nothing staged**, so in CI it scans nothing.

The audit-ci *agent* noticed these by hand. The deterministic inventory did not, so a less careful run reports green.

## Root cause (in the harness)
- `recipes/ci/gate-inventory/` checks that a hook runner / CI workflow / coverage floor *exist*. It does not cross-check **declared tool config → an invocation**, so "contract declared, no runner" scores as covered.
- It treats a gitleaks pre-commit hook as the secrets gate for CI too, without checking that the hook's mode (`--staged`) means it is a no-op under `run --all-files`.
- `recipes/ci/python-fastapi/github-ci.yml` has no standalone secrets step: `grep -in "leak\|secret"` → 0 hits. Projects that follow the recipe inherit the gap. (CI_REVIEW pointed at this recipe for the fix, but the recipe doesn't have it.)

## Proposed changes
1. `_gates.py`: add an **inert-gate** advisory pass. For each tree, map config markers to their runner command: `[tool.importlinter]` → `lint-imports`; `[tool.pyright]` / `pyrightconfig.json` → `pyright`; `pip-audit` in the deps → `pip-audit`; `[tool.mypy]` → `mypy`. Emit ⚠️ **drift (inert)** when the runner appears in neither hooks nor CI. Add a fixture with a declared contract and no runner.
2. `_gates.py`: when the only CI secrets coverage is a `gitleaks` pre-commit hook whose entry/args contain `--staged` or `protect`, emit ⚠️ **drift (no-op in CI)**.
3. `recipes/ci/python-fastapi/github-ci.yml` (and the other stack CI recipes): add a `gitleaks detect --source . --log-opts=HEAD` (or `gitleaks/gitleaks-action`) step.
4. `commands/audit-ci.md`: one line in the gate matrix explaining "inert", meaning configured but never invoked, and that inert ranks with drift.

## Why it matters
A declared-but-unrun gate is worse than a missing one: docs and reviewers read it as enforced. Here the two purity contracts are the backbone of ARCHITECTURE.md's layering claims, and nothing checks them. It was caught only at the expensive late review, by judgment.

_Filed by /harness-feedback from REVIEW.md of data-lab on 2026-11-04._

---

## Issue 2 — Gate inventory: list undeclared depth-2 trees when depth 0–1 already has a manifest

## What happened
data-lab has `app/package.json` (depth 1) and three Python trees at depth 2: `packages/datalab`, `projects/mini-rag`, `templates/project`. `ci_gate_inventory.py` detected **only `app/`**. Its "PASS — every core gate present or exempt" said nothing about the Python trees, which hold all the product logic. The audit-ci agent caught the blind spot by hand.

## Root cause (in the harness)
`recipes/ci/gate-inventory/_trees.py:82-88` (`_detected`) falls back to depth 2 **only when depth 0–1 holds no manifest and nothing is declared** (#228). The restriction exists so that fixture manifests (`tests/dirty-fastapi`) aren't counted as trees. Its side effect: any monorepo with one shallow tree (`app/`) plus `packages/*` / `projects/*` / `services/*` silently loses the deep trees.

## Proposed changes
- Keep the core verdict unchanged, so the #228 fixture protection stays. Always *scan* depth 2 and print an advisory **"undeclared trees (not in verdict)"** section listing depth-2 manifests not already covered. Exclude paths under `tests/`, `fixtures/`, `test-fixtures/`, `node_modules/`, `.venv/` and git submodules.
- When that list is non-empty, append a hint naming the config keys to declare them in.
- Add a fixture reproducing this layout (`app/package.json` + `packages/a/pyproject.toml` + `projects/b/pyproject.toml` + `tests/fixture/pyproject.toml`). Assert that a and b are listed and the fixture is not.

## Why it matters
"PASS" on a partial inventory is false confidence. The uncovered trees are exactly where an agent would assume gates exist. Monorepos that pair a shallow app with `packages/*` are common.

_Filed by /harness-feedback from CI_REVIEW_2026-11-04.md / REVIEW.md of data-lab on 2026-11-04._

---

## Issue 3 — Sharpen resilience-auditor's RAG/data row: content-keyed derived artifacts, persist-before-remote-log, LLM truncation

## What happened
The audit-time resilience pass on data-lab's RAG pilot found failure modes that the plan-time pass (`/plan-features` Step 2d.7, Phase 3) did not turn into acceptance criteria. `IMPLEMENTATION_PLAN_PHASE_3.md` has no mention of per-question persistence, a corpus hash or `stop_reason`:
- **🔴** `run.py:82-87`: every LLM answer is held in memory until `mlflow.log_metrics`/`log_dict`. If MLflow is down at that point, all the run's results are lost, after MLflow's default 7×120 s retry policy has blocked for a long time.
- **🟡** `index.py:34-38,70-73`: the vector collection name hashes embedder/size/overlap but **not the corpus content**, and reuse is `count == len(chunks)`. Editing the corpus without changing the chunk count reuses stale vectors and produces wrong metrics with no warning.
- **🟡** `generate.py:70-73`: `stop_reason == "max_tokens"` is never checked, so truncated answers are scored as complete. Same for a 200 response whose body is not JSON.

## Root cause (in the harness)
`agents/resilience-auditor.md` § "Stack-specific emphasis" lists **RAG / data** as "contract & dimension mismatch (7), large-payload & chunking (9), absent-index config (5)". That row misses the three classes that bit here:
- cache/index keys that don't cover the inputs they derive from;
- expensive compute (LLM / GPU) persisted only through a remote tracker, at the end;
- LLM-response completeness signals (`stop_reason`, empty or thinking-only content).

## Proposed changes
Extend the RAG / data row in `agents/resilience-auditor.md`, which is an on-demand tier with no always-on cost:

> **RAG / data / experiment runs** | contract & dimension mismatch (7), large-payload & chunking (9), absent-index config (5), **derived-artifact keys must hash the content they derive from — reuse-on-count is stale-reuse (7)**, **persist expensive (LLM/GPU) results locally before remote tracker logging; bound tracker retries (4/1)**, **LLM truncation & non-contract 2xx — check `stop_reason`/finish reason (1/7)**

## Why it matters
These are silent-wrong-result modes. The run finishes "green" with bad metrics, which is the worst outcome for an experimentation lab. Caught at plan time they cost one acceptance criterion each; caught at review they cost a fix cycle, and the stale-index one may never be caught at all.

_Filed by /harness-feedback from REVIEW.md of data-lab on 2026-11-04._

---

## Issue 4 — Python validation regexes: `fullmatch`/`\Z`, never `^…$` with `.match`; cross-language contract vectors carry line-terminator cases

## What happened
`packages/datalab/src/datalab/project.py:13` defines `NAME_RE = re.compile(r"^[a-z][a-z0-9]*(-[a-z0-9]+)*$")` and uses it with `.match` at 3 call sites (`:35`, `:101`, `:122`). Python's `$` matches before a trailing `\n`. Reproduced: `validate_name("mini-rag\n")` → `'mini-rag\n'` and `experiment_name("mini-rag\n")` → `'mini-rag\n'`. The JS twin (`/^…$/.test`) rejects that input.

The shared `contracts/name_vectors.json` exists precisely to keep the two sides aligned, but it has no line-terminator vector, so both suites pass. This name feeds directory paths (`datalab-new`), MLflow experiment names and Weaviate collection names.

## Root cause (in the harness)
`grep -rn "fullmatch\|\\\\Z" rules/python-fastapi/ agents/python-fastapi.md` → 0 hits. Nothing in the Python rules covers anchored-regex validation. `rules/shared/security.md` says "validate untrusted input" but not *how* to anchor. Neither `spec-gap-auditor` nor the testing rules prompt for line-terminator cases in shared cross-language vectors.

## Proposed changes
- `rules/python-fastapi/security.md` § Input Validation (stack-scoped, on-demand). Add a BAD/GOOD pair:
  - BAD: `re.compile(r"^[a-z]+$").match(s)`, which accepts `"abc\n"`.
  - GOOD: `re.compile(r"[a-z]+").fullmatch(s)`, or anchor with `\A…\Z`.
- One line: "a regex shared with another language (JS/TS) must have contract vectors including `"x\n"`, `"x\r"` and `"x\r\n"` in the reject list."
- Optional, if it recurs: a ruff-free AST linter recipe that flags a `re.compile` pattern ending in `$` (and not `\Z`) whose compiled object is used with `.match`/`.search` on a validation path.

## Why it matters
This is a classic validation bypass: names with control characters reach the filesystem and external stores. The cross-language contract gave false confidence because its vectors never probed the one place the two regex engines differ.

_Filed by /harness-feedback from REVIEW.md of data-lab on 2026-11-04._

---

## Issue 5 — Mechanize the documented "max 5 function args" rule with ruff `PLR0913` in the Python baseline

## What happened
`projects/mini-rag/src/mini_rag/run.py:60-74`: `def run(project, settings, pilot, questions, *, retrieval, k, n, size, overlap, collection, answer, search) -> str` takes **12 parameters**. It reached the architecture review because only an LLM judge looks for it.

## Root cause (in the harness)
`rules/python-fastapi/module-size.md:29` documents "Maximum function arguments: 5". The opinionated ruff baseline in `recipes/linters/python-fastapi-layered/README.md` (`select = ["E","F","W","I","B","T20","RUF","UP","SIM"]`) does not include `PLR0913`, and `recipes/ci/python-fastapi/pyproject-gates.toml` has no ruff selection at all. The rule is documented but never mechanized, even though ruff ships it for free.

## Proposed changes
Add to the README baseline (and to `pyproject-gates.toml` if it is meant to carry ruff config):
```toml
select = [..., "PLR0913"]          # too-many-arguments — mechanizes module-size.md "max 5 args"
[tool.ruff.lint.pylint]
max-args = 5
```
Optionally also add `PLR0915`/`C901` with thresholds matching module-size.md's function-length guidance.

## Why it matters
It is a one-line config change that turns a review-time judgment into a pre-commit failure. Note that only one occurrence was found in this project, which is below the usual 3× recurrence bar. It is filed anyway because the rule already exists and the cost is a single selector. Reject it if you'd rather wait for a recurrence.

_Filed by /harness-feedback from REVIEW.md of data-lab on 2026-11-04._

---

## Vetted out

| Candidate | Reason |
|---|---|
| Unbounded `>=` runtime deps (datalab, mini-rag) | `uv.lock` committed for every tree; the shared rule ("pin via lockfile") is satisfied. Project-level tidy-up, no harness gap. |
| 9 `# type: ignore` / `# noqa` without reason | Already mechanized: `rules/python-fastapi/tooling.md:174` + the `any-justified` WHY linters exist. data-lab simply didn't vendor them. Project choice, not a harness hole. |
| Testing gaps (TQ9 properties, missing `main()`/`search()` tests, partial assertions, shared `globalThis` state) | The judgment pass (`JUDGMENT_PASS.md`, TQ1–TQ9) caught every one of them as designed; the mechanical audit can't, by contract. No harness change. |
| Astro app: MLflow REST without zod, scattered env reads, no `noUncheckedIndexedAccess` | No Astro stack in the harness. The nearest rules (`rules/vite-react/`) already require zod-validated env and strict TS. Watch for recurrence before adding an Astro stack. |
| pyright in `basic` mode | Folded into Issue 1: the real gap is that pyright never runs, not its mode. |
| `templates/project` ships without coverage/pyright/audit gates | Project template content, owned by data-lab. |
| CI `uv sync` without `--locked` | Single occurrence. The recipe CI already uses locked installs. Project-level fix. |
| Implementation-notes deviations (MLflow `max_results`, uv Python 3.14, `--directory` for vendored linters, `node --test` coverage exclude, astro daemonize, coverage-floor-in-addopts) | Recorded as promotion targets in REVIEW.md. Each was seen once, in one project, so it stays below the recurrence bar. Re-evaluate on the next project. |

## File them manually

Dedup first: `gh issue list --repo <harness-owner/name> --state open --limit 100`.

Then, for each new issue, after saving its body (the section between the `---` rules) to `/tmp/hf-<n>.md`:

```bash
gh issue create --repo <harness-owner/name> --label enhancement \
  --title "Flag inert gates in the CI gate inventory: tools configured but never invoked, and --staged gitleaks as the CI secrets gate" --body-file /tmp/hf-1.md
gh issue create --repo <harness-owner/name> --label enhancement \
  --title "Gate inventory: list undeclared depth-2 trees when depth 0-1 already has a manifest" --body-file /tmp/hf-2.md
gh issue create --repo <harness-owner/name> --label enhancement \
  --title "Sharpen resilience-auditor's RAG/data row: content-keyed derived artifacts, persist-before-remote-log, LLM truncation" --body-file /tmp/hf-3.md
gh issue create --repo <harness-owner/name> --label enhancement \
  --title "Python validation regexes: fullmatch/\\Z, never ^...\$ with .match; contract vectors carry line-terminator cases" --body-file /tmp/hf-4.md
gh issue create --repo <harness-owner/name> --label enhancement \
  --title "Mechanize the documented 'max 5 function args' rule with ruff PLR0913 in the Python baseline" --body-file /tmp/hf-5.md
```
