from __future__ import annotations

from collections.abc import Iterable


class Pattern(tuple):
    def __new__(cls, pattern: Iterable[float] | str | None = None):
        if pattern is None:
            return super().__new__(cls)

        pattern_parts = pattern.strip().split() if isinstance(pattern, str) else pattern

        try:
            return super().__new__(cls, (float(item) for item in pattern_parts))
        except (ValueError, TypeError):
            raise ValueError(pattern) from None

    def __str__(self) -> str:
        return " ".join(map(str, self))
