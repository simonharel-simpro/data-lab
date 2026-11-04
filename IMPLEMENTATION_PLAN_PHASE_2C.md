# Phase 2C — Weavit UI fork: auto-connect to the `data-lab` profile

**Depends on:** Phase 1 (fork `simonharel-simpro/weavit-ui` attached as submodule `tools/weavit-ui`).
**Runs in parallel with:** 2A, 2B. **Agent:** `general-purpose` (TypeScript, Electron 37, React, zustand, TanStack
Query, vitest — the fork's own stack, pnpm). **Work happens in the fork repo** (`tools/weavit-ui`, branch
`feat/autoconnect-data-lab`); data-lab only bumps the submodule pointer afterwards.

## Context
Weavit UI persists connection profiles (`src/main/store/store.ts:17,62-68`, type `ConnectionConfig` in
`src/shared/types.ts:25`, no "default" field) but keeps the active connection in renderer memory
(`src/renderer/src/store.ts:10`, `setActiveConnection` used in `src/renderer/src/app/Sidebar.tsx:68`). The user wants
the app to connect by itself on launch to data-lab's Weaviate.
Decisions D-6 / U-11 / B-2 (user, 2026-11-03): auto-connect **only** to a saved profile whose `name` is exactly
`data-lab`, and **only if it provably targets data-lab**: `type === 'local'`, `localHost` in `{'127.0.0.1',
'localhost'}` **or undefined** (undefined means `localhost` in `connectionManager.ts:86`, still this machine, so it
is accepted), `localPort === 8090` AND `localGrpcPort === 50052` set explicitly (ports have no safe default:
undefined means Demo-RAG's 8080/50051). An empty port is refused, never
"repaired": `connectionManager.ts:86-88` falls back to `8080` / `50051`, which are Demo-RAG's ports, so a blank field
would silently open the wrong Weaviate. No eligible profile → no auto-connect. On failure → the normal UI with the
existing `error` status; never try another profile, never retry in a loop. No new field, no new UI.

**Test constraint:** the fork's vitest runs with `environment: 'node'` (`vitest.config.ts:9`) and has no
testing-library / jsdom. `src/renderer/src/lib/api.ts:4` reads `window.api` at module load, so **any test file that
imports it (even transitively) crashes with `ReferenceError: window is not defined`** (reproduced). Therefore
`autoConnect.ts` imports **only** `@shared/types`; the hook lives in its own file and is not unit-tested.
The existing connect path is already shared: `src/renderer/src/lib/useConnect.ts:9-41` (used by `App.tsx:20`). It
returns `Promise<boolean>` and **never rejects** — on failure it sets the `error` status, shows a toast and returns
`false`. Reuse it; do not write a second connect path.

## Files (in the fork)

#### `src/renderer/src/features/connections/autoConnect.ts` (NEW)
- `export const AUTOCONNECT_PROFILE_NAME = 'data-lab'`; `export const DATALAB_PORTS = { http: 8090, grpc: 50052 }`
  (comment: must match data-lab `compose.yaml`).
- `export type AutoConnectDecision = { kind: 'connect'; profile: ConnectionConfig } | { kind: 'skip'; reason:
  'no-profile' | 'ambiguous' | 'not-local' | 'host' | 'ports' }`.
- `export function decideAutoConnect(profiles: ConnectionConfig[]): AutoConnectDecision` — pure: filter
  `name === AUTOCONNECT_PROFILE_NAME`; 0 → `no-profile`; > 1 → `ambiguous`; then check type, host, both ports
  explicitly equal to `DATALAB_PORTS` (undefined counts as wrong) → the matching `skip` reason, else `connect`.
- `export async function autoConnectOnce(deps: { list: () => Promise<ConnectionConfig[]>; connect: (id: string) =>
  Promise<boolean>; hasActive: () => boolean; onSkip?: (reason: string) => void }): Promise<boolean>` — guarded by a
  module-level `started` flag **set synchronously before the first `await`** so it runs once per launch even when
  two calls overlap (React StrictMode double effects included); if
  `hasActive()` → return `false`; `decideAutoConnect(await list())`; `skip` → `onSkip(reason)` and return `false`;
  `connect` → `return await deps.connect(profile.id)` exactly once; `false` (failure, already surfaced by
  `useConnect`) is never retried and no other profile is tried. Export `__resetForTests()` to clear the flag.

#### `src/renderer/src/features/connections/useAutoConnectOnLaunch.ts` (NEW) — the only file importing `api` / React
`export function useAutoConnectOnLaunch(): void` — gets `connect` from `useConnect()`; one `useEffect` (with a
`// WHY:` comment: one-shot connect after launch) calling `autoConnectOnce({ list: api.connections.list, connect,
hasActive: () => !!useApp.getState().activeConnectionId, onSkip: r => console.info('autoconnect skip:', r) })
.catch(console.error)` (a `list()` failure must not become an unhandled rejection).

#### `src/renderer/src/app/App.tsx` (MODIFY) — import from `../features/connections/useAutoConnectOnLaunch` and call
`useAutoConnectOnLaunch()` once at the top level of `App`.

#### `README.md` (MODIFY, fork) — short "Fork notes" section: what auto-connect does, the reserved profile name, the
explicit 8090/50052 requirement and why; that this is a fork of XenoraAI/weavit-ui (Apache-2.0, keep `LICENSE` and
`NOTICE` untouched).

## Tests — `src/renderer/src/features/connections/autoConnect.test.ts` (vitest, node environment)
Fixture: a `profile(overrides)` factory returning a valid `data-lab` local profile on 127.0.0.1:8090/50052.

| Test | Given → expected | Source |
|---|---|---|
| "U-11: connects to the eligible data-lab profile" | `[local-other, profile(), cloud]` → `{kind:'connect', profile: <data-lab>}` | U-11 |
| "U-11: skips when no profile is named data-lab" | `[local-other, cloud]` → `skip/no-profile` | U-11 |
| "skips when two profiles are named data-lab" | two `profile()` → `skip/ambiguous` | U-11 |
| "B-2: skips when the gRPC port is empty" | `profile({localGrpcPort: undefined})` → `skip/ports` | B-2 |
| "B-2: skips when ports are Demo-RAG's" | `profile({localPort: 8080, localGrpcPort: 50051})` → `skip/ports` | B-2 |
| "skips a non-local or remote-host profile" | `profile({type:'cloud'})` → `skip/not-local`; `profile({localHost:'10.0.0.5'})` → `skip/host` | B-2 |
| "F-14: connect returning false is not retried, no fallback" | `connect` resolves `false`, a second non-eligible profile present → result `false`; `connect` called exactly 1× with the data-lab id | F-14, D-6 |
| "accepts an undefined localHost" | `profile({localHost: undefined})` → `connect` | D-6 |
| "runs only once per launch, even concurrently" | `await Promise.all([autoConnectOnce(d), autoConnectOnce(d)])` with a `list` that resolves after a tick → `list` and `connect` called 1× each | U-11 |
| "does nothing when a connection is already active" | `hasActive: () => true` → `list` never called | U-11 |

## Gate
`pnpm install && pnpm typecheck && pnpm test` green in the fork (its existing scripts). Manual check: a `data-lab`
profile on 8090/50052 while data-lab's compose runs → connected without a click; the same profile with an empty gRPC
port → no auto-connect, log line `skip: ports`. Commit and push the branch to the fork, merge into the fork's main;
then in data-lab: `cd tools/weavit-ui && git checkout <merged sha>`, commit the submodule bump.
`git config push.recurseSubmodules check` stops a pointer to an unpushed commit.

## Done when
Fork typecheck and tests green; both manual checks recorded; data-lab's submodule pointer bumped to a pushed commit.

<!-- plan-validate: READY 2026-11-03 sha256:8554f8fb6256 -->
