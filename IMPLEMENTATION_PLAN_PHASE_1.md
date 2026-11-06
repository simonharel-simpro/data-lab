# Phase 1 — Infra, gates, OpenRouter audio, stage-1 bench, browser smoke

**Depends on:** nothing. **Agent:** `python-fastapi` (Python 3.12, uv). Repo: data-lab (`main`).
**Produces for Phase 2:** `VoiceSettings`, `make_stt / make_tts / make_llm`, `key_usage()`, `fields.py`, chosen model defaults.

Context you need (restated, self-contained): `projects/voice-arch` is an experiment comparing voice-agent architectures on
LiveKit for an English (US) appointment-booking phone agent. Every model call goes through OpenRouter
(`https://openrouter.ai/api/v1`): STT `/audio/transcriptions`, TTS `/audio/speech` (both OpenAI-compatible), LLM
`/chat/completions`. Pins: `livekit-agents==1.8.8`, `livekit-plugins-openai==1.8.8`, `livekit-plugins-silero==1.8.8`,
`livekit-api==1.2.2`, image `livekit/livekit-server:v1.13.10`. Follow the patterns of `projects/mini-rag` (settings,
JSONL crash copy, `tracked_run`), and the data-lab rules: 127.0.0.1-only ports, `src/` modules ≤ 200 lines, ruff, pyright.

## 1. Scaffold

Run from the repo root: `uv run --project packages/datalab datalab-new voice-arch --title "Voice agent architectures (LiveKit)"`.

#### `projects/voice-arch/PROJECT.md` (MODIFY the generated card)
Front matter: `status: en cours`, `tags: [voice, livekit, agents]`, `data: "generated US caller utterances + 6 personas"`,
`metric: {key: exact_rate, goal: max}`. `## Objectif`: pick the control architecture (A orchestrator / B + TaskGroup /
C + call record) for a Simpro phone agent; bar ≥ 90 % exact records, median e2e latency < 1.2 s, ≤ 50 $.
`## Approche`: stage 1 bench (STT, TTS, LLM on identical inputs), stage 2 three architectures × 6 personas × 5 reps.

#### `projects/voice-arch/pyproject.toml` (MODIFY)
Add runtime deps (exact pins): `livekit-agents==1.8.8`, `livekit-plugins-openai==1.8.8`, `livekit-plugins-silero==1.8.8`,
`livekit-api==1.2.2`, `httpx2` only if the plugins don't already bring an HTTP client you can use for `/api/v1/key`
(prefer `httpx`, already used by datalab). Add `[tool.importlinter]` with one contract like mini-rag
(`voice_arch.booking` must not import `livekit`, `mlflow`, `datalab` — the domain stays pure). Run `uv lock`.

#### `projects/voice-arch/.gitignore` (NEW)
`results/`, `data/audio/`, `.env`.

## 2. Infra

#### `infra/livekit.yaml` (NEW, repo root)
LiveKit server config: `port: 7880`; `rtc: {tcp_port: 7881, udp_port: 7882, use_external_ip: false, node_ip: 127.0.0.1}`;
`keys:` NOT in the file (comes from the `LIVEKIT_KEYS` env var); `logging: {level: info}`.

#### `compose.yaml` (MODIFY)
Add service `livekit`: `image: livekit/livekit-server:v1.13.10`, `command: ["--config", "/etc/livekit.yaml"]`,
`environment: LIVEKIT_KEYS: "${LIVEKIT_API_KEY:?set in .env}: ${LIVEKIT_API_SECRET:?set in .env}"`, volume
`./infra/livekit.yaml:/etc/livekit.yaml:ro`, ports `127.0.0.1:7880:7880`, `127.0.0.1:7881:7881`,
`127.0.0.1:7882:7882/udp`, `restart: unless-stopped`. Healthcheck only if the image ships a usable binary (check
`docker run --rm --entrypoint ls livekit/livekit-server:v1.13.10 /`); otherwise none, with a comment saying why.
Keep the header comment's 127.0.0.1 rule; mention LiveKit's ports.

#### `.env.example` (MODIFY, root)
`LIVEKIT_API_KEY=` and `LIVEKIT_API_SECRET=` (blank; comment: the secret must be ≥ 32 characters, local-only keys).

#### `tests/test_compose.py` (MODIFY)
Add the three LiveKit ports to `EXPECTED_PORTS` (`("livekit","127.0.0.1","7880",7880)`, `7881`, and the UDP `7882`).
Render with `LIVEKIT_API_KEY`/`LIVEKIT_API_SECRET` dummy values in the subprocess env so `${…:?}` resolves.

## 3. Gates

#### `.pre-commit-config.yaml` (MODIFY)
Add `declared-deps-voice-arch` (copy `declared-deps-mini-rag`, paths `projects/voice-arch`) and `gates-voice-arch`
(copy `gates-mini-rag`: `cd projects/voice-arch && uv run --locked lint-imports && uv run --locked pyright && uv run
--locked pytest -q --cov`, `files: ^(projects/voice-arch/|packages/datalab/src/)`, stage pre-push).

#### `.github/workflows/ci.yml` (MODIFY)
Add a job `voice-arch` mirroring `pilot` (submodules false, setup uv, `uv sync --locked`, lint-imports, pyright, pytest
`--cov`, pip-audit) in `projects/voice-arch`.

#### `packages/datalab/tests/test_settings.py` (MODIFY)
Add `REPO_ROOT / "projects" / "voice-arch" / ".env.example"` to the `test_g_10_env_examples_agree` list.

#### `projects/voice-arch/.env.example` (NEW)
The shared `DATALAB_*` lines (copied from the root, G-10), then blank `VOICE_ARCH_OPENROUTER_API_KEY=`,
`VOICE_ARCH_LIVEKIT_API_KEY=`, `VOICE_ARCH_LIVEKIT_API_SECRET=` with a comment: use a dedicated OpenRouter key with a
50 $ credit limit; LiveKit keys = the root ones.

## 4. Source

#### `src/voice_arch/settings.py`
**Purpose:** `VoiceSettings(BaseSettings)`, prefix `VOICE_ARCH_`, `env_file=".env"`, `extra="ignore"`,
`env_ignore_empty=True`, `hide_input_in_errors=True` (as `mini_rag/settings.py`).
**Fields:** `openrouter_api_key: SecretStr` (required) · `livekit_url: str = "ws://127.0.0.1:7880"` (scheme `ws`/`wss`
checked) · `livekit_api_key: SecretStr`, `livekit_api_secret: SecretStr` (required) · `stt_model: str`,
`tts_model: str`, `tts_voice: str`, `llm_model: str` (defaults = the bench winners, set at the end of this phase;
until then `deepgram/nova-3`, `elevenlabs/eleven-flash-v2.5`, `21m00Tcm4TlvDq8ikWAM`, `deepseek/deepseek-v4-flash`) ·
`openrouter_providers: str = "deepinfra,gmicloud,parasail"` (slug list validated) · `openrouter_quantization: str = "fp8"` ·
`call_timeout_s: float = 240` · `agent_join_timeout_s: float = 20`.
**Constraints:** no secret in `repr`; a validation error never echoes input.

#### `src/voice_arch/audio.py`
**Purpose:** the only place that builds LiveKit model clients on OpenRouter (D-4).
**Functions:** `make_stt(settings, model: str | None = None) -> stt.STT` (openai.STT, `base_url`, `api_key`, `language="en"`;
returns the raw non-streaming STT — callers wrap it in `StreamAdapter` with silero VAD) · `make_tts(settings,
model=None, voice=None) -> tts.TTS` (openai.TTS, `response_format="pcm"`) · `make_llm(settings, model=None) -> llm.LLM`
(`openai.LLM.with_openrouter(model=…, api_key=…, provider={"order": [...], "quantizations": [q], "allow_fallbacks":
False})`, temperature 0).
**Constraints:** if the spike (below) shows the plugins don't work against OpenRouter, add `openrouter_adapters.py` with
one `stt.STT` and one `tts.TTS` subclass (HTTP via httpx) and point these factories at them — never two code paths.

#### `src/voice_arch/openrouter_key.py`
**Purpose:** spend accounting (D-6). `key_usage(api_key) -> float` = `GET https://openrouter.ai/api/v1/key` → `data.usage`
(USD). `KeyError`-shaped body → `OpenRouterKeyError` (never 0). `SpendTracker` context manager: reads usage before and
after; on a read failure logs a warning and exposes `cost_usd = None` (F-12).

#### `src/voice_arch/fields.py`
**Purpose:** stage-1 transcript scoring. `spoken_digits(text) -> str` maps "oh"/"zero"→0, "one"…"nine", "double X"→XX,
"triple X"→XXX, keeps digits. `normalize(text)` and `contains_phrase(hay, needle)` copied from
`projects/mini-rag/src/mini_rag/scoring.py` (cite it). `field_errors(transcript, truth: dict[str,str]) -> dict[str,bool]`:
phone = truth digits ⊂ `spoken_digits(transcript)`; name/address/slot = normalised containment.

#### `src/voice_arch/winners.py`
**Purpose:** pure selection (U-9). `pick_stt(rows, margin_per_40=1)`: fewest field errors; candidates within the margin
(scaled to the utterance count) tie → lower p50 latency → lower cost. `pick_tts(rows)`: rows failing the intelligibility
gate (round-trip transcript loses a field) are excluded → lowest median TTFB. `pick_llm(rows)`: highest tool-arg accuracy
→ lowest median TTFT. Each returns the model id plus a one-line reason.

#### `src/voice_arch/bench.py` (CLI `python -m voice_arch.bench --component stt|tts|llm [--n N]`)
**Purpose:** stage 1 (D-9, U-6). Candidates are constants: STT `deepgram/nova-3`, `assemblyai/universal-3-6-pro`,
`openai/gpt-4o-mini-transcribe`; TTS `elevenlabs/eleven-flash-v2.5` (voice `21m00Tcm4TlvDq8ikWAM`), `deepgram/aura-2`
(`aura-2-thalia-en`), `deepgram/flux-tts` (`flux-bree-en`); LLM `deepseek/deepseek-v4-flash`,
`google/gemini-3.5-flash-lite`, `anthropic/claude-haiku-5.5`.
- Corpus: `data/utterances.jsonl` synthesised once with `google/gemini-3.8-flash-lite-tts` (not an STT vendor) to
  `data/audio/<id>.wav` via tmp + rename; `data/audio/manifest.json` = sha256 of every file + TTS model + voice; a
  mismatch rebuilds (F-11). The manifest hash is a run param.
- STT: per candidate, `recognize()` each wav; latency, empty transcript = error (F-10), `field_errors`.
- TTS: 6 agent lines × 3 reps; TTFB = first audio frame, total time; intelligibility gate = transcribe the TTS output with
  the current STT winner and check the line's fields survive.
- LLM: `data/llm_cases.jsonl` (20 cases: a caller line + the expected tool name and args); TTFT, args exact.
- One `tracked_run(sub="bench", run_name=f"{component}")`: params (candidates, corpus hash, n), metrics per candidate
  `stt_<slug>_errors`, `stt_<slug>_p50_s`, `tts_<slug>_ttfb_p50_s`, `llm_<slug>_accuracy`, `llm_<slug>_ttft_p50_s`, and
  `cost_usd` from `SpendTracker`; rows to `results/<run_id>.jsonl`; winner + reason as tags. Never logs `exact_rate`.
- A 401/402 from OpenRouter aborts the bench, run FAILED (F-4).

#### `data/utterances.jsonl` (NEW, ~40 lines)
`{"id", "text", "truth": {"name"?, "phone"?, "address"?, "slot"?}}`. US formats: spelled names (`S-M-Y-T-H`), phones
with "oh"/"double", unusual street names, "next Tuesday afternoon", self-corrections ("…oh one nine, no, oh one eight").
Every truth value must appear in the text (a loader test checks it).

#### `data/llm_cases.jsonl` (NEW, 20 lines)
`{"id", "caller", "expected_tool", "expected_args"}` for the booking tools of Phase 2 (`record_name`, `record_phone`,
`record_address`, `record_problem`, `choose_slot`), including corrections.

## 5. Browser smoke (manual, README)
`docker compose up -d livekit`; run arch-A-only worker stub (`python -m voice_arch.smoke_agent`, a 20-line agent with the
current STT/TTS/LLM); `lk token create --join --room smoke` (LiveKit CLI); open the MIT agent-starter web page against
`ws://127.0.0.1:7880` from the Windows browser. Check audio both ways, note UDP vs TCP (F-13), hand-time 3 turns vs the
reported `e2e_latency` and log the offset as an MLflow param of the smoke run.

## 6. Docs
`ARCHITECTURE.md`: LiveKit line in Tech Stack and compose, `infra/livekit.yaml` and `projects/voice-arch/` in Project
Structure. `decisions.md`: ADR "LiveKit self-hosted + OpenRouter audio for voice-arch" (D-1, D-2, D-4, the 2.2 s estimate).

## Tests

#### `tests/test_settings.py`
| Test | Given → expected | Source |
|---|---|---|
| `test_missing_openrouter_key_fails_at_settings` | no key → ValidationError naming `openrouter_api_key` | F-13 pattern |
| `test_validation_error_never_echoes_secrets` | bad livekit_url + key `sk-or-v1-x` → message without `sk-or` | security |
| `test_livekit_url_needs_ws_scheme` | `http://x` → ValidationError; `ws://127.0.0.1:7880` ok | D-2 |

#### `tests/test_fields.py`
| Test | Given → expected | Source |
|---|---|---|
| `test_spoken_digits_maps_oh_double_triple` | "oh four one two double five triple nine" → "0412559999" | U-4 |
| `test_field_errors_flags_wrong_phone_only` | transcript with phone …018, truth …019 → `{"phone": True, "name": False}` | U-9 |
| `test_utterance_truth_appears_in_text` | every `data/utterances.jsonl` truth value ⊂ normalised text | data contract |

#### `tests/test_winners.py`
| Test | Given → expected | Source |
|---|---|---|
| `test_u_9_accuracy_within_margin_falls_back_to_latency` | A 2 errors 0.6 s, B 1 error 1.1 s, 40 utt → A | U-9 |
| `test_pick_stt_outside_margin_prefers_accuracy` | A 4 errors 0.6 s, B 1 error 1.1 s → B | U-9 |
| `test_pick_tts_excludes_unintelligible` | fastest fails gate → second fastest | U-9 |
| `test_pick_llm_accuracy_then_ttft` | 19/20 0.9 s vs 20/20 1.2 s → the 20/20 one | U-9 |

#### `tests/test_bench.py`
| Test | Given → expected | Source |
|---|---|---|
| `test_f_10_empty_transcript_counts_as_stt_error_in_bench` | fake STT returns "" → every field of that row is an error | F-10 |
| `test_f_11_truncated_or_other_voice_cache_is_rejected` | manifest hash mismatch / other voice → rebuild requested | F-11 |
| `test_f_4_402_aborts_the_bench` | fake STT raises 402 status error → run FAILED, later candidates not called | F-4 |
| `test_u_6_bench_never_logs_exact_rate` | bench on sqlite MLflow → no metric key `exact_rate` | U-6 |

#### `tests/test_openrouter_key.py`
| Test | Given → expected | Source |
|---|---|---|
| `test_key_usage_reads_data_usage` | MockTransport `{"data":{"usage":1.25}}` → 1.25 | D-6 |
| `test_key_usage_wrong_shape_raises` | `{"data":{}}` → `OpenRouterKeyError` | F-12 |
| `test_f_12_key_usage_read_failure_omits_cost_without_failing_run` | 2nd read raises → `cost_usd is None`, no exception | F-12 |

#### `tests/test_spike.py` (`@pytest.mark.integration`)
| Test | Given → expected | Source |
|---|---|---|
| `test_openrouter_stt_returns_text` | `data/audio/<first>.wav` through `make_stt().recognize` → non-empty text containing the truth name | D-4 |
| `test_openrouter_tts_returns_frames` | "Hello" through `make_tts().synthesize` → ≥ 1 audio frame, 24 kHz or declared rate | D-4 |
| `test_openrouter_llm_calls_a_tool` | llm_cases[0] → tool call `record_phone` with expected digits | D-5 |

**Done when:** all hooks pass (incl. the new gates), the integration spike passes live, the three bench runs are in
MLflow `voice-arch/bench`, the `VoiceSettings` defaults are the winners, the browser smoke is recorded in the README.
