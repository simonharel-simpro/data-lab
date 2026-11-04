"""The pilot's Weaviate collection: vectors computed by the `text2vec-transformers` module (D-5), no embedding here."""

import logging
from enum import StrEnum
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
    """The collection's object count never matched the chunk count, even after one rebuild (F-13)."""


def index_name(embedder: str, size: int, overlap: int) -> str:
    """The embedder id is one of the hashed parts, so another model never reuses these vectors (U-13)."""
    return collection_name("mini-rag", "t2v", embedder, f"w{size}o{overlap}")


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


def ensure_collection(
    client: WeaviateClient, chunks: list[Chunk], *, size: int, overlap: int, embedder: str = EMBEDDER
) -> str:
    """Reuse a complete collection; else build it, and rebuild once if the count is short, then raise (F-13)."""
    name = index_name(embedder, size, overlap)
    if client.collections.exists(name) and _count(client, name) == len(chunks):
        logger.info("reusing complete collection %s (%d chunks)", name, len(chunks))
        return name
    for attempt in (1, 2):
        _build(client, name, chunks)
        found = _count(client, name)
        if found == len(chunks):
            return name
        logger.warning("collection %s holds %d objects, expected %d (attempt %d)", name, found, len(chunks), attempt)
    raise IndexBuildError(f"collection {name} holds {found} objects after a rebuild, expected {len(chunks)}")


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
