import logging
import re
from typing import Any, cast

import pytest
import yaml
from weaviate import WeaviateClient

from mini_rag.corpus import Chunk
from mini_rag.index import EMBEDDER, IndexBuildError, Retrieval, corpus_hash, ensure_collection, index_name, search
from tests.conftest import REPO_ROOT


def test_u_13_embedder_id_is_part_of_collection_hash() -> None:
    ours, other = index_name("bge-small-en-v1.5", 120, 20, "c0"), index_name("other", 120, 20, "c0")

    assert ours != other
    assert ours.startswith("MiniRag_")
    assert other.startswith("MiniRag_")


def test_index_name_depends_on_chunking() -> None:
    assert index_name(EMBEDDER, 120, 20, "c0") != index_name(EMBEDDER, 100, 20, "c0")
    assert index_name(EMBEDDER, 120, 20, "c0") != index_name(EMBEDDER, 120, 10, "c0")


def test_d_5_embedder_matches_compose_vectorizer_image() -> None:
    compose = yaml.safe_load((REPO_ROOT / "compose.yaml").read_text(encoding="utf-8"))
    image = compose["services"]["t2v-transformers"]["image"]
    tag = image.rsplit(":", 1)[1]

    assert re.fullmatch(rf"[a-z]+-{re.escape(EMBEDDER)}-[0-9.]+", tag), f"{EMBEDDER!r} vs compose tag {tag!r}"


class _FakeCollections:
    """Records the calls `ensure_collection` makes; `counts` is what each aggregate returns, in order."""

    def __init__(
        self, *, exists: bool, counts: list[int], failed: list[Any] | None = None, empty_probes: int = 0
    ) -> None:
        self._exists, self.counts, self.calls = exists, counts, []
        self.empty_probes, self.probes = empty_probes, 0  # the first `empty_probes` vector probes find nothing
        self.failed = failed or []
        self.queries: list[tuple[str, dict[str, Any]]] = []
        self.hits: list[dict[str, str]] = []

    def exists(self, name: str) -> bool:
        return self._exists

    def delete(self, name: str) -> None:
        self.calls.append(("delete", name))
        self._exists = False

    def create(self, name: str, **_: Any) -> Any:
        self.calls.append(("create", name))
        self._exists = True
        return self.get(name)

    def get(self, name: str) -> Any:
        fake = self

        class _Batch:
            def __enter__(self) -> "_Batch":
                return self

            def __exit__(self, *_: object) -> None:
                return None

            def add_object(self, **_: Any) -> None:
                return None

        class _Collection:
            class batch:  # mirrors the client attribute name
                @staticmethod
                def fixed_size(batch_size: int) -> _Batch:
                    return _Batch()

                failed_objects = fake.failed

            class aggregate:
                @staticmethod
                def over_all(total_count: bool) -> Any:
                    return type("Agg", (), {"total_count": fake.counts.pop(0)})()

            class query:  # records the call and returns hits shaped like the client's response
                @staticmethod
                def bm25(query: str, query_properties: list[str], limit: int) -> Any:
                    fake.queries.append(("bm25", {"query": query, "properties": query_properties, "limit": limit}))
                    return _response(fake.hits)

                @staticmethod
                def near_text(query: str, limit: int) -> Any:
                    fake.queries.append(("near_text", {"query": query, "limit": limit}))
                    if fake.hits:
                        return _response(fake.hits)
                    fake.probes += 1  # an index probe: answers with one hit once `empty_probes` are used up
                    return _response([] if fake.probes <= fake.empty_probes else _HITS[:1])

        return _Collection()


def _response(hits: list[dict[str, str]]) -> Any:
    objects = [type("Obj", (), {"properties": props})() for props in hits]
    return type("Res", (), {"objects": objects})()


def _client(fake: _FakeCollections) -> WeaviateClient:
    return cast(WeaviateClient, type("Client", (), {"collections": fake})())


_CHUNKS = [Chunk(chunk_id=f"d#s0w{i}", doc="d", text=f"text {i}") for i in range(3)]
_CORPUS = corpus_hash(_CHUNKS)


def test_f_13_complete_collection_is_reused() -> None:
    fake = _FakeCollections(exists=True, counts=[3])

    name = ensure_collection(_client(fake), _CHUNKS, size=120, overlap=20, corpus=_CORPUS)

    assert name == index_name(EMBEDDER, 120, 20, _CORPUS)
    assert fake.calls == []


def test_f_13_short_count_rebuilds_once_then_raises() -> None:
    fake = _FakeCollections(exists=True, counts=[2, 2, 1])
    name = index_name(EMBEDDER, 120, 20, _CORPUS)

    with pytest.raises(IndexBuildError, match=name):
        ensure_collection(_client(fake), _CHUNKS, size=120, overlap=20, corpus=_CORPUS)

    assert all(n == name for _, n in fake.calls)
    assert sum(op == "create" for op, _ in fake.calls) == 2


def test_f_13_rebuild_that_reaches_the_count_succeeds() -> None:
    fake = _FakeCollections(exists=False, counts=[2, 3])
    name = index_name(EMBEDDER, 120, 20, _CORPUS)

    assert ensure_collection(_client(fake), _CHUNKS, size=120, overlap=20, corpus=_CORPUS) == name
    assert all(n == name for _, n in fake.calls)
    assert sum(op == "create" for op, _ in fake.calls) == 2


def test_corpus_content_change_with_same_count_gets_a_new_index() -> None:
    edited = [*_CHUNKS[:2], Chunk(chunk_id="d#s0w2", doc="d", text="text 2 edited")]
    same = [Chunk(chunk_id=c.chunk_id, doc=c.doc, text=c.text) for c in _CHUNKS]

    assert len(edited) == len(_CHUNKS)
    assert index_name(EMBEDDER, 120, 20, corpus_hash(edited)) != index_name(EMBEDDER, 120, 20, corpus_hash(_CHUNKS))
    assert index_name(EMBEDDER, 120, 20, corpus_hash(same)) == index_name(EMBEDDER, 120, 20, corpus_hash(_CHUNKS))


_HITS = [
    {"chunk_id": "a#s0w0", "doc": "a", "text": "first passage"},
    {"chunk_id": "b#s1w0", "doc": "b", "text": "second passage"},
]
_EXPECTED = [
    Chunk(chunk_id="a#s0w0", doc="a", text="first passage"),
    Chunk(chunk_id="b#s1w0", doc="b", text="second passage"),
]


def test_search_bm25_maps_objects_to_chunks() -> None:
    fake = _FakeCollections(exists=True, counts=[])
    fake.hits = _HITS

    found = search(_client(fake), "C", "which port", Retrieval.BM25, 2)

    assert found == _EXPECTED
    assert fake.queries == [("bm25", {"query": "which port", "properties": ["text"], "limit": 2})]


def test_search_vector_uses_near_text() -> None:
    fake = _FakeCollections(exists=True, counts=[])
    fake.hits = _HITS

    found = search(_client(fake), "C", "which port", Retrieval.VECTOR, 2)

    assert found == _EXPECTED
    assert fake.queries == [("near_text", {"query": "which port", "limit": 2})]


def test_build_logs_failed_objects(caplog: pytest.LogCaptureFixture) -> None:
    failed = type("Failed", (), {"message": "t2v unreachable"})()
    fake = _FakeCollections(exists=False, counts=[3], failed=[failed])
    name = index_name(EMBEDDER, 120, 20, _CORPUS)

    with caplog.at_level(logging.WARNING, logger="mini_rag.index"):
        ensure_collection(_client(fake), _CHUNKS, size=120, overlap=20, corpus=_CORPUS)

    warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert name in warnings[0]
    assert "t2v unreachable" in warnings[0]


def test_reuse_with_matching_count_but_empty_vector_search_rebuilds() -> None:
    fake = _FakeCollections(exists=True, counts=[3, 3], empty_probes=1)  # HNSW lost: objects intact, near_text empty
    name = index_name(EMBEDDER, 120, 20, _CORPUS)

    assert ensure_collection(_client(fake), _CHUNKS, size=120, overlap=20, corpus=_CORPUS) == name
    assert fake.calls == [("delete", name), ("create", name)]
    assert [q["query"] for _, q in fake.queries] == [_CHUNKS[0].text] * 2  # the probe is the first chunk's text


def test_rebuilt_collection_whose_vector_search_stays_empty_raises() -> None:
    fake = _FakeCollections(exists=True, counts=[3, 3, 3], empty_probes=99)

    with pytest.raises(IndexBuildError, match="vector search"):
        ensure_collection(_client(fake), _CHUNKS, size=120, overlap=20, corpus=_CORPUS)

    assert sum(op == "create" for op, _ in fake.calls) == 2


def test_ensure_collection_without_chunks_is_refused() -> None:
    fake = _FakeCollections(exists=True, counts=[0])

    with pytest.raises(IndexBuildError, match="no chunks"):
        ensure_collection(_client(fake), [], size=120, overlap=20, corpus="c0")

    assert fake.calls == []
