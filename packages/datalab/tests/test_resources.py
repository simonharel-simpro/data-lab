import shutil
import subprocess
import zipfile
from pathlib import Path

import pytest

from datalab import resources
from datalab.project import ProjectError
from tests.conftest import REPO_ROOT

SRC = Path(__file__).resolve().parents[1] / "src" / "datalab"


def _no_checkout(monkeypatch: pytest.MonkeyPatch, package: Path) -> None:
    def raise_error() -> Path:
        raise ProjectError("no checkout")

    monkeypatch.setattr(resources, "repo_root", raise_error)
    monkeypatch.setattr(resources, "files", lambda _name: package)


def test_f7_editable_prefers_checkout() -> None:
    assert resources.contract_path("milestones.json") == REPO_ROOT / "contracts" / "milestones.json"


def test_f7_wheel_layout_uses_package_data(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "contracts").mkdir()
    (tmp_path / "contracts" / "milestones.json").write_text("{}", encoding="utf-8")
    _no_checkout(monkeypatch, tmp_path)

    assert resources.contract_path("milestones.json") == tmp_path / "contracts" / "milestones.json"


def test_f7_missing_file_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "contracts").mkdir()
    (tmp_path / "contracts" / "milestones.json").write_text("{}", encoding="utf-8")
    _no_checkout(monkeypatch, tmp_path)

    with pytest.raises(ProjectError, match="contracts"):
        resources.contract_path("value_sets.json")


def test_wheel_layout_template_and_ruff(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "template").mkdir()
    (tmp_path / "ruff.toml").write_text("", encoding="utf-8")
    _no_checkout(monkeypatch, tmp_path)

    assert resources.template_dir() == tmp_path / "template"
    assert resources.ruff_toml() == tmp_path / "ruff.toml"


def test_missing_ruff_toml_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _no_checkout(monkeypatch, tmp_path)

    with pytest.raises(ProjectError, match=r"ruff\.toml"):
        resources.ruff_toml()


def test_u5_source_tree_has_no_packaged_copies() -> None:
    assert not (SRC / "contracts").exists()
    assert not (SRC / "template").exists()


def test_u10_resources_cli(capsys: pytest.CaptureFixture[str]) -> None:
    assert resources.main(["milestones.json"]) == 0
    out = capsys.readouterr().out.strip()
    assert Path(out).is_absolute()
    assert Path(out).is_file()

    for bad in ("../x", "nope"):
        assert resources.main([bad]) == 2
        assert "milestones.json" in capsys.readouterr().err


@pytest.mark.scaffold
def test_u6_wheel_matches_git_ls_files(tmp_path: Path) -> None:
    uv = shutil.which("uv")
    assert uv is not None, "uv is not on PATH"
    out = tmp_path / "dist"
    build = subprocess.run(  # noqa: S603  # fixed argv: uv from shutil.which, no shell
        [uv, "build", "--wheel", "--out-dir", str(out), str(REPO_ROOT / "packages" / "datalab")],
        capture_output=True,
        text=True,
        check=False,
        timeout=600,
    )
    assert build.returncode == 0, build.stderr
    with zipfile.ZipFile(next(out.glob("*.whl"))) as wheel:
        names = set(wheel.namelist())
    assert _tracked("templates/project", "datalab/template/") == _packaged(names, "datalab/template/")
    assert _tracked("contracts", "datalab/contracts/") == _packaged(names, "datalab/contracts/")
    assert "datalab/ruff.toml" in names


def _tracked(folder: str, prefix: str) -> set[str]:
    git = shutil.which("git")
    assert git is not None, "git is not on PATH"
    listing = subprocess.run(  # noqa: S603  # fixed argv, no shell
        [git, "ls-files", folder], cwd=REPO_ROOT, capture_output=True, text=True, check=True
    ).stdout.split()
    return {prefix + path.removeprefix(folder + "/") for path in listing}


def _packaged(names: set[str], prefix: str) -> set[str]:
    return {n for n in names if n.startswith(prefix)}
