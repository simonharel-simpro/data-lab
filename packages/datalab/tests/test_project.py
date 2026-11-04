import json
import re
from pathlib import Path

import pytest

from datalab.project import (
    Project,
    ProjectError,
    collection_name,
    experiment_name,
    load,
    repo_root,
    validate_name,
)
from tests.conftest import REPO_ROOT


def _card(folder: Path, text: str, *, encoding: str = "utf-8") -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "PROJECT.md"
    path.write_bytes(text.encode(encoding))
    return path


def test_f_12_name_re_matches_shared_vectors() -> None:
    vectors = json.loads((REPO_ROOT / "contracts" / "name_vectors.json").read_text(encoding="utf-8"))

    assert [validate_name(name) for name in vectors["accept"]] == vectors["accept"]
    for name in vectors["reject"]:
        with pytest.raises(ProjectError):
            validate_name(name)


def test_validate_name_rejects_non_str() -> None:
    with pytest.raises(ProjectError):
        validate_name(False)


def test_u_2_collection_name_differs_for_names_with_same_pascal() -> None:
    assert collection_name("a-bc", "x") != collection_name("ab-c", "x")


def test_u_3_hash_distinguishes_part_boundaries() -> None:
    assert collection_name("p", "a_b", "c") != collection_name("p", "a", "b_c")


def test_u_3_readable_part_is_weaviate_safe() -> None:
    name = collection_name("mini-rag", "bge/v1.5")

    assert re.fullmatch(r"^[A-Z][A-Za-z0-9_]*$", name)
    assert name.startswith("MiniRag_")


def test_u_3_non_str_part_raises_type_error() -> None:
    with pytest.raises(TypeError):
        collection_name("p", 3)  # type: ignore[arg-type]  # the wrong type is the point of the test


def test_u_7_experiment_name_format() -> None:
    assert experiment_name("p") == "p"
    assert experiment_name("p", "bm25") == "p/bm25"
    with pytest.raises(ProjectError):
        experiment_name("p", "Bad")


def test_f_11_crlf_and_bom_frontmatter_parse(fake_repo: Path) -> None:
    folder = fake_repo / "projects" / "demo"
    _card(folder, "---\r\nname: demo\r\ntitle: Demo\r\n---\r\n\r\n## Objectif\r\n", encoding="utf-8-sig")

    assert load(folder, root=fake_repo) == Project(name="demo", root=folder)


def test_load_walks_up_from_a_subdir(fake_repo: Path) -> None:
    folder = fake_repo / "projects" / "demo"
    _card(folder, "---\nname: demo\n---\n")
    (folder / "src" / "pkg").mkdir(parents=True)

    assert load(folder / "src" / "pkg", root=fake_repo).name == "demo"


@pytest.mark.parametrize("text", ["---\n---\n", "---\n- a\n---\n"])
def test_f_11_empty_or_list_frontmatter_raises_project_error(fake_repo: Path, text: str) -> None:
    path = _card(fake_repo / "projects" / "demo", text)

    with pytest.raises(ProjectError, match=re.escape(str(path))):
        load(path.parent, root=fake_repo)


def test_missing_or_bad_yaml_frontmatter_raises_project_error(fake_repo: Path) -> None:
    no_fm = _card(fake_repo / "projects" / "a", "# no frontmatter\n")
    bad = _card(fake_repo / "projects" / "b", "---\nname: [b\n---\n")

    with pytest.raises(ProjectError, match=re.escape(str(no_fm))):
        load(no_fm.parent, root=fake_repo)
    with pytest.raises(ProjectError, match=re.escape(str(bad))):
        load(bad.parent, root=fake_repo)


def test_f_11_yaml_bool_name_rejected(fake_repo: Path) -> None:
    path = _card(fake_repo / "projects" / "no", "---\nname: no\n---\n")

    with pytest.raises(ProjectError, match=re.escape(str(path))):
        load(path.parent, root=fake_repo)


def test_f_11_walk_up_stops_at_repo_root(fake_repo: Path, tmp_path: Path) -> None:
    _card(tmp_path, "---\nname: x\n---\n")  # stray card above the repo root
    (fake_repo / "projects" / "x").mkdir()

    with pytest.raises(ProjectError, match=re.escape("no PROJECT.md found")):  # the stray card was never read
        load(fake_repo / "projects" / "x", root=fake_repo)


def test_load_outside_root_raises(fake_repo: Path, tmp_path: Path) -> None:
    (tmp_path / "elsewhere").mkdir()

    with pytest.raises(ProjectError):
        load(tmp_path / "elsewhere", root=fake_repo)


def test_card_outside_projects_dir_raises(fake_repo: Path) -> None:
    path = _card(fake_repo / "notes" / "demo", "---\nname: demo\n---\n")

    with pytest.raises(ProjectError, match=re.escape(str(path))):
        load(path.parent, root=fake_repo)


def test_s9_name_must_equal_folder(fake_repo: Path) -> None:
    path = _card(fake_repo / "projects" / "alpha", "---\nname: beta\n---\n")

    with pytest.raises(ProjectError, match="alpha"):
        load(path.parent, root=fake_repo)


def test_load_defaults_to_cwd_and_real_root(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)

    with pytest.raises(ProjectError):  # tmp_path is outside data-lab: the walk finds no card under projects/
        load()


def test_f_10_root_found_from_nested_git_repo_cwd(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    nested = tmp_path / "submodule" / "deep"
    (tmp_path / "submodule" / ".git").mkdir(parents=True)
    nested.mkdir()
    monkeypatch.chdir(nested)

    assert repo_root() == REPO_ROOT


def test_f_10_non_editable_install_raises(tmp_path: Path) -> None:
    fake_module = tmp_path / "site-packages" / "datalab" / "project.py"
    fake_module.parent.mkdir(parents=True)
    fake_module.write_text("", encoding="utf-8")

    with pytest.raises(ProjectError, match="repo root not found"):
        repo_root(start=fake_module)
