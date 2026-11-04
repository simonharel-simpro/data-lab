# data-lab — instructions for Claude

## Structural queries — use ArchView, not grep

This project has an `archview` semantic-graph map (`.archview/`). For any question about
code *relationships* — who calls X, what X calls, where a symbol is defined, a module's
tree/dependencies, HTTP routes, or the blast-radius of a change — query `archview` (lead
with `archview context <symbol>`) instead of grep + file-reading. Reserve grep for literal
text: comments, string literals, config values, non-parsed files. If the map is missing or
stale, run `archview scan .` first.
