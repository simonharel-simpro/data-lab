"""One simulated call, from dispatch to a classified row (F-1 .. F-8, U-12)."""

import asyncio
import logging
from collections.abc import Awaitable
from dataclasses import dataclass
from enum import StrEnum
from typing import Final
from uuid import uuid4

from pydantic import BaseModel

from voice_arch import naturalness
from voice_arch.arch import Arch
from voice_arch.booking.record import BookingRecord, is_exact
from voice_arch.call_env import CallEnv, CallerHandle
from voice_arch.personas import Persona
from voice_arch.result import CallResult

logger = logging.getLogger(__name__)

AUTH_STATUSES: Final = frozenset({401, 402})
INTERJECT_AFTER_S: Final = 1.0
STEP_TIMEOUT_S: Final = 30.0
_POLL_S: Final = 0.25
_LAST_RESULT_GRACE_S: Final = 2.0  # the result is sent before the agent leaves, but its stream may still be arriving


class Outcome(StrEnum):
    SCORED = "scored"
    TIMEOUT = "timeout"
    AGENT_LOST = "agent_lost"
    CALLER_FAULT = "caller_fault"
    PROVIDER_ERROR = "provider_error"  # reserved: no rule assigns it yet (ESC-3-1)


class AgentNeverJoined(Exception):
    pass


class LiveKitUnresponsive(RuntimeError):
    """A LiveKit step accepted the connection but never answered; the sweep aborts rather than hang (P-4)."""


class ProviderAuthStop(Exception):
    """OpenRouter answered 401/402 on either side of the call: every further call would fail the same way."""


class CallRow(BaseModel):
    persona: str
    rep: int
    room: str
    outcome: Outcome
    record: BookingRecord | None
    exact: bool
    per_field: dict[str, bool]
    latencies: list[float | None]
    barge_ins: int
    barge_ins_handled: int
    long_silences: int
    agent_turns: int
    session_errors: int
    http_status: int | None
    error: str | None
    summarize_chat_ctx: bool | None
    max_tool_steps: int | None


@dataclass(frozen=True)
class _Counters:
    latencies: list[float | None]
    barge_ins: int
    barge_ins_handled: int
    long_silences: int
    session_errors: int


def _counters(outcome: Outcome, result: CallResult | None) -> _Counters:
    """Only a scored call has a report worth reading; without one (the worker failed to build it) the counters are
    0 and the error count is the worker's own."""
    if result is None or outcome is not Outcome.SCORED or result.report is None:
        return _Counters([], 0, 0, 0, 0 if result is None else result.session_errors)
    report = result.report
    interrupted, handled = naturalness.barge_ins(report)
    return _Counters(
        naturalness.latencies(report), interrupted, handled, naturalness.long_silences(report),
        naturalness.session_errors(report),
    )  # fmt: skip


def _row(persona: Persona, rep: int, room: str, outcome: Outcome, result: CallResult | None) -> CallRow:
    exact, per_field = is_exact(None if result is None else result.record, persona.expected_record)
    counters = _counters(outcome, result)
    return CallRow(
        persona=persona.id, rep=rep, room=room, outcome=outcome,
        record=None if result is None else result.record, exact=exact, per_field=per_field,
        latencies=counters.latencies, barge_ins=counters.barge_ins, barge_ins_handled=counters.barge_ins_handled,
        long_silences=counters.long_silences, agent_turns=len(counters.latencies),
        session_errors=counters.session_errors,
        http_status=None if result is None else result.http_status,
        error=None if result is None else result.error,
        summarize_chat_ctx=None if result is None else result.summarize_chat_ctx,
        max_tool_steps=None if result is None else result.max_tool_steps,
    )  # fmt: skip


async def _wait_for_result(handle: CallerHandle, persona: Persona, timeout_s: float) -> CallResult | None:
    """Poll for the result, firing the next interjection whenever the agent has been talking for a second (U-12)."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_s
    remaining_interjections = list(persona.interjections)
    while (left := deadline - loop.time()) > 0:
        if remaining_interjections and handle.agent_speaking_for() >= INTERJECT_AFTER_S:
            await handle.interject(remaining_interjections.pop(0))
        if (result := await handle.wait_result(min(_POLL_S, left))) is not None:
            return result
        if handle.agent_left:
            return await handle.wait_result(_LAST_RESULT_GRACE_S)
    return None


def _classify(handle: CallerHandle, result: CallResult | None) -> Outcome:
    if handle.caller_error is not None:  # first: a caller that never started yields no result either
        return Outcome.CALLER_FAULT
    if result is None:
        return Outcome.AGENT_LOST if handle.agent_left else Outcome.TIMEOUT
    return Outcome.SCORED


def _stop_on_auth(handle: CallerHandle, result: CallResult | None) -> None:
    statuses = {handle.caller_http_status, None if result is None else result.http_status}
    if statuses & AUTH_STATUSES:
        raise ProviderAuthStop(f"OpenRouter refused the call (HTTP {sorted(statuses & AUTH_STATUSES)[0]})")


async def _bounded[T](step: str, aw: Awaitable[T]) -> T:
    try:
        return await asyncio.wait_for(aw, STEP_TIMEOUT_S)
    except TimeoutError as err:
        raise LiveKitUnresponsive(f"{step} did not answer within {STEP_TIMEOUT_S:.0f} s") from err


async def _cleanup(env: CallEnv, handle: CallerHandle | None, room: str) -> None:
    try:
        if handle is not None:
            await asyncio.wait_for(handle.close(), STEP_TIMEOUT_S)
    except Exception:  # best-effort cleanup: a failed close must not hide the call's row
        logger.warning("closing the caller of room %s failed", room, exc_info=True)
    try:
        await asyncio.wait_for(env.delete_room(room), STEP_TIMEOUT_S)
    except Exception:  # the room may never have been created (dispatch failed): nothing left to delete
        logger.warning("deleting room %s failed", room, exc_info=True)


async def run_one_call(  # noqa: PLR0913  # call identity + two timeouts, kw-only (#39)
    env: CallEnv,
    persona: Persona,
    arch: Arch,
    run_id: str,
    rep: int,
    *,
    call_timeout_s: float,
    join_timeout_s: float,
) -> CallRow:
    room = f"va-{run_id[:8]}-{arch.value}-{persona.id}-{rep}-{uuid4().hex[:6]}"
    handle: CallerHandle | None = None
    try:
        await _bounded("create_dispatch", env.create_dispatch(room, arch, run_id))
        handle = await _bounded("connect_caller", env.connect_caller(room, persona, arch))
        if not await handle.wait_agent(join_timeout_s):
            raise AgentNeverJoined(f"no booking agent joined {room} within {join_timeout_s:.0f} s")
        result = await _wait_for_result(handle, persona, call_timeout_s)
        _stop_on_auth(handle, result)
        return _row(persona, rep, room, _classify(handle, result), result)
    finally:
        await _cleanup(env, handle, room)
