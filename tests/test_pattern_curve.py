import sys

import pytest

from gusnet.pattern_curve import Curve, CurveReadError, CurveXNotIncreasingError, Pattern, PatternReadError


class TestPattern:
    @pytest.mark.parametrize(
        ("input_val", "expected_list", "expected_str"),
        [
            ([1, 2, 3.5], [1.0, 2.0, 3.5], "1.0 2.0 3.5"),
            ("1 2 3.5", [1.0, 2.0, 3.5], "1.0 2.0 3.5"),
            ([], [], ""),
            ("   ", [], ""),
        ],
    )
    def test_pattern_roundtrip(self, input_val, expected_list, expected_str):
        p = Pattern(input_val)
        assert list(p.multipliers) == expected_list
        assert str(p) == expected_str

    def test_pattern_invalid(self):
        with pytest.raises(PatternReadError):
            Pattern("a b c")


class TestCurve:
    def test_curve_from_list(self):
        c = Curve([(1, 2), (3.5, 4)])
        assert str(c) == "(1.0, 2.0), (3.5, 4.0)"
        assert list(c) == [(1.0, 2.0), (3.5, 4.0)]

    def test_curve_from_str(self):
        c = Curve("[(1,2), (3.5,4)]")
        assert str(c) == "(1.0, 2.0), (3.5, 4.0)"
        assert list(c) == [(1.0, 2.0), (3.5, 4.0)]

    def test_curve_single_point_str(self):
        c = Curve("[1,2]")
        assert str(c) == "(1.0, 2.0)"
        assert list(c) == [(1.0, 2.0)]

    def test_curve_empty(self):
        c = Curve()
        assert str(c) == ""
        assert list(c) == []

    def test_curve_invalid_str(self):
        with pytest.raises(CurveReadError):
            Curve("not a curve")

    def test_curve_invalid_point(self):
        with pytest.raises(CurveReadError):
            Curve([("a", 2)])

    def test_curve_invalid_tuple_length(self):
        with pytest.raises(CurveReadError):
            Curve("[(1,2,3)]")

    def test_curve_empty_list_string_raises(self):
        # An explicit empty list string should raise (no points)
        with pytest.raises(CurveReadError):
            Curve("[]")

    @pytest.mark.parametrize("bad_input", ["[('a',1)]", "[(1,'b')]", "not a curve"])
    def test_curve_various_invalid_strings(self, bad_input):
        with pytest.raises(CurveReadError):
            Curve(bad_input)

    @pytest.mark.parametrize(
        ("curve_in", "expected_output"),
        [
            ("[(1,2), (3,4)]", [(1.0, 2.0), (3.0, 4.0)]),
            ("[(1.0,2.0), (3,4)]", [(1.0, 2.0), (3.0, 4.0)]),
            ("(1,2)", [(1.0, 2.0)]),
            ("(1,2), (3,4)", [(1.0, 2.0), (3.0, 4.0)]),
            ("[(1,2)]", [(1.0, 2.0)]),
            ("1,2", [(1.0, 2.0)]),
            ("    1   ,2.0", [(1.0, 2.0)]),
            ("[(1,2), (3,4), (5,6), (7,8)]", [(1.0, 2.0), (3.0, 4.0), (5.0, 6.0), (7.0, 8.0)]),
            ("('1','2')", [(1.0, 2.0)]),
            ("('1','2'),('3','4')", [(1.0, 2.0), (3.0, 4.0)]),
        ],
    )
    def test_ok_curve(self, curve_in, expected_output):
        if curve_in == "    1   ,2.0" and sys.version_info < (3, 10):
            pytest.skip("python 3.9 doesn't work")

        c = Curve(curve_in)

        assert list(c) == expected_output

    @pytest.mark.parametrize(("curve_in", "expected_output"), [("((1,2),(3,4))", [(1.0, 2.0), (3.0, 4.0)])])
    def test_curves_unusual_but_ok(self, curve_in, expected_output):
        c = Curve(curve_in)

        assert list(c) == expected_output

    @pytest.mark.parametrize("curve_in", ["", "     "])
    def test_none_curve(self, curve_in):
        c = Curve(curve_in)

        assert c == Curve()

    @pytest.mark.parametrize(
        "curve_in",
        [
            "[]",
            "[()]",
            "x,y",
            ".3",
            "string",
            "1, 2 , 3, 4",
            "[(1,2), (1,2,3)]",
            "{1,2,3}",
            "[(12)]",
            "(12)",
            "12",
            "(1,2),(3,'y')",
            "(1,2),('x',4)",
            "[(0.0,100),(10.0,1000)],(20,10000.0)",
            "assert False",
        ],
    )
    def test_string_curve(self, curve_in):
        with pytest.raises(CurveReadError):
            Curve(curve_in)

    @pytest.mark.parametrize("curve_in", [[("a", 2)], [(1, "b")]])
    def test_iterable_curve(self, curve_in):
        with pytest.raises(CurveReadError):
            Curve(curve_in)

    @pytest.mark.parametrize("curve_in", [1, 0, 1.0, 0.0, True, False])
    def test_invalid_type(self, curve_in):
        with pytest.raises(CurveReadError):
            Curve(curve_in)

    def test_curve_round_trip(self):
        c = Curve("[(1,2), (3,4), (5.5,6.6)]")
        str_c = str(c)
        c2 = Curve(str_c)
        str_c2 = str(c2)
        assert str_c == str_c2

    def test_curve_non_monotonic_x_raises(self):
        # x-values must be strictly increasing
        with pytest.raises(CurveXNotIncreasingError):
            Curve("[(2,3), (1,4)]")

    def test_curve_non_x_raises_starting_0(self):
        # check a first zero doesn't throw things
        with pytest.raises(CurveXNotIncreasingError):
            Curve("[(0,3), (-1,2), (1,4)]")

    def test_curve_duplicate_x_raises(self):
        # duplicate x-values should be rejected
        with pytest.raises(CurveXNotIncreasingError):
            Curve("[(1,2), (1,3)]")
