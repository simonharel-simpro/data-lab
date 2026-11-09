"""Retry an LLM call that completes with no text and no tool call (ESC-3-2), each retry hotter than the last.

Gemini through OpenRouter sometimes ends a stream with zero completion tokens. LiveKit treats that as a finished
turn: the agent says nothing, raises no error, and the call waits until the caller gives up. At temperature 0 an
identical request can come back empty every time, so a retry raises the temperature instead of repeating itself.
"""

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any, Final, cast

from livekit.agents import APIConnectionError, llm

from voice_arch.llm_dump import dump_empty_request, private_attr

logger = logging.getLogger("voice_arch.llm_guard")

EMPTY_COMPLETION = "the LLM completed without text or tool call"
RETRY_TEMPERATURE_STEP: Final = 0.3
MAX_RETRY_TEMPERATURE: Final = 1.0  # beyond this a booking agent starts to improvise


def retry_temperature(base: float, retry: int) -> float:
    """`retry` counts from 1 (the first re-send); the first attempt keeps `base`."""
    return max(base, min(base + RETRY_TEMPERATURE_STEP * retry, MAX_RETRY_TEMPERATURE))


def retry_on_empty_completion(model: llm.LLM[object], dump_dir: Path | None = None) -> llm.LLM[object]:
    """Same model; an empty stream raises a retryable error, so LiveKit re-sends it (`conn_options.max_retry`)."""
    chat: Callable[..., llm.LLMStream] = model.chat  # LiveKit's `LLM.chat` is keyword-heavy; forwarded as is

    def guarded_chat(*args: Any, **kwargs: Any) -> llm.LLMStream:  # forwards LiveKit's signature
        stream = chat(*args, **kwargs)
        run = stream._run  # pyright: ignore[reportPrivateUsage]  # the only hook on a stream's attempt
        # The dict LiveKit's OpenAI stream sends as request parameters on every attempt. Read directly: if a
        # LiveKit upgrade drops it, the first call fails loudly rather than retrying at an unchanged temperature.
        # The OpenAI stream's private kwargs dict is untyped in the plugin; cast to the shape it has.
        request = cast("dict[str, Any]", private_attr(stream, "_extra_kwargs"))
        base = float(request.get("temperature", 0.0))
        attempts = 0

        async def checked_run() -> None:
            nonlocal attempts
            if attempts > 0:
                request["temperature"] = retry_temperature(base, attempts)
                logger.warning("empty LLM completion, retry %d at temperature %.2f", attempts, request["temperature"])
            attempts += 1
            await run()
            if not stream._event_ch.output_sent:  # pyright: ignore[reportPrivateUsage,reportAttributeAccessIssue]
                dump_empty_request(stream, request, attempts, dump_dir)
                raise APIConnectionError(EMPTY_COMPLETION, retryable=True)

        stream._run = checked_run  # pyright: ignore[reportPrivateUsage]
        return stream

    model.chat = guarded_chat  # pyright: ignore[reportAttributeAccessIssue]
    return model
