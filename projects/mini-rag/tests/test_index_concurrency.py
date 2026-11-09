import threading
from pathlib import Path
from typing import Any, cast

import pytest
from weaviate import WeaviateClient

from mini_rag import index
from mini_rag.index import EMBEDDER, ensure_collection, index_name
from tests.test_index import _CHUNKS, _CORPUS, _HITS, _response


class _RacingCollections:
    """Thread-safe fake: the first batch keeps its tail unwritten until `release`, so a rival sees a partial count."""

    def __init__(self) -> None:
        self.mutex, self.calls, self.stored, self.exists_now = threading.Lock(), [], 0, False
        self.in_batch, self.release = threading.Event(), threading.Event()
        self.first_batch_done = False

    def _log(self, event: tuple[str, str]) -> None:
        with self.mutex:
            self.calls.append(event)

    def exists(self, name: str) -> bool:
        return self.exists_now

    def delete(self, name: str) -> None:
        self._log(("delete", name))
        self.exists_now, self.stored = False, 0

    def create(self, name: str, **_: Any) -> Any:
        self._log(("create", name))
        self.exists_now = True
        return self.get(name)

    def get(self, name: str) -> Any:
        fake = self

        class _Batch:
            def __init__(self) -> None:
                self.pending, self.slow = 0, not fake.first_batch_done
                fake.first_batch_done = True

            def __enter__(self) -> "_Batch":
                return self

            def add_object(self, **_: Any) -> None:
                if fake.stored == 0:
                    fake.stored = 1
                else:
                    self.pending += 1

            def __exit__(self, *_: object) -> None:
                if self.slow:
                    fake.in_batch.set()
                    fake.release.wait(timeout=5)
                fake.stored += self.pending
                fake._log(("batch_done", name))

        class _Collection:
            class batch:
                fixed_size = staticmethod(lambda batch_size: _Batch())
                failed_objects = ()

            class aggregate:
                over_all = staticmethod(lambda total_count: type("Agg", (), {"total_count": fake.stored})())

            class query:
                near_text = staticmethod(lambda query, limit: _response(_HITS[:1] if fake.stored else []))

        return _Collection()


def test_12_concurrent_ensure_collection_never_deletes_a_build_in_progress(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(index, "LOCK_DIR", tmp_path)
    fake = _RacingCollections()
    client = cast(WeaviateClient, type("Client", (), {"collections": fake})())
    name = index_name(EMBEDDER, 120, 20, _CORPUS)
    names: list[str] = []

    def call() -> None:
        names.append(ensure_collection(client, _CHUNKS, size=120, overlap=20, corpus=_CORPUS))

    first, second = threading.Thread(target=call), threading.Thread(target=call)
    first.start()
    assert fake.in_batch.wait(timeout=5)  # A has created the collection and is mid-batch
    second.start()
    second.join(timeout=0.5)  # B either blocks on the lock (fixed) or runs on and deletes A's build (bug)
    fake.release.set()
    for thread in (first, second):
        thread.join(timeout=5)

    assert [t.is_alive() for t in (first, second)] == [False, False]
    assert names == [name, name]
    assert fake.calls.count(("create", name)) == 1
    assert ("delete", name) not in fake.calls[: fake.calls.index(("batch_done", name))]
    assert fake.stored == len(_CHUNKS)
