from enum import Enum
from typing import TypeVar

_S = TypeVar("_S", bound="StrEnum")


class StrEnum(str, Enum):
    """
    Enum where members are also (and must be) strings
    """

    def __new__(cls: type[_S], *values: str) -> _S:
        if len(values) > 3:
            msg = f"too many arguments for str(): {values!r}"
            raise TypeError(msg)
        if len(values) == 1 and not isinstance(values[0], str):
            # it must be a string
            msg = f"{values[0]!r} is not a string"
            raise TypeError(msg)
        if len(values) >= 2 and not isinstance(values[1], str):
            # check that encoding argument is a string
            msg = f"encoding must be a string, not {values[1]!r}"
            raise TypeError(msg)
        if len(values) == 3 and not isinstance(values[2], str):
            # check that errors argument is a string
            msg = f"errors must be a string, not {values[2]!r}"
            raise TypeError(msg)
        value = str(*values)
        member = str.__new__(cls, value)
        member._value_ = value
        return member

    __str__ = str.__str__

    @staticmethod
    def _generate_next_value_(name: str, start: int, count: int, last_values: list[str]) -> str:  # noqa: ARG004
        """
        Return the lower-cased version of the member name.
        """
        return name.lower()
