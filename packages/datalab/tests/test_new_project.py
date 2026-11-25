import os
import re
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest
import yaml

from datalab import ledger, new_project
from datalab.new_project import main
from datalab.project import ProjectError, load
from tests.conftest import REPO_ROOT
from tests.ledger_support import ledger as vector_ledger


def _no_lock(project: Path) -> None:
    (project / "uv.lock").write_text("# fake lock\n", encoding="utf-8")


def _tree(root: Path) -> list[str]:
    return sorted(str(p.relative_to(root)) for p in root.rglob("*"))


def _frontmatter(card: Path) -> dict[str, object]:
    return yaml.safe_load(card.read_text(encoding="utf-8").split("---\n")[1])


def test_g_7_title_with_yaml_specials(fake_repo: Path) -> None:
    assert main(["demo", "--title", "RAG: v2 # b"], root=fake_repo, lock=_no_lock) == 0

    assert _frontmatter(fake_repo / "projects" / "demo" / "PROJECT.md")["title"] == "RAG: v2 # b"


def test_title_defaults_to_name(fake_repo: Path) -> None:
    assert main(["demo"], root=fake_repo, lock=_no_lock) == 0

    assert _frontmatter(fake_repo / "projects" / "demo" / "PROJECT.md")["title"] == "demo"


def test_g_12_package_name_prefixed(fake_repo: Path) -> None:
    assert main(["demo"], root=fake_repo, lock=_no_lock) == 0

    pyproject = tomllib.loads((fake_repo / "projects" / "demo" / "pyproject.toml").read_text(encoding="utf-8"))
    assert pyproject["project"]["name"] == "proj-demo"
    assert (fake_repo / "projects" / "demo" / ".python-version").read_text(encoding="utf-8").strip() == "3.12"
    assert pyproject["tool"]["coverage"]["report"]["fail_under"] == 70


def test_u_10_new_project_excludes_venv_and_lock(fake_repo: Path) -> None:
    assert main(["demo"], root=fake_repo, lock=lambda project: None) == 0  # writes no uv.lock: tests the copy filter

    out = fake_repo / "projects" / "demo"
    assert not (out / ".venv").exists()
    assert not (out / ".env").exists()
    assert not (out / "uv.lock").exists()
    assert (out / ".env.example").is_file()


def test_u_10_no_placeholder_left(fake_repo: Path) -> None:
    assert main(["demo-app"], root=fake_repo, lock=_no_lock) == 0

    out = fake_repo / "projects" / "demo-app"
    leftovers = [p for p in out.rglob("*") if p.is_file() and "__DATALAB_" in p.read_text(encoding="utf-8")]
    assert leftovers == []
    assert [str(p.relative_to(out)) for p in out.rglob("*") if "__DATALAB_" in str(p.relative_to(out))] == []
    assert (out / "src" / "demo_app" / "train.py").is_file()
    assert load(out, root=fake_repo).name == "demo-app"


def test_u_25_package_name_refusals_write_nothing(fake_repo: Path) -> None:
    wiring = (".pre-commit-config.yaml", ".github/workflows/ci.yml")
    before = {rel: (fake_repo / rel).read_bytes() for rel in wiring}

    codes = [main([name], root=fake_repo, lock=_no_lock) for name in ("class", "json", "hydra", "mlflow")]

    assert codes == [2, 2, 2, 2]
    assert _projects_entries(fake_repo) == []
    assert {rel: (fake_repo / rel).read_bytes() for rel in wiring} == before


def test_importlinter_root_is_the_package(fake_repo: Path) -> None:
    assert main(["demo-app"], root=fake_repo, lock=_no_lock) == 0

    pyproject = tomllib.loads((fake_repo / "projects" / "demo-app" / "pyproject.toml").read_text(encoding="utf-8"))
    assert pyproject["tool"]["importlinter"]["root_package"] == "demo_app"
    sources = pyproject["tool"]["importlinter"]["contracts"][0]["source_modules"]
    assert sources == ["demo_app.scoring", "demo_app.candidates", "demo_app.grid"]


@pytest.mark.parametrize("kind", ["empty-dir", "file"])
def test_u_10_refuses_existing_empty_dir_and_writes_nothing(fake_repo: Path, kind: str) -> None:
    target = fake_repo / "projects" / "x"
    if kind == "empty-dir":
        target.mkdir()
    else:
        target.write_text("", encoding="utf-8")
    before = _tree(fake_repo)

    assert main(["x"], root=fake_repo, lock=_no_lock) == 2

    assert _tree(fake_repo) == before


def test_f_8_failed_copy_leaves_no_project_dir(fake_repo: Path) -> None:
    stray = fake_repo / "templates" / "project" / "README.md"
    original = stray.read_text(encoding="utf-8")
    stray.write_text(original + "\n__DATALAB_UNKNOWN__\n", encoding="utf-8")

    assert main(["x"], root=fake_repo, lock=_no_lock) == 1
    assert sorted(p.name for p in (fake_repo / "projects").iterdir()) == []  # neither `x` nor `.x.tmp-*`

    stray.write_text(original, encoding="utf-8")
    assert main(["x"], root=fake_repo, lock=_no_lock) == 0
    assert (fake_repo / "projects" / "x" / "PROJECT.md").is_file()


def test_binary_template_file_is_copied_unchanged(fake_repo: Path) -> None:
    payload = b"\xff\xfe\x00"
    (fake_repo / "templates" / "project" / "blob.bin").write_bytes(payload)

    assert main(["demo"], root=fake_repo, lock=_no_lock) == 0

    assert (fake_repo / "projects" / "demo" / "blob.bin").read_bytes() == payload


def test_f_3_reserved_names_rejected(fake_repo: Path) -> None:
    assert main(["test"], root=fake_repo, lock=_no_lock) == 2
    assert main(["../escape"], root=fake_repo, lock=_no_lock) == 2

    assert sorted(p.name for p in (fake_repo / "projects").iterdir()) == []
    assert not (fake_repo / "escape").exists()


def test_missing_template_exits_1(fake_repo: Path) -> None:
    shutil.rmtree(fake_repo / "templates")

    assert main(["demo"], root=fake_repo, lock=_no_lock) == 1
    assert not (fake_repo / "projects" / "demo").exists()


@pytest.mark.integration
def test_b1_package_added_after_first_sync_imports(fake_repo: Path) -> None:
    uv = shutil.which("uv")
    if uv is None:
        pytest.skip("uv is not on PATH")
    real_pkg = REPO_ROOT / "packages" / "datalab"
    shutil.rmtree(fake_repo / "packages" / "datalab")
    ignore = shutil.ignore_patterns(".venv", "__pycache__", ".pytest_cache", ".ruff_cache", ".coverage", "uv.lock")
    shutil.copytree(real_pkg, fake_repo / "packages" / "datalab", ignore=ignore)
    assert main(["demo"], root=fake_repo, lock=_no_lock) == 0
    project = fake_repo / "projects" / "demo"
    env = {k: v for k, v in os.environ.items() if k not in {"VIRTUAL_ENV", "UV_PROJECT_ENVIRONMENT"}}

    def run(*args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(  # noqa: S603  # fixed argv: absolute uv binary, no shell
            [uv, *args], cwd=project, env=env, capture_output=True, text=True, check=False, timeout=600
        )

    synced = run("sync", "--offline")
    assert synced.returncode == 0, synced.stderr
    (project / "src" / "demo_pkg").mkdir()
    (project / "src" / "demo_pkg" / "__init__.py").write_text("", encoding="utf-8")

    imported = run("run", "--offline", "python", "-c", "import demo_pkg, datalab.project")
    assert imported.returncode == 0, imported.stderr


def test_template_dev_deps_are_exact_pins() -> None:
    pyproject = tomllib.loads((REPO_ROOT / "templates" / "project" / "pyproject.toml").read_text(encoding="utf-8"))

    dev = pyproject["dependency-groups"]["dev"]

    unpinned = [dep for dep in dev if not re.fullmatch(r"[A-Za-z0-9_.-]+==[0-9][^,;<>~!]*", dep)]
    assert dev
    assert unpinned == []


def _projects_entries(fake_repo: Path) -> list[str]:
    return sorted(p.name for p in (fake_repo / "projects").iterdir())


def test_scaffold_writes_the_lock_before_publishing(fake_repo: Path) -> None:
    seen: list[tuple[str, bool]] = []

    def lock(project: Path) -> None:
        seen.append((project.name, (fake_repo / "projects" / "x").exists()))
        _no_lock(project)

    assert main(["x"], root=fake_repo, lock=lock) == 0

    assert len(seen) == 1
    assert seen[0][0].startswith(".x.tmp-")
    assert seen[0][1] is False
    assert (fake_repo / "projects" / "x" / "uv.lock").is_file()


def test_lock_failure_leaves_no_project_dir(fake_repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    def lock(project: Path) -> None:
        raise ProjectError("resolver: no network")

    assert main(["x"], root=fake_repo, lock=lock) == 1

    assert "no network" in capsys.readouterr().err
    assert _projects_entries(fake_repo) == []


def test_uv_missing_is_reported(
    fake_repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(new_project.shutil, "which", lambda _cmd: None)

    assert main(["x"], root=fake_repo) == 1

    assert "uv not found" in capsys.readouterr().err
    assert _projects_entries(fake_repo) == []


@pytest.mark.skipif(sys.platform == "win32", reason="platform-conditional (#8): the uv stub is a #!/bin/sh executable")
def test_uv_lock_nonzero_exit_is_reported(
    fake_repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    stub = tmp_path / "uv"
    stub.write_text("#!/bin/sh\necho boom >&2\nexit 3\n", encoding="utf-8")
    stub.chmod(0o755)
    monkeypatch.setattr(new_project.shutil, "which", lambda _cmd: str(stub))

    assert main(["x"], root=fake_repo) == 1

    assert "boom" in capsys.readouterr().err
    assert _projects_entries(fake_repo) == []


def test_scaffold_ships_gitattributes(fake_repo: Path) -> None:
    assert main(["demo"], root=fake_repo, lock=_no_lock) == 0

    text = (fake_repo / "projects" / "demo" / ".gitattributes").read_text(encoding="utf-8")
    assert "split.json -text" in text
    assert "data/** -text" in text


def test_gitattributes_pins_hashed_files() -> None:
    git = shutil.which("git")
    assert git is not None
    result = subprocess.run(  # noqa: S603  # fixed argv: git from shutil.which, no shell
        [git, "check-attr", "text", "--", "projects/mini-rag/split.json", "projects/voice-arch/data/x.jsonl"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )

    lines = result.stdout.splitlines()
    assert len(lines) == 2
    assert all(line.endswith(": text: unset") for line in lines)


def test_crlf_split_mismatch_names_line_endings() -> None:
    audit = vector_ledger("audit-first-look")

    assert "line-ending" in str(ledger.test_access_problem(audit, "0" * 64, None))
