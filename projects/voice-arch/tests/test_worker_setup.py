"""M2.4: a worker setup failure reaches the caller as an error result, not as a result timeout."""

from types import ModuleType, SimpleNamespace
from typing import cast

import pytest
from livekit import rtc
from livekit.agents import JobContext

from voice_arch.result import RESULT_TOPIC, CallResult
from voice_arch.settings import VoiceSettings


class FakeParticipant:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    async def send_text(self, text: str, *, topic: str) -> None:
        self.sent.append((topic, text))


def _ctx(participant: FakeParticipant) -> JobContext:
    async def connect() -> None:
        return None

    room = cast("rtc.Room", SimpleNamespace(name="room-1", local_participant=participant))
    job = SimpleNamespace(metadata='{"arch":"a","run_id":"r1"}')
    return cast("JobContext", SimpleNamespace(room=room, job=job, connect=connect))


@pytest.fixture
def worker(voice_settings: VoiceSettings) -> ModuleType:
    import voice_arch.worker as module

    return module


async def test_entry_sends_one_error_result_when_session_setup_raises(
    worker: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken_tts(_settings: object) -> object:
        raise RuntimeError("tts unavailable")

    monkeypatch.setattr(worker, "make_tts", broken_tts)
    participant = FakeParticipant()

    await worker.entry(_ctx(participant))

    ((topic, text),) = participant.sent
    result = CallResult.from_json(text)
    assert topic == RESULT_TOPIC
    assert (result.arch, result.record, result.room) == (None, None, "room-1")
    assert "worker setup failed" in (result.error or "")
    assert "tts unavailable" in (result.error or "")


async def test_entry_lets_cancellation_during_setup_propagate(
    worker: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    import asyncio

    def cancelled(_settings: object) -> object:
        raise asyncio.CancelledError

    monkeypatch.setattr(worker, "make_tts", cancelled)
    participant = FakeParticipant()

    with pytest.raises(asyncio.CancelledError):
        await worker.entry(_ctx(participant))

    assert participant.sent == []
