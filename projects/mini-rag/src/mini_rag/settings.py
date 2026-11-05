"""Pilot-only settings (`MINI_RAG_*`); the shared infra settings come from `datalab.settings.Settings`."""

import re

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class PilotSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MINI_RAG_", env_file=".env", env_ignore_empty=True, extra="ignore")

    # Required, no default: a missing DGX URL fails at startup, before any I/O (F-13).
    dgx_base_url: str
    gen_model: str = "deepseek-v4-flash"
    gen_timeout_s: float = 60
    max_tokens: int = 512

    @field_validator("dgx_base_url")
    @classmethod
    def _needs_scheme(cls, v: str) -> str:
        # RFC 3986 scheme + "://" + non-empty, whitespace-free remainder (urlsplit("host:port").scheme == "host").
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9+.-]*://\S+", v):
            raise ValueError(f"dgx_base_url must be a URL with a scheme, e.g. http://host:port, got {v!r}")
        return v
