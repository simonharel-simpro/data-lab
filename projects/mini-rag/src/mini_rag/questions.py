"""The question set: one JSON object `{"id", "question", "answer"}` per non-empty line."""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Final, cast

_KEYS: Final = frozenset({"id", "question", "answer"})


@dataclass(frozen=True)
class Question:
    id: str
    question: str
    answer: str | None  # None: not in the corpus, the right output is "I don't know"


def _parse(line: str, lineno: int) -> Question:
    try:
        data: object = json.loads(line)
    except json.JSONDecodeError as err:
        raise ValueError(f"line {lineno}: invalid JSON: {err}") from err
    if not isinstance(data, dict):
        raise ValueError(f"line {lineno}: expected exactly the keys {sorted(_KEYS)}, got {type(data).__name__}")
    # json.loads yields str keys only; isinstance narrows to dict[Unknown, Unknown]
    obj = cast(dict[str, object], data)
    if obj.keys() != _KEYS:
        raise ValueError(f"line {lineno}: expected exactly the keys {sorted(_KEYS)}, got {sorted(obj)}")
    qid, question, answer = obj["id"], obj["question"], obj["answer"]
    if not isinstance(qid, str) or not isinstance(question, str) or not isinstance(answer, str | None):
        raise ValueError(f"line {lineno}: id and question must be strings, answer a string or null")
    return Question(id=qid, question=question, answer=answer)


def load_questions(path: Path) -> list[Question]:
    questions: list[Question] = []
    seen: set[str] = set()
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        question = _parse(line, lineno)
        if question.id in seen:
            raise ValueError(f"line {lineno}: duplicate id {question.id!r}")
        seen.add(question.id)
        questions.append(question)
    return questions
