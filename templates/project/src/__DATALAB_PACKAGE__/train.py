"""Train entry: one parent MLflow run per invocation, one child per candidate and grid combination (D-5)."""

import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import hydra
import mlflow
from hydra.core.hydra_config import HydraConfig
from hydra.utils import instantiate
from mlflow import MlflowClient
from mlflow.exceptions import MlflowException
from omegaconf import DictConfig, OmegaConf
from omegaconf.errors import OmegaConfBaseException

from datalab.project import NAME_RE, CardMetric, Project, ProjectError, card_metric, experiment_name, load
from datalab.settings import Settings
from datalab.split import Partition, SplitError, split_sha256
from datalab.tags import Tag
from datalab.tracking import TrackingUnavailable, preflight, tracked_run, tracked_trial

from .candidates import Row, config_sha256
from .grid import Combo, GridError, expand
from .paths import PROJECT_DIR, register_resolvers
from .prepare import PrepareError, compose_model, file_sha256, frozen_score_on, refuse_multirun, resolve_config
from .scoring import label, metric_key_problems, score
from .split import SplitAccessError, load_split, read_rows

register_resolvers()

_REFUSALS = (PrepareError, ProjectError, SplitError, GridError, SplitAccessError, OSError, OmegaConfBaseException)


@dataclass(frozen=True)
class _Child:
    combo: Combo
    model: dict[str, object]
    config_sha: str


@dataclass(frozen=True)
class _Plan:
    project: Project
    metric: CardMetric
    sub: str
    resolved: dict[str, object]
    candidates: list[str]
    on: Partition
    children: list[_Child]
    eval_rows: list[Row]
    labels: list[float]
    parent_tags: dict[str, str]


def _candidates(cfg: DictConfig) -> list[str]:
    names = [str(n) for n in cfg.experiment.candidates]
    if not names or len(set(names)) != len(names):
        raise PrepareError(f"experiment.candidates must be a non-empty list without duplicates, got {names}")
    bad = [n for n in names if not NAME_RE.fullmatch(n)]
    if bad:
        raise PrepareError(f"candidate names must match {NAME_RE.pattern}, got {bad}")
    return names


def _children(resolved: dict[str, object], overrides: Sequence[str], candidates: list[str]) -> list[_Child]:
    search = resolved.get("hparams_search") or {}
    if not isinstance(search, dict):
        raise PrepareError("hparams_search must map candidates to parameter lists")
    nodes = {name: compose_model("train", overrides, name) for name in candidates}
    children = []
    for combo in expand(candidates, search):
        try:
            merged = OmegaConf.merge(nodes[combo.candidate], dict(combo.params))
        except OmegaConfBaseException as err:
            unknown = [k for k in combo.params if k not in nodes[combo.candidate]]
            raise PrepareError(
                f"hparams_search: {combo.candidate} has no parameter {unknown} in configs/model/{combo.candidate}.yaml"
            ) from err
        model = OmegaConf.to_container(merged, resolve=True)
        if not isinstance(model, dict):
            raise PrepareError(f"model {combo.candidate!r} is not a mapping")
        plain = {str(k): v for k, v in model.items()}
        children.append(_Child(combo, plain, config_sha256(plain)))
    return children


def _eval_part(cfg: DictConfig, on: Partition) -> tuple[list[Row], list[float], dict[str, str]]:
    try:
        partitions = [Partition(p) for p in cfg.data.partitions]
        rows = read_rows(Path(cfg.paths.data_file))
    except ValueError as err:
        raise PrepareError(str(err)) from err
    if on not in partitions:
        raise PrepareError(f"data.score_on {on.value!r} is not in data.partitions {[p.value for p in partitions]}")
    folder = Path(cfg.paths.experiment_dir)
    eval_rows = load_split(folder, partitions, rows=rows)[on]
    if not eval_rows:
        raise PrepareError(f"the {on.value} partition is empty: nothing to score")
    try:
        labels = [label(row, str(cfg.data.target)) for row in eval_rows]
    except (KeyError, TypeError, ValueError) as err:
        raise PrepareError(f"data.target {cfg.data.target!r} is missing or not numeric in a row: {err!r}") from err
    tags = {
        Tag.SPLIT_SHA256.value: split_sha256(folder / "split.json"),
        Tag.DATA_SHA256.value: file_sha256(Path(cfg.paths.data_file)),
    }
    return eval_rows, labels, tags


def _prepare(cfg: DictConfig, overrides: Sequence[str]) -> _Plan:
    project = load(PROJECT_DIR)  # (1)
    metric = card_metric(project.root)
    sub = str(cfg.experiment.name)  # (2)
    experiment_name(project.name, sub)
    if sub == "audit":
        raise PrepareError("experiment.name 'audit' is reserved for eval")
    resolved = resolve_config(cfg)  # (3)
    on = frozen_score_on(cfg)  # (4) before anything is composed: the ledger's split and data must be unchanged
    candidates = _candidates(cfg)  # (5)
    children = _children(resolved, overrides, candidates)
    eval_rows, labels, tags = _eval_part(cfg, on)  # (6)
    parent_tags = {Tag.ENTRY.value: "train", Tag.SCORE_ON.value: on.value, **tags}
    return _Plan(project, metric, sub, resolved, candidates, on, children, eval_rows, labels, parent_tags)


def _run_child(plan: _Plan, child: _Child) -> bool:
    combo = child.combo
    try:
        with tracked_trial(combo.run_name, {Tag.CONFIG_SHA256.value: child.config_sha}, candidate=combo.candidate):
            if combo.params:
                mlflow.log_params(dict(combo.params))
            model = instantiate(child.model)
            mlflow.log_metric(plan.metric.key, score([model.predict(r) for r in plan.eval_rows], plan.labels))
    except (MlflowException, TrackingUnavailable):
        raise
    except Exception as err:  # isolation boundary: one candidate's failure must not stop the others
        print(f"candidate {combo.run_name} failed: {err!r}", file=sys.stderr)
        return False
    return True


def _key_problems(plan: _Plan, parent_id: str) -> list[str]:
    client = MlflowClient()
    experiment_id = client.get_run(parent_id).info.experiment_id
    found = client.search_runs([experiment_id], filter_string=f"tags.mlflow.parentRunId = '{parent_id}'")
    keys = {r.info.run_name or r.info.run_id: frozenset(r.data.metrics) for r in found if r.info.status == "FINISHED"}
    # resolve_config yields plain containers and the experiment group is validated at compose time
    experiment = cast("dict[str, list[object]]", plan.resolved["experiment"])
    allowed = [str(k) for k in experiment["metrics"]]
    return metric_key_problems(keys, plan.metric.key, allowed, plan.candidates)


def _execute(plan: _Plan, settings: Settings) -> int:
    params = {"experiment": plan.sub, "candidates": ",".join(plan.candidates), "score_on": plan.on.value}
    params |= {"seed": plan.resolved["seed"], "n_combos": len(plan.children)}
    with tracked_run(plan.project, settings, plan.sub, sub=plan.sub, tags=plan.parent_tags) as parent_id:
        mlflow.log_params(params)
        mlflow.log_dict(plan.resolved, "config.yaml")
        failed = [c.combo.run_name for c in plan.children if not _run_child(plan, c)]
    problems = _key_problems(plan, parent_id)
    for problem in problems:
        print(f"train: {problem}", file=sys.stderr)
    return 1 if problems or failed else 0


def run(cfg: DictConfig, overrides: Sequence[str] = ()) -> int:
    try:
        plan = _prepare(cfg, overrides)
    except _REFUSALS as err:
        print(f"train: {err}", file=sys.stderr)
        return 2
    try:
        settings = Settings()
    except ValueError as err:
        print(f"train: invalid DATALAB_* settings: {err}", file=sys.stderr)
        return 1
    try:
        preflight(settings.mlflow_tracking_uri)
        return _execute(plan, settings)
    except (MlflowException, TrackingUnavailable) as err:
        print(f"tracking failed: {err}", file=sys.stderr)
        return 1


@hydra.main(version_base=None, config_path="../../configs", config_name="train")
def main(cfg: DictConfig) -> None:
    refuse_multirun("train")
    code = run(cfg, tuple(HydraConfig.get().overrides.task))
    if code:
        raise SystemExit(code)


if __name__ == "__main__":
    main()
