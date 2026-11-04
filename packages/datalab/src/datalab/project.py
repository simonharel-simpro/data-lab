"""Project identity and naming. Pure: no weaviate/mlflow import, so it loads anywhere (app tooling, tests)."""

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import yaml

# Identical literal in app/src/lib/name.ts; vectors in contracts/name_vectors.json.
NAME_RE: Final = re.compile(r"^[a-z][a-z0-9]*(-[a-z0-9]+)*$")
# Test/infra namespaces + the YAML 1.1 bool/null words PyYAML and the JS parser read differently (U-4, F-3).
RESERVED: Final = frozenset(
    {"test", "datalab", "datalab-test", "template", "y", "n", "yes", "no", "on", "off", "true", "false", "null"}
)
_UNSAFE: Final = re.compile(r"[^0-9A-Za-z]")  # Demo-RAG index.py: Weaviate class names are [A-Z][_0-9A-Za-z]*
_FRONTMATTER: Final = re.compile(r"\A---[ \t]*\n(.*?)^---[ \t]*$", re.DOTALL | re.MULTILINE)


class ProjectError(ValueError):
    """A bad project name or card; the message names the file (when there is one) and the problem."""


@dataclass(frozen=True)
class Project:
    name: str
    root: Path


def validate_name(name: object) -> str:
    if not isinstance(name, str):
        raise ProjectError(f"project name must be a string, got {type(name).__name__} {name!r}")
    if not NAME_RE.match(name):
        raise ProjectError(f"invalid project name {name!r}: must match {NAME_RE.pattern}")
    if name in RESERVED:
        raise ProjectError(f"project name {name!r} is reserved")
    return name


def repo_root(start: Path | None = None) -> Path:
    """The data-lab checkout this package lives in. Found from the package file, not cwd or git (F-10).

    Works only for editable installs (the template's path dep, `uv tool install --editable`); from site-packages
    there is no checkout above, so it raises instead of guessing.
    """
    here = (start or Path(__file__)).resolve()
    for candidate in here.parents:
        if (candidate / "packages" / "datalab").is_dir() and (candidate / "compose.yaml").is_file():
            return candidate
    raise ProjectError(f"repo root not found above {here}: install datalab editable from a data-lab checkout")


def _find_card(start: Path, root: Path) -> Path | None:
    for folder in (start, *start.parents):
        card = folder / "PROJECT.md"
        if card.is_file():
            return card
        if folder == root:
            return None
    return None


def _frontmatter(card: Path) -> dict[object, object]:
    text = card.read_text(encoding="utf-8-sig").replace("\r\n", "\n")
    match = _FRONTMATTER.match(text)
    if match is None:
        raise ProjectError(f"{card}: no YAML frontmatter (a leading '---' line and a closing '---' line)")
    try:
        data = yaml.safe_load(match.group(1))
    except yaml.YAMLError as err:
        raise ProjectError(f"{card}: frontmatter is not valid YAML: {err}") from err
    if not isinstance(data, dict):
        raise ProjectError(f"{card}: frontmatter must be a mapping, got {type(data).__name__}")
    return data


def load(start: Path | None = None, *, root: Path | None = None) -> Project:
    """The project whose `PROJECT.md` is the nearest one above `start` (default: cwd), inside `root/projects`."""
    root = (root or repo_root()).resolve()
    origin = (start or Path.cwd()).resolve()
    card = _find_card(origin, root)
    if card is None:
        raise ProjectError(f"no PROJECT.md found from {origin} up to {root}")
    folder = card.parent
    if folder.parent != root / "projects":
        raise ProjectError(f"{card}: a project card must sit at {root / 'projects'}/<name>/PROJECT.md")
    data = _frontmatter(card)
    try:
        name = validate_name(data.get("name"))
    except ProjectError as err:
        raise ProjectError(f"{card}: {err}") from err
    if name != folder.name:
        raise ProjectError(f"{card}: name {name!r} must equal its folder name {folder.name!r}")
    return Project(name=name, root=folder)


def _check_name_shape(project: object) -> str:
    # Shape only, not RESERVED: integration tests own the reserved `datalab-test` namespace on purpose.
    if not isinstance(project, str) or not NAME_RE.match(project):
        raise ProjectError(f"invalid project name {project!r}: must match {NAME_RE.pattern}")
    return project


def collection_name(project: str, *parts: str) -> str:
    """`<Pascal(project)>_<parts>_<hash8>`; the hash covers the raw name and part boundaries (U-2, U-3)."""
    _check_name_shape(project)
    bad = [p for p in parts if not isinstance(p, str)]
    if bad:
        raise TypeError(f"collection name parts must be str, got {bad!r}")
    pascal = "".join(word.capitalize() for word in project.split("-"))
    digest = hashlib.sha256(json.dumps([project, *parts]).encode("utf-8")).hexdigest()[:8]
    return "_".join([_UNSAFE.sub("_", "_".join([pascal, *parts])), digest])


def experiment_name(project: str, sub: str | None = None) -> str:
    """`<name>` or `<name>/<sub>`; the app keeps exact matches only (U-7, F-6)."""
    _check_name_shape(project)
    if sub is None:
        return project
    if not isinstance(sub, str) or not NAME_RE.match(sub):
        raise ProjectError(f"invalid experiment sub-name {sub!r}: must match {NAME_RE.pattern}")
    return f"{project}/{sub}"
