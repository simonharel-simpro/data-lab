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
