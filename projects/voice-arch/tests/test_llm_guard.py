import logging

import pytest
from livekit.agents import APIConnectionError, APIConnectOptions, llm

from voice_arch.audio import make_llm
from voice_arch.llm_guard import EMPTY_COMPLETION, retry_on_empty_completion
from voice_arch.settings import VoiceSettings

NO_WAIT = APIConnectOptions(max_retry=2, retry_interval=0.0, timeout=5.0)


class _Stream(llm.LLMStream):
    """Like LiveKit's OpenAI stream, it reads its request parameters from `_extra_kwargs` on every attempt."""

    def __init__(self, model: llm.LLM, *, temperature: float, **kwargs: object) -> None:
        super().__init__(model, **kwargs)  # pyright: ignore[reportArgumentType]  # loose test fake
        self._extra_kwargs = {"temperature": temperature}

    async def _run(self) -> None:
        # Attr missing in stubs.
        self._llm.temperatures.append(self._extra_kwargs["temperature"])  # pyright: ignore[reportAttributeAccessIssue]
        self._llm.attempts += 1  # pyright: ignore[reportAttributeAccessIssue]  # attr missing in stubs
        if self._llm.attempts > self._llm.empty_attempts:  # pyright: ignore[reportAttributeAccessIssue]  # not in stubs
            delta = llm.ChoiceDelta(role="assistant", content="Hello")
            self._event_ch.send_nowait(llm.ChatChunk(id="c", delta=delta))


class _Llm(llm.LLM):
    """Answers with no output for its first `empty_attempts` attempts, then with the text `Hello`."""

    def __init__(self, empty_attempts: int, temperature: float = 0.0) -> None:
        super().__init__()
        self.attempts = 0
        self.temperatures: list[float] = []
        self.temperature = temperature
        self.empty_attempts = empty_attempts

    def chat(self, *, chat_ctx: llm.ChatContext, tools: list[llm.Tool] | None = None,
             conn_options: APIConnectOptions = NO_WAIT, **_: object) -> llm.LLMStream:  # fmt: skip
        return _Stream(
            self, temperature=self.temperature, chat_ctx=chat_ctx, tools=tools or [], conn_options=conn_options
        )


async def _text(model: llm.LLM) -> str:
    async with model.chat(chat_ctx=llm.ChatContext()) as stream:
        return "".join([c.delta.content or "" async for c in stream if c.delta is not None])


async def test_unguarded_empty_completion_ends_silently_without_error() -> None:
    model = _Llm(empty_attempts=1)

    assert await _text(model) == ""
    assert model.attempts == 1


async def test_guarded_empty_completion_is_retried_until_it_answers() -> None:
    model = retry_on_empty_completion(_Llm(empty_attempts=2))

    assert await _text(model) == "Hello"
    assert model.attempts == 3  # type: ignore[attr-defined]  # private LiveKit attr


async def test_guarded_completion_that_is_always_empty_fails_loud_after_the_retries() -> None:
    model = retry_on_empty_completion(_Llm(empty_attempts=99))

    with pytest.raises(APIConnectionError) as err:
        await _text(model)

    assert model.attempts == NO_WAIT.max_retry + 1  # type: ignore[attr-defined]  # private LiveKit attr
    assert EMPTY_COMPLETION in str(err.value.__cause__)


async def test_guarded_non_empty_completion_is_not_retried() -> None:
    model = retry_on_empty_completion(_Llm(empty_attempts=0))

    assert await _text(model) == "Hello"
    assert model.attempts == 1  # type: ignore[attr-defined]  # private LiveKit attr


async def test_first_attempt_uses_the_base_temperature() -> None:
    model = retry_on_empty_completion(_Llm(empty_attempts=0, temperature=0.0))

    await _text(model)

    assert model.temperatures == [0.0]  # type: ignore[attr-defined]  # private LiveKit attr


async def test_each_retry_raises_the_temperature_by_a_step() -> None:
    model = retry_on_empty_completion(_Llm(empty_attempts=2, temperature=0.0))

    assert await _text(model) == "Hello"

    assert model.temperatures == pytest.approx([0.0, 0.3, 0.6])  # type: ignore[attr-defined]  # private LiveKit attr


async def test_retry_temperature_is_capped() -> None:
    model = retry_on_empty_completion(_Llm(empty_attempts=2, temperature=0.7))

    await _text(model)

    assert model.temperatures == pytest.approx([0.7, 1.0, 1.0])  # type: ignore[attr-defined]  # private LiveKit attr


async def test_always_empty_completion_still_fails_loud_with_rising_temperatures() -> None:
    model = retry_on_empty_completion(_Llm(empty_attempts=99, temperature=0.0))

    with pytest.raises(APIConnectionError):
        await _text(model)

    assert model.temperatures == pytest.approx([0.0, 0.3, 0.6])  # type: ignore[attr-defined]  # private LiveKit attr


async def test_each_retry_is_logged_at_warning_with_its_number_and_no_text(caplog: pytest.LogCaptureFixture) -> None:
    model = retry_on_empty_completion(_Llm(empty_attempts=2))

    with caplog.at_level(logging.WARNING, logger="voice_arch.llm_guard"):
        await _text(model)

    ours = [r for r in caplog.records if r.name == "voice_arch.llm_guard"]
    assert [r.levelno for r in ours] == [logging.WARNING, logging.WARNING]
    assert [r.getMessage() for r in ours] == [
        "empty LLM completion, retry 1 at temperature 0.30",
        "empty LLM completion, retry 2 at temperature 0.60",
    ]


async def test_each_call_starts_again_from_the_base_temperature() -> None:
    model = retry_on_empty_completion(_Llm(empty_attempts=1, temperature=0.0))
    await _text(model)
    model.attempts = 0  # type: ignore[attr-defined]  # private LiveKit attr
    model.temperatures.clear()  # type: ignore[attr-defined]  # private LiveKit attr

    await _text(model)

    assert model.temperatures == pytest.approx([0.0, 0.3])  # type: ignore[attr-defined]  # private LiveKit attr


async def test_guard_wraps_the_real_openrouter_stream_and_keeps_its_temperature(
    voice_settings: VoiceSettings,
) -> None:
    model = make_llm(voice_settings, temperature=0.4, retry_empty=True)

    stream = model.chat(chat_ctx=llm.ChatContext())
    await stream.aclose()  # cancelled before its first await: nothing is sent

    # Private LiveKit attr.
    assert stream._extra_kwargs["temperature"] == 0.4  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]


async def test_guard_dumps_the_request_of_every_empty_attempt(monkeypatch: pytest.MonkeyPatch) -> None:
    dumped: list[int] = []
    monkeypatch.setattr("voice_arch.llm_guard.dump_empty_request", lambda _s, _r, attempt, _dir: dumped.append(attempt))
    model = retry_on_empty_completion(_Llm(empty_attempts=2))

    assert await _text(model) == "Hello"

    assert dumped == [1, 2]  # the third attempt answered: nothing to dump
