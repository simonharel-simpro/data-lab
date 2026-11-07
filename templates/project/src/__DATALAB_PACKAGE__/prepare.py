"""Everything train and eval check before they open an MLflow run: composition, ledger, hashes (F-11, F-21)."""

import hashlib
import re
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Final

import hydra
from hydra.core.hydra_config import HydraConfig
from hydra.errors import HydraException
from hydra.types import RunMode
from omegaconf import DictConfig, OmegaConf
from omegaconf.errors import OmegaConfBaseException

from datalab import ledger
from datalab.ledger import Kind, LedgerError, RunLedger
from datalab.split import Partition

_MODEL_CHOICE: Final = re.compile(r"^[~+]*model=")


class PrepareError(ValueError):
    """A refusal before any run: the message says what to fix (the entry point exits 2)."""


def resolve_config(cfg: DictConfig) -> dict[str, object]:
    try:
        resolved = OmegaConf.to_container(cfg, resolve=True, throw_on_missing=True)
    except OmegaConfBaseException as err:
        raise PrepareError(f"config does not resolve: {err}") from err
    if not isinstance(resolved, dict):
        raise PrepareError("config is not a mapping")
    return {str(k): v for k, v in resolved.items()}


def compose_model(config_name: str, overrides: Sequence[str], candidate: str) -> DictConfig:
    """The `model` node of `candidate`: the user's own `model=` choice never leaks into another candidate."""
    kept = [o for o in overrides if not _MODEL_CHOICE.match(o)]
    try:
        cfg = hydra.compose(config_name, [*kept, f"model={candidate}"])
        resolved = OmegaConf.to_container(cfg.model, resolve=True, throw_on_missing=True)
        node = OmegaConf.create(resolved)
        if not isinstance(node, DictConfig):
            raise PrepareError(f"model {candidate!r} is not a mapping")
        OmegaConf.set_struct(node, True)  # a grid key the model does not have must fail, not be added
        hydra.utils.get_object(str(node["_target_"]))
    except (HydraException, OmegaConfBaseException, ImportError, AttributeError) as err:
        raise PrepareError(f"model {candidate!r} cannot be built: {err}") from err
    return node


def read_ledger(experiment_dir: Path) -> RunLedger | None:
    if not (experiment_dir / ledger.RUN_JSON).exists():
        return None
    try:
        return ledger.read(experiment_dir)
    except LedgerError as err:
        raise PrepareError(str(err)) from err


def score_on(cfg: DictConfig, lg: RunLedger | None) -> Partition:
    """Explicit `data.score_on` wins; else train for a comparison ledger (nothing to tune on), else val (U-30)."""
    chosen = cfg.data.score_on
    if chosen is None:
        return Partition.TRAIN if lg is not None and lg.kind is Kind.COMPARISON else Partition.VAL
    try:
        return Partition(chosen)
    except ValueError as err:
        raise PrepareError(f"data.score_on must be one of {[p.value for p in Partition]}, got {chosen!r}") from err


def file_sha256(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def refuse_multirun(program: str) -> None:
    if HydraConfig.get().mode == RunMode.MULTIRUN:
        print(
            f"{program}: --multirun is not supported: list candidates and an hparams_search grid instead (D-4)",
            file=sys.stderr,
        )
        raise SystemExit(2)
