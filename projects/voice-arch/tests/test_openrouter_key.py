from collections.abc import Callable, Iterator

import httpx
import pytest

from voice_arch.openrouter_key import KeyUsage, OpenRouterKeyError, SpendTracker, key_usage


def _client(handler: Callable[[httpx.Request], httpx.Response]) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def _sequence(*responses: httpx.Response) -> httpx.Client:
    it: Iterator[httpx.Response] = iter(responses)
    return _client(lambda _request: next(it))


def _ok(usage: float, remaining: float | None = 48.0) -> httpx.Response:
    return httpx.Response(200, json={"data": {"usage": usage, "limit_remaining": remaining}})


def test_key_usage_reads_data_usage() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return _ok(1.25)

    result = key_usage("k", client=_client(handler))

    assert result == KeyUsage(usage=1.25, limit_remaining=48.0)
    assert (seen[0].url.host, seen[0].url.path) == ("openrouter.ai", "/api/v1/key")
    assert seen[0].headers["authorization"] == "Bearer k"


def test_key_usage_null_limit_remaining_is_none() -> None:
    assert key_usage("k", client=_sequence(_ok(2.0, None))).limit_remaining is None


@pytest.mark.parametrize("response", [httpx.Response(200, json={"data": {}}), httpx.Response(401, json={})])
def test_key_usage_wrong_shape_or_401_raises(response: httpx.Response) -> None:
    with pytest.raises(OpenRouterKeyError):
        key_usage("k", client=_sequence(response))


def test_key_usage_non_json_body_raises() -> None:
    with pytest.raises(OpenRouterKeyError):
        key_usage("k", client=_sequence(httpx.Response(200, text="<html>")))


def test_spend_tracker_computes_cost_and_calls_on_exit() -> None:
    costs: list[float] = []

    with SpendTracker("k", client=_sequence(_ok(1.0, 49.0), _ok(1.4)), on_exit=costs.append) as tracker:
        assert tracker.remaining_before == 49.0

    assert tracker.cost_usd == pytest.approx(0.4)
    assert costs == [pytest.approx(0.4)]


def test_spend_tracker_spent_now_is_usage_delta() -> None:
    with SpendTracker("k", client=_sequence(_ok(1.0), _ok(1.3), _ok(1.3))) as tracker:
        assert tracker.spent_now() == pytest.approx(0.3)


def test_spend_tracker_reports_cost_on_exception() -> None:
    costs: list[float] = []

    with (
        pytest.raises(RuntimeError, match="boom"),
        SpendTracker("k", client=_sequence(_ok(1.0), _ok(1.4)), on_exit=costs.append),
    ):
        raise RuntimeError("boom")

    assert costs == [pytest.approx(0.4)]


@pytest.mark.parametrize("failing", [0, 1])
def test_f_12_key_usage_read_failure_omits_cost_without_failing_run(failing: int) -> None:
    responses = [_ok(1.0), _ok(1.4)]
    responses[failing] = httpx.Response(500)
    costs: list[float] = []

    with SpendTracker("k", client=_sequence(*responses), on_exit=costs.append) as tracker:
        pass

    assert tracker.cost_usd is None
    assert costs == []
