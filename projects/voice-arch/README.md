# voice-arch

Voice-agent control architectures (A orchestrator, B + state machine, C + call record) on LiveKit, for an English
(US-format) appointment-booking phone agent. Every model call goes through OpenRouter. See `PROJECT.md` for the
objective and the stage-1 results.

## Setup

```bash
uv sync                      # own env; datalab comes from ../../packages/datalab (editable)
cp .env.example .env         # then fill VOICE_ARCH_LIVEKIT_API_KEY / _SECRET (= the root LIVEKIT_* values)
```

- OpenRouter: `VOICE_ARCH_OPENROUTER_API_KEY`, or blank to use the root `OPENROUTER_API_KEY`. Do not use that key
  elsewhere during a bench or sweep: the cost of a run is the key's usage delta (D-6). The experiment budget is
  `VOICE_ARCH_EXPERIMENT_BUDGET_USD` (default 50), enforced from the `cost_usd` metrics in MLflow.
- The shared stack must be up (`docker compose up -d` at the repo root) for MLflow.

## Stage-1 bench

```bash
uv run pytest -m integration tests/integration/test_spike.py -q   # live spike: STT, TTS, LLM through OpenRouter
uv run python -m voice_arch.bench --component stt    # 40 synthesised utterances; judge = none
uv run python -m voice_arch.bench --component tts    # judge = the `stt_model` default (set it first)
uv run python -m voice_arch.bench --component llm    # 20 tool-call cases
# --n N runs the first N items only (smoke). Rows land in results/<run_id>.jsonl, runs in `voice-arch/bench`.
```

A run refuses to start when the money spent so far plus 2 $ would reach the budget. After a run, copy the
`winner` tag into the `VoiceSettings` default (`src/voice_arch/settings.py`) and the reason into `PROJECT.md`.

## Browser smoke (manual, F-13)

Checks the media path from a Windows browser to the WSL2 LiveKit and times the real turn latency.

```bash
# 1. LiveKit (root LIVEKIT_API_KEY / LIVEKIT_API_SECRET must be set in the root .env)
docker compose --profile voice up -d livekit        # at the repo root; confirm the healthcheck turns healthy
# 2. the smoke agent (in projects/voice-arch)
uv run python -m voice_arch.smoke_agent dev
# 3. a join token that also dispatches the agent
uv run python -m voice_arch.token --room smoke --agent smoke
# 4. serve the client
python -m http.server --bind 127.0.0.1 8765 --directory web
```

Open `http://127.0.0.1:8765` in the Windows browser, keep `ws://127.0.0.1:7880`, paste the token, press Join and
allow the microphone. Then:

1. Check you hear the agent and it hears you (both ways).
2. Read the selected ICE candidate line in the page log: UDP is the real media path, TCP (7881) is the fallback.
3. Say three sentences and hand-time each (end of your speech to first agent sound); compare with the
   `e2e_latency=` lines the agent logs. Write the three offsets, the UDP/TCP result and any audio problem in
   `PROJECT.md` (no MLflow run). If the browser cannot reach the WSL2 ports, note it there before Phase 2.

## Booking agent worker (Phase 2)

```bash
# 1. LiveKit up (see "Browser smoke"), then the worker (dev mode: auto-reload, one job per call)
uv run python -m voice_arch.worker dev            # production-like: `... worker start`
# 2. a join token that does NOT auto-dispatch, then dispatch the architecture you want into the room
uv run python -m voice_arch.token --room t1
uv run python -m voice_arch.dispatch --arch b --room t1     # --arch a | b | c
```

Join from `web/index.html` as in the smoke run. The agent greets, books name, phone, address, problem type and slot,
reads the booking back and hangs up after the caller confirms. When the call ends the worker sends one
`CallResult` JSON on the room text topic `voice-arch.result` (record, session report, close reason, error counts);
it writes no file. An unknown `--arch` is refused with an error result, never defaulted to A.

Live text-mode check of the three architectures (OpenRouter LLM only, a few cents):

```bash
uv run pytest -m integration tests/integration/test_arch_text.py
```

## Sweeps against the simulated caller (Phase 3)

A sweep is one architecture x 6 personas x N repetitions, logged as one MLflow run in `voice-arch/conversations`.
The caller is an `AgentSession` (LLM `caller_llm_model` at `caller_temperature`) that joins the room, never speaks
first, and plays one persona from `data/personas.jsonl`; the call ends when the booking agent's `CallResult` arrives
or after `call_timeout_s`. The runner scores each record with `is_exact` and deletes the room.

The cost of a sweep is the OpenRouter key's usage delta and includes the simulated caller (D-16). It uses the root
`OPENROUTER_API_KEY` with the 50 $ software budget (`experiment_budget_usd`): do not use that key elsewhere during a
sweep, and run one sweep at a time. A sweep refuses to start when the money spent so far plus the cost of the last
full sweep (15 $ until one has finished) would reach the budget, and stops between two calls when the key's usage
reaches it.

```bash
# 1. LiveKit and the worker (see "Booking agent worker"); .env holds the LIVEKIT_* keys
docker compose --profile voice up -d livekit          # at the repo root
uv run python -m voice_arch.worker start              # leave it running; `dev` also works
# 2. smoke: one persona, one repetition (metrics are all `smoke_*`, tag full=false)
uv run python -m voice_arch.runner --arch a --personas self_correction --reps 1
# 3. the full sweeps, one at a time: 6 personas x 5 reps = 30 calls, roughly 1 to 1.5 h each
uv run python -m voice_arch.runner --arch a
uv run python -m voice_arch.runner --arch b
uv run python -m voice_arch.runner --arch c
# 4. a browser call per arch (Browser smoke), then your rating of how natural it felt
uv run python -m voice_arch.rate --arch a --rating 4 --notes "a bit slow"     # 1 (robotic) .. 5 (natural)
# 5. the table and the decision, to paste into PROJECT.md `## Enseignements`
uv run python -m voice_arch.decide
```

Rows are appended to `results/<run_id>.jsonl` as each call ends, so a failed sweep keeps its finished calls. A
sweep fails (run FAILED) when no agent joins in time, when OpenRouter answers 401/402 on either side, when the budget
is reached, or when more than 10 % of the calls fail on the caller's side. Only a FINISHED run tagged `full=true`
counts for `decide` and for the app card (`exact_rate`); a smoke run logs `smoke_exact_rate` and never stands in.

The agent LLM is pinned to `openrouter_providers` (default `google-vertex,google-ai-studio`, no fallback; set
`openrouter_quantization` to add a quantization filter); the caller LLM is not. Both LLMs are guarded against empty completions (`llm_guard`): an empty reply is retried, and
each retry raises the temperature by 0.3 (capped at 1.0) so it is not an identical request; every retry is logged at
WARNING with its number. A live call takes 3 to 5 minutes (real-time
read-backs); `call_timeout_s` is 420 by default (a `self_correction` call needs 265 to 300 s). Under host CPU load the `start` worker marks itself unavailable (load
threshold 0.7) and no agent joins: use `worker dev` (no threshold) for live checks on a busy machine.

Three behaviours of the agent worker, equal for A, B and C:

- **Reasoning effort.** The agent LLM is sent `reasoning_effort` (`agent_reasoning_effort`, default `low`; `minimal`
  is refused). Without it Gemini answers most tool turns with `MALFORMED_FUNCTION_CALL`, which LiveKit reads as an
  empty completion (see `IMPLEMENTATION_NOTES.md`, "Empty completion root cause"). The caller LLM never gets it.
- **Fail fast.** The first unrecoverable LLM error (for example the guard giving up) shuts the session down at once
  and the `CallResult` carries the error, its HTTP status and `close_reason` `error`. The call is scored by its
  record and counts against the architecture (ESC-3-1); it no longer idles until `call_timeout_s`.
- **Confirm waits for the caller.** `confirm_booking` is refused ("Wait for the caller to confirm the read-back
  first") until the caller has spoken after the last write to the record, so a read-back and its confirmation can no
  longer share one turn.

Debugging an empty completion: set `VOICE_ARCH_DUMP_EMPTY_DIR` to a directory **outside the repository** (the dump
holds the whole conversation, so it is PII) and the guard writes the messages, tool definitions and request
parameters of every empty attempt there as `empty-<time>-attempt<n>.json`. It is off when the variable is unset.

Live check of the whole path (one call, a few cents; the worker must be running):

```bash
uv run pytest -m integration tests/integration/test_one_call.py -s
```
