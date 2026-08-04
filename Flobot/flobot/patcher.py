from collections.abc import Sequence
from typing import TypeVar

T = TypeVar("T")


def patch(old: Sequence[T], diff: Sequence[T | int]) -> list[T]:
    """Apply a generals.io alternating copy/replace diff to an array."""
    output: list[T] = []
    cursor = 0
    while cursor < len(diff):
        matching = int(diff[cursor])
        if matching:
            output.extend(old[len(output) : len(output) + matching])
        cursor += 1

        if cursor < len(diff):
            mismatching = int(diff[cursor])
            if mismatching:
                start = cursor + 1
                output.extend(diff[start : start + mismatching])  # type: ignore[arg-type]
                cursor += mismatching
        cursor += 1
    return output
