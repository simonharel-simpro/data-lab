import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

_SCRIPT = Path(__file__).resolve().parent.parent / "tools" / "check_file_size.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_file_size_under_test", _SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _module(root: Path, rel: str, lines: int) -> str:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("x = 1\n" * lines, encoding="utf-8")
    return rel


def test_file_over_cap_fails_and_names_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    rel = _module(tmp_path, "packages/x/src/m.py", 201)

    assert _load().main([rel]) == 1
    assert "packages/x/src/m.py" in capsys.readouterr().err


def test_file_at_cap_passes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    rel = _module(tmp_path, "packages/x/src/m.py", 200)

    assert _load().main([rel]) == 0


def test_file_outside_src_is_ignored(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    rel = _module(tmp_path, "packages/x/tests/m.py", 500)

    assert _load().main([rel]) == 0


def test_file_in_warn_band_warns_but_passes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    rel = _module(tmp_path, "packages/x/src/m.py", 195)

    assert _load().main([rel]) == 0
    assert "warning: packages/x/src/m.py: 195 lines (cap 200): split before adding" in capsys.readouterr().err


def test_file_below_warn_band_is_silent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    rel = _module(tmp_path, "packages/x/src/m.py", 189)

    assert _load().main([rel]) == 0
    assert capsys.readouterr().err == ""
