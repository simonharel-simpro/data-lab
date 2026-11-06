import json
from types import ModuleType, SimpleNamespace
from typing import cast

import pytest
from livekit import rtc
from livekit.agents import JobContext

from voice_arch.result import RESULT_TOPIC, CallResult
from voice_arch.settings import VoiceSettings


class FakeParticipant:
    def __init__(self, fail: bool = False) -> None:
        self.sent: list[tuple[str, str]] = []
        self._fail = fail

    async def send_text(self, text: str, *, topic: str) -> None:
        if self._fail:
            raise RuntimeError("room is gone")
        self.sent.append((topic, text))


def _room(participant: FakeParticipant) -> rtc.Room:
    return cast("rtc.Room", SimpleNamespace(name="room-1", local_participant=participant))


def _ctx(participant: FakeParticipant, metadata: str) -> JobContext:
    async def connect() -> None:
        return None

    ctx = SimpleNamespace(room=_room(participant), job=SimpleNamespace(metadata=metadata), connect=connect)
    return cast("JobContext", ctx)


@pytest.fixture
def worker(voice_settings: VoiceSettings) -> ModuleType:
    # Imported lazily: the module builds its AgentServer from the settings at import time.
    import voice_arch.worker as module

    return module


async def test_send_result_publishes_the_json_on_the_result_topic(worker: ModuleType) -> None:
    participant = FakeParticipant()
    result = worker.error_result("room-1", "boom")

    await worker.send_result(_room(participant), result)

    ((topic, text),) = participant.sent
    assert topic == RESULT_TOPIC
    assert CallResult.from_json(text) == result


async def test_send_result_failure_is_logged_not_raised(worker: ModuleType, caplog: pytest.LogCaptureFixture) -> None:
    participant = FakeParticipant(fail=True)

    await worker.send_result(_room(participant), worker.error_result("room-1", "boom"))

    assert "could not send the call result" in caplog.text


@pytest.mark.parametrize("metadata", ["", "{x", '{"run_id":"r"}', '{"arch":"A"}'])
async def test_f_9_entry_refuses_bad_metadata_with_an_error_result(worker: ModuleType, metadata: str) -> None:
    participant = FakeParticipant()

    await worker.entry(_ctx(participant, metadata))

    ((topic, text),) = participant.sent
    result = CallResult.from_json(text)
    assert topic == RESULT_TOPIC
    assert (result.arch, result.record, result.room) == (None, None, "room-1")
    assert result.error is not None
    assert json.loads(text)["error"] == result.error
