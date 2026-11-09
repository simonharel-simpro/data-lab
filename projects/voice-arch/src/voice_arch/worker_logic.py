"""The worker's testable parts: dispatch metadata, pinned session options, and the `CallResult` assembly.

Kept apart from `worker.py`, which builds the `AgentServer` from the settings at import time.
"""

import asyncio
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Final

from livekit.agents import AgentSession
from livekit.agents.llm import LLMError
from livekit.agents.voice.events import CloseEvent, CloseReason, ErrorEvent
from livekit.agents.voice.turn import TurnHandlingOptions

from voice_arch.agents.state import BookingState
from voice_arch.arch import Arch, UnknownArchError, parse_arch
from voice_arch.result import CallResult, http_status_of

# F-16: pinned so `dev` and `start` behave alike and nothing falls back to LiveKit Cloud inference.
# ESC-3-2: preemptive generation off (see IMPLEMENTATION_NOTES); it is on by LiveKit default.
TURN_HANDLING: Final[TurnHandlingOptions] = {
    "turn_detection": "vad",
    "interruption": {"mode": "vad"},
    "preemptive_generation": {"enabled": False},
}
MAX_TOOL_STEPS: Final = 6
_DEFAULT_RUN_ID: Final = "manual"


def parse_metadata(raw: str) -> tuple[Arch, str]:
    """Never defaults the arch (F-9); a missing `run_id` is the only optional part."""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as err:
        raise UnknownArchError(f"dispatch metadata is not JSON: {raw[:40]!r}") from err
    if not isinstance(data, dict):
        raise UnknownArchError("dispatch metadata must be a JSON object")
    arch = data.get("arch")
    if arch is not None and not isinstance(arch, str):
        raise UnknownArchError(f"arch must be a string, got {type(arch).__name__}")
    run_id = data.get("run_id") or _DEFAULT_RUN_ID
    if not isinstance(run_id, str):
        raise UnknownArchError(f"run_id must be a string, got {type(run_id).__name__}")
    return parse_arch(arch), run_id


@dataclass
class SessionWatch:
    """Counts the session's errors and ends the call on the first unrecoverable LLM one.

    LiveKit tolerates three unrecoverable errors per component and otherwise leaves the session open and silent
    (the guard's "failed after 4 attempts" is one such error), so the call would idle until the runner's timeout.
    """

    errors: int = 0
    close: CloseEvent | None = None
    fatal: LLMError | None = None
    closed: asyncio.Event = field(default_factory=asyncio.Event)
    _session: AgentSession[BookingState] | None = None

    def on_error(self, event: ErrorEvent) -> None:
        self.errors += 1
        error = event.error
        if self._session is None or not isinstance(error, LLMError) or error.recoverable:
            return
        self.fatal = error
        self._session.shutdown(drain=False)  # nothing is left to say: the agent never got its answer

    def on_close(self, event: CloseEvent) -> None:
        self.close = event
        self.closed.set()

    def attach(self, session: AgentSession[BookingState]) -> None:
        self._session = session
        session.on("error", self.on_error)
        session.on("close", self.on_close)


def error_result(room: str, message: str) -> CallResult:
    return CallResult(
        room=room, arch=None, run_id=None, record=None, report=None, close_reason=None, error=message,
        http_status=None, summarize_chat_ctx=None, max_tool_steps=None,
    )  # fmt: skip


def _close_error(close: CloseEvent | None) -> str | None:
    if close is None or close.error is None:
        return None
    return f"session closed on error: {getattr(close.error, 'error', close.error)}"


def _close_reason(close: CloseEvent | None, fatal: LLMError | None) -> str | None:
    if fatal is not None:
        return CloseReason.ERROR.value  # the worker's own shutdown reads as user-initiated otherwise
    return None if close is None else close.reason.value


@dataclass(frozen=True)
class CallIdentity:
    room: str
    arch: Arch
    run_id: str


@dataclass(frozen=True)
class SessionOutcome:
    state: BookingState
    close: CloseEvent | None
    errors: int
    summarize_chat_ctx: bool | None
    max_tool_steps: int
    fatal: LLMError | None = None  # the unrecoverable LLM error the worker ended the call for


def _problems(
    report_fn: Callable[[], dict[str, object]], close: CloseEvent | None, fatal: LLMError | None
) -> tuple[dict[str, object] | None, list[str]]:
    """The report (None when it failed) and everything that went wrong, in the order they are reported."""
    report: dict[str, object] | None = None
    problems: list[str] = []
    try:
        report = report_fn()
    except Exception as err:  # noqa: BLE001  # any failure to build the report must still yield a result
        problems.append(f"report failed: {type(err).__name__}: {err}")
    if (close_problem := _close_error(close)) is not None:
        problems.append(close_problem)
    if fatal is not None:
        problems.append(f"unrecoverable LLM error: {fatal.error}")
    return report, problems


def build_result(call: CallIdentity, outcome: SessionOutcome, report_fn: Callable[[], dict[str, object]]) -> CallResult:
    """A report failure keeps the record and says why (F-3); the close error gives the HTTP status (F-4).

    `outcome.fatal` is reported like a close error and, per ESC-3-1, the call stays scored by its record.
    """
    close, fatal = outcome.close, outcome.fatal
    report, problems = _problems(report_fn, close, fatal)
    return CallResult(
        room=call.room,
        arch=call.arch,
        run_id=call.run_id,
        record=outcome.state.record.model_copy(deep=True),
        report=report,
        close_reason=_close_reason(close, fatal),
        error="; ".join(problems) or None,
        http_status=http_status_of(fatal if close is None or close.error is None else close.error),
        session_errors=outcome.errors,
        summarize_chat_ctx=outcome.summarize_chat_ctx,
        max_tool_steps=outcome.max_tool_steps,
    )
