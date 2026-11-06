import json

import httpx2
import pytest

from mini_rag.corpus import Chunk
from mini_rag.generate import GenerationError, LlmGenerator

_KEY = "sk-or-test"
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


def _generator(
    status: int,
    body: dict[str, object],
    seen: list[dict[str, object]] | None = None,
    requests: list[httpx2.Request] | None = None,
    **kwargs: object,
) -> LlmGenerator:
    def handler(request: httpx2.Request) -> httpx2.Response:
        if seen is not None:
            seen.append(json.loads(request.content))
        if requests is not None:
            requests.append(request)
        return httpx2.Response(status, json=body)

    return _with_transport(handler, **kwargs)


def _raw_generator(response: httpx2.Response) -> LlmGenerator:
    return _with_transport(lambda _request: response)


def _with_transport(handler: object, **kwargs: object) -> LlmGenerator:
    """One factory for every test; max_retries=0 so error cases never sleep through SDK backoff."""
    client = httpx2.Client(transport=httpx2.MockTransport(handler))  # type: ignore[arg-type]
    options: dict[str, object] = {"api_key": _KEY, "timeout_s": 5, "max_tokens": 64, "max_retries": 0} | kwargs
    return LlmGenerator("https://openrouter.ai/api", "m", http_client=client, **options)  # type: ignore[arg-type]


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


def test_request_targets_messages_endpoint_with_bearer_key() -> None:
    requests: list[httpx2.Request] = []
    gen = _generator(200, _message([{"type": "text", "text": "5050"}]), requests=requests)

    gen.answer("Which port?", _PASSAGES)

    (request,) = requests
    assert str(request.url) == "https://openrouter.ai/api/v1/messages"
    assert request.headers["authorization"] == f"Bearer {_KEY}"


@pytest.mark.parametrize(
    ("status", "kind"),
    [(401, "authentication_error"), (402, "invalid_request_error"), (429, "rate_limit_error")],
    ids=["bad-key", "no-credits", "rate-limited"],
)
def test_provider_refusal_becomes_generation_error_with_reason(status: int, kind: str) -> None:
    body = {"type": "error", "error": {"type": kind, "message": f"provider says {status}"}}

    with pytest.raises(GenerationError, match=f"provider says {status}"):
        _generator(status, body).answer("q", _PASSAGES)


def test_openrouter_routing_is_restricted_to_the_listed_providers_and_quantization() -> None:
    seen: list[dict[str, object]] = []
    gen = _generator(200, _message([{"type": "text", "text": "5050"}]), seen, providers=["a", "b"], quantization="fp8")

    gen.answer("Which port?", _PASSAGES)

    assert seen[0]["provider"] == {"order": ["a", "b"], "allow_fallbacks": False, "quantizations": ["fp8"]}


def test_served_provider_is_counted_per_answer() -> None:
    gen = _generator(200, {**_message([{"type": "text", "text": "5050"}]), "provider": "Parasail"})

    gen.answer("q", _PASSAGES)
    gen.answer("q", _PASSAGES)

    assert gen.served == {"Parasail": 2}


def test_response_without_provider_counts_nothing() -> None:
    gen = _generator(200, _message([{"type": "text", "text": "5050"}]))

    gen.answer("q", _PASSAGES)

    assert gen.served == {}


def test_no_provider_sends_no_routing_field() -> None:
    seen: list[dict[str, object]] = []
    _generator(200, _message([{"type": "text", "text": "5050"}]), seen).answer("q", _PASSAGES)

    assert "provider" not in seen[0]


def test_keyless_endpoint_gets_a_placeholder_not_a_crash() -> None:
    requests: list[httpx2.Request] = []
    gen = _generator(200, _message([{"type": "text", "text": "5050"}]), requests=requests, api_key=None)

    assert gen.answer("q", _PASSAGES) == "5050"
    assert requests[0].headers["authorization"] == "Bearer not-needed"
