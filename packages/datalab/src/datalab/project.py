"""Project identity and naming. Pure: no weaviate/mlflow import, so it loads anywhere (app tooling, tests)."""

import hashlib
import importlib.metadata
import json
import keyword
import re
import sys
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Final, cast

import yaml

# Identical literal in app/src/lib/name.ts; Python uses fullmatch (its "$" also matches before a final "\n").
# Vectors in contracts/name_vectors.json.
NAME_RE: Final = re.compile(r"^[a-z][a-z0-9]*(-[a-z0-9]+)*$")
# Test/infra namespaces + the YAML 1.1 bool/null words PyYAML and the JS parser read differently (U-4, F-3).
RESERVED: Final = frozenset(
    {"test", "datalab", "datalab-test", "template", "y", "n", "yes", "no", "on", "off", "true", "false", "null"}
)
# Identical literal in app/src/lib/card.ts; read with fullmatch for the same "$" reason as NAME_RE.
METRIC_KEY_RE: Final = re.compile(r"^[A-Za-z0-9_.\-/]+$")
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
    if not NAME_RE.fullmatch(name):
        raise ProjectError(f"invalid project name {name!r}: must match {NAME_RE.pattern}")
    if name in RESERVED:
        raise ProjectError(f"project name {name!r} is reserved")
    return name


def package_name(name: str) -> str:
    """The import name of a project: `name` with dashes as underscores, refused when it would shadow something (U-25).

    Refused: a Python keyword, a stdlib module, an import name installed in this env (where `datalab-new` runs), or
    one of the template's Hydra deps (`hydra`, `omegaconf`, `antlr4`).
    """
    pkg = validate_name(name).replace("-", "_")
    taken = set(importlib.metadata.packages_distributions()) | {"hydra", "omegaconf", "antlr4"}
    if keyword.iskeyword(pkg) or pkg in sys.stdlib_module_names or pkg in taken:
        raise ProjectError(f"project name {name!r} gives the package {pkg!r}, which shadows a keyword or module")
    return pkg


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
    return cast(dict[object, object], data)  # yaml.safe_load is untyped; just checked to be a mapping


class Goal(StrEnum):
    """Which way the card's metric improves; values in contracts/value_sets.json."""

    MAX = "max"
    MIN = "min"


@dataclass(frozen=True)
class CardMetric:
    key: str
    goal: Goal


def card_metric(project_dir: Path) -> CardMetric:
    """The `metric: {key, goal}` of the project card; anything else is a `ProjectError` naming the card."""
    card = project_dir / "PROJECT.md"
    try:
        metric = _frontmatter(card).get("metric")
    except OSError as err:
        raise ProjectError(f"{card}: cannot read: {err}") from err
    if not isinstance(metric, dict):
        raise ProjectError(f"{card}: frontmatter needs metric: {{key, goal}}")
    fields = cast(dict[object, object], metric)  # isinstance(dict) leaves the key/value types unknown
    key, goal = fields.get("key"), fields.get("goal")
    if not isinstance(key, str) or not METRIC_KEY_RE.fullmatch(key):
        raise ProjectError(f"{card}: metric.key must match {METRIC_KEY_RE.pattern}, got {key!r}")
    try:
        parsed = Goal(goal)
    except ValueError as err:
        allowed = " or ".join(repr(g.value) for g in Goal)
        raise ProjectError(f"{card}: metric.goal must be {allowed}, got {goal!r}") from err
    return CardMetric(key=key, goal=parsed)


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


def _not_str(value: object) -> bool:
    # `object`, so the runtime guard survives strict mode: callers outside the type system may pass a non-str.
    return not isinstance(value, str)


def _check_name_shape(project: object) -> str:
    # Shape only, not RESERVED: integration tests own the reserved `datalab-test` namespace on purpose.
    if not isinstance(project, str) or not NAME_RE.fullmatch(project):
        raise ProjectError(f"invalid project name {project!r}: must match {NAME_RE.pattern}")
    return project


def collection_name(project: str, *parts: str) -> str:
    """`<Pascal(project)>_<parts>_<hash8>`; the hash covers the raw name and part boundaries (U-2, U-3)."""
    _check_name_shape(project)
    bad = [p for p in parts if _not_str(p)]
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
    if _not_str(sub) or not NAME_RE.fullmatch(sub):
        raise ProjectError(f"invalid experiment sub-name {sub!r}: must match {NAME_RE.pattern}")
    return f"{project}/{sub}"
