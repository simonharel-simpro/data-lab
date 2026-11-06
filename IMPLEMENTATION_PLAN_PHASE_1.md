# Phase 1 — Infra, gates, OpenRouter audio, stage-1 bench, browser smoke

**Depends on:** nothing. **Agent:** `python-fastapi` (Python 3.12, uv). Repo: data-lab (`main`).
**Produces for Phase 2:** `VoiceSettings`, `make_stt / make_tts / make_llm`, `SpendTracker`, the pure normalisers
(`booking/normalize.py`), `TOOL_SCHEMAS` (`tool_schemas.py`), the chosen model defaults, `token.py` / `dispatch.py`.

Context (self-contained): `projects/voice-arch` compares voice-agent control architectures on LiveKit for an English
(US-format) appointment-booking phone agent. Every model call goes through OpenRouter (`https://openrouter.ai/api/v1`):
STT `/audio/transcriptions`, TTS `/audio/speech` (OpenAI-compatible), LLM `/chat/completions`. Pins:
`livekit-agents==1.8.8`, `livekit-plugins-openai==1.8.8`, `livekit-plugins-silero==1.8.8` (the VAD model ships in the
wheel), `livekit-api==1.2.2`, server image `livekit/livekit-server:v1.13.10`, browser `livekit-client@2.23.0`.
Data-lab rules: 127.0.0.1-only ports, `src/` modules ≤ 200 lines (pre-commit), ruff (root `ruff.toml`), pyright,
coverage ≥ 70. Reference patterns: `projects/mini-rag/src/mini_rag/settings.py` (settings), `.../run.py` (tracked_run,
JSONL crash copy, `smoke_*`), `.../scoring.py:56-69` (`normalize`).

## 1. Scaffold
`uv run --project packages/datalab datalab-new voice-arch --title "Voice agent architectures (LiveKit)"` (repo root).

#### `projects/voice-arch/PROJECT.md` (MODIFY the generated card)
Front matter `status: en cours`, `tags: [voice, livekit, agents]`, `data: "generated US caller utterances + 6 personas"`,
`metric: {key: exact_rate, goal: max}`. `## Objectif`: pick the control architecture (A orchestrator / B + state machine
/ C + call record) for a Simpro phone agent; bar ≥ 90 % exact, median e2e latency < 1.2 s, ≤ 50 $. `## Approche`: stage 1
bench, stage 2 three archs × 6 personas × 5 reps.

#### `projects/voice-arch/pyproject.toml` (MODIFY)
Runtime: `livekit-agents==1.8.8`, `livekit-plugins-openai==1.8.8`, `livekit-plugins-silero==1.8.8`, `livekit-api==1.2.2`,
`httpx~=0.28` (as datalab). Dev group (add to the template's): `import-linter>=2.15` (as mini-rag),
`pytest-asyncio==1.4.0`. Add `[tool.pytest.ini_options] asyncio_mode = "auto"`, `testpaths = ["tests"]`;
`[tool.coverage.run] source = ["voice_arch"]`. Import-linter contract "booking stays pure": `source_modules =
["voice_arch.booking"]`, `forbidden_modules = ["livekit", "mlflow", "datalab", "httpx"]`. Create
`src/voice_arch/__init__.py`, `src/voice_arch/booking/__init__.py`. Run `uv lock`.

#### `projects/voice-arch/.gitignore` (NEW): `results/`, `data/audio/`, `.env`.

## 2. Infra

#### `infra/livekit.yaml` (NEW, repo root)
`port: 7880`; `rtc: {tcp_port: 7881, udp_port: 7882, use_external_ip: false, node_ip: 127.0.0.1}`;
`logging: {level: info}`. No keys in the file (env `LIVEKIT_KEYS`).

#### `compose.yaml` (MODIFY)
Service `livekit` with `profiles: [voice]` (the default `docker compose up -d` is unchanged, D-19):
`image: livekit/livekit-server:v1.13.10`, `command: ["--config", "/etc/livekit.yaml"]`, `environment: LIVEKIT_KEYS:
"${LIVEKIT_API_KEY:-}: ${LIVEKIT_API_SECRET:-}"` (`:-`, never `:?` — interpolation runs for every service, so `:?`
would break every compose command without the keys; the server itself refuses empty keys at start),
volume `./infra/livekit.yaml:/etc/livekit.yaml:ro`, ports `127.0.0.1:7880:7880`, `127.0.0.1:7881:7881`,
`127.0.0.1:7882:7882/udp`, `restart: unless-stopped`. Healthcheck only if the image ships a binary usable for it (check
`docker run --rm --entrypoint ls livekit/livekit-server:v1.13.10 /`); else none, with a comment. Header comment: add
LiveKit's ports and `docker compose --profile voice up -d`.

#### `.env.example` (MODIFY, root): blank `LIVEKIT_API_KEY=`, `LIVEKIT_API_SECRET=` (comment: secret ≥ 32 chars).

#### `tests/test_compose.py` (MODIFY)
Render with `--profile voice` added to the argv. Add `("livekit","127.0.0.1","7880",7880)`, `("livekit","127.0.0.1",
"7881",7881)`, `("livekit","127.0.0.1","7882",7882)` to `EXPECTED_PORTS` (check how the existing comparison reads the
protocol; extend it to UDP if needed). Assert the default render (no profile) has no `livekit` service.

## 3. Gates

#### `.pre-commit-config.yaml` (MODIFY)
`declared-deps-voice-arch` (copy `declared-deps-mini-rag`, paths `projects/voice-arch`) and `gates-voice-arch` (copy
`gates-mini-rag`: `cd projects/voice-arch && uv run --locked lint-imports && uv run --locked pyright && uv run --locked
pytest -q --cov`, `files: ^(projects/voice-arch/|packages/datalab/src/)`, stage pre-push).

#### `.github/workflows/ci.yml` (MODIFY): job `voice-arch` mirroring `pilot` (uv sync --locked, lint-imports, pyright,
pytest --cov, pip-audit) in `projects/voice-arch`.

#### `packages/datalab/tests/test_settings.py` (MODIFY)
In `test_g_10_env_examples_agree`, add `REPO_ROOT / "projects" / "voice-arch" / ".env.example"` to the list and
`assert shared[3] == shared[0]` next to the existing asserts.

#### `projects/voice-arch/.env.example` (NEW)
The root `DATALAB_*` lines (G-10), then blank `VOICE_ARCH_OPENROUTER_API_KEY=`, `VOICE_ARCH_LIVEKIT_API_KEY=`,
`VOICE_ARCH_LIVEKIT_API_SECRET=`; comment: a dedicated OpenRouter key with a 50 $ credit limit; LiveKit keys = the root ones.

## 4. Source

#### `src/voice_arch/settings.py`
`VoiceSettings(BaseSettings)`, prefix `VOICE_ARCH_`, `env_file=".env"`, `extra="ignore"`, `env_ignore_empty=True`,
`hide_input_in_errors=True` (as mini-rag). Fields: `openrouter_api_key: SecretStr` (required); `livekit_url: str =
"ws://127.0.0.1:7880"` (validator: scheme `ws`/`wss`); `livekit_api_key: SecretStr`, `livekit_api_secret: SecretStr`
(required); `stt_model`, `tts_model`, `tts_voice`, `llm_model: str` (defaults until the bench decides:
`deepgram/nova-3`, `elevenlabs/eleven-flash-v2.5`, `21m00Tcm4TlvDq8ikWAM`, `deepseek/deepseek-v4-flash`);
`caller_llm_model: str = "google/gemini-3.5-flash-lite"`, `caller_temperature: float = 0.7` (D-17);
`openrouter_providers: str = "deepinfra,gmicloud,parasail"` (slug list validated, as mini-rag) + `provider_list`
property; `openrouter_quantization: str = "fp8"`; `call_timeout_s: float = 240`; `agent_join_timeout_s: float = 20`.

#### `src/voice_arch/audio.py`
`make_stt(settings, model: str | None = None) -> stt.STT` = `openai.STT(model=…, base_url=OPENROUTER, api_key=…,
language="en")` (non-streaming; `AgentSession` wraps it with its VAD automatically) · `make_tts(settings, model=None,
voice=None) -> tts.TTS` = `openai.TTS(model, voice, base_url, api_key, response_format="pcm")` · `make_llm(settings,
model=None, temperature=0.0, providers: list[str] | None = None) -> llm.LLM` = `openai.LLM.with_openrouter(model=…,
api_key=…, temperature=…, provider={"order": providers, "quantizations": [q], "allow_fallbacks": False})` when a provider
list is given, else no `provider`. `OPENROUTER = "https://openrouter.ai/api/v1"`. If the spike fails, add
`openrouter_adapters.py` (one `stt.STT` + one `tts.TTS` subclass over httpx) and point these factories at it — one path.

#### `src/voice_arch/openrouter_key.py`
`KeyUsage(usage: float, limit_remaining: float | None)` (frozen dataclass). `key_usage(api_key: str, *, client:
httpx.Client | None = None) -> KeyUsage` = `GET https://openrouter.ai/api/v1/key`, `Authorization: Bearer`; non-200 →
`OpenRouterKeyError(f"HTTP {status}")`; missing `data.usage` → `OpenRouterKeyError` (never 0). `SpendTracker(api_key, *,
client=None)` context manager: `before = key_usage()` in `__enter__` (raises on failure), `__exit__` reads again; a read
failure there logs a warning → `cost_usd = None`; else `cost_usd = after - before`; exposes `remaining_before`.

#### `src/voice_arch/booking/normalize.py` (pure)
`spoken_digits(text) -> str`: tokens "oh"/"zero"→0, "one"…"nine", "double X"→XX, "triple X"→XXX, digit characters kept,
everything else dropped. `normalize_phone(text)`: `spoken_digits`, an 11-digit value starting with 1 loses it.
`normalize_address(text)`: NFKC, casefold, punctuation → space, map `street→st, road→rd, avenue→ave, drive→dr, lane→ln,
boulevard→blvd, court→ct, apartment|apt→unit`, US state names (incl. multi-word "new york", "north carolina") → codes,
collapse spaces, drop a trailing 5-digit ZIP. `normalize_name(text)`: join runs of single letters separated by `-` or
spaces ("S-M-Y-T-H" → "smyth", U-24), NFKC, casefold, drop `'` and `.`, collapse spaces.
`normalize_text(text)` / `contains_phrase(hay, needle)`: copied from mini-rag `scoring.py:56-69` (cite it).

#### `src/voice_arch/tool_schemas.py` (pure)
`ToolArg(name: str, type: Literal["str","problem_type","slot_id"])`, `ToolSchema(name: str, description: str, args:
tuple[ToolArg, ...])`; `TOOL_SCHEMAS: tuple[ToolSchema, ...]` = `record_name(name)`, `record_phone(phone)`,
`record_address(address)`, `record_problem(problem_type)`, `choose_slot(slot_id)`. `to_openai_tools() -> list[dict]`
(JSON-schema function tools; `problem_type` enum = plumbing/electrical/hvac/appliance/other). Phase 2's tools must use
these names and arg names (U-26).

#### `src/voice_arch/fields.py`
`field_errors(transcript: str, truth: Mapping[str, str]) -> dict[str, bool]` (True = error): phone → `normalize_phone(
truth) not in spoken_digits(transcript)`; name/address/slot → not `contains_phrase(transcript, truth)` after the matching
normaliser. Empty transcript → every field True (F-10). `args_correct(actual: Mapping, expected: Mapping) -> bool`:
per-arg equality after the matching normaliser; `problem_type`/`slot_id` exact (U-15).

#### `src/voice_arch/winners.py` (pure)
Rows (frozen dataclasses): `SttRow(model, errors: int, n_utterances: int, p50_s: float)`, `TtsRow(model, ttfb_p50_s:
float, intelligible: bool)`, `LlmRow(model, correct: int, n_cases: int, ttft_p50_s: float)`. `pick_stt(rows) -> Choice`:
best = fewest errors; candidates with `errors ≤ best + ceil(n_utterances / 40)` tie (margin measured from the best,
U-22) → lowest `p50_s`. `pick_tts(rows)`: intelligible rows only → lowest TTFB; none → `NoEligibleCandidate` (U-22).
`pick_llm(rows)`: most correct → lowest TTFT. `Choice(model: str, reason: str)`. Cost is reported (catalog prices in
PROJECT.md), not used to rank.

#### `src/voice_arch/corpus.py`
`build_corpus(utterances: list[Utterance], tts: tts.TTS, out_dir: Path, *, tts_model: str, voice: str) -> Corpus`:
reuses `out_dir/manifest.json` only if it lists the same ids, `tts_model`, `voice` and every wav's sha256 matches; else
re-synthesises each wav to a tmp file then `os.replace` (F-11). `Corpus(paths: dict[str, Path], hash: str)`.
`load_utterances(path)`: validates every truth value appears in the text under the field's normaliser.

#### `src/voice_arch/bench.py` (CLI `python -m voice_arch.bench --component stt|tts|llm [--n N]`)
Seams take objects, not settings: `run_stt(stts: Mapping[str, stt.STT], corpus, utterances) -> list[SttRow]` ·
`run_tts(ttss: Mapping[str, tts.TTS], lines: list[str], judge_stt: stt.STT, reps=3) -> list[TtsRow]` (TTFB = first frame;
intelligible = `field_errors` of the round-trip transcript all False) · `run_llm(llms: Mapping[str, llm.LLM], cases) ->
list[LlmRow]` (tools from `to_openai_tools()`, `args_correct`). Candidates (constants): STT `deepgram/nova-3`,
`assemblyai/universal-3-6-pro`, `openai/gpt-4o-mini-transcribe`; TTS `elevenlabs/eleven-flash-v2.5`
(`21m00Tcm4TlvDq8ikWAM`), `deepgram/aura-2` (`aura-2-thalia-en`), `deepgram/flux-tts` (`flux-bree-en`); LLM
`deepseek/deepseek-v4-flash`, `google/gemini-3.5-flash-lite`, `anthropic/claude-haiku-5.5`. Corpus voice: TTS
`google/gemini-3.8-flash-lite-tts` (no STT vendor). Run order: stt, then tts (judge = the STT winner from settings).
`main()`: `VoiceSettings`, datalab `Settings`, `preflight`, one `tracked_run(project, settings, run_name=component,
sub="bench")` with `SpendTracker` inside it; params (candidates, corpus hash, n); metrics `stt_<slug>_errors`,
`stt_<slug>_p50_s`, `tts_<slug>_ttfb_p50_s`, `llm_<slug>_correct`, `llm_<slug>_ttft_p50_s` (slug = model id with
non-alnum → `_`), `cost_usd` when known; rows to `results/<run_id>.jsonl`; tags `winner`, `winner_reason`. Never logs
`exact_rate` (U-6). An `APIStatusError` with status 401/402 aborts, run FAILED (F-4).

#### `src/voice_arch/token.py` and `dispatch.py` (CLIs, for the smoke and manual calls)
`token.py --room R [--identity me] [--agent NAME]` prints a join token (`livekit.api.AccessToken(key, secret)
.with_identity(...).with_grants(VideoGrants(room_join=True, room=R))`, plus the room-config agent dispatch when
`--agent` is given, `.to_jwt()`); `make_token(settings, room, identity, agent=None) -> str` is the tested function. `dispatch.py --arch a|b|c --room R` creates an agent
dispatch (`LiveKitAPI(url=http form of livekit_url, ...)`, `agent_dispatch.create_dispatch(CreateAgentDispatchRequest(
agent_name="booking-agent", room=R, metadata=json))`) — usable once Phase 2's worker exists; Phase 1 uses `smoke_agent`.

#### `src/voice_arch/smoke_agent.py` (CLI `python -m voice_arch.smoke_agent dev`)
≤ 40 lines: `AgentServer(ws_url, api_key, api_secret from VoiceSettings)`, `@server.rtc_session(agent_name="smoke")`,
an `Agent("You are a friendly test agent. Keep answers short.")` with `make_stt/make_tts/make_llm`; logs each
`e2e_latency` from `conversation_item_added`.

#### `web/index.html` (NEW, static, MIT-style minimal client)
~60 lines: inputs for URL (default `ws://127.0.0.1:7880`) and token; `livekit-client@2.23.0` from
`https://cdn.jsdelivr.net/npm/livekit-client@2.23.0/dist/livekit-client.umd.js`; connect, publish the microphone,
attach remote audio tracks, show the connection's ICE candidate type (UDP/TCP). Open it from Windows over
`python -m http.server --bind 127.0.0.1 8765 --directory web`.

#### Data
`data/utterances.jsonl` (~40): `{"id", "text", "truth": {"name"?, "phone"?, "address"?, "slot"?}}`, US formats, spelled
names, "oh"/"double", unusual streets, "next Tuesday afternoon", self-corrections. `data/llm_cases.jsonl` (20):
`{"id", "caller", "expected_tool", "expected_args"}` using `TOOL_SCHEMAS` names; includes corrections and a spelled name.
`data/agent_lines.txt` (6 short agent lines for the TTS bench).

## 5. Browser smoke (manual, README) — F-13
`docker compose --profile voice up -d livekit`; `python -m voice_arch.smoke_agent dev`; `python -m voice_arch.token
--room smoke --agent smoke` (the token carries the dispatch: `.with_room_config(RoomConfiguration(agents=[
RoomAgentDispatch(agent_name="smoke")]))`, so no CLI is needed); serve `web/`, open it in the Windows browser, paste the
token. Check audio both ways, record UDP vs TCP, hand-time 3 turns vs the logged `e2e_latency`; write the offset in
PROJECT.md (no MLflow run).

## 6. Docs
`ARCHITECTURE.md`: LiveKit in Tech Stack and compose (profile `voice`), `infra/livekit.yaml` and `projects/voice-arch/`
in Project Structure. `decisions.md`: ADR "voice-arch: self-hosted LiveKit + OpenRouter audio" (D-1, D-2, D-4, D-19,
the ~2.2 s estimate, #25).

## Tests (fakes: tiny classes with the plugin method used — `recognize`, `synthesize`, `chat` — returning canned data;
MLflow on a tmp sqlite URI as in mini-rag `tests/conftest.py`)

| File · test | Given → expected | Source |
|---|---|---|
| test_settings · `test_missing_openrouter_key_fails_at_settings` | no key → ValidationError naming `openrouter_api_key` | startup validation |
| test_settings · `test_validation_error_never_echoes_secrets` | bad livekit_url + key `sk-or-v1-x` → message without `sk-or` | security |
| test_settings · `test_livekit_url_needs_ws_scheme` | `http://x` → error; `ws://127.0.0.1:7880` ok | D-2 |
| test_normalize · `test_spoken_digits_maps_oh_double_triple` | "oh four one two double five triple nine" → "041255999" | U-4 |
| test_normalize · `test_u_4_phone_spoken_double_and_oh_normalise_to_digits` | "four one five, five double five, oh one three four" → "4155550134" | U-4 |
| test_normalize · `test_phone_drops_leading_country_code` | "1 415 555 0134" → "4155550134" | U-4 |
| test_normalize · `test_address_variants_are_equal` (param) | "12 Oak Road, Springfield, IL" vs "12 oak rd springfield illinois 62704" → equal; "5 Elm St, New York, NY" vs "5 elm street new york new york" → equal | U-4 |
| test_normalize · `test_u_8_smyth_does_not_match_smith` | names differ after normalising | U-8 |
| test_normalize · `test_u_24_spelled_letters_normalise_to_joined_name` | "S-M-Y-T-H" and "s m y t h" → "smyth" | U-24 |
| test_fields · `test_field_errors_flags_wrong_phone_only` | transcript phone …018, truth …019 + right name → `{"phone": True, "name": False}` | U-9 |
| test_fields · `test_f_10_empty_transcript_counts_as_stt_error` | "" → every field True | F-10 |
| test_fields · `test_u_15_llm_arg_accuracy_compares_normalised_values` | actual phone "(415) 555-0134" vs expected "4155550134" → True | U-15 |
| test_tool_schemas · `test_u_26_llm_cases_match_tool_schemas` | every case's tool/arg keys ∈ `TOOL_SCHEMAS` | U-26 |
| test_winners · `test_u_9_accuracy_within_margin_falls_back_to_latency` | A 2 err 0.6 s, B 1 err 1.1 s, n=40 → A | U-9 |
| test_winners · `test_pick_stt_outside_margin_prefers_accuracy` | A 4 err 0.6 s, B 1 err 1.1 s → B | U-9 |
| test_winners · `test_u_22_stt_margin_is_measured_from_the_best` | A 1, B 2, C 3 err, n=40 → C excluded | U-22 |
| test_winners · `test_u_22_pick_tts_with_no_intelligible_candidate_raises` | all `intelligible=False` → `NoEligibleCandidate` | U-22 |
| test_winners · `test_pick_llm_accuracy_then_ttft` | 19/20 0.9 s vs 20/20 1.2 s → the 20/20 | U-9 |
| test_corpus · `test_f_11_truncated_or_other_voice_cache_is_rejected` | manifest voice differs / a wav's hash differs → re-synthesised (fake TTS called) | F-11 |
| test_corpus · `test_utterance_truth_must_appear_in_text` | truth phone absent from text → error naming the id | data |
| test_bench · `test_f_4_402_aborts_the_bench` | fake STT raises `APIStatusError(402)` → run FAILED, next candidate not called | F-4 |
| test_bench · `test_u_6_bench_never_logs_exact_rate` | stt bench with fakes → no `exact_rate` metric | U-6 |
| test_openrouter_key · `test_key_usage_reads_data_usage` | MockTransport `{"data":{"usage":1.25,"limit_remaining":48.0}}` → (1.25, 48.0) | D-6 |
| test_openrouter_key · `test_key_usage_wrong_shape_or_401_raises` | `{"data":{}}` / HTTP 401 → `OpenRouterKeyError` | F-12 |
| test_openrouter_key · `test_f_12_failed_second_read_leaves_cost_none` | 2nd read 500 → `cost_usd is None`, no exception | F-12 |
| integration test_spike · `test_openrouter_stt_returns_text` | first corpus wav → non-empty text containing its truth name | D-4 |
| integration test_spike · `test_openrouter_tts_returns_frames` | "Hello" → ≥ 1 frame | D-4 |
| integration test_spike · `test_openrouter_llm_calls_a_tool` | llm_cases[0] → its expected tool and args | D-5 |

**Done when:** hooks pass (incl. the new gates), the spike passes live, the three bench runs are in MLflow
`voice-arch/bench`, `VoiceSettings` defaults = winners (reason in PROJECT.md), the browser smoke is in the README.
