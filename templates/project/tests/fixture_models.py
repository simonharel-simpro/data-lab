from dataclasses import dataclass

from __DATALAB_PACKAGE__.candidates import Row


@dataclass(frozen=True)
class Offset:
    """A family with a parameter `dummy` lacks: exercises the `model=<family>` form of the eval hint."""

    value: float
    offset: float

    def predict(self, row: Row) -> float:
        return self.value + self.offset
