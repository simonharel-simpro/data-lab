import json
from pathlib import Path

import pytest
from livekit.agents import llm

from voice_arch.audio import make_llm
from voice_arch.llm_dump import DUMP_DIR_ENV, dump_empty_request
from voice_arch.settings import VoiceSettings


async def _stream(voice_settings: VoiceSettings) -> llm.LLMStream:
    chat_ctx = llm.ChatContext()
    chat_ctx.add_message(role="system", content="Be brief.")
    chat_ctx.add_message(role="user", content="Hello there")
    stream = make_llm(voice_settings).chat(chat_ctx=chat_ctx)
    await stream.aclose()  # cancelled before its first await: nothing is sent
    return stream


async def test_dump_is_off_without_the_env_var(voice_settings: VoiceSettings, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(DUMP_DIR_ENV, raising=False)
    stream = await _stream(voice_settings)

    assert dump_empty_request(stream, {"temperature": 0.0}, 1) is None


async def test_dump_writes_messages_tools_and_params(
    voice_settings: VoiceSettings, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv(DUMP_DIR_ENV, str(tmp_path / "dumps"))
    stream = await _stream(voice_settings)

    path = dump_empty_request(stream, {"temperature": 0.3, "extra_headers": {"X": "secret"}}, 2)

    assert path is not None and path.name.endswith("-attempt2.json")
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert [m["role"] for m in payload["messages"]] == ["system", "user"]
    assert payload["messages"][1]["content"] == "Hello there"
    assert payload["tools"] == []
    assert payload["params"] == {"temperature": 0.3}  # headers are not dumped
