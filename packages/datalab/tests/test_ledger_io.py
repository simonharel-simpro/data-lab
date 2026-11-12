import hashlib
import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from datalab import ledger
from datalab.ledger import (
    Decision,
    Kind,
    LedgerError,
    MilestoneEntry,
    RunLedger,
    Status,
    freeze_split,
    main,
    new_ledger,
    parse,
    read,
    record_data,
    validate_dir,
    write_atomic,
)
from tests.ledger_support import after_dataset, at_modeling, project, vector
from tests.test_split import _split

_BOM = "\N{ZERO WIDTH NO-BREAK SPACE}"


def _text(run: dict[str, Any]) -> str:
    return json.dumps(run)


def test_f_5_read_corrupt_raises_ledger_error(tmp_path: Path) -> None:
    folder = project(tmp_path)
    (folder / "run.json").write_text('{"schema_version": 1,', encoding="utf-8")

    with pytest.raises(LedgerError, match=r"run\.json"):
        read(folder)


def test_read_missing_run_json_raises(tmp_path: Path) -> None:
    with pytest.raises(LedgerError, match=r"run\.json"):
        read(tmp_path)


def test_parse_strips_bom() -> None:
    assert parse(_BOM + _text(vector("fresh-comparison"))).kind is Kind.COMPARISON


def test_record_data_hashes_file_and_requires_freeze(tmp_path: Path) -> None:
    data = tmp_path / "data.jsonl"
    data.write_bytes(b'{"a": 1}\n')

    result = record_data(parse(_text(at_modeling("todo"))), data)

    assert result.data_sha256 == hashlib.sha256(b'{"a": 1}\n').hexdigest()
    with pytest.raises(LedgerError, match="frozen"):
        record_data(parse(_text(vector("fresh-comparison"))), data)


def test_freeze_split_before_dataset_validated_refused(tmp_path: Path) -> None:
    split = tmp_path / "split.json"
    split.write_text(json.dumps(_split()), encoding="utf-8")
    fresh = parse(_text(vector("fresh-comparison")))

    with pytest.raises(LedgerError, match="dataset"):
        freeze_split(fresh, split, "random seed 0")
    assert (fresh.split_sha256, fresh.split_summary) == (None, None)


def test_f_4_split_changed_after_freeze_fails_validate(tmp_path: Path) -> None:
    folder = project(tmp_path, after_dataset())
    split = folder / "split.json"
    split.write_text(json.dumps(_split()), encoding="utf-8")
    write_atomic(folder, freeze_split(read(folder), split, "random seed 0"), replace_corrupt=False)
    validate_dir(folder)

    split.write_text(json.dumps(_split(splits={"train": [0, 1, 3], "val": [2], "test": [4]})), encoding="utf-8")

    with pytest.raises(LedgerError, match="V-2"):
        validate_dir(folder)


def test_u_23_validate_accepts_split_without_run_json(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    folder = tmp_path / "proj"
    folder.mkdir()
    (folder / "split.json").write_text(json.dumps(_split()), encoding="utf-8")

    assert validate_dir(folder) is None
    assert main(["validate", str(folder)]) == 0
    assert capsys.readouterr().out == f"ok {folder.resolve()}\n"


def test_u_15_missing_artifact_fails_validate(tmp_path: Path) -> None:
    folder = project(tmp_path, vector("training-mid-run"), files=["scope.md", "dataset.md", "src/demo/data/clean.py"])

    with pytest.raises(LedgerError, match=r"V-1.*eda\.md"):
        validate_dir(folder)


def test_artifact_symlink_escape_rejected(tmp_path: Path) -> None:
    folder = project(tmp_path, vector("training-mid-run"))
    outside = tmp_path / "outside.md"
    outside.write_text("x", encoding="utf-8")
    (folder / "scope.md").unlink()
    (folder / "scope.md").symlink_to(outside)

    with pytest.raises(LedgerError, match=r"V-1.*scope\.md"):
        validate_dir(folder)


def test_metric_not_matching_card_fails_validate(tmp_path: Path) -> None:
    run = vector("fresh-comparison")
    run["metric"] = "loss (min): x"

    with pytest.raises(LedgerError, match="V-3"):
        validate_dir(project(tmp_path, run))


@pytest.mark.parametrize("target", ["datalab.ledger.os.replace", "datalab.ledger.os.fsync"])
def test_f_6_write_failure_leaves_run_json_byte_identical_and_no_tmp(tmp_path: Path, target: str) -> None:
    folder = project(tmp_path, vector("fresh-comparison"))
    before = (folder / "run.json").read_bytes()
    nxt = ledger.produce(read(folder), "scoping", ["scope.md"])

    with patch(target, side_effect=OSError("boom")), pytest.raises(OSError, match="boom"):
        write_atomic(folder, nxt)

    assert (folder / "run.json").read_bytes() == before
    assert list(folder.glob("*.json.tmp")) == []


def test_f_6_invalid_model_never_written(tmp_path: Path) -> None:
    folder = tmp_path / "proj"
    folder.mkdir()
    good = new_ledger(Kind.COMPARISON, "m")
    entry = MilestoneEntry.model_construct(status=Status.TODO, artifacts=(), decision=Decision.VALIDATE)
    bad = RunLedger.model_construct(**{**dict(good), "milestones": {**good.milestones, "dataset": entry}})

    with pytest.raises(LedgerError, match="I-2"):
        write_atomic(folder, bad)

    assert not (folder / "run.json").exists()


def test_write_atomic_roundtrips_in_sequence_order(tmp_path: Path) -> None:
    folder = tmp_path / "proj"
    folder.mkdir()
    fresh = new_ledger(Kind.TRAINING, "m")

    write_atomic(folder, fresh)

    assert read(folder) == fresh
    assert list(json.loads((folder / "run.json").read_text(encoding="utf-8"))["milestones"]) == list(fresh.sequence())


def test_write_refuses_rewritten_log_or_looks(tmp_path: Path) -> None:
    folder = project(tmp_path, after_dataset())
    rewritten = after_dataset()
    rewritten["decisions_log"][0]["note"] = "changed"
    with pytest.raises(LedgerError, match="decisions_log"):
        write_atomic(folder, parse(_text(rewritten)))

    folder = project(tmp_path, vector("audit-first-look"))
    no_looks = vector("audit-first-look")
    no_looks["test_looks"] = []
    with pytest.raises(LedgerError, match="test_looks"):
        write_atomic(folder, parse(_text(no_looks)))


def test_write_refuses_kind_change_after_scoping_validated(tmp_path: Path) -> None:
    old = vector("fresh-comparison")
    old["milestones"]["scoping"] = {"status": "validated", "artifacts": ["scope.md"], "decision": "validate"}
    old["current_milestone"] = "dataset"
    old["decisions_log"] = [{"milestone": "scoping", "decision": "validate", "note": "ok"}]
    folder = project(tmp_path, old)

    with pytest.raises(LedgerError, match="kind"):
        write_atomic(folder, parse(_text(vector("training-mid-run"))))


def test_write_refuses_corrupt_existing_unless_replace_corrupt(tmp_path: Path) -> None:
    folder = project(tmp_path)
    (folder / "run.json").write_text("{", encoding="utf-8")
    fresh = new_ledger(Kind.COMPARISON, "m")
    with pytest.raises(LedgerError, match=r"run\.json"):
        write_atomic(folder, fresh)

    write_atomic(folder, fresh, replace_corrupt=True)

    assert read(folder) == fresh


def test_main_maps_file_paths_to_dirs(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    good = project(tmp_path, vector("fresh-comparison"))
    assert main(["validate", f"{good}/run.json", f"{good}/split.json"]) == 0
    assert capsys.readouterr().out.splitlines() == [f"ok {good.resolve()}"]

    assert main(["validate", str(tmp_path / "nowhere")]) == 2
    assert capsys.readouterr().err.startswith(str(tmp_path / "nowhere"))

    bad = tmp_path / "bad"
    bad.mkdir()
    (bad / "run.json").write_text("{}", encoding="utf-8")
    assert main(["validate", str(bad)]) == 1
    assert capsys.readouterr().err.startswith(f"FAIL {bad.resolve()}: ")


def _exploration_after_scoping() -> RunLedger:
    fresh = new_ledger(Kind.EXPLORATION, "score (max): x")
    return ledger.decide(ledger.produce(fresh, "scoping", ["scope.md"]), "scoping", Decision.VALIDATE, "ok")


def test_exploration_runs_to_report(tmp_path: Path) -> None:
    lg = new_ledger(Kind.EXPLORATION, "score (max): share of rows with a usable transcript")
    for m, artifact in (("scoping", "scope.md"), ("eda", "eda.md"), ("report", "reports/report.html")):
        lg = ledger.decide(ledger.produce(lg, m, [artifact]), m, Decision.VALIDATE, "ok")
    folder = project(tmp_path, lg.model_dump(mode="json"))

    assert all(e.status is Status.VALIDATED for e in lg.milestones.values())
    assert lg.current_milestone == "report"
    assert validate_dir(folder) is None


def test_freeze_split_refuses_exploration(tmp_path: Path) -> None:
    split = tmp_path / "split.json"
    split.write_text(json.dumps(_split()), encoding="utf-8")

    with pytest.raises(LedgerError, match="dataset is not in the exploration sequence"):
        freeze_split(_exploration_after_scoping(), split, "random seed 0")


def test_record_data_refuses_exploration(tmp_path: Path) -> None:
    data = tmp_path / "data.jsonl"
    data.write_bytes(b'{"a": 1}\n')

    with pytest.raises(LedgerError, match="the split must be frozen"):
        record_data(_exploration_after_scoping(), data)


def _stale_pair(tmp_path: Path) -> tuple[Path, RunLedger, RunLedger]:
    folder = project(tmp_path, new_ledger(Kind.EXPLORATION, "score (max): x").model_dump(mode="json"))
    return folder, read(folder), read(folder)


def test_stale_write_does_not_revert_produce(tmp_path: Path) -> None:
    folder, a, b = _stale_pair(tmp_path)
    write_atomic(folder, ledger.produce(a, "scoping", ["scope.md"]), base=a)

    with pytest.raises(LedgerError, match="changed since it was read"):
        write_atomic(folder, b, base=b)

    assert read(folder).milestones["scoping"].status is Status.PRODUCED


def test_write_without_base_keeps_old_behaviour(tmp_path: Path) -> None:
    folder, a, b = _stale_pair(tmp_path)
    write_atomic(folder, ledger.produce(a, "scoping", ["scope.md"]), base=a)

    write_atomic(folder, b)

    assert read(folder).milestones["scoping"].status is Status.TODO
