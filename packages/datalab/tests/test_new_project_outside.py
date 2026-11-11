import re
import sys
from pathlib import Path

import pytest

from datalab import new_project, wiring
from datalab.new_project import DATALAB_GIT_URL, main
from datalab.project import ProjectError
from tests.conftest import REPO_ROOT

SOURCE_LINE = (
    'datalab = { git = "https://github.com/simonharel-simpro/data-lab", subdirectory = "packages/datalab", '
    'branch = "main" }'
)
BOOTSTRAP = (
    'uvx --refresh --from "git+https://github.com/simonharel-simpro/data-lab#subdirectory=packages/datalab" datalab-new'
)


def _no_lock(project: Path) -> None:
    (project / "uv.lock").write_text("# fake lock\n", encoding="utf-8")


def _readme_new_project() -> str:
    text = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    return text.split("## New project")[1].split("\n## ")[0]


def test_f4_outside_scaffold_never_touches_user_ci(workspace: Path, capsys: pytest.CaptureFixture[str]) -> None:
    own = {".pre-commit-config.yaml": b"repos: []\n", ".github/workflows/ci.yml": b"name: mine\n"}
    for rel, data in own.items():
        (workspace / rel).parent.mkdir(parents=True, exist_ok=True)
        (workspace / rel).write_bytes(data)

    assert main(["demo"], root=workspace, lock=_no_lock) == 0

    assert {rel: (workspace / rel).read_bytes() for rel in own} == own
    assert "#48" in capsys.readouterr().out


def test_f4_outside_without_ci_files_succeeds(workspace: Path) -> None:
    assert main(["demo"], root=workspace, lock=_no_lock) == 0

    assert (workspace / "projects" / "demo" / "pyproject.toml").is_file()


def test_f2_outside_source_follows_main(workspace: Path) -> None:
    assert main(["demo"], root=workspace, lock=_no_lock) == 0

    lines = (workspace / "projects" / "demo" / "pyproject.toml").read_text(encoding="utf-8").splitlines()
    assert SOURCE_LINE in lines
    src = REPO_ROOT / "packages" / "datalab" / "src" / "datalab"
    hits = sum(p.read_text(encoding="utf-8").count(DATALAB_GIT_URL) for p in src.glob("*.py"))
    assert hits == 1  # the constant itself: every other use goes through the name
    assert DATALAB_GIT_URL == "https://github.com/simonharel-simpro/data-lab"


def test_u18_outside_creates_projects_dir(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "datalab.toml").write_text("", encoding="utf-8")

    assert main(["demo"], root=ws, lock=_no_lock) == 0

    assert (ws / "projects" / "demo" / "PROJECT.md").is_file()


def test_u1_inside_decided_by_workspace_not_install(
    workspace: Path, fake_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    planned: list[str] = []
    real_plan = wiring.plan

    def spy(root: Path, name: str) -> wiring.WiringPlan:
        planned.append(name)
        return real_plan(root, name)

    monkeypatch.setattr(new_project.wiring, "plan", spy)

    assert main(["demo"], root=workspace, lock=_no_lock) == 0
    outside = (workspace / "projects" / "demo" / "pyproject.toml").read_text(encoding="utf-8")
    assert SOURCE_LINE in outside
    assert (workspace / "ruff.toml").is_file()
    assert planned == []

    assert main(["demo"], root=fake_repo, lock=_no_lock) == 0
    inside = (fake_repo / "projects" / "demo" / "pyproject.toml").read_text(encoding="utf-8")
    assert 'datalab = { path = "../../packages/datalab", editable = true }' in inside
    assert planned == ["demo"]
    assert not (fake_repo / "ruff.toml").exists()


def test_f10_failed_lock_leaves_no_ruff_toml(workspace: Path) -> None:
    def lock(project: Path) -> None:
        raise ProjectError("resolver: boom")

    assert main(["demo"], root=workspace, lock=lock) == 1

    assert not (workspace / "ruff.toml").exists()
    assert sorted(p.name for p in (workspace / "projects").iterdir()) == []


def test_f10_existing_ruff_toml_untouched(workspace: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (workspace / "ruff.toml").write_text("x = 1\n", encoding="utf-8")

    assert main(["demo"], root=workspace, lock=_no_lock) == 0

    assert (workspace / "ruff.toml").read_text(encoding="utf-8") == "x = 1\n"
    assert "kept existing" in capsys.readouterr().out


def test_f10_missing_packaged_ruff_writes_nothing(workspace: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def missing() -> Path:
        raise ProjectError("datalab resources: ruff.toml does not exist")

    monkeypatch.setattr(new_project, "ruff_toml", missing)

    assert main(["demo"], root=workspace, lock=_no_lock) == 1

    assert not (workspace / "ruff.toml").exists()
    assert sorted(p.name for p in (workspace / "projects").iterdir()) == []


def test_f10_ruff_write_failure_reports_created_project(
    workspace: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def read_only_workspace(*_args: object, **_kwargs: object) -> None:
        raise PermissionError("read-only workspace")

    # shadows the builtin inside new_project only: its sole open() call is the workspace ruff.toml write
    monkeypatch.setattr(new_project, "open", read_only_workspace, raising=False)

    assert main(["demo"], root=workspace, lock=_no_lock) == 1

    assert (workspace / "projects" / "demo" / "PROJECT.md").exists()
    assert "project created but" in capsys.readouterr().err


def test_f5_success_message_names_workspace(workspace: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["demo"], root=workspace, lock=_no_lock) == 0

    assert f"in workspace {workspace}" in capsys.readouterr().out


def _fake_uv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, body: str) -> None:
    stub = tmp_path / "uv"
    stub.write_text(f"#!/bin/sh\n{body}\n", encoding="utf-8")
    stub.chmod(0o755)
    monkeypatch.setattr(new_project.shutil, "which", lambda _cmd: str(stub))


@pytest.mark.skipif(sys.platform == "win32", reason="platform-conditional (#8): the uv stub is a #!/bin/sh executable")
def test_f1_uv_lock_runs_non_interactive(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    dump = tmp_path / "dump.txt"
    _fake_uv(tmp_path, monkeypatch, f'echo "$GIT_TERMINAL_PROMPT $GCM_INTERACTIVE" > {dump}; cat >> {dump}')
    project = tmp_path / "p"
    project.mkdir()

    new_project._uv_lock(project)

    assert dump.read_text(encoding="utf-8") == "0 never\n"


@pytest.mark.skipif(sys.platform == "win32", reason="platform-conditional (#8): the uv stub is a #!/bin/sh executable")
def test_f1_auth_failure_is_classified(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_uv(tmp_path, monkeypatch, "echo 'fatal: could not read Username' >&2; exit 1")
    project = tmp_path / "p"
    project.mkdir()

    with pytest.raises(ProjectError) as raised:
        new_project._uv_lock(project)

    assert DATALAB_GIT_URL in str(raised.value)
    assert "gh auth setup-git" in str(raised.value)


def test_f3_readme_has_outside_bootstrap() -> None:
    assert BOOTSTRAP in (REPO_ROOT / "README.md").read_text(encoding="utf-8")


def test_u11_upgrade_command_matches_source_form() -> None:
    assert "uv lock --upgrade-package datalab" in (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    assert "branch =" in SOURCE_LINE
    assert "rev =" not in SOURCE_LINE


def test_u14_template_gitignore_covers_python_patterns() -> None:
    lines = (REPO_ROOT / "templates" / "project" / ".gitignore").read_text(encoding="utf-8").splitlines()

    wanted = {".venv/", "__pycache__/", ".env", ".coverage", "*.json.tmp", ".pytest_cache/", ".ruff_cache/"}
    assert wanted <= set(lines)


def test_u15_readme_states_unique_names() -> None:
    section = _readme_new_project()

    assert re.search(r"unique per stack", section)
    assert "#50" in section


def test_u16_readme_documents_projects_dir() -> None:
    assert "DATALAB_PROJECTS_DIR" in _readme_new_project()


def test_u19_readme_inside_uses_editable_form() -> None:
    assert "uv run --project packages/datalab datalab-new" in _readme_new_project()
