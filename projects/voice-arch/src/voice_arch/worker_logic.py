"""The worker's testable parts: dispatch metadata, pinned session options, and the `CallResult` assembly.

Kept apart from `worker.py`, which builds the `AgentServer` from the settings at import time.
"""

import asyncio
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Final

from livekit.agents import AgentSession
from livekit.agents.voice.events import CloseEvent, ErrorEvent
from livekit.agents.voice.turn import TurnHandlingOptions

from voice_arch.agents.state import BookingState
from voice_arch.arch import Arch, UnknownArchError, parse_arch
from voice_arch.result import CallResult, http_status_of

# F-16: pinned so `dev` and `start` behave alike and nothing falls back to LiveKit Cloud inference.
TURN_HANDLING: Final[TurnHandlingOptions] = {"turn_detection": "vad", "interruption": {"mode": "vad"}}
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
    errors: int = 0
    close: CloseEvent | None = None
    closed: asyncio.Event = field(default_factory=asyncio.Event)

    def on_error(self, _event: ErrorEvent) -> None:
        self.errors += 1

    def on_close(self, event: CloseEvent) -> None:
        self.close = event
        self.closed.set()

    def attach(self, session: AgentSession[BookingState]) -> None:
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


def build_result(  # the plan fixes this 7-argument signature
    room: str,
    arch: Arch,
    run_id: str,
    state: BookingState,
    close: CloseEvent | None,
    errors: int,
    report_fn: Callable[[], dict[str, object]],
    *,
    summarize_chat_ctx: bool | None,
    max_tool_steps: int,
) -> CallResult:
    """A report failure keeps the record and says why (F-3); the close error gives the HTTP status (F-4)."""
    report: dict[str, object] | None = None
    problems: list[str] = []
    try:
        report = report_fn()
    except Exception as err:  # any failure to build the report must still yield a result
        problems.append(f"report failed: {type(err).__name__}: {err}")
    if (close_problem := _close_error(close)) is not None:
        problems.append(close_problem)
    return CallResult(
        room=room,
        arch=arch,
        run_id=run_id,
        record=state.record.model_copy(deep=True),
        report=report,
        close_reason=None if close is None else close.reason.value,
        error="; ".join(problems) or None,
        http_status=None if close is None else http_status_of(close.error),
        session_errors=errors,
        summarize_chat_ctx=summarize_chat_ctx,
        max_tool_steps=max_tool_steps,
    )
