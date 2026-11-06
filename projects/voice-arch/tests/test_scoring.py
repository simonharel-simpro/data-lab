import pytest

from tests.call_fakes import row
from voice_arch.booking.record import SCORED_FIELDS
from voice_arch.call import Outcome
from voice_arch.scoring import FULL_REPS, aggregate, cost_per_call

# Metric names as the plan spells them (U-10): the tests read them through these names, not the source constants.
P50, P90 = "latency_p50_s", "latency_p90_s"


def test_f_5_timeouts_and_errors_count_as_misses_in_exact_rate() -> None:
    rows = [row(Outcome.SCORED, exact=True) for _ in range(8)]
    rows += [row(Outcome.TIMEOUT), row(Outcome.AGENT_LOST)]

    metrics = aggregate(rows, full=True)

    assert metrics["exact_rate"] == pytest.approx(8 / 10)


def test_u_3_agent_timeout_counts_as_not_exact_in_denominator() -> None:
    metrics = aggregate([row(Outcome.SCORED, exact=True), row(Outcome.TIMEOUT)], full=True)

    assert metrics["exact_rate"] == pytest.approx(0.5)


def test_f_6_caller_fault_excluded_and_counted() -> None:
    rows = [row(Outcome.SCORED, exact=True), row(Outcome.SCORED, exact=True), row(Outcome.CALLER_FAULT)]

    metrics = aggregate(rows, full=True)

    assert metrics["exact_rate"] == 1.0
    assert metrics["n_caller_fault"] == 1


def test_f_7_latency_aggregation_tolerates_missing_and_all_missing_e2e() -> None:
    metrics = aggregate([row(Outcome.SCORED, latencies=[1.0, None, 3.0])], full=True)

    assert metrics[P50] == pytest.approx(2.0)
    assert metrics["latency_turns"] == 2
    assert metrics["latency_turns_missing"] == 1

    all_missing = aggregate([row(Outcome.SCORED, latencies=[None, None])], full=True)
    assert P50 not in all_missing
    assert all_missing["latency_turns_missing"] == 2


def test_single_latency_turn_is_p50_and_p90() -> None:
    turn = 1.4

    metrics = aggregate([row(Outcome.SCORED, latencies=[turn])], full=True)

    assert (metrics[P50], metrics[P90]) == (turn, turn)


def test_u_10_no_turns_omits_latency_metrics() -> None:
    metrics = aggregate([row(Outcome.SCORED, latencies=[])], full=True)

    assert metrics["latency_turns"] == 0
    assert not [key for key in metrics if key.startswith("latency_p")]


def test_u_10_p90_interpolates_inclusive_deciles() -> None:
    metrics = aggregate([row(Outcome.SCORED, latencies=[1.0, 2.0, 3.0, 4.0, 5.0])], full=True)

    assert metrics[P50] == pytest.approx(3.0)
    assert metrics[P90] == pytest.approx(4.6)


def test_u_13_missing_field_counts_as_incorrect() -> None:
    rows = [row(Outcome.SCORED, exact=True), row(Outcome.TIMEOUT)]

    metrics = aggregate(rows, full=True)

    assert [metrics[f"field_{f}_acc"] for f in SCORED_FIELDS] == [0.5] * len(SCORED_FIELDS)


def test_u_1_smoke_metrics_are_prefixed() -> None:
    metrics = aggregate([row(Outcome.SCORED, exact=True)], full=False)

    assert metrics["smoke_exact_rate"] == 1.0
    assert not [key for key in metrics if not key.startswith("smoke_")]


def test_counters_are_summed_over_rows() -> None:
    rows = [
        row(Outcome.SCORED, barge_ins=2, barge_ins_handled=1, long_silences=1, agent_turns=4, session_errors=1),
        row(Outcome.SCORED, barge_ins=1, barge_ins_handled=1, long_silences=2, agent_turns=6, session_errors=0),
    ]

    metrics = aggregate(rows, full=True)

    assert (metrics["barge_ins"], metrics["barge_ins_handled"]) == (3, 2)
    assert metrics["long_silences"] == 3
    assert metrics["long_silences_per_turn"] == pytest.approx(3 / 10)
    assert metrics["session_errors"] == 1


def test_every_outcome_has_a_count_and_exact_is_counted() -> None:
    metrics = aggregate([row(Outcome.SCORED, exact=True), row(Outcome.TIMEOUT)], full=True)

    assert {o: metrics[f"n_{o.value}"] for o in Outcome} == {
        Outcome.SCORED: 1,
        Outcome.TIMEOUT: 1,
        Outcome.AGENT_LOST: 0,
        Outcome.CALLER_FAULT: 0,
        Outcome.PROVIDER_ERROR: 0,
    }
    assert metrics["n_exact"] == 1


def test_only_caller_faults_leaves_no_rate() -> None:
    metrics = aggregate([row(Outcome.CALLER_FAULT)], full=True)

    assert "exact_rate" not in metrics
    assert metrics["n_caller_fault"] == 1


def test_u_19_cost_per_call_uses_exact_rate_denominator() -> None:
    rows = [row(Outcome.SCORED, exact=True) for _ in range(8)] + [row(Outcome.TIMEOUT), row(Outcome.CALLER_FAULT)]
    cost = 3.0

    assert cost_per_call(cost, rows) == pytest.approx(cost / 9)


def test_cost_per_call_without_countable_rows_is_none() -> None:
    assert cost_per_call(1.0, [row(Outcome.CALLER_FAULT)]) is None


def test_full_sweep_is_five_reps() -> None:
    assert FULL_REPS == 5
