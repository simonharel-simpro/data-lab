"""Per-call state shared by every agent and tool of a session (`AgentSession.userdata`)."""

from dataclasses import dataclass, field

from voice_arch.booking.record import BookingRecord


@dataclass
class BookingState:
    record: BookingRecord = field(default_factory=BookingRecord)
    taken: set[str] = field(default_factory=set)
