"""Shared builders of the tracking tests."""

from pathlib import Path

from datalab.project import Project
from datalab.settings import Settings


def make_project(tmp_path: Path) -> Project:
    return Project(name="p", root=tmp_path)


def make_settings(sqlite_uri: str) -> Settings:
    return Settings(_env_file=None, mlflow_tracking_uri=sqlite_uri)  # type: ignore[call-arg]  # pydantic-settings init kwarg
