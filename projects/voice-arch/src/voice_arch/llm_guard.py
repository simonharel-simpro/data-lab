"""Retry an LLM call that completes with no text and no tool call (ESC-3-2).

Gemini through OpenRouter sometimes ends a stream with zero completion tokens. LiveKit treats that as a finished
turn: the agent says nothing, raises no error, and the call waits until the caller gives up.
"""

from collections.abc import Callable
from typing import Any

from livekit.agents import APIConnectionError, llm

EMPTY_COMPLETION = "the LLM completed without text or tool call"


def retry_on_empty_completion(model: llm.LLM) -> llm.LLM:
    """Same model; an empty stream raises a retryable error, so LiveKit re-sends it (`conn_options.max_retry`)."""
    chat: Callable[..., llm.LLMStream] = model.chat

    def guarded_chat(*args: Any, **kwargs: Any) -> llm.LLMStream:  # forwards LiveKit's signature
        stream = chat(*args, **kwargs)
        run = stream._run  # pyright: ignore[reportPrivateUsage]  # the only hook on a stream's attempt

        async def checked_run() -> None:
            await run()
            if not stream._event_ch.output_sent:  # pyright: ignore[reportPrivateUsage,reportAttributeAccessIssue]
                raise APIConnectionError(EMPTY_COMPLETION, retryable=True)

        stream._run = checked_run  # pyright: ignore[reportPrivateUsage]
        return stream

    model.chat = guarded_chat  # pyright: ignore[reportAttributeAccessIssue]
    return model
