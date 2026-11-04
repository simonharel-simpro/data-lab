#!/usr/bin/env bash
# PreToolUse(Bash) guard — makes the loop's git contract MECHANICAL (simpro-shared#196).
#
# Prose rules ("subagents never open PRs", "a phase lands only after a clean /check") were skipped
# under throughput pressure. This hook enforces them whatever the prompt says:
#   1. A SUBAGENT (hook input carries `agent_id`) may never `git push`, `gh pr create`, or
#      `gh pr merge` — the orchestrator owns shipping. During an active loop run it may not
#      `git commit`/`git merge` either (quality-blocks Block 4).
#   2. The MAIN session, during an active loop run, may `git merge` a phase branch only when
#      loop_gate.py confirms a clean /check verdict bound to that branch's tip, and may push /
#      open a PR only when every landed phase is verified (loop_gate.py assert-ready).
# Loop checks apply only to the repo + branches of a live run (loop_scope.py): outside a loop, or on
# another repo / branch, the main session is never restricted.
# Escape hatch for a human who really means it: HARNESS_GUARD_OFF=1 in Claude Code's environment.
input=$(cat)
[ "${HARNESS_GUARD_OFF:-0}" = "1" ] && exit 0

tool=$(printf '%s' "$input" | jq -r '.tool_name // empty' 2>/dev/null)
[ "$tool" = "Bash" ] || exit 0
cmd=$(printf '%s' "$input" | jq -r '.tool_input.command // empty' 2>/dev/null)
agent=$(printf '%s' "$input" | jq -r '.agent_id // empty' 2>/dev/null)
cwd=$(printf '%s' "$input" | jq -r '.cwd // empty' 2>/dev/null)
[ -n "$cmd" ] || exit 0

GATE="${HARNESS_LOOP_GATE:-$HOME/.claude/recipes/hooks/loop-resilience/loop_gate.py}"

deny() {
  jq -n --arg r "$1" '{hookSpecificOutput: {hookEventName: "PreToolUse",
    permissionDecision: "deny", permissionDecisionReason: $r}}'
  exit 0
}

# Word-boundary matches (tolerating `git -C <dir>` / `git -c k=v`) so lookalikes don't trip it.
G='(^|[;&|[:space:]])git([[:space:]]+-[Cc][[:space:]]+[^[:space:]]+)*[[:space:]]+'
is_ship()  { printf '%s' "$cmd" | grep -Eq "(${G}push|(^|[;&|[:space:]])gh[[:space:]]+pr[[:space:]]+(create|merge))([[:space:]]|\$)"; }
is_land()  { printf '%s' "$cmd" | grep -Eq "${G}(commit|merge)([[:space:]]|\$)"; }
is_merge() { printf '%s' "$cmd" | grep -Eq "${G}merge([[:space:]]|\$)"; }
# The first non-option argument after `merge` (skips -m <msg>); empty for `merge --abort` etc.
merge_ref() {
  # Collapse quoted strings (a -m 'multi word' message) to one placeholder token first.
  printf '%s' "$cmd" | sed -E "s/'[^']*'/Q/g; s/\"[^\"]*\"/Q/g" | awk '{
    for (i = 1; i <= NF; i++) if ($i == "merge") { m = i; break }
    if (!m) exit
    for (j = m + 1; j <= NF; j++) {
      if ($j ~ /^[;&|]/) exit
      if ($j == "-m" || $j == "-F" || $j == "--strategy" || $j == "-s" || $j == "-X") { j++; continue }
      if ($j ~ /^-/) continue
      print $j; exit
    }
  }'
}

# Which loop (if any) governs THIS command? Scoped to the repo the command runs in (`cd X &&`,
# `git -C X`, `gh --repo`) and to the loop's own branches (feature branch, phase-*), so a stale or
# unrelated loop — e.g. a HALTED run in an umbrella repo — can't block pushes elsewhere (#199 follow-up).
SCOPE="$(dirname "$GATE")/loop_scope.py"
loop_root=""; loop_state=""; loop_branch=""; loop_kind=""
if { is_ship || is_land; } && [ -n "$cwd" ] && [ -d "$cwd" ]; then
  if command -v python3 >/dev/null 2>&1 && [ -f "$SCOPE" ]; then
    hit=$(python3 "$SCOPE" --cmd "$cmd" --cwd "$cwd" 2>&1); rc=$?
    if [ "$rc" -eq 0 ]; then
      IFS=$'\x1f' read -r loop_root loop_state loop_branch loop_kind <<<"$hit"
    elif [ "$rc" -ne 1 ]; then
      # Fail CLOSED (F-3): a broken scoper must never read as "no loop here".
      deny "Loop guard could not decide whether a loop governs this command, so it is denied: ${hit:-exit $rc}. Fix or archive the loop state (move .harness/loop/ to .harness-archive/), or set HARNESS_GUARD_OFF=1 deliberately."
    fi
  else
    # No scoper available: fall back to the session repo (the pre-scoping behaviour).
    root=$(git -C "$cwd" rev-parse --show-toplevel 2>/dev/null)
    for f in "$root/.harness/loop/state.json" "$root/.harness/loop-fix/state.json"; do
      [ -n "$root" ] && [ -f "$f" ] && { loop_root=$root; loop_state=$f; loop_kind=gate; break; }
    done
  fi
fi

if [ -n "$agent" ]; then
  is_ship && deny "Subagents never push or open/merge PRs — the orchestrator owns shipping (loop-implement Step 10; quality-blocks Block 4). Leave your changes uncommitted and report back."
  [ -n "$loop_root" ] && is_land && deny "Loop run active: subagents never commit or merge (quality-blocks Block 4 — the orchestrator stages, verifies, and commits). Leave changes in the working tree and report back."
  exit 0
fi

[ -n "$loop_root" ] || exit 0
stale_hint=" (If this loop is finished or abandoned: python3 \$HOME/.claude/recipes/hooks/loop-resilience/loop_gate.py close --reason '<why>' — it archives $loop_state and stops gating.)"
# The loop never merges and never ships to trunk (F-2) — in passport-ai a trunk push stages a deploy.
[ "$loop_kind" = merge ] && deny "A loop run is live in $loop_root: the loop never merges PRs — a human merges.$stale_hint"
[ "$loop_kind" = trunk ] && deny "A loop run is live in $loop_root: pushing to the trunk ($loop_branch) is never part of the loop — it ships via the loop's PR.$stale_hint"
if ! command -v python3 >/dev/null 2>&1 || [ ! -f "$GATE" ]; then deny "Loop run active but the loop gate ($GATE) is unavailable — run 'bash deploy.sh recipes' from the harness repo, or set HARNESS_GUARD_OFF=1 to bypass deliberately."; fi
if is_ship; then
  out=$(cd "$loop_root" && python3 "$GATE" --state "$loop_state" assert-ready ${loop_branch:+--branch "$loop_branch"} 2>&1) || deny "$out$stale_hint"
  exit 0
fi
if is_merge; then
  ref=$(merge_ref)
  [ -n "$ref" ] || exit 0   # `git merge --abort` etc. — nothing to verify
  out=$(cd "$loop_root" && python3 "$GATE" --state "$loop_state" assert-phase --ref "$ref" 2>&1) || deny "$out$stale_hint"
fi
exit 0
