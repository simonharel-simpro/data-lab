"""The live `CallerHandle`: a self-connected room, the caller session, and what they report back."""

import asyncio
import logging
import time
from collections.abc import Coroutine
from typing import Final

from livekit import rtc
from livekit.agents import AgentSession
from livekit.agents.testing import fake_job_context
from livekit.agents.types import ATTRIBUTE_AGENT_STATE
from livekit.agents.voice.events import CloseEvent, CloseReason, ErrorEvent
from livekit.agents.voice.room_io import RoomOptions

from voice_arch.caller import CallerAgent
from voice_arch.result import RESULT_TOPIC, CallResult, ResultFormatError, http_status_of

logger = logging.getLogger(__name__)
_AGENT: Final = rtc.ParticipantKind.PARTICIPANT_KIND_AGENT
_SPEAKING: Final = "speaking"
_POLL_S: Final = 0.1


def _describe(err: object) -> str:
    inner = getattr(err, "error", err)
    status = http_status_of(err)
    return f"{type(inner).__name__}" + ("" if status is None else f" (HTTP {status})")  # never the message: no secrets


class LiveCaller:
    """`listen_after`: speaking turns of the agent the caller lets pass unheard before it starts listening.

    B and C greet, then hand off to the first task: a reply sent in that window lands in the previous agent's
    context (Phase 2 notes), so their caller waits for the first question; A has no such hand-off.
    """

    def __init__(self, room: rtc.Room, session: AgentSession[None], listen_after: int) -> None:
        self._room, self._session, self._listen_after = room, session, listen_after
        self.agent_left = False
        self.caller_http_status: int | None = None
        self.caller_error: str | None = None
        self._joined, self._got_result = asyncio.Event(), asyncio.Event()
        self._result: CallResult | None = None
        self._speaking_since: float | None = None
        self._episodes = 0
        self._started = False
        self._tasks: set[asyncio.Task[None]] = set()
        room.register_text_stream_handler(RESULT_TOPIC, self._on_stream)
        room.on("participant_connected", self._on_joined)
        room.on("participant_disconnected", self._on_left)
        room.on("participant_attributes_changed", self._on_attributes)
        session.on("error", self._on_error)
        session.on("close", self._on_close)

    def scan(self) -> None:
        """Agents already in the room when we connected raise no `participant_connected`."""
        for participant in self._room.remote_participants.values():
            self._on_joined(participant)
            self._on_agent_state(participant.attributes.get(ATTRIBUTE_AGENT_STATE))

    def start(self, agent: CallerAgent) -> None:
        self._spawn(self._run_session(agent))

    def _spawn(self, coro: Coroutine[None, None, None]) -> None:
        task = asyncio.create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _run_session(self, agent: CallerAgent) -> None:
        """`start` waits for an agent participant to link, so it runs in the background (F-2 needs the timeout)."""
        try:
            with fake_job_context(room=self._room):
                await self._session.start(
                    agent,
                    room=self._room,
                    room_options=RoomOptions(participant_kinds=[_AGENT]),
                    record=False,
                )
        except Exception as err:  # the caller never started: the call cannot be scored
            logger.exception("the caller session failed to start")
            self.caller_error = f"caller session failed to start: {type(err).__name__}"
            return
        self._started = True
        self._apply_gate()

    def _apply_gate(self) -> None:
        if self._started and self._listen_after > 0:
            self._session.input.set_audio_enabled(self._episodes >= self._listen_after)

    def _on_stream(self, reader: rtc.TextStreamReader, participant_identity: str) -> None:
        self._spawn(self._read_result(reader))

    async def _read_result(self, reader: rtc.TextStreamReader) -> None:
        try:
            self._result = CallResult.from_json(await reader.read_all())
        except ResultFormatError:
            logger.exception("an unreadable call result arrived on the result topic")
            return
        self._got_result.set()

    def _on_joined(self, participant: rtc.RemoteParticipant) -> None:
        if participant.kind == _AGENT:
            self._joined.set()

    def _on_left(self, participant: rtc.RemoteParticipant) -> None:
        if participant.kind == _AGENT:
            self.agent_left = True

    def _on_attributes(self, changed: dict[str, str], participant: rtc.Participant) -> None:
        if participant.kind == _AGENT and ATTRIBUTE_AGENT_STATE in changed:
            self._on_agent_state(changed[ATTRIBUTE_AGENT_STATE])

    def _on_agent_state(self, state: str | None) -> None:
        if state == _SPEAKING:
            self._speaking_since = self._speaking_since or time.monotonic()
        elif self._speaking_since is not None:
            self._speaking_since = None
            self._episodes += 1
            self._apply_gate()

    def _on_error(self, event: ErrorEvent) -> None:
        status = http_status_of(event.error)
        self.caller_http_status = self.caller_http_status or status
        if getattr(event.error, "recoverable", None) is not True:  # an unknown error type is a fault, not noise
            self.caller_error = _describe(event.error)

    def _on_close(self, event: CloseEvent) -> None:
        if event.error is not None or event.reason is CloseReason.ERROR:
            self.caller_http_status = self.caller_http_status or http_status_of(event.error)
            self.caller_error = _describe(event.error) if event.error is not None else "session closed on error"

    async def wait_agent(self, timeout: float) -> bool:
        try:
            await asyncio.wait_for(self._joined.wait(), timeout)
        except TimeoutError:
            return False
        return True

    async def wait_result(self, timeout: float) -> CallResult | None:
        try:
            await asyncio.wait_for(self._got_result.wait(), timeout)
        except TimeoutError:
            return None
        return self._result

    async def interject(self, text: str) -> None:
        self._session.say(text, allow_interruptions=False)

    def agent_speaking_for(self) -> float:
        return 0.0 if self._speaking_since is None else time.monotonic() - self._speaking_since

    async def close(self) -> None:
        for task in list(self._tasks):
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._room.unregister_text_stream_handler(RESULT_TOPIC)
        try:
            await self._session.aclose()
        except Exception:
            logger.exception("closing the caller session failed")
        await self._room.disconnect()
