"""Project settings (`VOICE_ARCH_*`); the shared infra settings come from `datalab.settings.Settings`."""

import re
from typing import Self
from urllib.parse import urlsplit

from pydantic import AliasChoices, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from datalab.project import repo_root


class VoiceSettings(BaseSettings):
    # The project .env (cwd) comes last, so it wins over the repo-root one. hide_input_in_errors: a validation
    # error must not echo the settings, which carry the API keys.
    model_config = SettingsConfigDict(
        env_prefix="VOICE_ARCH_",
        env_file=(repo_root() / ".env", ".env"),
        env_ignore_empty=True,
        extra="ignore",
        hide_input_in_errors=True,
    )

    # The prefixed name first, then the repo-root key. Source priority still beats alias order: an exported shell
    # OPENROUTER_API_KEY overrides a project-file VOICE_ARCH_OPENROUTER_API_KEY.
    openrouter_api_key: SecretStr = Field(
        validation_alias=AliasChoices("VOICE_ARCH_OPENROUTER_API_KEY", "OPENROUTER_API_KEY")
    )
    experiment_budget_usd: float = Field(default=50.0, gt=0)

    livekit_url: str = "ws://127.0.0.1:7880"
    livekit_api_key: SecretStr
    livekit_api_secret: SecretStr

    # Defaults until the stage-1 bench decides (the reason goes in PROJECT.md).
    stt_model: str = "assemblyai/universal-3-6-pro"
    tts_model: str = "deepgram/aura-2"
    tts_voice: str = "aura-2-thalia-en"
    llm_model: str = "google/gemini-3.5-flash-lite"
    # PROVISIONAL (ESC-1-2): D-17 needs caller != agent; haiku scored 20/20 in the LLM bench. User confirms later.
    caller_llm_model: str = "anthropic/claude-haiku-5.5"
    caller_temperature: float = 0.7

    # Same pinning rationale as mini-rag: unrestricted OpenRouter routing makes runs non-reproducible. The agent
    # LLM is pinned to Google's own endpoints (ESC-2-1 option C); they report quantization "unknown", so no
    # quantization filter by default (it would exclude them). The caller LLM stays unpinned (ESC-1-2).
    openrouter_providers: str = "google-vertex,google-ai-studio"
    openrouter_quantization: str | None = None

    call_timeout_s: float = 240
    agent_join_timeout_s: float = 20

    @field_validator("livekit_url")
    @classmethod
    def _ws_scheme(cls, v: str) -> str:
        if urlsplit(v).scheme not in {"ws", "wss"}:
            raise ValueError(f"livekit_url must use the ws or wss scheme, got {v!r}")
        return v

    @field_validator("openrouter_providers")
    @classmethod
    def _provider_slugs(cls, v: str) -> str:
        slugs = [s.strip() for s in v.split(",")]
        if not all(re.fullmatch(r"[a-z0-9][a-z0-9._/-]*", s) for s in slugs):
            raise ValueError(f"openrouter_providers must be comma-separated provider slugs, got {v!r}")
        return ",".join(slugs)

    @model_validator(mode="after")
    def _caller_differs_from_agent(self) -> Self:
        if self.caller_llm_model == self.llm_model:
            raise ValueError("caller_llm_model must differ from llm_model (D-17)")
        return self

    @property
    def provider_list(self) -> list[str]:
        return self.openrouter_providers.split(",")
