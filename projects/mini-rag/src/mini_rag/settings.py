"""Pilot-only settings (`MINI_RAG_*`); the shared infra settings come from `datalab.settings.Settings`."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class PilotSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MINI_RAG_", env_file=".env", env_ignore_empty=True, extra="ignore")

    # Required, no default: a missing DGX URL fails at startup, before any I/O (F-13).
    dgx_base_url: str
    gen_model: str = "deepseek-v4-flash"
    gen_timeout_s: float = 60
    max_tokens: int = 512
