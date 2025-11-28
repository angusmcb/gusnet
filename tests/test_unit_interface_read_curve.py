# import sys

# import pytest

# import gusnet.elements
# from gusnet.interface import Converter, CurveReadError, _Curves


# @pytest.fixture
# def wn():
#     import wntr

#     return wntr.network.WaterNetworkModel()


# @pytest.fixture
# def converter():
#     return Converter(gusnet.elements.FlowUnit.LPS, gusnet.elements.HeadlossFormula.HAZEN_WILLIAMS)


# def test_curves_add_one(wn, converter):
#     curves = _Curves(wn, converter)
#     curve_name = curves._add_one("[(1,2), (3,4)]", _Curves.Type.HEAD)
#     assert curve_name == "1"


# def test_curves_get(wn, converter):
#     curves = _Curves(wn, converter)
#     curve_name = curves._add_one("[(1,2), (3,4)]", _Curves.Type.HEAD)
#     curve = curves.get(curve_name)
#     assert curve == "[(1.0, 2.0), (3.0, 4.0)]"


# def test_curves_add_invalid(wn, converter):
#     curves = _Curves(wn, converter)
#     with pytest.raises(gusnet.interface.CurveError):
#         curves._add_one(None, _Curves.Type.HEAD)
