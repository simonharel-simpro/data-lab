import itertools

import pytest

from mini_rag.scoring import Outcome, contains_phrase, metrics, normalize, numbers_equal, outcome, parse_number


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


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("42", 42.0),
        ("1,200", 1200.0),
        ("1.5", 1.5),
        ("-7", -7.0),
        ("2k", 2_000.0),
        ("2 thousand", 2_000.0),
        ("3m", 3_000_000.0),
        ("3 mn", 3_000_000.0),
        ("1 million", 1_000_000.0),
        ("4b", 4_000_000_000.0),
        ("4 bn", 4_000_000_000.0),
        ("4 billion", 4_000_000_000.0),
        ("5t", 5_000_000_000_000.0),
        ("5 trillion", 5_000_000_000_000.0),
        ("$3.2 bn", 3_200_000_000.0),
        ("5 apples", None),
        ("five", None),
        ("", None),
    ],
)
def test_parse_number_table(text: str, expected: float | None) -> None:
    result = parse_number(text)

    if expected is None:
        assert result is None
    else:
        assert result == pytest.approx(expected)


# math.isclose(x, y, rel_tol=1e-9, abs_tol=1e-12): equal iff |x - y| <= max(1e-9 * max(|x|, |y|), 1e-12).
@pytest.mark.parametrize(
    ("a", "b", "expected"),
    [
        ("1,200", "1200", True),  # thousands separator: both parse to 1200.0
        ("1.2k", "1200", True),  # 1.2 * 1e3 = 1200.0
        ("1 million", "1000000", True),
        # |diff| = 0.5 <= 1e-9 * 1_000_000_000.5 ~= 1.0
        ("1000000000", "1000000000.5", True),
        # |diff| = 2 > 1e-9 * 1_000_000_002 ~= 1.000000002
        ("1000000000", "1000000002", False),
        ("0.0000000000001", "0", True),  # 1e-13 <= abs_tol 1e-12 (rel part is ~0)
        ("0.00000000001", "0", False),  # 1e-11 > abs_tol 1e-12
        ("-5", "5", False),  # |diff| = 10 > 1e-9 * 5
        ("five", "5", False),  # left unparseable
        ("5", "five", False),  # right unparseable
        ("five", "seven", False),  # both unparseable
    ],
)
def test_numbers_equal_table(a: str, b: str, expected: bool) -> None:
    assert numbers_equal(a, b) is expected


_NORMALIZE_CASES = [
    ("Don\N{RIGHT SINGLE QUOTATION MARK}t", "dont"),
    ("Don't", "dont"),
    ("\N{FULLWIDTH DIGIT FIVE}\N{FULLWIDTH DIGIT ZERO}\N{FULLWIDTH DIGIT FIVE}\N{FULLWIDTH DIGIT ZERO}", "5050"),
    ("the port", "port"),
    ("Port: 5050!", "port 5050"),
    ("A cat, an owl & the dog", "cat owl dog"),
]


@pytest.mark.parametrize(("text", "expected"), _NORMALIZE_CASES)
def test_normalize_table(text: str, expected: str) -> None:
    assert normalize(text) == expected


@pytest.mark.parametrize("text", [case[0] for case in _NORMALIZE_CASES])
def test_normalize_is_idempotent(text: str) -> None:
    assert normalize(normalize(text)) == normalize(text)


@pytest.mark.parametrize(
    ("haystack", "needle", "expected"),
    [("x", "", False), ("", "", False), ("port 5050", "5050", True), ("50505", "5050", False)],
)
def test_contains_phrase_table(haystack: str, needle: str, expected: bool) -> None:
    assert contains_phrase(haystack, needle) is expected


def test_metrics_invariants_hold_for_every_small_outcome_list() -> None:
    for n in range(1, 5):
        for outcomes in itertools.product(list(Outcome), repeat=n):
            rates = metrics(outcomes).as_dict()

            assert rates["accuracy"] + rates["hallucination"] + rates["missing"] == pytest.approx(1.0, abs=1e-9)
            assert -1 <= rates["score"] <= 1


def test_metrics_all_correct() -> None:
    result = metrics([Outcome.CORRECT] * 3)

    assert result.accuracy == 1.0
    assert result.score == 1.0


def test_metrics_all_hallucination() -> None:
    result = metrics([Outcome.HALLUCINATION] * 3)

    assert result.hallucination == 1.0
    assert result.score == -1.0
