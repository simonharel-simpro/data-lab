#!/usr/bin/env bash
# Statusline WRAPPER — derives the context BURN RATE, writes the loop meter to disk, then delegates
# to the existing statusline unchanged. The /init-component installer points the project's
# statusLine at this and leaves ~/.claude/statusline.sh untouched (revert = repoint statusLine back).
#
# Two outputs, deliberately different scopes:
#   1. `.harness/context-meter.json` — written ONLY when a loop run is active (a `.harness/` dir
#      exists in cwd), so it never litters other projects. Powers /loop-implement Step 1.5.
#   2. A ` | ^N tok/s ~Xm` segment APPENDED to the delegated statusline — useful in every project,
#      so its cross-render state lives in TMPDIR keyed by session id, never in the project tree.
#
# Why the rate is DERIVED: the statusline payload carries no cumulative token counter.
# `context_window.total_input_tokens` is a LEVEL ("token counts currently in the context window"),
# so the only honest rate is Δlevel/Δt — how fast context is FILLING. That is exactly what the
# Step 1.5 guard needs to turn "72% full" into "~13 minutes of headroom". It is NOT model output
# throughput; that is not derivable from this payload.
input=$(cat)

# Rate tuning. MIN_DT avoids a divide-by-tiny spike on back-to-back renders; MAX_DT invalidates a
# baseline from a session idle or suspended long enough that the old level means nothing.
MIN_DT=2
MAX_DT=300
EMA_NUM=3 # smoothing weight/10 on the newest sample — raw deltas are far too jumpy to read

is_num() { [ -n "${1:-}" ] && [ "$1" -eq "$1" ] 2>/dev/null; }

fmt_headroom() { # seconds -> "~13m" / "~2h5m"; prints nothing when unknown
  is_num "${1:-}" || return 0
  if [ "$1" -ge 3600 ]; then printf '~%dh%dm' "$(($1 / 3600))" "$((($1 % 3600) / 60))"
  else printf '~%dm' "$(($1 / 60))"; fi
}

# --- 1) one jq call for every field (the statusline re-renders often — keep it cheap) ---
IFS=$'\t' read -r cwd sid in_tok win_size used_pct rem_pct <<EOF
$(echo "$input" | jq -r '[
  (.workspace.current_dir // ""),
  (.session_id // "default"),
  ((.context_window.total_input_tokens // 0) | floor),
  ((.context_window.context_window_size // 0) | floor),
  ((.context_window.used_percentage // 0) | floor),
  ((.context_window.remaining_percentage // (100 - (.context_window.used_percentage // 0))) | floor)
] | @tsv' 2>/dev/null)
EOF

# A missing jq or a malformed payload must degrade to a plain delegate, never break the statusline.
: "${sid:=default}"
is_num "$in_tok" || in_tok=0
is_num "$win_size" || win_size=0
is_num "$used_pct" || used_pct=0
is_num "$rem_pct" || rem_pct=$((100 - used_pct))

# --- 2) burn rate: Δ(level)/Δt against the previous render, EMA-smoothed ---
now=$(date +%s)
state="${TMPDIR:-/tmp}/.claude-burn-${sid}.tsv"
rate="" # empty = not enough information yet; the segment is omitted rather than guessed
prev_ts=""
prev_tok=""
prev_ema=""
[ -r "$state" ] && IFS=$'\t' read -r prev_ts prev_tok prev_ema <"$state"

if is_num "$prev_ts" && is_num "$prev_tok"; then
  dt=$((now - prev_ts))
  dtok=$((in_tok - prev_tok))
  if [ "$dt" -ge "$MIN_DT" ] && [ "$dt" -le "$MAX_DT" ]; then
    if [ "$dtok" -lt 0 ]; then
      # Context SHRANK — compaction or /clear. A negative burn rate is meaningless AND the old
      # level is no longer a valid baseline, so drop the history and re-seed from this sample.
      rate=""
    elif is_num "$prev_ema"; then
      # dtok == 0 (idle) feeds a genuine 0, so an idle session decays toward 0 instead of
      # freezing at whatever it was burning when it stopped.
      rate=$(((EMA_NUM * (dtok / dt) + (10 - EMA_NUM) * prev_ema) / 10))
    else
      rate=$((dtok / dt))
    fi
  elif [ "$dt" -lt "$MIN_DT" ] && is_num "$prev_ema"; then
    rate=$prev_ema # too soon to re-measure — hold the last value rather than flicker
  fi
fi

# Atomic replace: a concurrent render must never read a half-written baseline.
printf '%s\t%s\t%s\n' "$now" "$in_tok" "${rate:-}" >"$state.tmp" 2>/dev/null &&
  mv -f "$state.tmp" "$state" 2>/dev/null

headroom=""
if is_num "$rate" && [ "$rate" -gt 0 ] && [ "$win_size" -gt 0 ]; then
  left=$((win_size - in_tok))
  [ "$left" -lt 0 ] && left=0
  headroom=$((left / rate))
fi

# --- 3) meter side-effect (non-fatal; never affects the delegated statusline) ---
if [ -n "$cwd" ]; then
  ucwd=$(cygpath -u "$cwd" 2>/dev/null || echo "$cwd")
  if [ -d "$ucwd/.harness" ]; then
    # Build with jq so absent fields degrade to null (Pro/Max-only rate_limits, or present only
    # after the first API response). Step 1.5 skips any window whose field is null — including
    # burn_rate_tps, which is null until two usable samples exist and after every compaction.
    echo "$input" | jq --argjson ts "$now" \
      --argjson burn "${rate:-null}" \
      --argjson head "${headroom:-null}" '{
      used_percentage: ((.context_window.used_percentage // 0) | floor),
      remaining_percentage: ((.context_window.remaining_percentage // (100 - (.context_window.used_percentage // 0))) | floor),
      ts: $ts,
      burn_rate_tps: $burn,
      headroom_seconds: $head,
      five_hour: (if .rate_limits.five_hour then {used_percentage: (.rate_limits.five_hour.used_percentage | floor), resets_at: .rate_limits.five_hour.resets_at} else null end),
      seven_day: (if .rate_limits.seven_day then {used_percentage: (.rate_limits.seven_day.used_percentage | floor), resets_at: .rate_limits.seven_day.resets_at} else null end)
    }' >"$ucwd/.harness/context-meter.json" 2>/dev/null
  fi
fi

# A 0 tok/s readout is noise on an idle session — show the segment only while context is moving.
burn_tag=""
if is_num "$rate" && [ "$rate" -gt 0 ]; then
  burn_tag=$(printf ' \033[90m|\033[0m \033[90m^%s tok/s %s\033[0m' "$rate" "$(fmt_headroom "$headroom")")
fi

# --- 4) delegate to the real statusline with the SAME stdin, then append our segment ---
if [ -f "$HOME/.claude/statusline.sh" ]; then
  rendered=$(echo "$input" | bash "$HOME/.claude/statusline.sh")
else
  rendered=$(printf '%s | ctx %s%%' "$(basename "${cwd:-?}")" "$used_pct")
fi
printf '%s' "$rendered"

# Append ONLY if the delegate doesn't already show a rate. A statusline that computes the burn
# rate itself (some do) would otherwise render it twice — the meter above is written either way.
case "$rendered" in
*tok/s*) ;;
*) [ -n "$burn_tag" ] && printf '%s' "$burn_tag" ;;
esac
exit 0
