from pathlib import Path

import pytest
from mlflow import MlflowClient

from datalab import ledger

# The package name varies per project and would sort differently against `datalab`: sort the two apart.
# isort: split
from __DATALAB_PACKAGE__.train import run

from .conftest import E, composed, ledger_at_modeling


def _train(configs: Path, overrides: list[str]) -> int:
    with composed(configs, "train", overrides) as cfg:
        return run(cfg, overrides)


def test_train_refuses_split_changed_after_freeze_before_any_run(
    configs: Path, exp_dir: Path, data_overrides: list[str], tracking: str, capsys: pytest.CaptureFixture[str]
) -> None:
    ledger.write_atomic(exp_dir, ledger_at_modeling(exp_dir))
    split = exp_dir / "split.json"
    split.write_text(split.read_text(encoding="utf-8").replace("[0, 1, 2]", "[1, 0, 2]"), encoding="utf-8")

    assert _train(configs, data_overrides) == 2

    assert "split.json changed after the freeze" in capsys.readouterr().err
    assert MlflowClient(tracking).get_experiment_by_name(E) is None


def test_train_refuses_data_changed_after_freeze_before_any_run(
    configs: Path, exp_dir: Path, data_overrides: list[str], tracking: str, capsys: pytest.CaptureFixture[str]
) -> None:
    ledger.write_atomic(exp_dir, ledger_at_modeling(exp_dir))
    data = exp_dir / "sample.jsonl"
    # same row count and split.json untouched: only the data hash can refuse this
    data.write_text(data.read_text(encoding="utf-8").replace('"y": 0.5}', '"y": 0.25}', 1), encoding="utf-8")

    assert _train(configs, data_overrides) == 2

    assert "data_sha256" in capsys.readouterr().err
    assert MlflowClient(tracking).get_experiment_by_name(E) is None


def test_train_runs_when_frozen_split_and_data_are_unchanged(
    configs: Path, exp_dir: Path, data_overrides: list[str], tracking: str
) -> None:
    ledger.write_atomic(exp_dir, ledger_at_modeling(exp_dir))

    assert _train(configs, data_overrides) == 0


def test_train_refuses_exploration_ledger_before_any_run(
    configs: Path, exp_dir: Path, data_overrides: list[str], tracking: str, capsys: pytest.CaptureFixture[str]
) -> None:
    ledger.write_atomic(exp_dir, ledger.new_ledger(ledger.Kind.EXPLORATION, "score (max): x"))

    assert _train(configs, data_overrides) == 2

    assert "an exploration ledger has no train run" in capsys.readouterr().err
    assert MlflowClient(tracking).get_experiment_by_name(E) is None
