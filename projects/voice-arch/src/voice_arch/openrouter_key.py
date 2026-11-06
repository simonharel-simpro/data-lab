"""Cost attribution from OpenRouter's key usage (D-6): cost of a block = the key's usage delta around it."""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from types import TracebackType
from typing import Final, Self

import httpx

logger = logging.getLogger(__name__)

KEY_URL: Final = "https://openrouter.ai/api/v1/key"
_TIMEOUT_S: Final = 10.0


class OpenRouterKeyError(Exception):
    """The key endpoint failed or answered something that is not a usage figure (never read as 0)."""


@dataclass(frozen=True)
class KeyUsage:
    usage: float
    limit_remaining: float | None


def _parse(response: httpx.Response) -> KeyUsage:
    if response.status_code != 200:
        raise OpenRouterKeyError(f"HTTP {response.status_code}")
    try:
        data = response.json()["data"]
        usage = data["usage"]
        remaining = data.get("limit_remaining")
    except (ValueError, KeyError, TypeError, AttributeError) as err:
        raise OpenRouterKeyError("unexpected /key body: no data.usage") from err
    if isinstance(usage, bool) or not isinstance(usage, int | float):
        raise OpenRouterKeyError(f"data.usage is not a number: {type(usage).__name__}")
    if remaining is not None and (isinstance(remaining, bool) or not isinstance(remaining, int | float)):
        raise OpenRouterKeyError(f"data.limit_remaining is not a number: {type(remaining).__name__}")
    return KeyUsage(usage=float(usage), limit_remaining=None if remaining is None else float(remaining))


def key_usage(api_key: str, *, client: httpx.Client | None = None) -> KeyUsage:
    headers = {"Authorization": f"Bearer {api_key}"}
    try:
        if client is None:
            with httpx.Client(timeout=_TIMEOUT_S) as own:
                return _parse(own.get(KEY_URL, headers=headers))
        return _parse(client.get(KEY_URL, headers=headers))
    except httpx.HTTPError as err:
        raise OpenRouterKeyError(f"transport error: {type(err).__name__}") from err


class SpendTracker:
    """Reads the key usage on enter and exit. A failed read leaves `cost_usd` None and never raises (F-12)."""

    def __init__(
        self,
        api_key: str,
        *,
        client: httpx.Client | None = None,
        on_exit: Callable[[float], None] | None = None,
    ) -> None:
        self._api_key = api_key
        self._client = client
        self._on_exit = on_exit
        self._before: float | None = None
        self.remaining_before: float | None = None
        self.cost_usd: float | None = None

    def _read(self) -> KeyUsage | None:
        try:
            return key_usage(self._api_key, client=self._client)
        except OpenRouterKeyError as err:
            logger.warning("OpenRouter key usage unreadable, cost not attributed: %s", err)
            return None

    def __enter__(self) -> Self:
        before = self._read()
        if before is not None:
            self._before = before.usage
            self.remaining_before = before.limit_remaining
        return self

    def spent_now(self) -> float | None:
        now = self._read()
        if now is None or self._before is None:
            return None
        return now.usage - self._before

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.cost_usd = self.spent_now()
        if self.cost_usd is not None and self._on_exit is not None:
            self._on_exit(self.cost_usd)
