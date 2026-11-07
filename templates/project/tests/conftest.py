import json
import os
import shutil
import sys
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path

import pytest
from hydra import compose, initialize_config_dir
from mlflow import MlflowClient
from mlflow.entities import Run
from omegaconf import DictConfig

from datalab import ledger
from datalab.ledger import Kind, RunLedger, Winner

# The package name varies per project and would sort differently against `datalab`: sort the two apart.
# isort: split
from __DATALAB_PACKAGE__ import paths

PROJECT_DIR = paths.PROJECT_DIR
CONFIGS = PROJECT_DIR / "configs"
FIXTURES = Path(__file__).resolve().parent / "fixtures"
E = "__DATALAB_PROJECT__/default"
A = "__DATALAB_PROJECT__/audit"
METRIC = "score (max): template"


@pytest.fixture(autouse=True)
def _isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """No DATALAB_*/MLFLOW_* from the shell, no .env from the cwd, no tracking URI left by another test."""
    for key in list(os.environ):
        if key.startswith(("DATALAB_", "MLFLOW_")):
            monkeypatch.delenv(key)
    monkeypatch.chdir(tmp_path)
    yield
    if "mlflow" in sys.modules:
        import mlflow

        # None is handled at runtime (unsets the URI and the MLFLOW_TRACKING_URI it exports); the stub omits it.
        mlflow.set_tracking_uri(None)  # pyright: ignore[reportArgumentType]


@pytest.fixture(autouse=True)
def _resolvers() -> None:
    paths.register_resolvers()  # so a bare `compose` resolves ${project_dir:}


@pytest.fixture
def sqlite_uri(tmp_path: Path) -> str:
    return f"sqlite:///{tmp_path / 'mlflow.db'}"


@pytest.fixture
def tracking(sqlite_uri: str, monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setenv("DATALAB_MLFLOW_TRACKING_URI", sqlite_uri)
    return sqlite_uri


@pytest.fixture
def configs(tmp_path: Path) -> Path:
    """A copy of the shipped configs: tests add model and grid files to it."""
    target = tmp_path / "configs"
    shutil.copytree(CONFIGS, target)
    return target


@pytest.fixture
def exp_dir(tmp_path: Path) -> Path:
    target = tmp_path / "exp"
    shutil.copytree(FIXTURES, target)
    return target


@pytest.fixture
def data_overrides(exp_dir: Path) -> list[str]:
    return [f"paths.experiment_dir={exp_dir}", f"paths.data_file={exp_dir}/sample.jsonl"]


@contextmanager
def composed(configs: Path, name: str, overrides: Sequence[str]) -> Iterator[DictConfig]:
    with initialize_config_dir(version_base=None, config_dir=str(configs)):
        yield compose(name, overrides=list(overrides))


def write_model(configs: Path, name: str, target: str, **params: object) -> None:
    lines = [f"_target_: {target}", *(f"{key}: {value!r}" for key, value in params.items())]
    (configs / "model" / f"{name}.yaml").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _runs(uri: str, experiment: str) -> list[Run]:
    client = MlflowClient(tracking_uri=uri)
    found = client.get_experiment_by_name(experiment)
    return [] if found is None else client.search_runs([found.experiment_id])


def ledger_at_modeling(exp: Path) -> RunLedger:
    """A comparison ledger with data recorded and modeling still to do; the split of `exp` is frozen."""
    lg = ledger.new_ledger(Kind.COMPARISON, METRIC)
    lg = ledger.produce(lg, "scoping", ["PROJECT.md"])
    lg = ledger.decide(lg, "scoping", ledger.Decision.VALIDATE, "ok")
    lg = ledger.produce(lg, "dataset", ["sample.jsonl"])
    doc = lg.model_dump(mode="json") | {"dataset": {"id": "sample", "hash": "h"}}  # no op sets it: build by hand
    lg = RunLedger.model_validate_json(json.dumps(doc))
    lg = ledger.decide(lg, "dataset", ledger.Decision.VALIDATE, "ok")
    lg = ledger.freeze_split(lg, exp / "split.json", "3/2/2 random")
    lg = ledger.produce(lg, "eda", ["sample.jsonl"])
    lg = ledger.decide(lg, "eda", ledger.Decision.VALIDATE, "ok")
    return ledger.record_data(lg, exp / "sample.jsonl")


def with_winner(lg: RunLedger, candidate: str, run_id: str) -> RunLedger:
    lg = ledger.produce(lg, "modeling", ["sample.jsonl"])
    return ledger.decide(
        lg, "modeling", ledger.Decision.VALIDATE, "ok", winner=Winner(candidate=candidate, run_id=run_id)
    )


@pytest.fixture
def audit_ready(
    configs: Path, exp_dir: Path, data_overrides: list[str], tracking: str
) -> Callable[..., tuple[RunLedger, str]]:
    from __DATALAB_PACKAGE__.train import run as train_run

    def make(candidate: str = "dummy") -> tuple[RunLedger, str]:
        overrides = [*data_overrides, f"experiment.candidates=[{candidate}]"]
        with composed(configs, "train", overrides) as cfg:
            assert train_run(cfg, overrides) == 0
        child = next(r for r in _runs(tracking, E) if r.data.tags.get("mlflow.parentRunId"))
        lg = with_winner(ledger_at_modeling(exp_dir), candidate, child.info.run_id)
        ledger.write_atomic(exp_dir, lg)
        return lg, child.info.run_id

    return make
