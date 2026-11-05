#!/usr/bin/env bash
# PreCompact augmentation — NON-BLOCKING, additive (runs ALONGSIDE any existing PreCompact hook).
#
# Compaction can't be reacted to in the moment ("the bulldozer started"), but it CAN leave a
# breadcrumb: this drops a one-shot flag so the next turn knows compaction happened and must
# re-hydrate from disk instead of trusting summarized memory. It NEVER blocks compaction.
#
# Acts only when a /loop-implement run is active in this project (a `.harness/` dir exists), so it
# stays silent in every other repo.
input=$(cat)

cwd=$(echo "$input" | jq -r '.cwd // .workspace.current_dir // empty' 2>/dev/null)
[ -z "$cwd" ] && exit 0
ucwd=$(cygpath -u "$cwd" 2>/dev/null || echo "$cwd")
[ -d "$ucwd/.harness" ] || exit 0

trigger=$(echo "$input" | jq -r '.trigger // "auto"' 2>/dev/null)
ts=$(date +%s)
printf '{"compaction_ts": %s, "trigger": "%s"}\n' "$ts" "${trigger:-auto}" \
  > "$ucwd/.harness/compaction-pending" 2>/dev/null
printf '%s compaction (%s)\n' "$ts" "${trigger:-auto}" \
  >> "$ucwd/.harness/compaction.log" 2>/dev/null
exit 0
