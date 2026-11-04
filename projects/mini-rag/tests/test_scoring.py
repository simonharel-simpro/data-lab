import pytest

from mini_rag.scoring import Outcome, metrics, outcome


def test_u_12_containment_counts_as_correct() -> None:
    assert outcome("The MLflow port is 5050.", "5050") == "correct"


def test_b_3_token_boundary_rejects_longer_number() -> None:
    assert outcome("port 50505", "5050") == "hallucination"


def test_u_12_numeric_normalisation() -> None:
    assert outcome("1,200", "1200") == "correct"


def test_u_12_idk_is_missing_not_wrong() -> None:
    assert outcome("I don't know.", "5050") == "missing"
    assert outcome("I do not know", "5050") == "missing"


def test_b_3_word_unknown_is_not_idk() -> None:
    assert outcome("The unknown port is 5050", "5050") == "correct"


def test_u_12_answer_to_unanswerable_is_hallucination() -> None:
    assert outcome("8080", None) == "hallucination"
    assert outcome("I don't know", None) == "missing"


def test_u_12_score_formula() -> None:
    outcomes = [Outcome.CORRECT] * 6 + [Outcome.HALLUCINATION] * 2 + [Outcome.MISSING] * 2

    result = metrics(outcomes)

    assert result.accuracy == pytest.approx(0.6)
    assert result.hallucination == pytest.approx(0.2)
    assert result.missing == pytest.approx(0.2)
    assert result.score == pytest.approx(0.4)


def test_metrics_of_no_outcome_is_refused() -> None:
    # An empty run has no rate: refuse rather than log a 0 that would look like a real score.
    with pytest.raises(ValueError, match="no outcome"):
        metrics([])
