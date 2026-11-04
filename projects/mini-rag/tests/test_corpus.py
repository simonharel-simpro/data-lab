import itertools

import pytest

from mini_rag.corpus import chunk_doc, load_corpus
from tests.conftest import CORPUS_DIR

_WORDS = " ".join(f"w{i}" for i in range(300))
_DOC = f"# Title\n\nintro words here\n\n## Section A\n\n{_WORDS}\n\n## Section B\n\nshort tail\n"


def test_chunking_overlap_and_ids_stable() -> None:
    first = chunk_doc("doc", _DOC, size=120, overlap=20)
    second = chunk_doc("doc", _DOC, size=120, overlap=20)

    assert [c.chunk_id for c in first] == [c.chunk_id for c in second]
    assert len({c.chunk_id for c in first}) == len(first)
    section_a = [c for c in first if "w150" in c.text.split() or "Section A" in c.text or "w299" in c.text.split()]
    assert len(section_a) == 3  # 303 words (heading included): [0:120], [100:220], [200:303]
    for left, right in itertools.pairwise(section_a):
        assert left.text.split()[-20:] == right.text.split()[:20]


def test_chunks_split_on_sections_and_respect_size() -> None:
    chunks = chunk_doc("doc", _DOC, size=120, overlap=20)

    assert all(len(c.text.split()) <= 120 for c in chunks)
    assert not any("Section B" in c.text and "w299" in c.text for c in chunks)
    assert chunks[-1].text.split()[-2:] == ["short", "tail"]
    assert {c.doc for c in chunks} == {"doc"}


def test_no_tail_chunk_made_only_of_overlap() -> None:
    # 220 words with the heading, size 120, overlap 20: [0:120] and [100:220] cover it;
    # no third window made only of overlap.
    text = "## S\n" + " ".join(f"w{i}" for i in range(218))

    chunks = chunk_doc("d", text, size=120, overlap=20)

    assert len(chunks) == 2


def test_overlap_must_be_smaller_than_size() -> None:
    with pytest.raises(ValueError, match="overlap"):
        chunk_doc("d", "## S\nx", size=20, overlap=20)


def test_snapshot_corpus_loads_every_file_with_unique_ids() -> None:
    chunks = load_corpus(CORPUS_DIR, size=120, overlap=20)

    assert {c.doc for c in chunks} == {p.stem for p in CORPUS_DIR.glob("*.md")}
    assert len({c.chunk_id for c in chunks}) == len(chunks)
