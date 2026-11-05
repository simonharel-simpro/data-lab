import json

import httpx2
import pytest

from mini_rag.corpus import Chunk
from mini_rag.generate import DgxGenerator, GenerationError

_PASSAGES = [Chunk(chunk_id="README#s1w0", doc="README", text="MLflow listens on 127.0.0.1:5050.")]


def _message(content: list[dict[str, object]]) -> dict[str, object]:
    return {
        "id": "msg_1",
        "type": "message",
        "role": "assistant",
        "model": "m",
        "content": content,
        "stop_reason": "end_turn",
        "stop_sequence": None,
        "usage": {"input_tokens": 1, "output_tokens": 1},
    }


def _generator(status: int, body: dict[str, object], seen: list[dict[str, object]] | None = None) -> DgxGenerator:
    def handler(request: httpx2.Request) -> httpx2.Response:
        if seen is not None:
            seen.append(json.loads(request.content))
        return httpx2.Response(status, json=body)

    client = httpx2.Client(transport=httpx2.MockTransport(handler))
    return DgxGenerator("http://dgx.invalid", "m", timeout_s=5, max_tokens=64, http_client=client)


def _raw_generator(response: httpx2.Response) -> DgxGenerator:
    client = httpx2.Client(transport=httpx2.MockTransport(lambda _request: response))
    return DgxGenerator("http://dgx.invalid", "m", timeout_s=5, max_tokens=64, http_client=client)


def test_f_13_html_200_raises_generation_error() -> None:
    with pytest.raises(GenerationError):
        _raw_generator(httpx2.Response(200, content=b"<html>")).answer("Which port?", _PASSAGES)


def test_f_13_json_list_200_raises_generation_error() -> None:
    with pytest.raises(GenerationError):
        _raw_generator(httpx2.Response(200, json=[1, 2])).answer("Which port?", _PASSAGES)


def test_f_13_answer_truncated_at_max_tokens_raises() -> None:
    body = {**_message([{"type": "text", "text": "50"}]), "stop_reason": "max_tokens"}

    with pytest.raises(GenerationError, match="truncated"):
        _generator(200, body).answer("Which port?", _PASSAGES)


def test_f_13_wrong_shape_200_raises_not_empty_answer() -> None:
    with pytest.raises(GenerationError):
        _generator(200, {"content": []}).answer("Which port?", _PASSAGES)


def test_f_13_well_formed_message_without_text_raises() -> None:
    gen = _generator(200, _message([{"type": "thinking", "thinking": "only thoughts", "signature": "s"}]))

    with pytest.raises(GenerationError):
        gen.answer("Which port?", _PASSAGES)


def test_b1_thinking_block_stripped() -> None:
    gen = _generator(
        200,
        _message(
            [
                {"type": "thinking", "thinking": "x", "signature": "s"},
                {"type": "text", "text": "<think>y</think>5050"},
            ]
        ),
    )

    assert gen.answer("Which port?", _PASSAGES) == "5050"


def test_b1_api_error_becomes_generation_error() -> None:
    with pytest.raises(GenerationError):
        _generator(500, {"type": "error", "error": {"type": "api_error", "message": "boom"}}).answer("q", _PASSAGES)


def test_request_pins_temperature_zero_and_carries_passages() -> None:
    seen: list[dict[str, object]] = []
    gen = _generator(200, _message([{"type": "text", "text": "5050"}]), seen)

    gen.answer("Which port does MLflow use?", _PASSAGES)

    (request,) = seen
    assert request["temperature"] == 0
    assert request["max_tokens"] == 64
    assert "I don't know" in str(request["system"])
    user = str(request["messages"])
    assert "127.0.0.1:5050" in user
    assert "Which port does MLflow use?" in user
