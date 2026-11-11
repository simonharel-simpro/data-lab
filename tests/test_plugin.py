"""Guards the `datalab` Claude Code plugin and its marketplace (platform Phase 2: D-5, S-1, F-3, F-8, F-9, U-4).

The skill runs in any workspace, so its text must not lean on data-lab-only paths, and an installed plugin is copied
to a cache, so its links must not leave `plugins/datalab/`. The rules work on Markdown units (a paragraph, a bullet
with its continuation lines, a table row, a fenced line): the allowed mentions are whole sentences, not substrings.
"""

import json
import re
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
MARKETPLACE = REPO_ROOT / ".claude-plugin" / "marketplace.json"
PLUGIN_DIR = REPO_ROOT / "plugins" / "datalab"
SKILL = PLUGIN_DIR / "skills" / "experiment" / "SKILL.md"
INSIDE = "inside data-lab"
UPGRADE = "uv lock --upgrade-package datalab"

_UNIT_START = re.compile(r"^(- |\||#|\d+\. |[a-z]\. )")
_CONTRACTS = re.compile(r"(?<![\w./-])contracts/")
_TOOLS = re.compile(r"(?<![\w./-])tools/")
_MD_LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
_BACKTICK = re.compile(r"`([^`\s]+)`")
_LINE_CITE = re.compile(r":\d+(-\d+)?$")


def _units(text: str) -> list[str]:
    units: list[str] = []
    current: list[str] = []
    fenced = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("```") or fenced:
            if current:
                units.append(" ".join(current))
                current = []
            if stripped.startswith("```"):
                fenced = not fenced
            units.append(stripped)
            continue
        if not stripped or _UNIT_START.match(stripped):
            if current:
                units.append(" ".join(current))
            current = [stripped] if stripped else []
        else:
            current.append(stripped)
    if current:
        units.append(" ".join(current))
    return units


def _is_predicate(unit: str) -> bool:
    return (
        INSIDE in unit.lower() and "`packages/datalab/`" in unit and "compose.yaml" in unit and "--project" not in unit
    )


def _is_create(unit: str) -> bool:
    return INSIDE in unit.lower() and "datalab-new" in unit and "README §New project" in unit


def path_violations(text: str) -> list[str]:
    found: list[str] = []
    for unit in _units(text):
        if "packages/datalab" in unit and not (_is_predicate(unit) or _is_create(unit)):
            found.append(f"packages/datalab outside the predicate/create sentences: {unit}")
        if _CONTRACTS.search(unit):
            found.append(f"repo path contracts/: {unit}")
        if _TOOLS.search(unit) and not ("hydra_gate.py" in unit and INSIDE in unit.lower()):
            found.append(f"tools/ outside the guarded Hydra-gate sentence: {unit}")
    return found


def link_targets(text: str) -> list[tuple[str, bool]]:
    """(target, must_exist): Markdown links and backticked skill-file paths; line cites and home paths are not links."""
    targets: list[tuple[str, bool]] = []
    for raw in _MD_LINK.findall(text):
        target = raw.split("#", 1)[0]
        if target and not re.match(r"^[a-z]+:", target):
            targets.append((target, True))
    for raw in _BACKTICK.findall(text):
        token = _LINE_CITE.sub("", raw)
        if token.startswith("references/"):
            targets.append((token, True))
        elif token.startswith(("./", "../")) or "/../" in token:
            targets.append((token, False))
    return targets


def link_violations(md: Path, plugin_dir: Path) -> list[str]:
    found: list[str] = []
    for target, must_exist in link_targets(md.read_text(encoding="utf-8")):
        resolved = (md.parent / target).resolve()
        if not resolved.is_relative_to(plugin_dir.resolve()):
            found.append(f"{md.name}: {target} leaves the plugin")
        elif must_exist and not resolved.exists():
            found.append(f"{md.name}: {target} does not exist")
    return found


def _plugin_markdown() -> list[Path]:
    files = sorted(PLUGIN_DIR.rglob("*.md"))
    assert files, f"no Markdown under {PLUGIN_DIR}"
    return files


def _skill_units() -> list[str]:
    return _units(SKILL.read_text(encoding="utf-8"))


def _readme_section(heading: str) -> str:
    text = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    match = re.search(rf"^## {re.escape(heading)}\n(.*?)(?=^## |\Z)", text, re.MULTILINE | re.DOTALL)
    assert match is not None, f"README.md has no '## {heading}' section"
    return match.group(1)


def test_marketplace_lists_existing_plugins() -> None:
    market = json.loads(MARKETPLACE.read_text(encoding="utf-8"))
    assert market["name"] == "data-lab"
    assert market["owner"]["name"]
    assert market["plugins"], "the marketplace lists no plugin"
    for entry in market["plugins"]:
        source = (REPO_ROOT / entry["source"]).resolve()
        assert source.is_relative_to(REPO_ROOT), entry["source"]
        manifest = json.loads((source / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
        assert manifest["name"] == entry["name"]
    assert [e["name"] for e in market["plugins"]] == ["datalab"]


def test_skill_frontmatter() -> None:
    skills = sorted((REPO_ROOT / "plugins").glob("*/skills/*/SKILL.md"))
    assert skills, "no plugin skill found"
    for skill in skills:
        match = re.match(r"^---\n(.*?)\n---\n", skill.read_text(encoding="utf-8"), re.DOTALL)
        assert match is not None, f"{skill}: no YAML frontmatter"
        front = yaml.safe_load(match.group(1))
        assert isinstance(front, dict)
        assert isinstance(front.get("name"), str) and front["name"].strip(), skill
        assert isinstance(front.get("description"), str) and front["description"].strip(), skill
    assert yaml.safe_load(SKILL.read_text(encoding="utf-8").split("---")[1])["name"] == "experiment"


def test_skill_has_no_data_lab_paths() -> None:
    found = [v for md in _plugin_markdown() for v in path_violations(md.read_text(encoding="utf-8"))]
    assert found == []


def test_path_rules_catch_violations() -> None:
    assert path_violations("uv run --locked --project packages/datalab python -m datalab.ledger validate")
    assert path_violations("Read `contracts/milestones.json`.")
    assert path_violations("Run `python3 tools/pre_commit_checks/hydra_gate.py projects/<name>` always.")
    assert path_violations(f"{INSIDE}: install `packages/datalab` here.")
    allowed = (
        '"Inside data-lab" = the workspace root holds `packages/datalab/` and `compose.yaml`.\n\n'
        f"Create it ({INSIDE}: `uv run --project packages/datalab datalab-new <name>`), see README §New project.\n\n"
        f"- {INSIDE}: `python3 tools/pre_commit_checks/hydra_gate.py projects/<name>`."
    )
    assert path_violations(allowed) == []


def test_skill_links_stay_in_plugin() -> None:
    files = _plugin_markdown()
    assert any(link_targets(md.read_text(encoding="utf-8")) for md in files), "no link checked: the test is vacuous"
    assert [v for md in files for v in link_violations(md, PLUGIN_DIR)] == []


def test_link_rule_catches_escapes(tmp_path: Path) -> None:
    md = tmp_path / "plugin" / "SKILL.md"
    md.parent.mkdir()
    md.write_text("[c](../../../contracts/x.md) `../outside.md` `references/missing.md` `ds-modeler.md:24-25`\n")
    found = link_violations(md, tmp_path / "plugin")
    assert len(found) == 3, found


def test_skill_hydra_gate_guarded_by_checkout() -> None:
    units = _skill_units()
    gate = [u for u in units if "hydra_gate.py" in u]
    assert gate, "SKILL.md never runs the Hydra gate"
    for unit in gate:
        lowered = unit.lower()
        assert INSIDE in lowered and lowered.index(INSIDE) < lowered.index("hydra_gate.py"), unit
        assert "skip" in lowered and "no Hydra gate outside data-lab (#48)" in unit, unit
    assert [u for u in units if _is_predicate(u)], "no 'inside data-lab' predicate naming packages/datalab/ and compose"


def test_skill_missing_project_points_to_readme() -> None:
    create = [u for u in _skill_units() if _is_create(u)]
    assert len(create) == 1, create
    assert "uvx" in create[0]
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    assert re.search(r"^## New project$", readme, re.MULTILINE)


def test_resources_module_referenced_exists() -> None:
    names = set(re.findall(r"python -m datalab\.resources (\S+?)`", SKILL.read_text(encoding="utf-8")))
    assert names == {"EXPERIMENT.md", "milestones.json"}
    assert (REPO_ROOT / "packages" / "datalab" / "src" / "datalab" / "resources.py").is_file()
    for name in names:
        assert (REPO_ROOT / "contracts" / name).is_file(), name


def test_old_skill_location_is_gone() -> None:
    assert not (REPO_ROOT / ".claude" / "skills" / "experiment").exists()


def test_plugin_json_has_no_version() -> None:
    manifest = json.loads((PLUGIN_DIR / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    assert manifest["name"] == "datalab"
    assert "version" not in manifest


def test_u11_skill_upgrade_command() -> None:
    remedy = [u for u in _skill_units() if "No module named datalab.resources" in u]
    assert remedy, "SKILL.md does not handle a project whose datalab predates datalab.resources"
    assert all(UPGRADE in u for u in remedy), remedy


def test_readme_says_upgrade_after_plugin_update() -> None:
    section = _readme_section("Claude Code")
    sentences = [s for s in _units(section) if UPGRADE in s]
    assert sentences, "README §Claude Code does not say to upgrade datalab"
    assert any("plugin update" in s for s in sentences), sentences
