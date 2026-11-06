import pytest
from livekit.agents import APIConnectionError, APIConnectOptions, llm

from tests.test_llm_guard import _Llm  # pyright: ignore[reportPrivateUsage]
from voice_arch.caller import make_caller_session
from voice_arch.settings import VoiceSettings


async def test_caller_session_llm_is_requested_with_the_empty_completion_guard(
    voice_settings: VoiceSettings, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("voice_arch.caller.silero.VAD.load", lambda: None)
    seen: list[bool] = []

    def spy(settings: VoiceSettings, *, model: str, temperature: float, retry_empty: bool) -> llm.LLM:
        seen.append(retry_empty)
        return _Llm(empty_attempts=0)

    make_caller_session(voice_settings, llm_factory=spy)

    assert seen == [True]


async def test_caller_session_llm_fails_loud_instead_of_staying_silent_when_always_empty(
    voice_settings: VoiceSettings, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("voice_arch.caller.silero.VAD.load", lambda: None)
    empty = _Llm(empty_attempts=99, temperature=0.7)
    # The real factory, with only the network-bound OpenRouter model replaced.
    monkeypatch.setattr("voice_arch.audio.openai.LLM.with_openrouter", lambda **_: empty)

    session = make_caller_session(voice_settings)

    no_wait = APIConnectOptions(max_retry=1, retry_interval=0.0, timeout=5.0)
    with pytest.raises(APIConnectionError):
        async with session.llm.chat(chat_ctx=llm.ChatContext(), conn_options=no_wait) as stream:  # type: ignore[union-attr]
            async for _ in stream:
                pass
    assert empty.attempts == 2
