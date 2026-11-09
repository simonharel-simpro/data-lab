import hashlib
import importlib.util
import re
import time
from pathlib import Path
from types import ModuleType

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent

_VENDORED = REPO_ROOT / "tools" / "check_hydra_project.py"
_SHA = "312f6242dc31e4d7930a13d33df9cbed3537aa2ff3fc444f0c9dcf67252a61b2"


def _load() -> ModuleType:
    path = REPO_ROOT / "tools" / "pre_commit_checks" / "hydra_gate.py"
    spec = importlib.util.spec_from_file_location("hydra_gate_under_test", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _wired_demo(repo: Path, name: str = "demo", *, main: bool = True) -> Path:
    root = repo / "projects" / name
    _write(root / "pyproject.toml", '[project]\nname = "demo"\ndependencies = ["hydra-core"]\n')
    _write(root / "configs" / "train.yaml", "defaults:\n  - model: a\n")
    _write(root / "configs" / "model" / "a.yaml", "_target_: x.Y\n")
    decorator = "@hydra.main(config_path='../../configs')\n" if main else ""
    source = f"import hydra\n\n{decorator}def run(cfg):\n    hydra.utils.instantiate(cfg)\n"
    _write(root / "src" / name / "train.py", source)
    return root


def test_f_1_hook_entry_with_two_changed_configs_in_one_project_exits_0(
    tmp_path: Path, capfd: pytest.CaptureFixture[str]
) -> None:
    _wired_demo(tmp_path)

    code = _load().main(["projects/demo/configs/train.yaml", "projects/demo/configs/model/a.yaml"], repo_root=tmp_path)

    assert code == 0
    assert capfd.readouterr().err.count("hydra-gate projects/demo") == 1


def test_f_2_hydra_hook_files_regex_matches_src_and_pyproject() -> None:
    config = yaml.safe_load((REPO_ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8"))
    hook = next(h for repo in config["repos"] for h in repo["hooks"] if h["id"] == "hydra-gate")

    for path in ("projects/d/src/d/train.py", "projects/d/pyproject.toml", "projects/d/configs/train.yaml"):
        assert re.search(hook["files"], path), path
    for path in ("projects/d/README.md", "packages/datalab/src/x.py"):
        assert re.search(hook["files"], path) is None, path


def test_u_22_gate_fails_project_with_configs_but_no_hydra_main(tmp_path: Path) -> None:
    _wired_demo(tmp_path, main=False)

    assert _load().main(["projects/demo/configs/train.yaml"], repo_root=tmp_path) == 1


def test_project_without_configs_skipped(tmp_path: Path, capfd: pytest.CaptureFixture[str]) -> None:
    _write(tmp_path / "projects" / "legacy" / "src" / "legacy" / "x.py", "x = 1\n")

    code = _load().main(["projects/legacy/src/legacy/x.py"], repo_root=tmp_path)

    assert code == 0
    assert capfd.readouterr().err == "skip projects/legacy: no configs/\n"


def test_oc_env_in_configs_fails(tmp_path: Path, capfd: pytest.CaptureFixture[str]) -> None:
    demo = _wired_demo(tmp_path)
    _write(demo / "configs" / "paths" / "default.yaml", "root: .\ntoken: ${oc.env:SECRET}\n")

    code = _load().main(["projects/demo/configs/paths/default.yaml"], repo_root=tmp_path)

    assert code == 1
    assert "configs/paths/default.yaml:2" in capfd.readouterr().err


def test_no_args_scans_every_project(tmp_path: Path) -> None:
    _wired_demo(tmp_path)
    _write(tmp_path / "projects" / "unwired" / "configs" / "train.yaml", "a: 1\n")

    assert _load().main([], repo_root=tmp_path) == 1


def test_paths_outside_projects_are_ignored(tmp_path: Path) -> None:
    (tmp_path / "projects" / "demo" / "configs").mkdir(parents=True)

    assert _load().project_roots(["packages/datalab/src/x.py", "README.md"], tmp_path) == []


def test_project_roots_dedupes_and_sorts_across_projects(tmp_path: Path) -> None:
    paths = ["projects/b/src/b/x.py", "projects/a/configs/t.yaml", "projects/b/pyproject.toml", "projects/a"]

    roots = _load().project_roots(paths, tmp_path)

    assert roots == [tmp_path / "projects" / "a", tmp_path / "projects" / "b"]


def test_vendored_gate_body_matches_trouvetou_sha256() -> None:
    text = _VENDORED.read_text(encoding="utf-8")
    body = re.sub(r"# >>> vendored header\n.*?# <<< vendored header\n", "", text, count=1, flags=re.DOTALL)

    assert hashlib.sha256(body.encode("utf-8")).hexdigest() == _SHA


def test_gate_subprocess_timeout_fails_with_message(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str]
) -> None:
    _wired_demo(tmp_path)
    stub = _write(tmp_path / "slow_gate.py", "import time\ntime.sleep(5)\n")
    module = _load()
    monkeypatch.setattr(module, "GATE", stub)
    monkeypatch.setattr(module, "GATE_TIMEOUT_S", 0.01)

    started = time.monotonic()
    code = module.main(["projects/demo/configs/train.yaml"], repo_root=tmp_path)

    assert code == 1
    assert "hydra-gate projects/demo: timed out after 0.01 s" in capfd.readouterr().err
    assert time.monotonic() - started < 4
