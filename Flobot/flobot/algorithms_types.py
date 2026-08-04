from typing import Protocol


class Reachable(Protocol):
    index: int
    general_distance: int
