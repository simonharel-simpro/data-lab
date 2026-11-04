import re
from typing import Any, ClassVar, cast

import pytest
import yaml
from weaviate import WeaviateClient

from mini_rag.corpus import Chunk
from mini_rag.index import EMBEDDER, IndexBuildError, ensure_collection, index_name
from tests.conftest import REPO_ROOT


def test_u_13_embedder_id_is_part_of_collection_hash() -> None:
    ours, other = index_name("bge-small-en-v1.5", 120, 20), index_name("other", 120, 20)

    assert ours != other
    assert ours.startswith("MiniRag_")
    assert other.startswith("MiniRag_")


def test_index_name_depends_on_chunking() -> None:
    assert index_name(EMBEDDER, 120, 20) != index_name(EMBEDDER, 100, 20)
    assert index_name(EMBEDDER, 120, 20) != index_name(EMBEDDER, 120, 10)


def test_d_5_embedder_matches_compose_vectorizer_image() -> None:
    compose = yaml.safe_load((REPO_ROOT / "compose.yaml").read_text(encoding="utf-8"))
    image = compose["services"]["t2v-transformers"]["image"]
    tag = image.rsplit(":", 1)[1]

    assert re.fullmatch(rf"[a-z]+-{re.escape(EMBEDDER)}-[0-9.]+", tag), f"{EMBEDDER!r} vs compose tag {tag!r}"


class _FakeCollections:
    """Records the calls `ensure_collection` makes; `counts` is what each aggregate returns, in order."""

    def __init__(self, *, exists: bool, counts: list[int]) -> None:
        self._exists, self.counts, self.calls = exists, counts, []

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
            failed_objects: ClassVar[list[Any]] = []

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

                failed_objects: ClassVar[list[Any]] = []

            class aggregate:
                @staticmethod
                def over_all(total_count: bool) -> Any:
                    return type("Agg", (), {"total_count": fake.counts.pop(0)})()

        return _Collection()


def _client(fake: _FakeCollections) -> WeaviateClient:
    return cast(WeaviateClient, type("Client", (), {"collections": fake})())


_CHUNKS = [Chunk(chunk_id=f"d#s0w{i}", doc="d", text=f"text {i}") for i in range(3)]


def test_f_13_complete_collection_is_reused() -> None:
    fake = _FakeCollections(exists=True, counts=[3])

    name = ensure_collection(_client(fake), _CHUNKS, size=120, overlap=20)

    assert name == index_name(EMBEDDER, 120, 20)
    assert fake.calls == []


def test_f_13_short_count_rebuilds_once_then_raises() -> None:
    fake = _FakeCollections(exists=True, counts=[2, 2, 1])
    name = index_name(EMBEDDER, 120, 20)

    with pytest.raises(IndexBuildError, match=name):
        ensure_collection(_client(fake), _CHUNKS, size=120, overlap=20)

    assert fake.calls == [("delete", name), ("create", name), ("delete", name), ("create", name)]


def test_f_13_rebuild_that_reaches_the_count_succeeds() -> None:
    fake = _FakeCollections(exists=False, counts=[2, 3])
    name = index_name(EMBEDDER, 120, 20)

    assert ensure_collection(_client(fake), _CHUNKS, size=120, overlap=20) == name
    assert fake.calls == [("create", name), ("delete", name), ("create", name)]
