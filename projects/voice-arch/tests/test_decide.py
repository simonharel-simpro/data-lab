import pytest

from voice_arch.decide import ArchSummary, human_rating_mean, pick_arch


def _summary(arch: str, exact: int, p50: float | None, *, cost: float | None = 0.1, n: int = 30) -> ArchSummary:
    return ArchSummary(arch=arch, exact=exact, n=n, latency_p50_s=p50, cost_per_call_usd=cost, human_rating_mean=None)


def test_u_16_arch_within_exact_margin_falls_back_to_latency() -> None:
    decision = pick_arch([_summary("a", 27, 2.3), _summary("b", 26, 2.0)])

    assert decision.winner == "b"


def test_pick_arch_outside_margin_prefers_exact() -> None:
    decision = pick_arch([_summary("a", 28, 2.5), _summary("b", 25, 1.9)])

    assert decision.winner == "a"


def test_u_16_exactly_two_calls_apart_still_ties() -> None:
    decision = pick_arch([_summary("a", 24, 2.4), _summary("b", 22, 2.0)])

    assert decision.winner == "b"


def test_u_16_no_arch_meets_bar_still_ranks_and_flags() -> None:
    decision = pick_arch([_summary("a", 24, 1.0), _summary("b", 20, 0.9)])

    assert decision.winner == "a"
    assert decision.production_ready is False
    assert [s.arch for s in decision.ranking] == ["a", "b"]


def test_production_ready_needs_exact_rate_and_latency() -> None:
    assert pick_arch([_summary("a", 27, 1.1)]).production_ready is True
    assert pick_arch([_summary("a", 27, 1.2)]).production_ready is False
    assert pick_arch([_summary("a", 26, 1.1)]).production_ready is False


def test_missing_latency_ranks_last_in_a_tie_and_blocks_ready() -> None:
    decision = pick_arch([_summary("a", 27, None), _summary("b", 26, 3.0)])

    assert decision.winner == "b"
    assert pick_arch([_summary("a", 30, None)]).production_ready is False


def test_equal_latency_falls_back_to_lowest_cost() -> None:
    decision = pick_arch([_summary("a", 27, 2.0, cost=0.30), _summary("b", 27, 2.0, cost=0.10)])

    assert decision.winner == "b"


def test_exact_rate_property() -> None:
    assert _summary("a", 27, 1.0, n=30).exact_rate == pytest.approx(0.9)


def test_no_summaries_is_an_error() -> None:
    with pytest.raises(ValueError, match="no arch"):
        pick_arch([])


def test_u_23_human_ratings_aggregate_by_mean_per_arch() -> None:
    assert human_rating_mean([4, 5, 3]) == 4.0
    assert human_rating_mean([]) is None
