"""The pilot's Weaviate collection: vectors computed by the `text2vec-transformers` module (D-5), no embedding here."""

import fcntl  # POSIX-only: data-lab runs on Linux/WSL (ADR 3)
import hashlib
import json
import logging
import tempfile
from collections.abc import Generator
from contextlib import contextmanager
from enum import StrEnum
from pathlib import Path
from typing import Final

from weaviate import WeaviateClient
from weaviate.classes.config import Configure, DataType, Property, Tokenization
from weaviate.util import generate_uuid5

from datalab.project import collection_name
from mini_rag.corpus import Chunk

logger = logging.getLogger(__name__)

# Must match the compose vectorizer image (`baai-bge-small-en-v1.5-1.13.3`, D-5); a test guards it.
EMBEDDER: Final = "bge-small-en-v1.5"
INSERT_BATCH: Final = 64
LOCK_DIR: Final = Path(tempfile.gettempdir()) / "datalab-index-locks"
_PROPERTIES: Final = [
    Property(name="text", data_type=DataType.TEXT, tokenization=Tokenization.WORD),
    # ids: exact-match only, never BM25 terms nor part of the embedded text
    Property(name="chunk_id", data_type=DataType.TEXT, tokenization=Tokenization.FIELD, index_searchable=False),
    Property(name="doc", data_type=DataType.TEXT, tokenization=Tokenization.FIELD, index_searchable=False),
]


class Retrieval(StrEnum):
    BM25 = "bm25"
    VECTOR = "vector"


class IndexBuildError(RuntimeError):
    """The collection never held every chunk AND answered a vector search, even after one rebuild (F-13)."""


def corpus_hash(chunks: list[Chunk]) -> str:
    return hashlib.sha256(json.dumps([[c.chunk_id, c.text] for c in chunks]).encode("utf-8")).hexdigest()[:12]


def index_name(embedder: str, size: int, overlap: int, corpus: str) -> str:
    """The embedder id is one of the hashed parts, so another model never reuses these vectors (U-13).

    The corpus hash is another: a corpus edit gets a new collection, never stale vectors.
    """
    return collection_name("mini-rag", "t2v", embedder, f"w{size}o{overlap}", f"c{corpus}")


def _count(client: WeaviateClient, name: str) -> int:
    return int(client.collections.get(name).aggregate.over_all(total_count=True).total_count or 0)


def _build(client: WeaviateClient, name: str, chunks: list[Chunk]) -> None:
    if client.collections.exists(name):
        client.collections.delete(name)  # our own exact name only, never a prefix
    collection = client.collections.create(
        name,
        vector_config=Configure.Vectors.text2vec_transformers(
            source_properties=["text"], vectorize_collection_name=False
        ),
        properties=_PROPERTIES,
    )
    with collection.batch.fixed_size(batch_size=INSERT_BATCH) as batch:
        for chunk in chunks:
            batch.add_object(
                properties={"text": chunk.text, "chunk_id": chunk.chunk_id, "doc": chunk.doc},
                uuid=generate_uuid5(chunk.chunk_id),
            )
    failed = collection.batch.failed_objects
    if failed:
        logger.warning("%d objects failed to import into %s: %s", len(failed), name, failed[0].message)


def _searchable(client: WeaviateClient, name: str, probe: str) -> bool:
    """No try/except: with the vectorizer down `near_text` raises, and a rebuild could not help (S-15b)."""
    return bool(client.collections.get(name).query.near_text(query=probe, limit=1).objects)


def _complete(client: WeaviateClient, name: str, chunks: list[Chunk]) -> bool:
    if not client.collections.exists(name):
        return False
    found = _count(client, name)
    if found != len(chunks):
        logger.warning("collection %s holds %d objects, expected %d", name, found, len(chunks))
        return False
    if not _searchable(client, name, chunks[0].text):
        logger.warning("collection %s holds every object but its vector search returns nothing", name)
        return False
    return True


@contextmanager
def _build_lock(name: str) -> Generator[None]:
    """One builder per collection name on this host; Weaviate is local (127.0.0.1), so the host is the scope."""
    LOCK_DIR.mkdir(parents=True, exist_ok=True)
    with (LOCK_DIR / f"{name}.lock").open("w") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        yield


def ensure_collection(  # noqa: PLR0913  # index identity (size/overlap/corpus/embedder), kw-only (#39)
    client: WeaviateClient, chunks: list[Chunk], *, size: int, overlap: int, corpus: str, embedder: str = EMBEDDER
) -> str:
    """Reuse a complete collection; else build it, rebuild once, then raise (F-13).

    Complete = the right count AND a vector probe answers (the HNSW-loss incident). Serialized per name (#12).
    """
    if not chunks:
        raise IndexBuildError("no chunks to index")
    name = index_name(embedder, size, overlap, corpus)
    with _build_lock(name):
        if _complete(client, name, chunks):
            logger.info("reusing complete collection %s (%d chunks)", name, len(chunks))
            return name
        for _attempt in (1, 2):
            _build(client, name, chunks)
            if _complete(client, name, chunks):
                return name
    raise IndexBuildError(
        f"collection {name} is incomplete after a rebuild: expected {len(chunks)} objects "
        "and a vector search that returns them (vector search returns nothing, or the count is short)"
    )


def search(client: WeaviateClient, name: str, query: str, mode: Retrieval, k: int) -> list[Chunk]:
    collection = client.collections.get(name)
    if mode is Retrieval.BM25:
        res = collection.query.bm25(query=query, query_properties=["text"], limit=k)
    else:
        res = collection.query.near_text(query=query, limit=k)
    return [
        Chunk(chunk_id=str(o.properties["chunk_id"]), doc=str(o.properties["doc"]), text=str(o.properties["text"]))
        for o in res.objects
    ]
