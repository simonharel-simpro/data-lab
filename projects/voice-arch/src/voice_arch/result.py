"""What a call leaves behind: one `CallResult`, sent over the room as a text stream (D-7). No LiveKit import."""

from collections import deque
from typing import Final

from pydantic import BaseModel, ValidationError

from voice_arch.arch import Arch
from voice_arch.booking.record import BookingRecord

RESULT_TOPIC: Final = "voice-arch.result"
_MAX_CAUSE_DEPTH: Final = 8


class ResultFormatError(ValueError):
    pass


class CallResult(BaseModel):
    room: str
    arch: Arch | None
    run_id: str | None
    record: BookingRecord | None
    report: dict[str, object] | None  # SessionReport.to_dict(): JSON-shaped, schema owned by LiveKit
    close_reason: str | None
    error: str | None
    http_status: int | None
    session_errors: int = 0
    summarize_chat_ctx: bool | None
    max_tool_steps: int | None

    def to_json(self) -> str:
        return self.model_dump_json()

    @classmethod
    def from_json(cls, text: str) -> "CallResult":
        try:
            return cls.model_validate_json(text)
        except ValidationError as err:
            raise ResultFormatError(f"not a CallResult: {err.error_count()} validation error(s)") from err


def http_status_of(err: object | None) -> int | None:
    """The first `status_code` found on `err`, its `.error` or its `__cause__` (an LLMError wraps the API error)."""
    queue: deque[tuple[object, int]] = deque([] if err is None else [(err, 0)])
    seen: set[int] = set()
    while queue:
        current, depth = queue.popleft()
        if id(current) in seen or depth > _MAX_CAUSE_DEPTH:
            continue
        seen.add(id(current))
        status = getattr(current, "status_code", None)
        if isinstance(status, int):
            return status
        children = (getattr(current, "error", None), getattr(current, "__cause__", None))
        queue.extend((child, depth + 1) for child in children if child is not None)
    return None
