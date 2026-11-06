import json
from pathlib import Path

import pytest

from voice_arch.personas import PersonaError, load_personas

SHIPPED = Path(__file__).resolve().parents[1] / "data" / "personas.jsonl"


def _lines() -> list[dict[str, object]]:
    return [json.loads(line) for line in SHIPPED.read_text(encoding="utf-8").splitlines() if line.strip()]


def _write(tmp_path: Path, rows: list[dict[str, object]]) -> Path:
    path = tmp_path / "personas.jsonl"
    path.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")
    return path


def _with_expected(index: int, **changes: str) -> list[dict[str, object]]:
    rows = _lines()
    expected = rows[index]["expected_record"]
    assert isinstance(expected, dict)
    rows[index]["expected_record"] = {**expected, **changes}
    return rows


def test_u_5_persona_expected_problem_type_is_valid_enum() -> None:
    personas = {p.id: p for p in load_personas(SHIPPED)}

    assert personas["vague_problem"].expected_record.problem_type == "plumbing"
    assert len(personas) == 6


def test_u_5_unknown_problem_type_is_refused(tmp_path: Path) -> None:
    path = _write(tmp_path, _with_expected(0, problem_type="roofing"))

    with pytest.raises(PersonaError, match="roofing"):
        load_personas(path)


def test_u_7_persona_expected_slot_exists_in_calendar(tmp_path: Path) -> None:
    unknown = "ST_20990101_0900"
    path = _write(tmp_path, _with_expected(0, slot_id=unknown))

    with pytest.raises(PersonaError, match=unknown):
        load_personas(path)


def test_u_17_persona_expected_slot_is_free(tmp_path: Path) -> None:
    booked = "ST_20261109_0900"
    path = _write(tmp_path, _with_expected(1, slot_id=booked))

    with pytest.raises(PersonaError) as err:
        load_personas(path)

    assert booked in str(err.value)
    assert err.value.line == 2


def test_u_25_extra_expected_key_rejected(tmp_path: Path) -> None:
    path = _write(tmp_path, _with_expected(0, zip="78701"))

    with pytest.raises(PersonaError, match="zip"):
        load_personas(path)


def test_duplicate_persona_id_is_refused(tmp_path: Path) -> None:
    rows = _lines()
    rows[1]["id"] = rows[0]["id"]

    with pytest.raises(PersonaError, match="duplicate"):
        load_personas(_write(tmp_path, rows))


def test_missing_behaviour_is_refused(tmp_path: Path) -> None:
    with pytest.raises(PersonaError, match="one persona per behaviour"):
        load_personas(_write(tmp_path, _lines()[:5]))


def test_malformed_json_line_names_the_line(tmp_path: Path) -> None:
    path = tmp_path / "personas.jsonl"
    path.write_text("{not json\n", encoding="utf-8")

    with pytest.raises(PersonaError) as err:
        load_personas(path)

    assert err.value.line == 1


def test_interrupter_has_interjections_and_others_none() -> None:
    by_id = {p.id: p for p in load_personas(SHIPPED)}

    assert len(by_id["interrupter"].interjections) == 2
    assert all(not p.interjections for pid, p in by_id.items() if pid != "interrupter")
