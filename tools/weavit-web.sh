#!/usr/bin/env bash
# Weavit UI in the browser (web mode) on the data-lab stack: http://127.0.0.1:3080
#   tools/weavit-web.sh            build once if needed, then serve
#   tools/weavit-web.sh --rebuild  rebuild first (after updating the tools/weavit-ui submodule)
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
[ -d node_modules ] || pnpm_ install --frozen-lockfile
if [ "${1:-}" = "--rebuild" ] || [ ! -f out/web/server/main.js ]; then
  pnpm_ run web:build
fi

key=""
if [ -f "$root/.env" ]; then
  key=$(grep -E '^OPENROUTER_API_KEY=' "$root/.env" | head -1 | cut -d= -f2- || true)
fi
WEAVIT_SEED_DATALAB=1 WEAVIT_OPENROUTER_API_KEY="$key" exec node out/web/server/main.js
