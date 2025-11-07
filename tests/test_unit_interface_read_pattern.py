import pytest

from gusnet.interface import _Patterns


@pytest.fixture
def wn():
    import wntr

    return wntr.network.WaterNetworkModel()


# @pytest.mark.parametrize(
#     ("pattern_in", "expected_output"),
#     [("1 2", [1.0, 2.0]), (" 1 2 ", [1.0, 2.0]), ("1", [1.0]), ("1.0  2.0", [1.0, 2.0])],
# )
# def test_read_pattern_string(pattern_in, expected_output):
#     assert _Patterns.read_pattern(pattern_in) == expected_output


# @pytest.mark.parametrize(
#     ("pattern_in", "expected_output"),
#     [
#         ([1.0, 2.0], [1.0, 2.0]),
#         ([1, 2], [1.0, 2.0]),
#         ((1, 2), [1.0, 2.0]),
#     ],
# )
# def test_read_pattern_list(pattern_in, expected_output):
#     assert _Patterns.read_pattern(pattern_in) == expected_output


def test_patterns_add(wn):
    patterns = _Patterns(wn)
    pattern_name = patterns.add("1 2 3")
    assert pattern_name == "2"


def test_patterns_get(wn):
    patterns = _Patterns(wn)
    pattern_name = patterns.add("1 2 3")
    pattern = patterns.get_str_or_none(pattern_name)
    assert pattern == "1.0 2.0 3.0"


def test_patterns_add_empty(wn):
    patterns = _Patterns(wn)
    pattern_name = patterns.add("")
    assert pattern_name is None
