# Phase 2 — Booking domain + architectures A/B/C + worker

**Depends on Phase 1:** `VoiceSettings` (`src/voice_arch/settings.py`), `make_stt / make_tts / make_llm`
(`src/voice_arch/audio.py`: OpenRouter-backed LiveKit plugins; STT is non-streaming → wrap with
`agents.stt.StreamAdapter` + silero VAD), the compose `livekit` service on `ws://127.0.0.1:7880`.
**Agent:** `python-fastapi`. **Produces for Phase 3:** `BookingRecord`, `normalize_*`, `CALENDAR`, `ProblemType`, `Arch`,
`CallResult`, the worker registered as `agent_name="booking-agent"` sending results on text-stream topic
`voice-arch.result`.

Context (self-contained): the agent books a US service appointment by voice: name, phone, address, problem type, slot,
then a read-back confirmation. Three control architectures must differ ONLY in control structure — same LLM, same audio,
same per-field instructions, same tools:
- **A** one `Agent` with all tools and one prompt.
- **B** a LiveKit `TaskGroup` (`livekit.agents.beta.workflows`) of AgentTasks, one per step, with regression allowed.
- **C** B + side memory: a structured `CallRecord` (fields, missing, corrections) injected into each task's context, with
  `read_record` / `update_record` tools.
`livekit.agents` 1.8.8 API: `Agent`, `AgentTask[T]`, `TaskGroup`, `function_tool`, `RunContext`, `AgentSession(stt, llm,
tts, vad, userdata=...)`, `AgentServer`, `JobContext`, `ctx.make_session_report()`, `session.shutdown()`,
`room.local_participant.send_text(text, topic=...)`. Check names against the installed package before coding.

## Domain (pure — must not import livekit, mlflow, datalab; import-linter contract from Phase 1)

#### `src/voice_arch/booking/record.py`
**Purpose:** the booking record and its exactness rule.
**Types:** `ProblemType(StrEnum)`: `PLUMBING="plumbing"`, `ELECTRICAL="electrical"`, `HVAC="hvac"`,
`APPLIANCE="appliance"`, `OTHER="other"` (U-5). `BookingRecord` (pydantic, mutable): `name: str | None`,
`phone: str | None`, `address: str | None`, `problem_type: ProblemType | None`, `slot_id: str | None`,
`confirmed: bool = False`, `corrections: list[str]` (field names corrected, for C and the report).
**Methods:** `set_field(field, value)` — sets the value, appends to `corrections` when it overwrites a different value,
and resets `confirmed = False` when the record was confirmed (U-2) · `missing() -> list[str]` · `confirm()` raises
`IncompleteRecordError` while `missing()` is not empty.
**Function:** `is_exact(actual: BookingRecord, expected: dict) -> tuple[bool, dict[str, bool]]`: per-field equality after
normalisation (below), exact = all 5 fields equal AND `actual.confirmed` (U-2); a missing field is wrong (U-13).

#### `src/voice_arch/booking/normalize.py`
**Purpose:** canonical forms (D-8, U-4, U-8).
- `normalize_phone(text) -> str`: spoken digits ("oh", "double", "triple" — reuse `voice_arch.fields.spoken_digits`
  would break purity, so the small map lives here and `fields.py` imports it from here instead), digits only, an
  11-digit value starting with `1` loses it; anything not 10 digits after that is returned as-is (so it fails equality).
- `normalize_address(text) -> str`: NFKC, casefold, punctuation → space, abbreviation map (`street→st`, `road→rd`,
  `avenue→ave`, `drive→dr`, `lane→ln`, `boulevard→blvd`, `court→ct`, `apartment/apt/unit→unit`), US state names → 2-letter
  codes, collapse spaces, drop a trailing 5-digit ZIP (optional field).
- `normalize_name(text) -> str`: NFKC, casefold, drop `'` and `.`, collapse spaces. No phonetic matching.

#### `src/voice_arch/booking/calendar.py`
**Purpose:** deterministic mock calendar (U-7, D-11). Copy the shape of LiveKit's example `FakeCalendar` (MIT; cite
`livekit/agents examples/.../calendar_api.py` in the docstring). `REFERENCE_DATE = date(2026, 11, 9)` (Monday).
`CALENDAR: tuple[Slot, ...]`: 12 slots over Mon–Fri of that week, mornings 9:00/11:00 and afternoons 14:00/16:00 (not
every day full), `Slot(id="ST_<yyyymmdd>_<hhmm>", start: datetime, booked: bool)`.
**Functions:** `available(day: date | None, part: Literal["morning","afternoon"] | None) -> list[Slot]` · `describe(slot)`
→ "Tuesday November 10 at 2 PM" · `slot_by_id(id)` → `UnknownSlotError`. Never reads `date.today()`.

#### `src/voice_arch/booking/instructions.py`
**Purpose:** the shared per-field instructions (D-5): `GREETING`, `ASK_NAME` (ask to spell when unusual), `ASK_PHONE`
(read back grouped digits), `ASK_ADDRESS` (number, street, city, state), `ASK_PROBLEM` (map to one of the five types; first
stated problem wins), `ASK_SLOT` (offer at most two slots from the calendar), `CONFIRM` (read the full record back, ask yes/no),
`GOODBYE`. Plain strings, English, ≤ 3 sentences each. Mention the reference date ("this week starts Monday November 9").

## LiveKit layer

#### `src/voice_arch/booking/state.py`
`BookingState` dataclass used as `AgentSession.userdata`: `record: BookingRecord`, `ended: bool`.

#### `src/voice_arch/booking/tools.py`
**Purpose:** the shared function tools; each is a thin wrapper on `BookingRecord` / `calendar`.
`record_name(ctx, name)`, `record_phone(ctx, phone)`, `record_address(ctx, address)`, `record_problem(ctx, problem_type:
ProblemType)`, `check_slots(ctx, day: str | None, part: str | None) -> str` (described slots), `choose_slot(ctx, slot_id)`
(unknown id → returns an error string the LLM can recover from, record unchanged), `confirm_booking(ctx)` (incomplete →
error string listing missing fields; complete → `confirm()`, then `ctx.session` says `GOODBYE` and ends the session, F-1).
Store raw caller values; normalisation happens at scoring time.

#### `src/voice_arch/agents/arch_a.py`
`OrchestratorAgent(Agent)`: instructions = `GREETING` + every `ASK_*` + `CONFIRM` concatenated; all tools.
`on_enter`: greet (only the booking agent greets, F-8).

#### `src/voice_arch/agents/arch_b.py`
`build_task_group(summarize_chat_ctx=False) -> TaskGroup` (F-15: explicit False): tasks in order `GetNameTask`,
`GetPhoneNumberTask`, `GetAddressTask` (LiveKit built-ins when their result types fit; otherwise thin custom AgentTasks
using the shared instructions — note which in a module docstring), custom `GetProblemTask`, `GetSlotTask`, `ConfirmTask`
(each `AgentTask[T]` calling the shared tools and `self.complete(...)`). `BookingFlowAgent(Agent)`: greets, then runs the
group and writes results into `BookingState.record`.

#### `src/voice_arch/agents/arch_c.py`
Same group as B. Each task's instructions get a `CallRecord` block rendered from `BookingState.record` (filled fields,
`missing()`, `corrections`) refreshed `on_enter`; extra tools `read_record(ctx) -> str` and `update_record(ctx, field,
value)` (delegates to `set_field`).

#### `src/voice_arch/agents/registry.py`
`Arch(StrEnum)`: `A="a"`, `B="b"`, `C="c"`. `build_agent(arch: Arch) -> Agent`. `parse_arch(raw: str | None) -> Arch`
raises `UnknownArchError` for missing/unknown values — no default (F-9).

#### `src/voice_arch/result.py`
`CallResult` (pydantic): `room: str`, `arch: Arch | None`, `record: BookingRecord | None`, `report: dict | None` (the
session report), `close_reason: str | None`, `error: str | None`, `summarize_chat_ctx: bool | None`.
`RESULT_TOPIC = "voice-arch.result"`. `to_json()` / `from_json()` (from_json on garbage → `ResultFormatError`).

#### `src/voice_arch/worker.py` (entry `python -m voice_arch.worker dev|start`)
`AgentServer` with `agent_name="booking-agent"`. Entry: parse dispatch metadata `{"arch": "a|b|c", "run_id": "…"}` with
`parse_arch` (error → send an error `CallResult` and disconnect, F-9); build `AgentSession(stt=StreamAdapter(make_stt(),
vad), llm=make_llm(), tts=make_tts(), vad=silero.VAD.load(), userdata=BookingState())`; start with `build_agent(arch)`.
`on_session_end`: build the session report (`ctx.make_session_report()`; if it raises, `report=None`, `error=` the message),
send `CallResult(...).to_json()` with `send_text(topic=RESULT_TOPIC)` to the room, then exit (D-7, F-3). Never writes files.

## Tests

#### `tests/booking/test_record.py`
| Test | Given → expected | Source |
|---|---|---|
| `test_u_2_record_edit_after_confirm_resets_confirmed` | complete + confirmed, `set_field("slot_id", other)` → `confirmed is False`, `corrections == ["slot_id"]` | U-2 |
| `test_u_2_unconfirmed_correct_record_is_not_exact` | all 5 fields right, not confirmed → `(False, all True)` | U-2 |
| `test_u_13_missing_field_counts_as_incorrect` | no address → `per_field["address"] is False`, exact False | U-13 |
| `test_confirm_incomplete_raises` | phone missing → `IncompleteRecordError` | U-2 |
| `test_exact_record_after_normalisation` | "Jon O'Neil", "+1 (415) 555-0134", "27 Wattle Street, Austin, Texas 73301", plumbing, slot, confirmed vs expected "jon oneil", "4155550134", "27 wattle st austin tx" → `(True, …)` | U-2, U-4, U-8 |

#### `tests/booking/test_normalize.py`
| Test | Given → expected | Source |
|---|---|---|
| `test_u_4_phone_spoken_double_and_oh_normalise_to_digits` | "four one five, five double five, oh one three four" → "4155550134" | U-4 |
| `test_phone_drops_leading_country_code` | "1 415 555 0134" → "4155550134" | U-4 |
| `test_address_variants_are_equal` (parametrized) | "12 Oak Road, Springfield, IL" / "12 oak rd springfield illinois 62704" → same | U-4 |
| `test_u_8_smyth_does_not_match_smith` | normalize_name("Smyth") != normalize_name("Smith") | U-8 |
| `test_u_8_case_and_apostrophe_insensitive` | "O'Brien" == "obrien" | U-8 |

#### `tests/booking/test_calendar.py`
| Test | Given → expected | Source |
|---|---|---|
| `test_u_7_calendar_is_independent_of_today` | freeze `date.today` to 2030-01-01 → same `CALENDAR` ids | U-7 |
| `test_available_filters_day_and_part` | Tuesday afternoon → only `ST_20261110_1400`/`_1600` that are free | D-11 |
| `test_unknown_slot_raises` | `ST_20990101_0900` → `UnknownSlotError` | D-11 |

#### `tests/agents/test_registry.py`
| Test | Given → expected | Source |
|---|---|---|
| `test_f_9_unknown_arch_metadata_is_refused_not_defaulted` | `None`, `""`, `"d"`, `"B "` → `UnknownArchError` | F-9 |
| `test_parse_arch_accepts_known_values` | "a","b","c" → `Arch.A/B/C` | F-9 |

#### `tests/agents/test_arch_b.py`
| Test | Given → expected | Source |
|---|---|---|
| `test_f_15_taskgroup_summarize_flag_is_off_and_logged` | `build_task_group()` → `summarize_chat_ctx is False`; `CallResult.summarize_chat_ctx` carries it | F-15 |

#### `tests/test_result.py`
| Test | Given → expected | Source |
|---|---|---|
| `test_result_round_trips` | CallResult with record + report → `from_json(to_json())` equal | D-7 |
| `test_f_3_garbage_result_raises_format_error` | `"{not json"` → `ResultFormatError` | F-3 |

#### `tests/test_tools.py` (LiveKit `mock_tools` / direct calls, no LLM)
| Test | Given → expected | Source |
|---|---|---|
| `test_choose_unknown_slot_returns_error_and_keeps_record` | `choose_slot("ST_x")` → string mentioning unknown slot, `slot_id is None` | D-11 |
| `test_confirm_incomplete_lists_missing_fields` | name only → string lists phone, address, problem, slot | U-2 |

#### `tests/integration/test_arch_text.py` (`@pytest.mark.integration`, live OpenRouter LLM, text mode)
| Test | Given → expected | Source |
|---|---|---|
| `test_arch_<a|b|c>_books_a_clean_caller` (parametrized) | scripted caller turns giving all fields → final record exact vs the script's expected record | goal |
| `test_arch_<a|b|c>_applies_a_phone_correction` | caller corrects the last digit → record holds the corrected phone | U-2 |

**Done when:** unit tests + hooks pass, the three integration tests pass live, and a manual browser call (Phase 1 smoke
page) completes a booking with each arch via `lk dispatch create --agent-name booking-agent --metadata '{"arch":"b"}'`.
