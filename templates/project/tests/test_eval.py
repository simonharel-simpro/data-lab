import json
import os
import subprocess  # the subprocess tests run this interpreter on the package entry points
import sys
from collections.abc import Callable
from pathlib import Path

import pytest
from mlflow import MlflowClient

from datalab import ledger
from datalab.ledger import RunLedger
from datalab.tags import Tag

# The package name varies per project and would sort differently against `datalab`: sort the two apart.
# isort: split
from __DATALAB_PACKAGE__.eval import run

from .conftest import PROJECT_DIR, A, _runs, composed, ledger_at_modeling, with_winner, write_model

AuditReady = Callable[..., tuple[RunLedger, str]]


def _eval(configs: Path, overrides: list[str]) -> int:
    with composed(configs, "eval", overrides) as cfg:
        return run(cfg, overrides)


def test_f_13_eval_logs_test_prefixed_key_not_metric_key(
    configs: Path, exp_dir: Path, data_overrides: list[str], tracking: str, audit_ready: AuditReady
) -> None:
    _, child_id = audit_ready()

    assert _eval(configs, data_overrides) == 0

    runs = _runs(tracking, A)
    child = next(r for r in runs if "mlflow.parentRunId" in r.data.tags)
    parent = next(r for r in runs if "mlflow.parentRunId" not in r.data.tags)
    assert child.info.run_name == "dummy-test"
    assert child.data.metrics == {"test_score": -0.5, "cost_usd": 0.0}
    for entry in (parent, child):
        assert entry.data.tags[Tag.SPLIT] == "test"
        assert entry.data.tags[Tag.TEST_LOOK] == "1"
    assert ledger.read(exp_dir).test_looks[0].run_id == child.info.run_id != child_id


def test_f_21_eval_without_ledger_exits_2(
    configs: Path, data_overrides: list[str], tracking: str, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _eval(configs, data_overrides) == 2

    assert "/datalab:experiment" in capsys.readouterr().err
    assert MlflowClient(tracking).get_experiment_by_name(A) is None


def test_f_21_eval_before_audit_exits_2(
    configs: Path, exp_dir: Path, data_overrides: list[str], tracking: str, capsys: pytest.CaptureFixture[str]
) -> None:
    lg = ledger.produce(ledger_at_modeling(exp_dir), "modeling", ["sample.jsonl"])
    ledger.write_atomic(exp_dir, lg)

    assert _eval(configs, data_overrides) == 2

    assert "audit" in capsys.readouterr().err
    assert MlflowClient(tracking).get_experiment_by_name(A) is None


def test_f_21_eval_after_audit_validated_exits_2(
    configs: Path, exp_dir: Path, data_overrides: list[str], tracking: str, audit_ready: AuditReady
) -> None:
    lg, _ = audit_ready()
    lg = ledger.produce(lg, "audit", ["sample.jsonl"])
    ledger.write_atomic(exp_dir, ledger.decide(lg, "audit", ledger.Decision.VALIDATE, "ok"))

    assert _eval(configs, data_overrides) == 2

    assert MlflowClient(tracking).get_experiment_by_name(A) is None


def test_u_28_second_look_needs_note(
    configs: Path,
    exp_dir: Path,
    data_overrides: list[str],
    tracking: str,
    audit_ready: AuditReady,
    capsys: pytest.CaptureFixture[str],
) -> None:
    audit_ready()
    assert _eval(configs, data_overrides) == 0
    capsys.readouterr()

    assert _eval(configs, data_overrides) == 2
    assert "note" in capsys.readouterr().err

    assert _eval(configs, [*data_overrides, "look_note='recheck after fix'"]) == 0
    child = [r for r in _runs(tracking, A) if r.info.run_name == "dummy-test" and r.data.tags[Tag.TEST_LOOK] == "2"]
    assert len(child) == 1
    assert len(ledger.read(exp_dir).test_looks) == 2


def test_u_27_config_hash_mismatch_refused(
    configs: Path,
    data_overrides: list[str],
    tracking: str,
    audit_ready: AuditReady,
    capsys: pytest.CaptureFixture[str],
) -> None:
    audit_ready()

    assert _eval(configs, [*data_overrides, "model.value=0.5"]) == 2

    assert "python -m __DATALAB_PACKAGE__.eval model=dummy model.value=" in capsys.readouterr().err
    assert MlflowClient(tracking).get_experiment_by_name(A) is None


def test_eval_refuses_changed_split_or_data(
    configs: Path,
    exp_dir: Path,
    data_overrides: list[str],
    tracking: str,
    audit_ready: AuditReady,
    capsys: pytest.CaptureFixture[str],
) -> None:
    audit_ready()
    split = exp_dir / "split.json"
    original = split.read_text(encoding="utf-8")
    split.write_text(original.replace("[0, 1, 2]", "[1, 0, 2]"), encoding="utf-8")

    assert _eval(configs, data_overrides) == 2
    assert "split.json" in capsys.readouterr().err

    split.write_text(original, encoding="utf-8")
    with (exp_dir / "sample.jsonl").open("a", encoding="utf-8") as handle:
        handle.write('{"x": 7, "y": 0.0}\n')

    assert _eval(configs, data_overrides) == 2
    assert "data" in capsys.readouterr().err


def test_eval_refuses_winner_from_another_split(
    configs: Path,
    exp_dir: Path,
    data_overrides: list[str],
    tracking: str,
    audit_ready: AuditReady,
    capsys: pytest.CaptureFixture[str],
) -> None:
    lg, child_id = audit_ready()
    client = MlflowClient(tracking)
    parent_id = client.get_run(child_id).data.tags["mlflow.parentRunId"]
    client.set_tag(parent_id, Tag.SPLIT_SHA256, "c" * 64)

    assert _eval(configs, data_overrides) == 2

    assert "another split or data" in capsys.readouterr().err
    assert client.get_experiment_by_name(A) is None
    assert ledger.read(exp_dir).test_looks == lg.test_looks


@pytest.mark.parametrize("case", ["missing", "deleted"])
def test_eval_with_deleted_winner_run_exits_2_naming_run(
    case: str,
    configs: Path,
    exp_dir: Path,
    data_overrides: list[str],
    tracking: str,
    audit_ready: AuditReady,
    capsys: pytest.CaptureFixture[str],
) -> None:
    lg, child_id = audit_ready()
    client = MlflowClient(tracking)
    if case == "deleted":
        client.delete_run(child_id)
    else:
        child_id = "f" * 32
        ledger.write_atomic(exp_dir, with_winner(ledger_at_modeling(exp_dir), "dummy", child_id))

    assert _eval(configs, data_overrides) == 2

    err = capsys.readouterr().err
    assert child_id in err
    assert ("does not exist" if case == "missing" else "is deleted") in err
    assert client.get_experiment_by_name(A) is None
    assert ledger.read(exp_dir).test_looks == lg.test_looks


def test_eval_with_deleted_parent_run_exits_2_naming_run(
    configs: Path,
    data_overrides: list[str],
    tracking: str,
    audit_ready: AuditReady,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _, child_id = audit_ready()
    client = MlflowClient(tracking)
    parent_id = client.get_run(child_id).data.tags["mlflow.parentRunId"]
    client.delete_run(parent_id)

    assert _eval(configs, data_overrides) == 2

    err = capsys.readouterr().err
    assert parent_id in err
    assert "is deleted" in err


def test_eval_refuses_mixed_timezones_before_recording_a_test_look(
    configs: Path,
    exp_dir: Path,
    data_overrides: list[str],
    tracking: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    rows = [{"x": i, "y": 0.0, "t": f"2024-12-{i + 1:02d}T00:00:00+00:00"} for i in range(7)]
    (exp_dir / "sample.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    bounds = {"train": "2024-12-03", "val": "2024-12-05", "test": "2024-12-31"}  # naive bounds, aware rows
    split = {"strategy": "temporal", "seed": 0, "target": "y", "group_key": None, "time_col": "t"}
    # Split dict built loosely in test.
    split["splits"] = {name: {"time_max": bound} for name, bound in bounds.items()}  # type: ignore[assignment]  # TypedDict field narrowed by the test on purpose
    (exp_dir / "split.json").write_text(json.dumps(split), encoding="utf-8")
    before = with_winner(ledger_at_modeling(exp_dir), "dummy", "f" * 32)
    ledger.write_atomic(exp_dir, before)

    assert _eval(configs, data_overrides) == 2

    assert "timezone" in capsys.readouterr().err
    assert ledger.read(exp_dir).test_looks == before.test_looks == ()
    assert MlflowClient(tracking).get_experiment_by_name(A) is None


def _cli(
    args: list[str], cwd: Path, sqlite_uri: str, *, pythonpath: Path | None = None
) -> subprocess.CompletedProcess[str]:
    env = {"PATH": os.environ["PATH"], "DATALAB_MLFLOW_TRACKING_URI": sqlite_uri}
    if pythonpath is not None:
        env["PYTHONPATH"] = str(pythonpath)
    return subprocess.run(  # noqa: S603  # fixed argv: this interpreter + the package entry + test paths, no shell
        [sys.executable, "-m", "__DATALAB_PACKAGE__.eval", *args],
        cwd=cwd, env=env, capture_output=True, text=True, check=False, timeout=300,
    )  # fmt: skip


def test_eval_cli_model_override_reaches_hash_check(
    tmp_path: Path, data_overrides: list[str], tracking: str, audit_ready: AuditReady
) -> None:
    audit_ready()

    done = _cli(["model.value=0.5", f"hydra.run.dir={tmp_path}/h", *data_overrides], tmp_path, tracking)

    assert done.returncode == 2, done.stderr
    assert "config_sha256 differs" in done.stderr
    assert "Could not override" not in done.stderr


def test_eval_cli_non_dummy_winner_override_form(
    configs: Path, tmp_path: Path, data_overrides: list[str], tracking: str, audit_ready: AuditReady
) -> None:
    write_model(configs, "offset", "tests.fixture_models.Offset", value=0.0, offset=0.0)
    audit_ready(candidate="offset")
    common = ["--config-dir", str(configs), f"hydra.run.dir={tmp_path}/h", *data_overrides]

    with_family = _cli([*common, "model=offset", "model.offset=0.5"], tmp_path, tracking, pythonpath=PROJECT_DIR)
    without = _cli([*common, "model.offset=0.5"], tmp_path, tracking, pythonpath=PROJECT_DIR)

    assert with_family.returncode == 2, with_family.stderr
    assert "config_sha256 differs" in with_family.stderr
    assert "model=offset model.offset=" in with_family.stderr
    assert without.returncode != 0
    assert "Could not override" in without.stderr
