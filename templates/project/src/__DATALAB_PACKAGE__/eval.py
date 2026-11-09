"""Eval entry: the one place that reads the test partition, and only when run.json allows it (F-13, F-21, U-27)."""

import json
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import hydra
import mlflow
from hydra.core.hydra_config import HydraConfig
from hydra.utils import instantiate
from mlflow import MlflowClient
from mlflow.entities import LifecycleStage, Run
from mlflow.exceptions import MlflowException
from mlflow.protos.databricks_pb2 import RESOURCE_DOES_NOT_EXIST, ErrorCode
from omegaconf import DictConfig, OmegaConf
from omegaconf.errors import OmegaConfBaseException

from datalab import ledger
from datalab.ledger import LedgerError, RunLedger, Winner
from datalab.project import CardMetric, Project, ProjectError, card_metric, load
from datalab.settings import Settings
from datalab.split import Partition, SplitError, read_split, split_sha256
from datalab.tags import Tag
from datalab.tracking import TrackingUnavailable, preflight, tracked_run, tracked_trial

from .candidates import config_sha256, plain_mapping
from .paths import AUDIT_EXPERIMENT, PROJECT_DIR, register_resolvers
from .prepare import PrepareError, check_data_hash, compose_model, refuse_multirun
from .scoring import label, score
from .split import SplitAccessError, check_time_kinds, load_split, read_rows

register_resolvers()

_REFUSALS = (PrepareError, ProjectError, SplitError, SplitAccessError, OSError, OmegaConfBaseException)
_PARENT = "mlflow.parentRunId"
_NOT_FOUND = ErrorCode.Name(RESOURCE_DOES_NOT_EXIST)


@dataclass(frozen=True)
class _Gate:
    project: Project
    metric: CardMetric
    ledger: RunLedger
    winner: Winner
    folder: Path
    data_file: Path
    split_sha: str
    candidate: str
    model: dict[str, object]
    config_sha: str
    target: str
    look_note: str | None


def _read_ledger(folder: Path) -> RunLedger:
    try:
        return ledger.read(folder)
    except LedgerError as err:
        raise PrepareError(f"eval runs at the audit only: /experiment ({err})") from err


def _check_time_kinds(folder: Path, data_file: Path) -> None:
    """Before the look is recorded: a split whose bounds and rows disagree on timezones cannot be cut."""
    try:
        rows = read_rows(data_file)
    except ValueError as err:
        raise PrepareError(str(err)) from err
    check_time_kinds(read_split(folder / "split.json"), rows)


def _gate(cfg: DictConfig, overrides: Sequence[str]) -> _Gate:
    project = load(PROJECT_DIR)  # (1)
    metric = card_metric(project.root)
    folder, data_file = Path(cfg.paths.experiment_dir), Path(cfg.paths.data_file)
    lg = _read_ledger(folder)  # (2)
    split_sha = split_sha256(folder / "split.json")  # (3)
    note = None if cfg.look_note is None else str(cfg.look_note)
    problem = ledger.test_access_problem(lg, split_sha, note)
    if problem is not None:
        raise PrepareError(problem)
    if lg.data_sha256 is None:
        raise PrepareError("data_file changed since modeling: its hash differs from run.json data_sha256")
    check_data_hash(lg.data_sha256, data_file)
    _check_time_kinds(folder, data_file)
    if lg.winner is None:
        raise PrepareError("run.json has no winner")
    candidate = str(cfg.candidate or lg.winner.candidate)  # (4)
    node = compose_model("eval", overrides, candidate)
    plain = plain_mapping(OmegaConf.to_container(node, resolve=True))
    if plain is None:
        raise PrepareError(f"model {candidate!r} is not a mapping")
    return _Gate(project, metric, lg, lg.winner, folder, data_file, split_sha, candidate, plain,
                 config_sha256(plain), str(cfg.data.target), note)  # fmt: skip


def _cli_value(value: object) -> str:
    return value if isinstance(value, str) else json.dumps(value)


def _cli_form(family: str, logged: dict[str, str]) -> str:
    """`model=<family> model.<k>=<v> ...`: the family's current defaults, then the winner's logged grid values."""
    defaults = OmegaConf.to_container(compose_model("eval", [], family), resolve=True)
    params = plain_mapping(defaults) or {}
    params.pop("_target_", None)
    params |= logged
    return " ".join([f"model={family}", *(f"model.{k}={_cli_value(params[k])}" for k in sorted(params))])


def _live_run(client: MlflowClient, run_id: str, role: str) -> Run:
    """The run, or a refusal naming it: a missing or deleted run is a fact about the ledger, not an outage."""
    try:
        run = client.get_run(run_id)
    except MlflowException as err:
        if err.error_code != _NOT_FOUND:
            raise
        raise PrepareError(f"the {role} run {run_id} does not exist in MLflow") from err
    if run.info.lifecycle_stage == LifecycleStage.DELETED:
        raise PrepareError(f"the {role} run {run_id} is deleted")
    return run


def _check_winner(gate: _Gate, client: MlflowClient) -> None:
    child = _live_run(client, gate.winner.run_id, "winner")
    parent_id = child.data.tags.get(_PARENT)
    if parent_id is None:
        raise PrepareError(f"the winner run {gate.winner.run_id} has no parent run")
    tags = _live_run(client, parent_id, "winner's parent").data.tags
    if tags.get(Tag.SPLIT_SHA256.value) != gate.ledger.split_sha256 or tags.get(Tag.DATA_SHA256.value) != (
        gate.ledger.data_sha256
    ):
        raise PrepareError("the winner was trained on another split or data than run.json freezes")
    if child.data.tags.get(Tag.CONFIG_SHA256.value) != gate.config_sha:
        family = child.data.tags.get(Tag.CANDIDATE.value, gate.winner.candidate)
        hint = _cli_form(family, child.data.params)
        raise PrepareError(f"config_sha256 differs from the winner's: rerun with `python -m {__package__}.eval {hint}`")


def _score_test(gate: _Gate, trial_id: str) -> None:
    # The look is recorded before the test rows are materialised: a crash after this point still counts as a look.
    ledger.write_atomic(gate.folder, ledger.record_test_look(gate.ledger, gate.split_sha, trial_id, gate.look_note))
    rows = read_rows(gate.data_file)
    test_rows = load_split(gate.folder, [Partition.TEST], rows=rows, allow_test=True)[Partition.TEST]
    model = instantiate(gate.model)
    predictions = [model.predict(row) for row in test_rows]
    labels = [label(row, gate.target) for row in test_rows]
    mlflow.log_metric(f"test_{gate.metric.key}", score(predictions, labels))


def _execute(gate: _Gate, settings: Settings) -> int:
    n = str(ledger.look_number(gate.ledger, gate.split_sha))
    parent_tags = {Tag.ENTRY.value: "eval", Tag.SPLIT.value: "test", Tag.TEST_LOOK.value: n}
    parent_tags[Tag.SPLIT_SHA256.value] = gate.split_sha
    child_tags = {Tag.SPLIT.value: "test", Tag.TEST_LOOK.value: n, Tag.CONFIG_SHA256.value: gate.config_sha}
    try:
        with (
            tracked_run(gate.project, settings, f"eval-{gate.candidate}", sub=AUDIT_EXPERIMENT, tags=parent_tags),
            tracked_trial(f"{gate.candidate}-test", child_tags, candidate=gate.candidate) as trial,
        ):
            _score_test(gate, trial.run_id)
    except (MlflowException, TrackingUnavailable) as err:
        print(f"tracking failed: {err}", file=sys.stderr)
        return 1
    except Exception as err:  # noqa: BLE001  # isolation boundary: any failure FAILs the child run, eval exits 1
        print(f"eval failed: {err!r}", file=sys.stderr)
        return 1
    return 0


def run(cfg: DictConfig, overrides: Sequence[str] = ()) -> int:
    try:
        gate = _gate(cfg, overrides)
    except _REFUSALS as err:
        print(f"eval: {err}", file=sys.stderr)
        return 2
    try:
        settings = Settings()
        preflight(settings.mlflow_tracking_uri)
        _check_winner(gate, MlflowClient())
    except PrepareError as err:
        print(f"eval: {err}", file=sys.stderr)
        return 2
    except (MlflowException, TrackingUnavailable, ValueError) as err:
        print(f"tracking failed: {err}", file=sys.stderr)
        return 1
    return _execute(gate, settings)


@hydra.main(version_base=None, config_path="../../configs", config_name="eval")
def main(cfg: DictConfig) -> None:
    refuse_multirun("eval")
    code = run(cfg, tuple(HydraConfig.get().overrides.task))
    if code:
        raise SystemExit(code)


if __name__ == "__main__":
    main()
