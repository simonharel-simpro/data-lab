"""Connection settings for the shared stack; only `DATALAB_*` env vars are read (F-5)."""

from collections.abc import Iterator
from contextlib import contextmanager

import weaviate
from pydantic_settings import BaseSettings, SettingsConfigDict
from weaviate.classes.init import AdditionalConfig, Timeout


class Settings(BaseSettings):
    # The prefix keeps a stray shell MLFLOW_TRACKING_URI (e.g. Demo-RAG's :5000) from being picked up (F-5).
    model_config = SettingsConfigDict(env_prefix="DATALAB_", env_file=".env", env_ignore_empty=True, extra="ignore")

    weaviate_host: str = "127.0.0.1"
    weaviate_http_port: int = 8090
    weaviate_grpc_port: int = 50052
    mlflow_tracking_uri: str = "http://127.0.0.1:5050"


@contextmanager
def connect_weaviate(settings: Settings) -> Iterator[weaviate.WeaviateClient]:
    """Both ports explicit: a default gRPC port would reach Demo-RAG's Weaviate (split brain, F-4)."""
    client = weaviate.connect_to_local(
        host=settings.weaviate_host,
        port=settings.weaviate_http_port,
        grpc_port=settings.weaviate_grpc_port,
        additional_config=AdditionalConfig(timeout=Timeout(init=10, query=60, insert=300)),
    )
    try:
        yield client
    finally:
        client.close()
