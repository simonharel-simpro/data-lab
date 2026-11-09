"""Opt-in debug dump of the request behind an empty completion (ESC-3-2 diagnosis).

Off unless `VoiceSettings.dump_empty_dir` (`VOICE_ARCH_DUMP_EMPTY_DIR`) names a directory. The dump holds the whole
conversation, so that directory must stay outside the repository.
"""

import json
import time
from pathlib import Path
from typing import Any

from livekit.agents import llm


def dump_empty_request(
    stream: llm.LLMStream, request: dict[str, Any], attempt: int, directory: Path | None
) -> Path | None:
    """Write the messages, tool definitions and parameters this attempt sent; None when the dump is off."""
    if directory is None:
        return None
    # The same formatting the OpenAI-compatible stream applies before sending (private attributes, like the guard).
    fmt: str = stream._provider_fmt  # pyright: ignore[reportAttributeAccessIssue,reportUnknownMemberType]
    strict: bool = stream._strict_tool_schema  # pyright: ignore[reportAttributeAccessIssue,reportUnknownMemberType]
    messages, _ = stream.chat_ctx.to_provider_format(format=fmt)
    tools = llm.ToolContext(stream.tools).parse_function_tools("openai", strict=strict)
    params = {k: v for k, v in request.items() if k != "extra_headers"}
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"empty-{time.strftime('%H%M%S')}-attempt{attempt}.json"
    payload = {"messages": messages, "tools": tools, "params": params}
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return path
