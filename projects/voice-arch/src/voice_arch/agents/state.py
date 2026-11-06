"""Per-call state shared by every agent and tool of a session (`AgentSession.userdata`)."""

import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field

from livekit.agents.llm import ChatItem, ChatMessage

from voice_arch.booking.record import BookingRecord


@dataclass
class BookingState:
    record: BookingRecord = field(default_factory=BookingRecord)
    taken: set[str] = field(default_factory=set)
    # When the agent last changed the record. The read-back that follows a change is spoken text, not a tool call,
    # so this is the nearest observable point: the caller has had no say on the record until they speak after it.
    last_write_at: float | None = None

    def note_write(self) -> None:
        self.last_write_at = time.time()

    def caller_replied_since_write(self, history: Callable[[], Iterable[ChatItem]]) -> bool:
        """True when no write is pending an answer, or a user message was committed after the last write.

        `history` is read only when a write is pending.
        """
        if self.last_write_at is None:
            return True
        return any(
            isinstance(item, ChatMessage) and item.role == "user" and item.created_at > self.last_write_at
            for item in history()
        )
