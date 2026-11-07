import json
import re
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from datalab import ledger, wiring
from datalab.new_project import main
from datalab.project import ProjectError
from datalab.wiring import CI, PRE_COMMIT, apply, declared_deps_block, gates_block, plan
from datalab.wiring_parity import parity_problems
from tests.conftest import REPO_ROOT
from tests.ledger_support import project, vector
from tests.test_new_project import _no_lock


def _hook_ids(root: Path) -> set[str]:
    config = yaml.safe_load((root / PRE_COMMIT).read_text(encoding="utf-8"))
    return {hook["id"] for repo in config["repos"] for hook in repo["hooks"]}


def _hook(root: Path, hook_id: str) -> dict[str, str]:
    config = yaml.safe_load((root / PRE_COMMIT).read_text(encoding="utf-8"))
    return next(hook for repo in config["repos"] for hook in repo["hooks"] if hook["id"] == hook_id)


def _matrix(root: Path) -> list[str]:
    return yaml.safe_load((root / CI).read_text(encoding="utf-8"))["jobs"]["projects"]["strategy"]["matrix"]["project"]


def _block_text(text: str, hook_id: str) -> str:
    pattern = rf"^ {{6}}- id: {re.escape(hook_id)}\n.*?(?=^ {{6}}- id: |^ {{6}}# <<< )"
    found = re.search(pattern, text, re.DOTALL | re.MULTILINE)
    assert found is not None
    return found.group(0)


def test_u_8_new_project_passes_parity_test(wired_repo: Path) -> None:
    assert parity_problems(wired_repo) == []

    assert main(["demo"], root=wired_repo, lock=_no_lock) == 0

    assert parity_problems(wired_repo) == []
    assert {"declared-deps-demo", "gates-demo"} <= _hook_ids(wired_repo)
    assert _matrix(wired_repo) == ["demo", "mini-rag", "voice-arch"]


def test_blocks_reproduce_voice_arch_stanzas_byte_for_byte() -> None:
    text = (REPO_ROOT / PRE_COMMIT).read_text(encoding="utf-8")

    assert _block_text(text, "declared-deps-voice-arch") == declared_deps_block("voice-arch")
    assert _block_text(text, "gates-voice-arch") == gates_block("voice-arch")


def test_wiring_is_idempotent(wired_repo: Path) -> None:
    apply(plan(wired_repo, "demo"))
    first = ((wired_repo / PRE_COMMIT).read_bytes(), (wired_repo / CI).read_bytes())

    again = plan(wired_repo, "demo")
    apply(again)

    assert again.writes == ()
    assert ((wired_repo / PRE_COMMIT).read_bytes(), (wired_repo / CI).read_bytes()) == first


def test_wiring_keeps_comments(wired_repo: Path) -> None:
    apply(plan(wired_repo, "demo"))

    text = (wired_repo / PRE_COMMIT).read_text(encoding="utf-8")
    assert "# CI: this hook scans staged files only; ci.yml runs a full-history scan" in text


def test_missing_marker_writes_nothing(wired_repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    pre_commit = wired_repo / PRE_COMMIT
    marker = re.compile(r"^ *# >>> datalab-new: gates\n", re.MULTILINE)
    pre_commit.write_text(marker.sub("", pre_commit.read_text("utf-8")), encoding="utf-8")
    before = (pre_commit.read_bytes(), (wired_repo / CI).read_bytes())

    assert main(["demo"], root=wired_repo, lock=_no_lock) == 1

    assert not (wired_repo / "projects" / "demo").exists()
    assert (pre_commit.read_bytes(), (wired_repo / CI).read_bytes()) == before
    assert "datalab-new: gates" in capsys.readouterr().err


def test_wiring_failure_after_publish_is_reported(wired_repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    with patch.object(wiring, "apply", side_effect=OSError("disk")):
        assert main(["demo"], root=wired_repo, lock=_no_lock) == 1

    assert (wired_repo / "projects" / "demo").is_dir()
    assert "hook/CI wiring failed: disk" in capsys.readouterr().err


def test_parity_reports_unwired_project(wired_repo: Path) -> None:
    (wired_repo / "projects" / "ghost").mkdir()
    (wired_repo / "projects" / "ghost" / "pyproject.toml").write_text("[project]\n", encoding="utf-8")

    problems = "\n".join(parity_problems(wired_repo))

    assert "declared-deps-ghost" in problems
    assert "gates-ghost" in problems
    assert "project ghost is missing from jobs.projects.strategy.matrix.project" in problems


@pytest.mark.parametrize(
    ("needle", "replacement", "mention"),
    [
        ("python -m datalab.ledger validate", "echo", "datalab.ledger validate"),
        ("hydra_gate.py", "other.py", "hydra_gate.py"),
    ],
)
def test_parity_reports_missing_gate_steps(wired_repo: Path, needle: str, replacement: str, mention: str) -> None:
    ci = wired_repo / CI
    ci.write_text(ci.read_text("utf-8").replace(needle, replacement), encoding="utf-8")

    problems = parity_problems(wired_repo)

    assert len(problems) == 1
    assert mention in problems[0]


def test_f_17_ci_matrix_fail_fast_false_and_covers_every_project() -> None:
    assert parity_problems(REPO_ROOT) == []

    ci = yaml.safe_load((REPO_ROOT / CI).read_text(encoding="utf-8"))
    assert ci["jobs"]["projects"]["strategy"]["fail-fast"] is False


def test_f_1_ledger_hook_given_file_paths_validates_their_project(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    config = yaml.safe_load((REPO_ROOT / PRE_COMMIT).read_text(encoding="utf-8"))
    hook = next(h for repo in config["repos"] for h in repo["hooks"] if h["id"] == "ledger")
    assert hook["entry"] == "uv run --locked --project packages/datalab python -m datalab.ledger validate"
    assert re.search(hook["files"], "projects/x/run.json")
    assert re.search(hook["files"], "projects/x/split.json")
    assert re.search(hook["files"], "projects/x/run.2026-11-06.json") is None

    repo = tmp_path / "repo"
    (repo / "projects").mkdir(parents=True)
    good = project(tmp_path, vector("fresh-comparison"))
    good.rename(repo / "projects" / "demo")
    monkeypatch.chdir(repo)
    assert ledger.main(["validate", "projects/demo/run.json"]) == 0

    run = repo / "projects" / "demo" / "run.json"
    run.write_text(json.dumps({"bad": 1}), encoding="utf-8")
    assert ledger.main(["validate", "projects/demo/run.json"]) == 1
    assert "FAIL" in capsys.readouterr().err


def test_parity_reports_fail_fast_not_false(wired_repo: Path) -> None:
    ci = wired_repo / CI
    ci.write_text(ci.read_text("utf-8").replace("fail-fast: false", "fail-fast: true"), encoding="utf-8")

    problems = parity_problems(wired_repo)

    assert problems == ["jobs.projects.strategy.fail-fast must be false"]


def test_parity_reports_scalar_matrix(wired_repo: Path) -> None:
    ci = wired_repo / CI
    text = ci.read_text("utf-8")
    start = text.index("        project:\n")
    end = text.index("    defaults:", start)
    ci.write_text(text[:start] + "        project: mini-rag\n" + text[end:], encoding="utf-8")

    problems = "\n".join(parity_problems(wired_repo))

    assert "unexpected shape" in problems
    assert "project mini-rag is missing from jobs.projects.strategy.matrix.project" in problems


_CI_WITHOUT_PROJECTS_JOB = (
    "jobs:\n  other:\n    strategy:\n      matrix:\n        project:\n"
    "          # >>> datalab-new: matrix\n          - mini-rag\n          # <<< datalab-new: matrix\n"
)


def test_plan_rejects_ci_without_projects_matrix(wired_repo: Path) -> None:
    (wired_repo / CI).write_text(_CI_WITHOUT_PROJECTS_JOB, encoding="utf-8")
    before = ((wired_repo / PRE_COMMIT).read_bytes(), (wired_repo / CI).read_bytes())

    with pytest.raises(ProjectError, match="unexpected shape"):
        plan(wired_repo, "demo")

    assert ((wired_repo / PRE_COMMIT).read_bytes(), (wired_repo / CI).read_bytes()) == before


def test_main_cleans_tmp_dir_when_wiring_shape_is_unexpected(
    wired_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (wired_repo / CI).write_text(_CI_WITHOUT_PROJECTS_JOB, encoding="utf-8")

    assert main(["demo"], root=wired_repo, lock=_no_lock) == 1

    assert sorted(p.name for p in (wired_repo / "projects").iterdir()) == ["mini-rag", "voice-arch"]
    assert "unexpected shape" in capsys.readouterr().err


def test_plan_rejects_matrix_that_is_not_a_list() -> None:
    with pytest.raises(ProjectError, match="unexpected shape"):
        wiring.matrix_entries({"jobs": {"projects": {"strategy": {"matrix": {"project": "demo"}}}}})


def test_duplicate_hook_id_in_region_rejected(wired_repo: Path) -> None:
    pre_commit = wired_repo / PRE_COMMIT
    text = pre_commit.read_text("utf-8")
    block = declared_deps_block("voice-arch")
    pre_commit.write_text(text.replace(block, block + block, 1), encoding="utf-8")

    with pytest.raises(ProjectError, match="duplicate hook id 'declared-deps-voice-arch'"):
        plan(wired_repo, "demo")
