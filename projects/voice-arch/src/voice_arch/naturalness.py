"""Naturalness counters read from a `SessionReport.to_dict()` (pure; the schema is owned by LiveKit).

Mapping, checked against a real text-mode `to_dict()` (IMPLEMENTATION_NOTES, Phase 3; `e2e_latency` needs audio):
`chat_history.items` holds the messages (`type == "message"`, `role`, `interrupted`, `content: list[str]`,
`metrics.started_speaking_at`, `metrics.stopped_speaking_at`, `metrics.e2e_latency`); `events` holds the session
events (`type == "error"`).
"""

import difflib
import re
from collections.abc import Mapping
from typing import Final, cast

LONG_SILENCE_S: Final = 2.0
SAME_REPLY_RATIO: Final = 0.9  # U-12: a reply at least this similar to the interrupted one is a verbatim repeat

type Item = Mapping[str, object]


class ReportShapeError(ValueError):
    """The report does not have the keys this module reads: LiveKit's schema changed, or the mapping is wrong."""


def _as_item(value: object) -> Item | None:
    # `isinstance(x, dict)` narrows JSON-decoded data to `dict[Unknown, Unknown]`; its keys are strings.
    return cast("Item", value) if isinstance(value, dict) else None


def _as_list(value: object) -> list[object] | None:
    return cast("list[object]", value) if isinstance(value, list) else None


def _messages(report: Mapping[str, object]) -> list[Item]:
    history = _as_item(report.get("chat_history"))
    items = _as_list(history.get("items")) if history is not None else None
    if items is None:
        raise ReportShapeError("report has no chat_history.items list")
    found = (_as_item(item) for item in items)
    return [item for item in found if item is not None and item.get("type") == "message"]


def _metric(item: Item, key: str) -> float | None:
    metrics = _as_item(item.get("metrics"))
    value = metrics.get(key) if metrics is not None else None
    return float(value) if isinstance(value, int | float) and not isinstance(value, bool) else None


def _text(item: Item) -> str:
    content = item.get("content")
    parts = _as_list(content) or []
    return " ".join(part for part in parts if isinstance(part, str))


def _normalised(text: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", text.lower()).split())


def latencies(report: Mapping[str, object]) -> list[float | None]:
    """`metrics.e2e_latency` of every assistant turn, None where the turn has none (F-7)."""
    return [_metric(m, "e2e_latency") for m in _messages(report) if m.get("role") == "assistant"]


def long_silences(report: Mapping[str, object]) -> int:
    """Assistant turns that start strictly more than 2.0 s after the last user turn stopped (U-11)."""
    count, last_user_stop = 0, None
    for message in _messages(report):
        if message.get("role") == "user":
            last_user_stop = _metric(message, "stopped_speaking_at")
        elif message.get("role") == "assistant":
            start = _metric(message, "started_speaking_at")
            if start is not None and last_user_stop is not None and start - last_user_stop > LONG_SILENCE_S:
                count += 1
    return count


def barge_ins(report: Mapping[str, object]) -> tuple[int, int]:
    """(interrupted assistant messages, handled): handled = the next assistant message differs (U-12)."""
    replies = [m for m in _messages(report) if m.get("role") == "assistant"]
    total = handled = 0
    for index, reply in enumerate(replies):
        if reply.get("interrupted") is not True:
            continue
        total += 1
        if index + 1 < len(replies):
            similarity = difflib.SequenceMatcher(
                None, _normalised(_text(reply)), _normalised(_text(replies[index + 1]))
            ).ratio()
            handled += similarity < SAME_REPLY_RATIO
    return total, handled


def session_errors(report: Mapping[str, object]) -> int:
    events = _as_list(report.get("events"))
    if events is None:
        raise ReportShapeError("report has no events list")
    found = (_as_item(event) for event in events)
    return sum(1 for event in found if event is not None and event.get("type") == "error")
