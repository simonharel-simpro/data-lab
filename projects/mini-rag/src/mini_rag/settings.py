"""Pilot-only settings (`MINI_RAG_*`); the shared infra settings come from `datalab.settings.Settings`."""

import re

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class PilotSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MINI_RAG_", env_file=".env", env_ignore_empty=True, extra="ignore")

    # Any Anthropic Messages API endpoint: OpenRouter by default, the LAN DGX by override.
    llm_base_url: str = "https://openrouter.ai/api"
    # Required, no default: a missing key fails at startup, before any I/O (F-13). The DGX ignores it.
    llm_api_key: SecretStr
    gen_model: str = "deepseek/deepseek-v4-flash"
    gen_timeout_s: float = 60
    max_tokens: int = 512

    @field_validator("llm_base_url")
    @classmethod
    def _needs_scheme(cls, v: str) -> str:
        # RFC 3986 scheme + "://" + non-empty, whitespace-free remainder (urlsplit("host:port").scheme == "host").
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9+.-]*://\S+", v):
            raise ValueError(f"llm_base_url must be a URL with a scheme, e.g. https://host/api, got {v!r}")
        return v
