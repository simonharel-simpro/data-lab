import hashlib
import os
import subprocess  # the subprocess tests run this interpreter on the package entry points
import sys
from pathlib import Path

import mlflow
import pytest
from hydra import compose, initialize_config_dir
from mlflow import MlflowClient
from mlflow.entities import Run
from mlflow.exceptions import MlflowException

from datalab import ledger
from datalab.ledger import Kind

# The package name varies per project and would sort differently against `datalab`: sort the two apart.
# isort: split
from __DATALAB_PACKAGE__.candidates import Constant
from __DATALAB_PACKAGE__.train import run

from .conftest import CONFIGS, FIXTURES, PROJECT_DIR, E, _runs, composed, write_model

CONSTANT = "__DATALAB_PACKAGE__.candidates.Constant"
MISSING = "__DATALAB_PACKAGE__.candidates.Missing"


def _train(configs: Path, overrides: list[str]) -> int:
    with composed(configs, "train", overrides) as cfg:
        return run(cfg, overrides)


def _split(runs: list[Run]) -> tuple[Run, dict[str, Run]]:
    parents = [r for r in runs if "mlflow.parentRunId" not in r.data.tags]
    assert len(parents) == 1
    return parents[0], {r.info.run_name or "": r for r in runs if "mlflow.parentRunId" in r.data.tags}


def test_u_5_train_logs_one_parent_and_one_child_per_listed_candidate(
    configs: Path, data_overrides: list[str], tracking: str
) -> None:
    write_model(configs, "dummy-high", CONSTANT, value=1.0)
    overrides = [*data_overrides, "experiment.candidates=[dummy,dummy-high]"]

    assert _train(configs, overrides) == 0

    parent, children = _split(_runs(tracking, E))
    sha = hashlib.sha256((FIXTURES / "split.json").read_bytes()).hexdigest()
    assert parent.data.metrics == {}
    assert {k: parent.data.tags[k] for k in ("n_children", "entry", "split_sha256", "score_on")} == {
        "n_children": "2", "entry": "train", "split_sha256": sha, "score_on": "val",
    }  # fmt: skip
    assert sorted(children) == ["dummy-0", "dummy-high-0"]
    assert children["dummy-0"].data.metrics == {"score": -1.0, "cost_usd": 0.0}
    assert children["dummy-high-0"].data.metrics == {"score": 0.0, "cost_usd": 0.0}
    assert children["dummy-high-0"].data.tags["candidate"] == "dummy-high"
    assert len(children["dummy-0"].data.tags["config_sha256"]) == 64


def test_u_26_grid_one_child_per_combination(configs: Path, data_overrides: list[str], tracking: str) -> None:
    (configs / "hparams_search").mkdir()
    (configs / "hparams_search" / "g.yaml").write_text("dummy:\n  value: [0.0, 0.5, 1.0]\n", encoding="utf-8")

    assert _train(configs, [*data_overrides, "hparams_search=g"]) == 0

    _, children = _split(_runs(tracking, E))
    assert sorted(children) == ["dummy-0", "dummy-1", "dummy-2"]
    assert [children[n].data.params["value"] for n in sorted(children)] == ["0.0", "0.5", "1.0"]
    assert [children[n].data.metrics["score"] for n in sorted(children)] == [-1.0, -0.5, 0.0]
    assert len({c.data.tags["config_sha256"] for c in children.values()}) == 3


def test_u_26_grid_naming_unknown_candidate_exits_2(
    configs: Path, data_overrides: list[str], tracking: str, capsys: pytest.CaptureFixture[str]
) -> None:
    (configs / "hparams_search").mkdir()
    (configs / "hparams_search" / "g.yaml").write_text("ghost:\n  value: [1]\n", encoding="utf-8")

    assert _train(configs, [*data_overrides, "hparams_search=g"]) == 2

    assert "ghost" in capsys.readouterr().err
    assert MlflowClient(tracking).get_experiment_by_name(E) is None


def test_grid_unknown_param_key_exits_2_before_any_run(
    configs: Path, data_overrides: list[str], tracking: str, capsys: pytest.CaptureFixture[str]
) -> None:
    (configs / "hparams_search").mkdir()
    (configs / "hparams_search" / "g.yaml").write_text("dummy:\n  offset: [0.1]\n", encoding="utf-8")

    assert _train(configs, [*data_overrides, "hparams_search=g"]) == 2

    err = capsys.readouterr().err
    assert "dummy" in err
    assert "offset" in err
    assert MlflowClient(tracking).get_experiment_by_name(E) is None


def test_f_8_one_failing_candidate_parent_lists_it_and_exit_nonzero(
    configs: Path, data_overrides: list[str], tracking: str
) -> None:
    write_model(configs, "boom", CONSTANT, value="nan-text")

    assert _train(configs, [*data_overrides, "experiment.candidates=[dummy,boom]"]) == 1

    parent, children = _split(_runs(tracking, E))
    assert children["boom-0"].info.status == "FAILED"
    assert children["dummy-0"].info.status == "FINISHED"
    assert parent.data.tags["n_failed"] == "1"
    assert parent.data.tags["failed_candidates"] == "boom-0"


def test_tracking_error_is_not_a_candidate_failure(
    configs: Path,
    data_overrides: list[str],
    tracking: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def down(*args: object, **kwargs: object) -> None:
        raise MlflowException("down")

    write_model(configs, "dummy-high", CONSTANT, value=1.0)
    monkeypatch.setattr(mlflow, "log_metric", down)

    assert _train(configs, [*data_overrides, "experiment.candidates=[dummy,dummy-high]"]) == 1

    assert "tracking failed: down" in capsys.readouterr().err
    assert len([r for r in _runs(tracking, E) if "mlflow.parentRunId" in r.data.tags]) == 1


def test_model_override_dropped_per_candidate(configs: Path, data_overrides: list[str], tracking: str) -> None:
    write_model(configs, "dummy-high", CONSTANT, value=1.0)
    overrides = [*data_overrides, "model=dummy-high"]

    assert _train(configs, overrides) == 0

    _, children = _split(_runs(tracking, E))
    assert children["dummy-0"].data.metrics["score"] == -1.0


def test_f_11_bad_target_fails_before_any_run_created(configs: Path, data_overrides: list[str], tracking: str) -> None:
    write_model(configs, "bad", MISSING)

    assert _train(configs, [*data_overrides, "experiment.candidates=[dummy,bad]"]) == 2

    assert MlflowClient(tracking).get_experiment_by_name(E) is None


def test_f_11_missing_value_fails_before_any_run(configs: Path, data_overrides: list[str], tracking: str) -> None:
    assert _train(configs, [*data_overrides, "model.value=???"]) == 2

    assert MlflowClient(tracking).get_experiment_by_name(E) is None


def test_f_11_composes_without_hparams_search(configs: Path, data_overrides: list[str], tracking: str) -> None:
    with composed(configs, "train", data_overrides) as cfg:
        assert "hparams_search" not in cfg
        assert run(cfg, data_overrides) == 0


def test_u_19_train_refuses_bad_experiment_name(configs: Path, data_overrides: list[str], tracking: str) -> None:
    assert _train(configs, [*data_overrides, "experiment.name=Bad_Name"]) == 2
    assert _train(configs, [*data_overrides, "experiment.name=audit"]) == 2

    assert [e.name for e in MlflowClient(tracking).search_experiments()] == ["Default"]


def test_u_3_train_entry_refuses_test_partition(
    configs: Path, data_overrides: list[str], tracking: str, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _train(configs, [*data_overrides, "data.partitions=[train,test]"]) == 2
    capsys.readouterr()

    # score_on is now in the partitions, so only the test-partition guard can refuse this one
    assert _train(configs, [*data_overrides, "data.partitions=[train,test]", "data.score_on=train"]) == 2
    assert "test partition" in capsys.readouterr().err

    assert MlflowClient(tracking).get_experiment_by_name(E) is None


def test_missing_split_exits_2(
    configs: Path, exp_dir: Path, tmp_path: Path, tracking: str, capsys: pytest.CaptureFixture[str]
) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    overrides = [f"paths.experiment_dir={empty}", f"paths.data_file={exp_dir}/sample.jsonl"]

    assert _train(configs, overrides) == 2

    assert "split.json" in capsys.readouterr().err


def test_u_30_comparison_ledger_scores_on_train(
    configs: Path, exp_dir: Path, data_overrides: list[str], tracking: str
) -> None:
    ledger.write_atomic(exp_dir, ledger.new_ledger(Kind.COMPARISON, "score (max): t"))

    assert _train(configs, data_overrides) == 0

    parent, children = _split(_runs(tracking, E))
    assert parent.data.tags["score_on"] == "train"
    assert children["dummy-0"].data.metrics["score"] == 0.0


def test_u_29_secondary_key_not_declared_exits_1(
    configs: Path,
    data_overrides: list[str],
    tracking: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    original = Constant.predict

    def predict(self: Constant, row: object) -> float:
        mlflow.log_metric("dummy_rate", 1.0)
        return original(self, row)  # pyright: ignore[reportArgumentType]

    monkeypatch.setattr(Constant, "predict", predict)

    assert _train(configs, data_overrides) == 1

    assert "dummy_rate" in capsys.readouterr().err


def test_hydra_output_dir_under_project() -> None:
    with initialize_config_dir(version_base=None, config_dir=str(CONFIGS)):
        cfg = compose("train", return_hydra_config=True)

    assert cfg.hydra.run.dir.startswith(str(PROJECT_DIR / "logs"))
    assert cfg.hydra.job.chdir is False


def _module(name: str, args: list[str], cwd: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603  # fixed argv: this interpreter + the package entry + test paths, no shell
        [sys.executable, "-m", name, *args], cwd=cwd, env=env, capture_output=True, text=True, check=False, timeout=300
    )


def test_f_10_train_runs_from_foreign_cwd_without_env(
    tmp_path: Path, data_overrides: list[str], sqlite_uri: str
) -> None:
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    env = {"PATH": os.environ["PATH"], "DATALAB_MLFLOW_TRACKING_URI": sqlite_uri}

    done = _module("__DATALAB_PACKAGE__.train", [f"hydra.run.dir={tmp_path}/h", *data_overrides], elsewhere, env)

    assert done.returncode == 0, done.stderr
    parent, children = _split(_runs(sqlite_uri, E))
    assert sorted(children) == ["dummy-0"]
    assert parent.data.tags["entry"] == "train"
    assert (tmp_path / "h" / ".hydra" / "config.yaml").is_file()


def test_f_12_multirun_refused(tmp_path: Path, data_overrides: list[str], sqlite_uri: str) -> None:
    env = {"PATH": os.environ["PATH"], "DATALAB_MLFLOW_TRACKING_URI": sqlite_uri}

    args = ["--multirun", f"hydra.sweep.dir={tmp_path}/m", *data_overrides]
    done = _module("__DATALAB_PACKAGE__.train", args, tmp_path, env)

    assert done.returncode == 2
    assert "--multirun is not supported" in done.stderr
    assert MlflowClient(sqlite_uri).get_experiment_by_name(E) is None
