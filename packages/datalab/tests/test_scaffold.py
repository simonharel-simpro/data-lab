import importlib.util
import os
import shutil
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

from datalab.new_project import main
from tests.conftest import REPO_ROOT

_COPY_IGNORE = shutil.ignore_patterns(
    ".venv", "__pycache__", ".pytest_cache", ".ruff_cache", ".coverage", "uv.lock", "weavit-ui", "node_modules"
)


def _hydra_gate(tools: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location("hydra_gate_scaffold", tools / "pre_commit_checks" / "hydra_gate.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _build_repo(fake_repo: Path) -> None:
    """The fake repo gets the real package, tools, contracts and ruff config the generated project reaches for."""
    shutil.rmtree(fake_repo / "packages" / "datalab")
    shutil.copytree(REPO_ROOT / "packages" / "datalab", fake_repo / "packages" / "datalab", ignore=_COPY_IGNORE)
    for name in ("tools", "contracts"):
        shutil.copytree(REPO_ROOT / name, fake_repo / name, ignore=_COPY_IGNORE)
    shutil.copyfile(REPO_ROOT / "ruff.toml", fake_repo / "ruff.toml")


def _failures(project: Path, uv: str) -> list[str]:
    env = {k: v for k, v in os.environ.items() if k not in {"VIRTUAL_ENV", "UV_PROJECT_ENVIRONMENT"}}
    check_deps = "../../tools/pre_commit_checks/check_declared_dependencies.py"
    commands = [
        [uv, "sync", "--locked"],
        [uv, "run", "--locked", "lint-imports"],
        [uv, "run", "--locked", "pyright"],
        [uv, "run", "--locked", "pytest", "-q", "--cov"],
        [uv, "run", "--locked", "pip-audit"],
        [uv, "run", "--locked", "python", check_deps],
        [uv, "run", "--locked", "ruff", "check", "."],
        [uv, "run", "--locked", "ruff", "format", "--check", "."],
    ]
    failed = []
    for command in commands:
        done = subprocess.run(  # noqa: S603  # fixed argv: uv from shutil.which, no shell
            command, cwd=project, env=env, capture_output=True, text=True, check=False, timeout=900
        )
        if done.returncode != 0:
            failed.append(f"{' '.join(command[1:])} -> {done.returncode}\n{done.stdout[-1500:]}\n{done.stderr[-1500:]}")
    return failed


@pytest.mark.scaffold
def test_f_3_scaffolded_project_passes_its_gates(fake_repo: Path, capfd: pytest.CaptureFixture[str]) -> None:
    uv = shutil.which("uv")
    assert uv is not None, "uv is not on PATH"
    _build_repo(fake_repo)

    assert main(["ci-scaffold"], root=fake_repo) == 0  # the real `uv lock`: needs the network

    project = fake_repo / "projects" / "ci-scaffold"
    assert _failures(project, uv) == []
    sources = sorted(str(p.relative_to(fake_repo)) for p in (project / "src" / "ci_scaffold").glob("*.py"))
    size = subprocess.run(  # noqa: S603  # fixed argv: this interpreter + the repo's script + repo-relative paths
        [sys.executable, "tools/check_file_size.py", *sources],
        cwd=fake_repo,
        capture_output=True,
        text=True,
        check=False,
    )
    assert size.returncode == 0, size.stderr
    capfd.readouterr()
    assert _hydra_gate(fake_repo / "tools").main(["projects/ci-scaffold"], repo_root=fake_repo) == 0
    assert "hydra-gate projects/ci-scaffold" in capfd.readouterr().out
