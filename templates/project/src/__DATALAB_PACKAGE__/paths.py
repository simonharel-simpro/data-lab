"""Where the project lives, and the `${project_dir:}` resolver the configs use (F-10)."""

from pathlib import Path
from typing import Final

from omegaconf import OmegaConf

PROJECT_DIR: Final[Path] = Path(__file__).resolve().parents[2]
AUDIT_EXPERIMENT: Final = "audit"  # reserved MLflow sub-experiment: eval writes it, train refuses it


def register_resolvers() -> None:
    OmegaConf.register_new_resolver("project_dir", lambda: str(PROJECT_DIR), replace=True)
