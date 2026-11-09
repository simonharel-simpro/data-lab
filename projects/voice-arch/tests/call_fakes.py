"""Scripted stand-ins for the call seam (`CallEnv` / `CallerHandle`) and builders for rows and results."""

import asyncio
from collections.abc import Callable, Iterable, Iterator
from pathlib import Path
from types import TracebackType
from typing import Self

from voice_arch.arch import Arch
from voice_arch.booking.record import SCORED_FIELDS, BookingRecord, ProblemType
from voice_arch.call import CallRow, Outcome
from voice_arch.call_env import CallerHandle
from voice_arch.personas import Persona, load_personas
from voice_arch.result import CallResult

SHIPPED = Path(__file__).resolve().parents[1] / "data" / "personas.jsonl"


def persona(persona_id: str = "self_correction") -> Persona:
    return next(p for p in load_personas(SHIPPED) if p.id == persona_id)


def record_for(who: Persona, *, confirmed: bool = True) -> BookingRecord:
    expected = who.expected_record
    return BookingRecord(
        name=expected.name,
        phone=expected.phone,
        address=expected.address,
        problem_type=ProblemType(expected.problem_type),
        slot_id=expected.slot_id,
        confirmed=confirmed,
    )


def result_for(
    who: Persona,
    *,
    http_status: int | None = None,
    report: dict[str, object] | None = None,
    error: str | None = None,
) -> CallResult:
    return CallResult(
        room="room-x", arch=Arch.A, run_id="run", record=record_for(who), report=report, close_reason="task_completed",
        error=error, http_status=http_status, summarize_chat_ctx=None, max_tool_steps=6,
    )  # fmt: skip


def row(
    outcome: Outcome,
    *,
    exact: bool = False,
    latencies: Iterable[float | None] = (),
    barge_ins: int = 0,
    barge_ins_handled: int = 0,
    long_silences: int = 0,
    agent_turns: int = 0,
    session_errors: int = 0,
) -> CallRow:
    return CallRow(
        persona="self_correction", rep=0, room="room", outcome=outcome, record=None, exact=exact,
        per_field=dict.fromkeys(SCORED_FIELDS, exact), latencies=list(latencies), barge_ins=barge_ins,
        barge_ins_handled=barge_ins_handled, long_silences=long_silences, agent_turns=agent_turns,
        session_errors=session_errors, http_status=None, error=None, summarize_chat_ctx=None, max_tool_steps=None,
    )  # fmt: skip


class FakeHandle:
    def __init__(
        self,
        result: CallResult | None = None,
        *,
        joins: bool = True,
        agent_left: bool = False,
        caller_http_status: int | None = None,
        caller_error: str | None = None,
        speaking_for: float = 0.0,
        result_after: int = 0,
    ) -> None:
        self._result, self._joins, self._result_after = result, joins, result_after
        self.agent_left, self.caller_http_status, self.caller_error = agent_left, caller_http_status, caller_error
        self._speaking_for = speaking_for
        self.interjected: list[str] = []
        self.closed = False

    async def wait_agent(self, timeout: float) -> bool:
        return self._joins

    async def wait_result(self, timeout: float) -> CallResult | None:
        if self._result is not None and self._result_after <= 0:
            return self._result
        self._result_after -= 1
        await asyncio.sleep(0 if self._result is not None else min(timeout, 0.05))
        return None

    async def interject(self, text: str) -> None:
        self.interjected.append(text)

    def agent_speaking_for(self) -> float:
        return self._speaking_for

    async def close(self) -> None:
        self.closed = True


class FakeEnv:
    """Hands out the scripted handles in order; once they run out, a clean caller whose result is exact."""

    def __init__(self, handles: Iterable[FakeHandle] = ()) -> None:
        self._scripted: Iterator[FakeHandle] = iter(handles)
        self.rooms: list[str] = []
        self.deleted: list[str] = []
        self.handles: list[FakeHandle] = []

    async def create_dispatch(self, room: str, arch: Arch, run_id: str) -> None:
        self.rooms.append(room)

    async def connect_caller(self, room: str, persona: Persona, arch: Arch) -> CallerHandle:
        handle = next(self._scripted, None) or FakeHandle(result_for(persona))
        self.handles.append(handle)
        return handle

    async def delete_room(self, room: str) -> None:
        self.deleted.append(room)


class FakeTracker:
    """A `SpendTracker` stand-in: `spent_now` walks `readings`, `final` is the cost reported on exit."""

    def __init__(
        self, key: str, *, on_exit: Callable[[float], None], readings: Iterable[float | None] = (),
        final: float | None = None,
    ) -> None:  # fmt: skip
        self._readings = iter(readings)
        self._on_exit, self.cost_usd = on_exit, final

    def __enter__(self) -> Self:
        return self

    def spent_now(self) -> float | None:
        return next(self._readings, None)

    def __exit__(
        self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None
    ) -> None:
        if self.cost_usd is not None:
            self._on_exit(self.cost_usd)
