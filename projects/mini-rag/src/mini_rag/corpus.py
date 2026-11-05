"""The frozen docs snapshot, chunked by `##` section, then by word windows with overlap. Pure."""

from dataclasses import dataclass
from pathlib import Path
from typing import Final

SIZE: Final = 120
OVERLAP: Final = 20


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    doc: str
    text: str


def _sections(text: str) -> list[str]:
    """Split before every `## ` heading; the text above the first one is a section too."""
    parts: list[list[str]] = [[]]
    for line in text.replace("\r\n", "\n").split("\n"):
        if line.startswith("## "):
            parts.append([])
        parts[-1].append(line)
    return ["\n".join(lines) for lines in parts]


def _windows(words: list[str], size: int, overlap: int) -> list[list[str]]:
    """Windows of `size` words, each sharing `overlap` words with the previous one; none is overlap only."""
    out, start = [], 0
    while True:
        out.append(words[start : start + size])
        if start + size >= len(words):
            return out
        start += size - overlap


def chunk_doc(doc: str, text: str, *, size: int = SIZE, overlap: int = OVERLAP) -> list[Chunk]:
    if not 0 <= overlap < size:
        raise ValueError(f"overlap must be in [0, size), got size={size} overlap={overlap}")
    chunks = []
    for s, section in enumerate(_sections(text)):
        words = section.split()
        if not words:
            continue
        for w, window in enumerate(_windows(words, size, overlap)):
            chunks.append(Chunk(chunk_id=f"{doc}#s{s}w{w}", doc=doc, text=" ".join(window)))
    return chunks


def load_corpus(folder: Path, *, size: int = SIZE, overlap: int = OVERLAP) -> list[Chunk]:
    """Every `*.md` of the snapshot, in name order; the doc id is the file stem."""
    files = sorted(folder.glob("*.md"))
    if not files:
        raise ValueError(f"no *.md file in corpus folder {folder}")
    chunks = [
        c for path in files for c in chunk_doc(path.stem, path.read_text(encoding="utf-8"), size=size, overlap=overlap)
    ]
    if not chunks:
        raise ValueError(f"corpus folder {folder} has *.md files but no text to index")
    return chunks
