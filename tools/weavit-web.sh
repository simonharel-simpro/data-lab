#!/usr/bin/env bash
# Weavit UI in the browser (web mode) on the data-lab stack: http://127.0.0.1:3080
#   tools/weavit-web.sh            install (idempotent), build once if needed, then serve
#   tools/weavit-web.sh --rebuild  reinstall and rebuild first (after updating the tools/weavit-ui submodule)
# The projector sidecar (Projection tab) is rebuilt incrementally on every start; without cargo, or if it fails
# to compile, the server still starts and the tab says the binary is missing.
# The data-lab connection profile is created on first start (auto-connect). OPENROUTER_API_KEY from the
# root .env, if set, is handed to the server for the RAG tab's OpenRouter preset; it stays in memory.
set -euo pipefail

# Print the value of the first OPENROUTER_API_KEY= line of the env file ($1): trailing CR (CRLF .env) and one
# pair of matching surrounding quotes removed. Empty when the file or the key is absent.
read_env_key() {
  local line="" value
  if [ -f "$1" ]; then
    line=$(grep -E -m1 '^OPENROUTER_API_KEY=' "$1" || true)
  fi
  value=${line#*=}
  value=${value%$'\r'}
  case "$value" in
    \"*\") value=${value#\"}; value=${value%\"} ;;
    \'*\') value=${value#\'}; value=${value%\'} ;;
  esac
  printf '%s' "$value"
}

# Sourced (by tests): only define the functions above.
if [[ "${BASH_SOURCE[0]}" != "$0" ]]; then return 0; fi

root=$(cd "$(dirname "$0")/.." && pwd)
[ -f "$root/tools/weavit-ui/package.json" ] || {
  echo "weavit-web: tools/weavit-ui is empty: run git submodule update --init tools/weavit-ui" >&2
  exit 1
}

major=$(node -p 'process.versions.node.split(".")[0]' 2>/dev/null || echo 0)
if [ "$major" -lt 22 ]; then
  echo "weavit-web: node >= 22 required (found $(node --version 2>/dev/null || echo none)); run: nvm use 22" >&2
  exit 1
fi

cd "$root/tools/weavit-ui"
pnpm_() { pnpm --config.verify-deps-before-run=false "$@"; }
pnpm_ install --frozen-lockfile
if [ "${1:-}" = "--rebuild" ] || [ ! -f out/web/server/main.js ]; then
  pnpm_ run web:build
fi
if ! command -v cargo >/dev/null 2>&1; then
  echo "weavit-web: cargo not found: the Projection tab will say the binary is missing"
elif ! pnpm_ run projector:build; then
  echo "weavit-web: projector build failed (see the cargo output above): the Projection tab will say the binary is missing" >&2
fi

key=$(read_env_key "$root/.env")
WEAVIT_SEED_DATALAB=1 WEAVIT_OPENROUTER_API_KEY="$key" exec node out/web/server/main.js
