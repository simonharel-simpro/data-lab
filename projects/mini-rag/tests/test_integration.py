"""Live stack only (`docker compose up -d`): builds or reuses the pilot's real collection and leaves it in place.

The collection is the one `mini_rag.run` uses (exact name from `index_name`); nothing is deleted, never by prefix.
"""

import pytest

from datalab.settings import Settings, connect_weaviate
from mini_rag.corpus import load_corpus
from mini_rag.index import Retrieval, corpus_hash, ensure_collection, search
from tests.conftest import CORPUS_DIR

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("mode", list(Retrieval))
def test_integration_bm25_and_vector_return_hits(mode: Retrieval) -> None:
    chunks = load_corpus(CORPUS_DIR, size=120, overlap=20)
    with connect_weaviate(Settings(_env_file=None)) as client:  # type: ignore[call-arg]  # settings kwarg
        name = ensure_collection(client, chunks, size=120, overlap=20, corpus=corpus_hash(chunks))
        hits = search(client, name, "Which port does MLflow use?", mode, 3)

    assert len(hits) == 3
    assert any("5050" in hit.text for hit in hits)
