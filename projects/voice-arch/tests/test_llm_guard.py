import pytest
from livekit.agents import APIConnectionError, APIConnectOptions, llm

from voice_arch.llm_guard import EMPTY_COMPLETION, retry_on_empty_completion

NO_WAIT = APIConnectOptions(max_retry=2, retry_interval=0.0, timeout=5.0)


class _Stream(llm.LLMStream):
    async def _run(self) -> None:
        self._llm.attempts += 1  # pyright: ignore[reportAttributeAccessIssue]
        if self._llm.attempts > self._llm.empty_attempts:  # pyright: ignore[reportAttributeAccessIssue]
            delta = llm.ChoiceDelta(role="assistant", content="Hello")
            self._event_ch.send_nowait(llm.ChatChunk(id="c", delta=delta))


class _Llm(llm.LLM):
    """Answers with no output for its first `empty_attempts` attempts, then with the text `Hello`."""

    def __init__(self, empty_attempts: int) -> None:
        super().__init__()
        self.attempts = 0
        self.empty_attempts = empty_attempts

    def chat(self, *, chat_ctx: llm.ChatContext, tools: list[llm.Tool] | None = None,
             conn_options: APIConnectOptions = NO_WAIT, **_: object) -> llm.LLMStream:  # fmt: skip
        return _Stream(self, chat_ctx=chat_ctx, tools=tools or [], conn_options=conn_options)


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
    assert model.attempts == 3  # type: ignore[attr-defined]


async def test_guarded_completion_that_is_always_empty_fails_loud_after_the_retries() -> None:
    model = retry_on_empty_completion(_Llm(empty_attempts=99))

    with pytest.raises(APIConnectionError) as err:
        await _text(model)

    assert model.attempts == NO_WAIT.max_retry + 1  # type: ignore[attr-defined]
    assert EMPTY_COMPLETION in str(err.value.__cause__)


async def test_guarded_non_empty_completion_is_not_retried() -> None:
    model = retry_on_empty_completion(_Llm(empty_attempts=0))

    assert await _text(model) == "Hello"
    assert model.attempts == 1  # type: ignore[attr-defined]
