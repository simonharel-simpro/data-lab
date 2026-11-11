# Implementation notes (deviation log)

## Platform Phase 2 — skill lines touched beyond the plan's list

- Plan assumed: only the listed lines of the `/experiment` skill change (ledger snippets, contracts, missing project,
  Hydra gate, agents line, working-directory rule); "the skill text names no sequence of its own" (U-12).
- Territory was: SKILL.md §5 hardcoded a sequence (`an exploration is scoping → eda → report`) and keyed the raw→clean
  copy on "a comparison (no cleaning milestone)"; §2 said "from the repo root"; the `# /experiment` heading; the
  agent-overrides "all agents" row said "the shared stack runs from the repo root" (false in another workspace).
- I did: dropped the arrow sequence; reworded the copy rule to "a kind whose sequence has no `cleaning` milestone"
  (same behaviour: per `contracts/milestones.json`, comparison is the only kind with `dataset` but no `cleaning`);
  "repo root" → "workspace root" / "data-lab checkout"; heading → `/datalab:experiment`. Per-kind statements such as
  "training only" and "An exploration: …" in the briefs were left as they are (they describe artifacts, not sequences).
- One-off or pattern?: one-off (moving a repo-local skill to a portable plugin).
