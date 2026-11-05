import itertools
from pathlib import Path

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
    # _DOC sections: s0 = title + intro, s1 = "Section A", s2 = "Section B"
    section_a = [c for c in first if c.chunk_id.startswith("doc#s1")]
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


def test_corpus_with_only_empty_files_raises(tmp_path: Path) -> None:
    (tmp_path / "a.md").write_text("\n  \n", encoding="utf-8")

    with pytest.raises(ValueError, match="no text to index"):
        load_corpus(tmp_path)


def _numbered(n: int) -> str:
    return " ".join(f"w{i}" for i in range(n))


@pytest.mark.parametrize(
    ("n", "windows", "last_first", "last_last"),
    [
        (1, 1, "w0", "w0"),
        (9, 1, "w0", "w8"),
        (10, 1, "w0", "w9"),
        (11, 2, "w8", "w10"),
        (18, 2, "w8", "w17"),
        (19, 3, "w16", "w18"),
    ],
)
def test_window_count_and_last_window_at_boundaries(n: int, windows: int, last_first: str, last_last: str) -> None:
    chunks = chunk_doc("d", _numbered(n), size=10, overlap=2)

    assert len(chunks) == windows
    last = chunks[-1].text.split()
    assert (last[0], last[-1]) == (last_first, last_last)


@pytest.mark.parametrize("n", [1, 9, 10, 11, 18, 19])
def test_windows_cover_every_word_and_share_exactly_the_overlap(n: int) -> None:
    chunks = chunk_doc("d", _numbered(n), size=10, overlap=2)

    words = [c.text.split() for c in chunks]
    assert {w for ws in words for w in ws} == {f"w{i}" for i in range(n)}
    for left, right in itertools.pairwise(words):
        assert left[-2:] == right[:2]
        assert len(set(left) & set(right)) == 2


def test_zero_overlap_windows_are_disjoint() -> None:
    chunks = chunk_doc("d", _numbered(25), size=10, overlap=0)

    assert [len(c.text.split()) for c in chunks] == [10, 10, 5]
    assert chunks[1].text.split()[0] == "w10"
    assert chunks[2].text.split()[0] == "w20"


def test_overlap_equal_to_size_is_refused() -> None:
    with pytest.raises(ValueError, match="overlap"):
        chunk_doc("d", _numbered(30), size=10, overlap=10)


def test_load_corpus_without_md_files_raises(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match=r"no \*\.md"):
        load_corpus(tmp_path)


@pytest.mark.parametrize("text", ["", "  \n\n "])
def test_empty_or_whitespace_doc_yields_no_chunks(text: str) -> None:
    assert chunk_doc("d", text) == []


def test_crlf_doc_splits_sections_like_lf() -> None:
    lf = "intro\n## A\nw1 w2\n## B\nw3"

    crlf_chunks = chunk_doc("d", lf.replace("\n", "\r\n"))
    lf_chunks = chunk_doc("d", lf)

    expected_ids = ["d#s0w0", "d#s1w0", "d#s2w0"]
    assert [c.chunk_id for c in crlf_chunks] == expected_ids
    assert [c.chunk_id for c in lf_chunks] == expected_ids
    assert [c.text for c in crlf_chunks] == [c.text for c in lf_chunks] == ["intro", "## A w1 w2", "## B w3"]
