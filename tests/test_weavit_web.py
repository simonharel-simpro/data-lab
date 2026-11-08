"""Guards tools/weavit-web.sh: clean OPENROUTER_API_KEY extraction and a clear empty-submodule failure (REVIEW §6)."""

import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "tools" / "weavit-web.sh"

BASH = shutil.which("bash")

pytestmark = pytest.mark.skipif(BASH is None, reason="bash absent (#8)")


def _read_env_key(env_file: Path) -> str:
    # Fixed argv, no shell, absolute bash path: the env file path is passed as $1, never interpolated.
    result = subprocess.run(  # noqa: S603
        [str(BASH), "-c", 'source tools/weavit-web.sh; read_env_key "$1"', "_", str(env_file)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        (b'OPENROUTER_API_KEY="dummy-key"\r\n', "dummy-key"),
        (b"OPENROUTER_API_KEY='dummy-key'\n", "dummy-key"),
        (b"OPENROUTER_API_KEY=dummy-key\n", "dummy-key"),
        (b"OPENROUTER_API_KEY=dummy-key\r\n", "dummy-key"),
        (b"OTHER=1\nOPENROUTER_API_KEY=first\nOPENROUTER_API_KEY=second\n", "first"),
        (b"OTHER=1\n", ""),
        (b"", ""),
    ],
    ids=["dquoted-crlf", "squoted", "bare", "bare-crlf", "first-line-wins", "missing", "empty-file"],
)
def test_read_env_key_cleans_value(tmp_path: Path, content: bytes, expected: str) -> None:
    env_file = tmp_path / ".env"
    env_file.write_bytes(content)

    assert _read_env_key(env_file) == expected


def test_read_env_key_absent_file_returns_empty(tmp_path: Path) -> None:
    assert _read_env_key(tmp_path / "no-such.env") == ""


def test_launcher_with_empty_submodule_exits_with_init_hint(tmp_path: Path) -> None:
    tools = tmp_path / "tools"
    (tools / "weavit-ui").mkdir(parents=True)
    script = tools / "weavit-web.sh"
    shutil.copy(SCRIPT, script)

    result = subprocess.run(  # noqa: S603
        [str(BASH), str(script)], capture_output=True, text=True, check=False, timeout=30
    )

    assert result.returncode == 1
    assert "git submodule update --init" in result.stderr
