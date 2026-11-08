#!/usr/bin/env bash
# Weavit UI in the browser (web mode) on the data-lab stack: http://127.0.0.1:3080
#   tools/weavit-web.sh            build once if needed, then serve
#   tools/weavit-web.sh --rebuild  reinstall and rebuild first (after updating the tools/weavit-ui submodule)
# The projector sidecar (Projection tab) is rebuilt incrementally on every start; without cargo, or if it fails
# to compile, the server still starts and the tab says the binary is missing.
# The data-lab connection profile is created on first start (auto-connect). OPENROUTER_API_KEY from the
# root .env, if set, is handed to the server for the RAG tab's OpenRouter preset; it stays in memory.
set -euo pipefail

root=$(cd "$(dirname "$0")/.." && pwd)
major=$(node -p 'process.versions.node.split(".")[0]' 2>/dev/null || echo 0)
if [ "$major" -lt 22 ]; then
  echo "weavit-web: node >= 22 required (found $(node --version 2>/dev/null || echo none)); run: nvm use 22" >&2
  exit 1
fi

cd "$root/tools/weavit-ui"
pnpm_() { pnpm --config.verify-deps-before-run=false "$@"; }
if [ "${1:-}" = "--rebuild" ] || [ ! -d node_modules ]; then
  pnpm_ install --frozen-lockfile
fi
if [ "${1:-}" = "--rebuild" ] || [ ! -f out/web/server/main.js ]; then
  pnpm_ run web:build
fi
if ! command -v cargo >/dev/null 2>&1; then
  echo "weavit-web: cargo not found: the Projection tab will say the binary is missing"
elif ! pnpm_ run projector:build; then
  echo "weavit-web: projector build failed (see the cargo output above): the Projection tab will say the binary is missing" >&2
fi

key=""
if [ -f "$root/.env" ]; then
  key=$(grep -E '^OPENROUTER_API_KEY=' "$root/.env" | head -1 | cut -d= -f2- || true)
fi
WEAVIT_SEED_DATALAB=1 WEAVIT_OPENROUTER_API_KEY="$key" exec node out/web/server/main.js
