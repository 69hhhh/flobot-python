from dataclasses import dataclass


@dataclass(frozen=True)
class Move:
    start: int
    end: int
    weight: int = 0
    split: bool = False
