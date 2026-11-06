# Phase 2 — Booking domain + architectures A/B/C + worker

**Depends on Phase 1 (already exists):** `src/voice_arch/settings.py` (`VoiceSettings`: OpenRouter key, LiveKit
url/key/secret, chosen `stt_model/tts_model/tts_voice/llm_model`, `provider_list`, `openrouter_quantization`),
`audio.py` (`make_stt`, `make_tts`, `make_llm(settings, model=None, temperature=0.0, providers=None)`),
`booking/normalize.py` (`normalize_phone/address/name`, pure), `tool_schemas.py` (`TOOL_SCHEMAS`: `record_name(name)`,
`record_phone(phone)`, `record_address(address)`, `record_problem(problem_type)`, `choose_slot(slot_id)`), the compose
`livekit` service (profile `voice`, `ws://127.0.0.1:7880`), the import-linter contract "booking stays pure"
(`voice_arch.booking` must not import livekit, mlflow, datalab, httpx), `token.py`, `dispatch.py`, `web/index.html`.
**Agent:** `python-fastapi`. **Produces for Phase 3:** `BookingRecord`, `SCORED_FIELDS`, `is_exact`, `CALENDAR`,
`ProblemType`, `Arch`/`parse_arch`, `CallResult` (+`RESULT_TOPIC`), the worker (`agent_name="booking-agent"`).

Context (self-contained): the agent books a US service appointment by voice — name, phone, address, problem type, slot,
then a read-back confirmation. A, B and C differ ONLY in control structure: same LLM, audio, per-field instructions and
tools. A = one `Agent` with all tools. B = a `TaskGroup` (`livekit.agents.beta.workflows`) of custom `AgentTask`s, one
per step, regression allowed. C = B + a structured call record injected into each task. LiveKit 1.8.8 APIs (verified):
`Agent`, `AgentTask[T]` (`self.complete(result)`), `TaskGroup(summarize_chat_ctx=…)` + `.add(factory, id=,
description=)` (factories, not instances; results in `TaskGroupResult.task_results[id]`), `function_tool`, `RunContext`
(`ctx.userdata`), `AgentSession(stt, llm, tts, vad, userdata)`, `session.on("close")` → `CloseEvent(reason, error)`,
`session.on("error")` → `ErrorEvent(error, source)`, `AgentServer(ws_url=, api_key=, api_secret=)`,
`@server.rtc_session(agent_name=…)`, `JobContext.make_session_report(session).to_dict()`,
`room.local_participant.send_text(text, topic=…)`, `silero.VAD.load()`.

## Domain (pure package `voice_arch.booking`)

#### `booking/record.py`
`ProblemType(StrEnum)`: plumbing, electrical, hvac, appliance, other (values lowercase). `SCORED_FIELDS: Final =
("name", "phone", "address", "problem_type", "slot_id")`. `BookingRecord(BaseModel)`: `name: str | None = None`,
`phone: str | None = None`, `address: str | None = None`, `problem_type: ProblemType | None = None`, `slot_id: str |
None = None`, `confirmed: bool = False`, `corrections: list[str] = Field(default_factory=list)`.
`set_field(field: Literal[...SCORED_FIELDS], value: str) -> None`: `problem_type` coerced with `ProblemType(value)`
(invalid → `ValueError`); overwriting a different value appends the field to `corrections`; any set while
`confirmed` resets `confirmed = False` (U-2). `missing() -> list[str]` (SCORED_FIELDS order). `confirm()` →
`IncompleteRecordError(missing)` when incomplete. `ExpectedRecord(BaseModel, extra="forbid")` with the 5 scored fields
as required `str` (U-25). `is_exact(actual: BookingRecord | None, expected: ExpectedRecord) -> tuple[bool, dict[str,
bool]]`: per field, normalised equality (phone/address/name via `normalize`, problem_type and slot_id exact); `None`
actual → all False (U-13); exact = all True AND `actual.confirmed` (U-2).

#### `booking/calendar.py`
`REFERENCE_DATE = date(2026, 11, 9)` (Monday). All times naive local, "America/Chicago" stated in docstrings only.
`Slot(id: str, start: datetime, booked: bool)` frozen. `CALENDAR: tuple[Slot, ...]` — exactly these 12 (U-7, D-18):
`ST_20261109_0900` booked · `ST_20261109_1400` · `ST_20261110_0900` · `ST_20261110_1400` · `ST_20261110_1600` booked ·
`ST_20261111_1100` · `ST_20261111_1600` · `ST_20261112_0900` booked · `ST_20261112_1400` · `ST_20261113_0900` ·
`ST_20261113_1100` · `ST_20261113_1600`. `available(day: date | None = None, part: Literal["morning","afternoon"] |
None = None, taken: frozenset[str] = frozenset()) -> list[Slot]` (excludes `booked` and `taken`; morning < 12:00).
`describe(slot) -> str` ("Tuesday November 10 at 2 PM"). `slot_by_id(id) -> Slot` → `UnknownSlotError`. Never reads
`date.today()`; never mutates `CALENDAR` (bookings live in the session state).

#### `booking/actions.py` (pure; the only code that writes the record)
Each returns the reply string the LLM sees. `apply_record(record, field, value) -> str` ("Noted.", or the error text
for an invalid problem type) · `apply_check_slots(day: str | None, part: str | None, taken) -> str` (≤ 2 described
slots with ids, or "No free slot then; offer another day.") · `apply_choose_slot(record, slot_id, taken) -> str`:
unknown id → "That slot doesn't exist…", booked/taken → "That slot is taken…" (record unchanged, U-17), else
`set_field("slot_id")` · `apply_confirm(record) -> str`: incomplete → "Still missing: …" listing fields; complete →
`confirm()`, "Confirmed."

#### `booking/instructions.py`
Shared English strings (≤ 3 sentences each): `GREETING`, `ASK_NAME` (ask to spell unusual names), `ASK_PHONE` (read
back grouped digits), `ASK_ADDRESS` (number, street, city, state), `ASK_PROBLEM` (one of the five types; first stated
problem wins), `ASK_SLOT` (call check_slots; offer at most two), `CONFIRM` (read the whole record back; on any change,
update it and read back again — U-18), `GOODBYE`, `CONTEXT` ("This week starts Monday November 9, 2026.").

## LiveKit layer (package `voice_arch.agents`)

#### `agents/state.py`: `@dataclass BookingState`: `record: BookingRecord = field(default_factory=BookingRecord)`,
`taken: set[str] = field(default_factory=set)`.

#### `agents/tools.py`
`@function_tool` wrappers named exactly as `TOOL_SCHEMAS` (+ `check_slots(day, part)`, `confirm_booking()`), each one
line delegating to `booking.actions` with `ctx.userdata`. `confirm_booking`, on "Confirmed.", says `GOODBYE` and
schedules `ctx.session.shutdown(drain=True)` (F-1). `ALL_TOOLS` list.

#### `agents/arch_a.py`: `OrchestratorAgent(Agent)`: instructions = CONTEXT + GREETING + every ASK_* + CONFIRM; tools
`ALL_TOOLS`; `on_enter` says GREETING (only the booking agent greets, F-8).

#### `agents/arch_b.py`
`SUMMARIZE_CHAT_CTX: Final = False` (F-15). Custom tasks (NOT LiveKit's built-in Get*Task — their own instructions would
break the shared-instruction rule): `NameTask`, `PhoneTask`, `AddressTask`, `ProblemTask`, `SlotTask`, `ConfirmTask`,
each `AgentTask[None]` with instructions = CONTEXT + its ASK_*/CONFIRM, its tool(s) from `agents/tools.py`, and
`self.complete(None)` once the tool reply is "Noted."/a chosen slot/"Confirmed.". `build_task_group() -> TaskGroup`:
`TaskGroup(summarize_chat_ctx=SUMMARIZE_CHAT_CTX)`, `.add(lambda: NameTask(), id="name", description="collect the
caller's name")`, then phone, address, problem, slot, confirm. `BookingFlowAgent(Agent)`: greets, then `await
build_task_group()`. The tools are the only write path (no write from task results).

#### `agents/arch_c.py`
Same tasks and group (import from arch_b) with `memory=True`: each task's `on_enter` calls `await
self.update_instructions(base + render_call_record(ctx.userdata.record))`; `render_call_record(record) -> str` (pure,
lives in `booking/actions.py`) lists filled fields, `missing()`, `corrections`. Extra tools `read_record()` and
`update_record(field, value)` (→ `apply_record`; unknown field → error text).

#### `agents/registry.py`: `Arch(StrEnum)` a/b/c; `parse_arch(raw: str | None) -> Arch` → `UnknownArchError` for
None/""/unknown/whitespace — never a default (F-9); `build_agent(arch) -> Agent`.

#### `src/voice_arch/result.py`
`RESULT_TOPIC: Final = "voice-arch.result"`. `CallResult(BaseModel)`: `room: str`, `arch: Arch | None`, `run_id: str |
None`, `record: BookingRecord | None`, `report: dict | None` (`SessionReport.to_dict()`), `close_reason: str | None`,
`error: str | None`, `http_status: int | None`, `session_errors: int = 0`, `summarize_chat_ctx: bool | None`.
`to_json()`, `from_json(text)` (invalid → `ResultFormatError`). `http_status_of(err) -> int | None`: walks `err`,
`err.error`, `__cause__` for a `status_code` attribute.

#### `src/voice_arch/worker.py` (`python -m voice_arch.worker dev|start`)
`server = AgentServer(ws_url=s.livekit_url, api_key=…, api_secret=…)`; `@server.rtc_session(agent_name="booking-agent")
async def entry(ctx: JobContext)`:
1. `meta = parse_metadata(ctx.job.metadata)` → `(Arch, run_id or "manual")`; `UnknownArchError` → send an error
   `CallResult` and return (F-9).
2. `session = AgentSession(stt=make_stt(s), llm=make_llm(s, providers=s.provider_list), tts=make_tts(s),
   vad=silero.VAD.load(), userdata=BookingState())`; count `error` events; keep the last `CloseEvent`.
3. `await session.start(agent=build_agent(arch), room=ctx.room)`; wait for the close event (asyncio.Event).
4. `result = build_result(...)`: report via `ctx.make_session_report(session).to_dict()` (raises → `report=None`,
   `error=` message, F-3); `http_status = http_status_of(close.error)`; then `await
   ctx.room.local_participant.send_text(result.to_json(), topic=RESULT_TOPIC)` BEFORE returning (not in
   `on_session_end`, where the room may be gone). Never writes files.
`parse_metadata(raw: str) -> tuple[Arch, str]` and `build_result(room, arch, run_id, state, close, errors,
report_fn) -> CallResult` are pure and unit-tested.

## Tests (pure units; LiveKit-free except the integration file)

| File · test | Given → expected | Source |
|---|---|---|
| booking/test_record · `test_u_2_record_edit_after_confirm_resets_confirmed` | confirmed, `set_field("slot_id", other)` → `confirmed False`, `corrections == ["slot_id"]` | U-2 |
| booking/test_record · `test_u_2_unconfirmed_correct_record_is_not_exact` | 5 right, not confirmed → `(False, all True)` | U-2 |
| booking/test_record · `test_u_13_missing_field_counts_as_incorrect` | no address → `per_field["address"] False`, exact False | U-13 |
| booking/test_record · `test_none_record_is_all_wrong` | `is_exact(None, e)` → `(False, all False)` | F-3 |
| booking/test_record · `test_confirm_incomplete_raises` | phone missing → `IncompleteRecordError(["phone",…])` | U-2 |
| booking/test_record · `test_exact_record_after_normalisation` | "Jon O'Neil", "+1 (415) 555-0134", "27 Wattle Street, Austin, Texas 73301", plumbing, ST_20261110_1400, confirmed vs "jon oneil", "4155550134", "27 wattle st austin tx", plumbing, ST_20261110_1400 → `(True, …)` | U-2, U-4, U-8 |
| booking/test_record · `test_u_25_expected_record_keys_equal_scored_fields` | `ExpectedRecord.model_fields` keys == `SCORED_FIELDS`; extra key → ValidationError | U-25 |
| booking/test_record · `test_invalid_problem_type_rejected` | `set_field("problem_type","roofing")` → ValueError | U-5 |
| booking/test_calendar · `test_u_7_calendar_is_independent_of_today` | monkeypatched today 2030-01-01 → same ids | U-7 |
| booking/test_calendar · `test_available_filters_day_and_part` | Tue Nov 10 afternoon → `["ST_20261110_1400"]` (1600 booked) | D-18 |
| booking/test_calendar · `test_available_excludes_taken` | Fri morning, taken {0900} → `["ST_20261113_1100"]` | D-18 |
| booking/test_calendar · `test_unknown_slot_raises` | `ST_20990101_0900` → `UnknownSlotError` | D-18 |
| booking/test_actions · `test_u_17_choose_booked_slot_returns_error_and_keeps_record` | `ST_20261109_0900` → text "taken", `slot_id is None` | U-17 |
| booking/test_actions · `test_choose_unknown_slot_returns_error` | `ST_x` → text "doesn't exist", record unchanged | D-18 |
| booking/test_actions · `test_confirm_incomplete_lists_missing_fields` | name only → "Still missing: phone, address, problem_type, slot_id" | U-2 |
| booking/test_actions · `test_render_call_record_lists_missing_and_corrections` | phone corrected once → text contains "phone" under corrections and the 3 missing fields | D-5 |
| agents/test_registry · `test_f_9_unknown_arch_metadata_is_refused_not_defaulted` | None, "", "d", "B " → `UnknownArchError` | F-9 |
| agents/test_registry · `test_parse_arch_accepts_known_values` | "a","b","c" → A/B/C | F-9 |
| agents/test_arch_b · `test_f_15_taskgroup_summarize_flag_is_off` | `build_task_group()._summarize_chat_ctx is False`; `SUMMARIZE_CHAT_CTX is False` | F-15 |
| agents/test_tools · `test_u_26_tool_names_and_args_match_schemas` | each `TOOL_SCHEMAS` name exists in `ALL_TOOLS` with the same arg names (inspect signatures) | U-26 |
| test_result · `test_result_round_trips` | CallResult with record + report → `from_json(to_json())` equal | D-7 |
| test_result · `test_f_3_garbage_result_raises_format_error` | `"{not json"` → `ResultFormatError` | F-3 |
| test_result · `test_http_status_of_finds_nested_status` | wrapper with `.error.status_code == 402` → 402; plain Exception → None | F-4 |
| test_worker · `test_parse_metadata_requires_arch` | `'{"run_id":"r"}'` → `UnknownArchError`; `'{"arch":"b"}'` → (B, "manual") | F-9 |
| test_worker · `test_f_3_report_failure_yields_error_result` | `report_fn` raises RuntimeError → `report None`, `error` contains its message, record kept | F-3 |
| integration/test_arch_text · `test_arch_<a|b|c>_books_a_clean_caller` (param) | text-mode session (`AgentSession(llm=make_llm(...))`, `await session.run(user_input=…)` turns giving all fields + "yes") → `is_exact` True vs the script's expected record | goal |
| integration/test_arch_text · `test_u_18_slot_change_during_readback_reconfirms_new_slot` (param) | during read-back the user says "actually Thursday at 2" → final slot `ST_20261112_1400`, confirmed | U-18 |

**Done when:** unit tests + hooks pass (coverage ≥ 70 with the pure modules carrying it), the integration tests pass
live, and a browser call (Phase 1 page, `python -m voice_arch.token --room t1` + `python -m voice_arch.dispatch --arch b
--room t1`) completes a booking with each arch.
