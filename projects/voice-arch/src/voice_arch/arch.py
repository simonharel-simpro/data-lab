"""The three control architectures. Pure: no LiveKit import, so dispatch metadata is checked without a worker."""

from enum import StrEnum


class UnknownArchError(ValueError):
    pass


class Arch(StrEnum):
    A = "a"
    B = "b"
    C = "c"


def parse_arch(raw: str | None) -> Arch:
    """Exact lowercase value only; no default, so a bad dispatch fails loudly (F-9)."""
    try:
        return Arch(raw)
    except ValueError as err:
        raise UnknownArchError(f"unknown arch {raw!r}; expected one of a, b, c") from err
