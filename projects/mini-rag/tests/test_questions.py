import json
from pathlib import Path

import pytest

from mini_rag.questions import load_questions
from tests.conftest import CORPUS_DIR, QUESTIONS_FILE


def _write(tmp_path: Path, *lines: str) -> Path:
    path = tmp_path / "q.jsonl"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def test_questions_answers_are_in_snapshot() -> None:
    corpus = "\n".join(p.read_text(encoding="utf-8") for p in sorted(CORPUS_DIR.glob("*.md")))
    questions = load_questions(QUESTIONS_FILE)

    absent = [q.id for q in questions if q.answer is not None and q.answer not in corpus]

    assert absent == []


def test_question_set_shape_matches_plan() -> None:
    # Plan: 20 questions, >= 3 numeric answers, >= 2 unanswerable (answer null).
    questions = load_questions(QUESTIONS_FILE)
    numeric = [q for q in questions if q.answer is not None and q.answer.isdigit()]

    assert len(questions) == 20
    assert len(numeric) >= 3
    assert sum(q.answer is None for q in questions) >= 2


def test_load_questions_valid_file(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        json.dumps({"id": "q1", "question": "Which port?", "answer": "5050"}),
        "",
        json.dumps({"id": "q2", "question": "Unknown?", "answer": None}),
    )

    q1, q2 = load_questions(path)

    assert (q1.id, q1.question, q1.answer) == ("q1", "Which port?", "5050")
    assert q2.id == "q2"
    assert q2.answer is None


def test_load_questions_malformed_line_raises(tmp_path: Path) -> None:
    good = json.dumps({"id": "q1", "question": "a", "answer": "b"})
    with pytest.raises(ValueError, match="line 2"):
        load_questions(_write(tmp_path, good, json.dumps({"id": "q2"})))
    with pytest.raises(ValueError, match="duplicate"):
        load_questions(_write(tmp_path, good, good))


@pytest.mark.parametrize(
    "bad",
    [
        "{not json",
        json.dumps({"id": "q2", "question": "a", "answer": "b", "extra": 1}),
        json.dumps({"id": "q2", "question": "a", "answer": 5050}),
        json.dumps(["q2", "a", "b"]),
    ],
)
def test_load_questions_bad_line_names_the_line(tmp_path: Path, bad: str) -> None:
    good = json.dumps({"id": "q1", "question": "a", "answer": "b"})

    with pytest.raises(ValueError, match="line 2"):
        load_questions(_write(tmp_path, good, bad))
