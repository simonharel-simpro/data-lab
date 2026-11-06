import pytest

from voice_arch.arch import Arch, UnknownArchError, parse_arch


@pytest.mark.parametrize("raw", [None, "", "d", "B ", "A"])
def test_f_9_unknown_arch_metadata_is_refused_not_defaulted(raw: str | None) -> None:
    with pytest.raises(UnknownArchError):
        parse_arch(raw)


def test_parse_arch_accepts_known_values() -> None:
    assert [parse_arch(raw) for raw in ("a", "b", "c")] == [Arch.A, Arch.B, Arch.C]
