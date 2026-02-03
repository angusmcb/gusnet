from __future__ import annotations

import ast
from collections.abc import Iterable
from typing import ClassVar, Self, SupportsFloat


class Pattern(str):
    """A representation of a simple pattern. Stored as a string, with multipliers as attribute.

    Will raise PatternReadError(ValueError) if invalid pattern is provided.

    Factory methods can be used if None is preferred for empty patterns, or if input type is uncertain."""

    multipliers: tuple[float, ...]

    _cache: ClassVar[dict] = {}

    def __new__(cls, pattern: Iterable[SupportsFloat | str] | str = "") -> Self:
        try:
            return cls._cache[pattern]
        except (TypeError, KeyError):
            pass

        pattern_parts = pattern.split() if isinstance(pattern, str) else pattern

        try:
            float_list = [float(item) for item in pattern_parts]
        except (ValueError, TypeError):
            raise PatternReadError(pattern) from None

        obj_str = " ".join(map(str, float_list))

        obj = super().__new__(cls, obj_str)
        obj.multipliers = tuple(float_list)

        try:
            cls._cache[obj_str] = obj
            cls._cache[pattern] = obj
        except TypeError:
            pass

        return obj


class Curve(str):
    _points: list[tuple[float, float]]
    _cache: ClassVar[dict[str, Curve]] = {}

    def __new__(cls, curve: Iterable[tuple[float, float]] | str | None = None):
        points: Iterable[tuple[float, float]]

        if curve is None:
            points = []
        elif isinstance(curve, str):
            # Check cache for string curves (most common case from INP files)
            if curve in cls._cache:
                return cls._cache[curve]
            points = _read_curve_str(curve)
        else:
            points = curve

        final_points = []
        last_x: float = -float("inf")
        try:
            for point in points:
                try:
                    x = float(point[0])
                    y = float(point[1])
                except ValueError as e:
                    raise CurveReadError(str(curve), e) from e

                if x <= last_x:
                    raise CurveXNotIncreasingError(str(curve))
                last_x = x
                final_points.append((x, y))
        except TypeError as e:
            raise CurveReadError(str(curve), e) from e

        point_strings = [f"({x}, {y})" for x, y in final_points]
        obj = super().__new__(cls, ", ".join(point_strings))
        obj._points = final_points

        # Cache the result if input was a string
        if isinstance(curve, str):
            cls._cache[curve] = obj

        return obj

    def __iter__(self):
        return self._points.__iter__()

    @classmethod
    def factory(cls, curve: Iterable[tuple[float, float]] | str | None = None) -> Curve | None:
        if curve_class := cls(curve):
            return curve_class
        else:
            return None


def _read_curve_str(curve_string: str) -> list[tuple[float, float]]:
    """Read a curve from a string"""

    if curve_string.strip() == "":
        return []

    try:
        curve_points_input: list = ast.literal_eval(curve_string)
    except Exception:
        msg = "Couldn't convert string to list of points"
        raise CurveReadError(curve_string, msg) from None

    try:
        curve_points_length = len(curve_points_input)
    except TypeError:
        msg = "Couldn't convert string to list of points"
        raise CurveReadError(curve_string, msg) from None

    if curve_points_length == 2:
        try:
            return [(float(curve_points_input[0]), float(curve_points_input[1]))]
        except (ValueError, TypeError):
            pass

    curve_points = []

    for point in curve_points_input:
        try:
            point_length = len(point)
        except TypeError:
            msg = f"Point '{point}' is not an x, y tuple"
            raise CurveReadError(curve_string, msg) from None
        if point_length != 2:
            msg = f"Point '{point}' is not an x, y tuple"
            raise CurveReadError(curve_string, msg)

        try:
            x = float(point[0])
        except (ValueError, TypeError):
            msg = f"In point '{point}', '{point[0]} is not a number"
            raise CurveReadError(curve_string, msg) from None
        try:
            y = float(point[1])
        except (ValueError, TypeError):
            msg = f"In point '{point}', '{point[0]} is not a number"
            raise CurveReadError(curve_string, msg) from None

        curve_points.append((x, y))

    if not len(curve_points):
        msg = "There are no points in the curve"
        raise CurveReadError(curve_string, msg)

    return curve_points


class PatternReadError(ValueError):
    pass


class CurveReadError(ValueError):
    def __init__(self, curve_string: str, message: str | Exception | None = None):
        super().__init__(curve_string)
        if message and hasattr(self, "add_note"):
            self.add_note(str(message))


class CurveXNotIncreasingError(CurveReadError):
    def __init__(self, curve_string: str):
        message = "x-values in curve must be strictly increasing"
        super().__init__(curve_string, message)
