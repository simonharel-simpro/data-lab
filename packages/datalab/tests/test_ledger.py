import json
from typing import Any

import pytest

from datalab import ledger
from datalab.ledger import (
    Decision,
    Kind,
    LedgerError,
    RunLedger,
    Status,
    Winner,
    contract,
    decide,
    look_number,
    new_ledger,
    parse,
    produce,
    record_test_look,
    redo,
)
from datalab.ledger_model import AUDIT, DATASET, FEATURES, MODELING
from tests.conftest import REPO_ROOT
from tests.ledger_support import VECTORS, at_modeling, h, vector
from tests.ledger_support import ledger as vec_ledger

_NAMES = [(v["name"], v, True) for v in VECTORS["valid"]] + [(v["name"], v, False) for v in VECTORS["invalid"]]


def _expected_prefix(rule: str) -> str:
    return {"schema": "schema:", "U-13": "unsupported schema (kind missing)"}.get(rule, f"{rule}:")


@pytest.mark.parametrize(("name", "entry", "valid"), _NAMES, ids=[n for n, _, _ in _NAMES])
def test_f_18_ledger_vectors(name: str, entry: dict[str, Any], valid: bool) -> None:
    text = json.dumps(entry["run"])

    if valid:
        assert parse(text).model_dump(mode="json") == entry["run"]
        return
    with pytest.raises(LedgerError) as caught:
        parse(text)
    message = str(caught.value)
    assert message.startswith(_expected_prefix(entry["rule"])), name
    assert entry["blames"] in message, name


def test_contract_matches_kind_enum() -> None:
    sequences = contract().sequences

    assert set(sequences) == {Kind.TRAINING, Kind.COMPARISON, Kind.EXPLORATION}
    assert sequences[Kind.TRAINING] == (
        "scoping", "dataset", "cleaning", "eda", "features", "modeling", "audit", "tracking", "report",
    )  # fmt: skip
    assert sequences[Kind.COMPARISON] == ("scoping", "dataset", "eda", "modeling", "audit", "tracking", "report")
    assert sequences[Kind.EXPLORATION] == ("scoping", "eda", "report")


def test_named_milestones_exist_in_contract() -> None:
    sequences = contract().sequences

    assert {MODELING, AUDIT} <= set(contract().agents)
    assert all(m in sequences[Kind.TRAINING] for m in (DATASET, FEATURES, MODELING, AUDIT))
    assert all(m in sequences[Kind.COMPARISON] for m in (DATASET, MODELING, AUDIT))


def test_ledger_enums_match_contract() -> None:
    sets = json.loads((REPO_ROOT / "contracts" / "value_sets.json").read_text(encoding="utf-8"))

    assert [s.value for s in Status] == sets["statuses"]
    assert [d.value for d in Decision] == sets["decisions"]
    assert [k.value for k in Kind] == sets["kinds"]


def test_u_2_redo_resets_later_milestones_to_todo() -> None:
    expected = vector("after-redo")
    expected["decisions_log"] = expected["decisions_log"][:-1]

    assert redo(vec_ledger("training-mid-run"), "dataset").model_dump(mode="json") == expected


def _scoping_produced() -> RunLedger:
    return produce(vec_ledger("fresh-comparison"), "scoping", ["scope.md"])


def test_decide_validate_advances_current() -> None:
    result = decide(_scoping_produced(), "scoping", Decision.VALIDATE, "ok")

    assert result.milestones["scoping"].status is Status.VALIDATED
    assert (result.current_milestone, len(result.decisions_log)) == ("dataset", 1)


def test_decide_correct_then_produce_resets_decision() -> None:
    corrected = decide(_scoping_produced(), "scoping", Decision.CORRECT, "narrow it")

    assert (corrected.milestones["scoping"].status, corrected.milestones["scoping"].decision) == (
        Status.PRODUCED,
        Decision.CORRECT,
    )
    assert produce(corrected, "scoping", ["scope.md"]).milestones["scoping"].decision is None


def test_redo_after_correct_resets_milestones() -> None:
    corrected = decide(_scoping_produced(), "scoping", Decision.CORRECT, "narrow it")
    again = produce(corrected, "scoping", ["scope.md"])

    result = decide(again, "scoping", Decision.REDO, "start over")

    scoping = result.milestones["scoping"]
    assert (scoping.status, scoping.decision) == (Status.TODO, None)
    assert result.decisions_log[-1].decision is Decision.REDO


def test_redo_directly_after_correct_resets_milestones() -> None:
    corrected = decide(_scoping_produced(), "scoping", Decision.CORRECT, "narrow it")

    result = decide(corrected, "scoping", Decision.REDO, "start over")

    scoping = result.milestones["scoping"]
    assert (scoping.status, scoping.decision) == (Status.TODO, None)
    assert [e.decision for e in result.decisions_log] == [Decision.CORRECT, Decision.REDO]


def test_produce_with_empty_artifact_rejected() -> None:
    for bad in ("", ".", "./", "a/.."):
        with pytest.raises(LedgerError, match="I-12"):
            produce(vec_ledger("fresh-comparison"), "scoping", [bad])


def test_decide_redo_from_modeling_at_audit() -> None:
    result = decide(vec_ledger("audit-first-look"), "audit", Decision.REDO, "leak", redo_from="modeling")

    assert [result.milestones[m].status for m in ("modeling", "audit")] == [Status.TODO, Status.TODO]
    assert (result.current_milestone, result.winner, result.data_sha256) == ("modeling", None, None)
    assert (result.decisions_log[-1].milestone, result.decisions_log[-1].decision) == ("audit", Decision.REDO)


def test_decide_modeling_requires_winner() -> None:
    produced = parse(json.dumps(at_modeling("produced")))

    with pytest.raises(LedgerError, match="winner"):
        decide(produced, "modeling", Decision.VALIDATE, "ok")
    result = decide(produced, "modeling", Decision.VALIDATE, "ok", winner=Winner(candidate="dummy", run_id="r1"))

    assert result.winner == Winner(candidate="dummy", run_id="r1")


def test_decide_refuses_blank_note() -> None:
    with pytest.raises(LedgerError, match="note"):
        decide(_scoping_produced(), "scoping", Decision.VALIDATE, "")


def test_produce_refuses_non_current_milestone() -> None:
    with pytest.raises(LedgerError, match="eda is not the current milestone"):
        produce(vec_ledger("fresh-comparison"), "eda", ["x"])


def test_decide_refuses_non_produced_milestone() -> None:
    with pytest.raises(LedgerError, match="scoping is todo: produce it before deciding"):
        decide(vec_ledger("fresh-comparison"), "scoping", Decision.VALIDATE, "ok")


def test_decide_refuses_redo_from_after_milestone() -> None:
    with pytest.raises(LedgerError, match="redo_from"):
        decide(vec_ledger("training-mid-run"), "eda", Decision.REDO, "x", redo_from="features")


def test_redo_unknown_milestone_refused() -> None:
    with pytest.raises(LedgerError, match="foo"):
        redo(vec_ledger("training-mid-run"), "foo")


def test_u_16_scoping_ledger_with_null_dataset_is_valid() -> None:
    fresh = new_ledger(Kind.COMPARISON, "m")

    assert fresh.dataset is None
    assert parse(json.dumps(fresh.model_dump(mode="json"))) == fresh


def test_f_5_unknown_key_rejected_not_dropped() -> None:
    with pytest.raises(LedgerError, match="notes"):
        parse(json.dumps(vector("unknown-key")))


def test_u_28_test_access_rules() -> None:
    audit = vec_ledger("audit-first-look")

    assert "note" in str(ledger.test_access_problem(audit, h("a"), None))
    assert ledger.test_access_problem(audit, h("a"), "why") is None
    assert "split.json" in str(ledger.test_access_problem(audit, h("c"), "why"))
    assert "audit" in str(ledger.test_access_problem(vec_ledger("training-mid-run"), h("a"), "why"))
    assert look_number(audit, h("a")) == 2
    assert ledger.test_access_allowed(audit, h("a"), "why")


def test_record_test_look_appends() -> None:
    result = record_test_look(vec_ledger("audit-first-look"), h("a"), "e2", "re-check after fix")

    assert [(look.run_id, look.note) for look in result.test_looks] == [("e1", ""), ("e2", "re-check after fix")]
    with pytest.raises(LedgerError, match="note"):
        record_test_look(vec_ledger("audit-first-look"), h("a"), "e2", None)


def test_new_exploration_ledger_starts_at_scoping() -> None:
    fresh = new_ledger(Kind.EXPLORATION, "m (max): x")

    assert fresh.current_milestone == "scoping"
    assert {m: e.status for m, e in fresh.milestones.items()} == {
        "scoping": Status.TODO,
        "eda": Status.TODO,
        "report": Status.TODO,
    }


def test_redo_exploration_resets_all() -> None:
    result = redo(vec_ledger("exploration-complete"), "scoping")

    assert [result.milestones[m].status for m in ("scoping", "eda", "report")] == [Status.TODO] * 3
    assert result.current_milestone == "scoping"
    assert (result.dataset, result.split_sha256, result.split_summary) == (None, None, None)
    assert (result.features, result.winner, result.data_sha256, result.test_looks) == (None, None, None, ())


def test_test_access_refuses_exploration() -> None:
    done = vec_ledger("exploration-complete")

    assert ledger.test_access_problem(done, h("a"), None) == (
        "the test partition is read at the audit; the current milestone is report"
    )
    with pytest.raises(LedgerError, match="the test partition is read at the audit"):
        record_test_look(done, h("a"), "e1", None)


def test_u_3_exploration_features_message() -> None:
    with pytest.raises(LedgerError) as caught:
        parse(json.dumps(vector("exploration-with-features")))

    assert str(caught.value) == "I-7: features is not in the exploration sequence, so features must be null"
