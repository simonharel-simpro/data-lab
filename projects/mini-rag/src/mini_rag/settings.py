"""Pilot-only settings (`MINI_RAG_*`); the shared infra settings come from `datalab.settings.Settings`."""

import re
from typing import Self
from urllib.parse import urlsplit

from pydantic import SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

OPENROUTER_HOST = "openrouter.ai"


def is_openrouter(url: str) -> bool:
    host = (urlsplit(url).hostname or "").lower()
    return host == OPENROUTER_HOST or host.endswith(f".{OPENROUTER_HOST}")


class PilotSettings(BaseSettings):
    # hide_input_in_errors: a validation error must not echo the settings, which carry the API key.
    model_config = SettingsConfigDict(
        env_prefix="MINI_RAG_", env_file=".env", env_ignore_empty=True, extra="ignore", hide_input_in_errors=True
    )

    # Any Anthropic Messages API endpoint: OpenRouter by default, the LAN DGX by override.
    llm_base_url: str = "https://openrouter.ai/api"
    # Required for OpenRouter (checked at startup, before any I/O, F-13); the unauthenticated DGX needs none.
    llm_api_key: SecretStr | None = None
    gen_model: str = "deepseek/deepseek-v4-flash"
    # OpenRouter only: the upstream providers allowed to serve the model, in order, all at one quantization.
    # Its ~15 providers run fp4/fp8/mxfp4 weights; unrestricted routing makes runs non-reproducible, and a
    # single provider fails runs whenever it is overloaded. Which one served each answer is logged.
    openrouter_providers: str = "deepinfra,gmicloud,parasail"
    openrouter_quantization: str = "fp8"
    gen_timeout_s: float = 60
    max_tokens: int = 512
    # Renamed to llm_base_url; declared only to refuse it loudly instead of silently switching to OpenRouter.
    dgx_base_url: str | None = None

    @field_validator("llm_base_url")
    @classmethod
    def _needs_scheme(cls, v: str) -> str:
        # RFC 3986 scheme + "://" + non-empty, whitespace-free remainder (urlsplit("host:port").scheme == "host").
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9+.-]*://\S+", v):
            raise ValueError(f"llm_base_url must be a URL with a scheme, e.g. https://host/api, got {v!r}")
        return v

    @field_validator("openrouter_providers")
    @classmethod
    def _provider_slugs(cls, v: str) -> str:
        slugs = [s.strip() for s in v.split(",")]
        if not all(re.fullmatch(r"[a-z0-9][a-z0-9._/-]*", s) for s in slugs):
            raise ValueError(f"openrouter_providers must be comma-separated provider slugs, got {v!r}")
        return ",".join(slugs)

    @property
    def provider_list(self) -> list[str]:
        return self.openrouter_providers.split(",")

    @model_validator(mode="after")
    def _endpoint_is_consistent(self) -> Self:
        if self.dgx_base_url is not None:
            raise ValueError(
                "MINI_RAG_DGX_BASE_URL was renamed: set MINI_RAG_LLM_BASE_URL (and MINI_RAG_GEN_MODEL) to use the DGX, "
                "or delete it to use OpenRouter"
            )
        if is_openrouter(self.llm_base_url):
            if self.llm_api_key is None:
                raise ValueError(
                    "MINI_RAG_LLM_API_KEY is required for OpenRouter (https://openrouter.ai/settings/keys)"
                )
        elif "gen_model" not in self.model_fields_set:
            # The default is an OpenRouter slug; another endpoint (the DGX serves `deepseek-v4-flash`) rejects it.
            raise ValueError(f"set MINI_RAG_GEN_MODEL for {self.llm_base_url}: the default model id is OpenRouter's")
        return self


def public_url(url: str) -> str:
    """The URL without userinfo, query or fragment: what may be logged."""
    parts = urlsplit(url)
    host = parts.hostname or ""
    netloc = f"[{host}]" if ":" in host else host
    if parts.port is not None:
        netloc += f":{parts.port}"
    return f"{parts.scheme}://{netloc}{parts.path}"
