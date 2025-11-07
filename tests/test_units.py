import numpy as np
import pandas as pd
import pytest

from gusnet.elements import DefaultOptions, FlowUnit, HeadlossFormula, Parameter
from gusnet.units import Converter, SpecificUnitNames, UnitNames


@pytest.fixture
def converter():
    return Converter(FlowUnit.LPS, HeadlossFormula.HAZEN_WILLIAMS)


def test_factory_creation():
    options = DefaultOptions()

    c = Converter.from_options(options)

    assert isinstance(c, Converter)


def test_converter_to_si():
    converter = Converter(FlowUnit.CFS, HeadlossFormula.HAZEN_WILLIAMS)
    value = converter.to_si(1.0, Parameter.ELEVATION)
    assert value == 0.3048


def test_converter_from_si():
    converter = Converter(FlowUnit.CFS, HeadlossFormula.HAZEN_WILLIAMS)
    value = converter.from_si(0.3048, Parameter.ELEVATION)
    assert value == 1.0


def test_converter_to_si_darcy_weisbach():
    converter = Converter(FlowUnit.LPS, HeadlossFormula.DARCY_WEISBACH)
    value = converter.to_si(1, Parameter.ROUGHNESS_COEFFICIENT)
    assert value == 0.001


def test_converter_to_si_hazen_williams():
    converter = Converter(FlowUnit.CFS, HeadlossFormula.HAZEN_WILLIAMS)
    value = converter.to_si(1, Parameter.ROUGHNESS_COEFFICIENT)
    assert value == 1


# @pytest.mark.parametrize("field", list(Field))
# def test_get_conversion_param(field):
#     converter = Converter(FlowUnit.LPS, HeadlossFormula.HAZEN_WILLIAMS)

#     conversion_parameter = converter._get_conversion_param(field)

#     assert isinstance(conversion_parameter, (type(None), Parameter))


@pytest.mark.parametrize("flow_unit", list(FlowUnit))
@pytest.mark.parametrize("headloss_formula", list(HeadlossFormula))
def test_factor_in_all_combinations(flow_unit, headloss_formula):
    converter = Converter(flow_unit, headloss_formula)

    for param in Parameter:
        factor = converter._factor(param)

        assert isinstance(factor, float), (
            f"Factor for {param} with {flow_unit} and {headloss_formula} should be a float, got {type(factor)}"
        )


def test_to_si_float(converter):
    value = 10.0
    # FlowUnit.LPS: factor = 0.001
    expected = 0.01
    result = converter.to_si(value, Parameter.FLOW)
    assert result == expected


def test_from_si_float(converter):
    value = 10.0
    # FlowUnit.LPS: factor = 0.001
    expected = 10000.0
    result = converter.from_si(value, Parameter.FLOW)
    assert result == expected


def test_to_si_numpy_array(converter):
    value = np.array([1.0, 2.0, 3.0])
    expected = np.array([0.001, 0.002, 0.003])
    result = converter.to_si(value, Parameter.FLOW)
    np.testing.assert_array_almost_equal(result, expected)


def test_from_si_numpy_array(converter):
    value = np.array([1.0, 2.0, 3.0])
    expected = np.array([1000.0, 2000.0, 3000.0])
    result = converter.from_si(value, Parameter.FLOW)
    np.testing.assert_array_almost_equal(result, expected)


def test_to_si_pandas_series(converter):
    value = pd.Series([1.0, 2.0, 3.0])
    expected = pd.Series([0.001, 0.002, 0.003])
    result = converter.to_si(value, Parameter.FLOW)
    pd.testing.assert_series_equal(result, expected)


def test_from_si_pandas_series(converter):
    value = pd.Series([1.0, 2.0, 3.0])
    expected = pd.Series([1000.0, 2000.0, 3000.0])
    result = converter.from_si(value, Parameter.FLOW)
    pd.testing.assert_series_equal(result, expected)


def test_to_si_pandas_dataframe(converter):
    value = pd.DataFrame({"a": [1.0, 2.0], "b": [3.0, 4.0]})
    expected = pd.DataFrame({"a": [0.001, 0.002], "b": [0.003, 0.004]})
    result = converter.to_si(value, Parameter.FLOW)
    pd.testing.assert_frame_equal(result, expected)


def test_from_si_pandas_dataframe(converter):
    value = pd.DataFrame({"a": [1.0, 2.0], "b": [3.0, 4.0]})
    expected = pd.DataFrame({"a": [1000.0, 2000.0], "b": [3000.0, 4000.0]})
    result = converter.from_si(value, Parameter.FLOW)
    pd.testing.assert_frame_equal(result, expected)


@pytest.mark.parametrize(
    ("param", "expected"),
    [
        (Parameter.FLOW, 0.001),
        (Parameter.EMITTER_COEFFICIENT, 0.001),
        (Parameter.PIPE_DIAMETER, 0.001),
        (Parameter.ROUGHNESS_COEFFICIENT, 1.0),
        (Parameter.TANK_DIAMETER, 1.0),
        (Parameter.ELEVATION, 1.0),
        (Parameter.HYDRAULIC_HEAD, 1.0),
        (Parameter.LENGTH, 1.0),
        (Parameter.UNIT_HEADLOSS, 0.001),
        (Parameter.VELOCITY, 1.0),
        (Parameter.ENERGY, 3600000.0),
        (Parameter.POWER, 1000.0),
        (Parameter.PRESSURE, 1.0),
        (Parameter.VOLUME, 1.0),
        (Parameter.CONCENTRATION, 0.001),
        (Parameter.REACTION_RATE, pytest.approx(1.1574074074074073e-8)),
        (Parameter.SOURCE_MASS_INJECTION, pytest.approx(1.6666666666666667e-8)),
        (Parameter.BULK_REACTION_COEFFICIENT, pytest.approx(1.1574074074074073e-05)),
        (Parameter.WALL_REACTION_COEFFICIENT, pytest.approx(1.1574074074074074e-05)),
        (Parameter.WATER_AGE, 3600.0),
    ],
)
def test_factor_for_parameters(converter, param, expected):
    factor = converter._factor(param)
    assert factor == expected


@pytest.mark.parametrize(
    ("param", "expected"),
    [
        (Parameter.FLOW, 0.0283168466),
        (Parameter.EMITTER_COEFFICIENT, pytest.approx(0.0283168466 * (0.4333 / 0.3048) ** 0.5)),
        (Parameter.PIPE_DIAMETER, 0.0254),
        (Parameter.ROUGHNESS_COEFFICIENT, 1.0),
        (Parameter.TANK_DIAMETER, 0.3048),
        (Parameter.ELEVATION, 0.3048),
        (Parameter.HYDRAULIC_HEAD, 0.3048),
        (Parameter.LENGTH, 0.3048),
        (Parameter.UNIT_HEADLOSS, 0.001),
        (Parameter.VELOCITY, 0.3048),
        (Parameter.ENERGY, 3600000.0),
        (Parameter.POWER, 745.699872),
        (Parameter.PRESSURE, pytest.approx(0.3048 / 0.4333)),
        (Parameter.VOLUME, pytest.approx(0.3048**3)),
        (Parameter.CONCENTRATION, 0.001),
        (Parameter.REACTION_RATE, pytest.approx(1.1574074074074073e-8)),
        (Parameter.SOURCE_MASS_INJECTION, pytest.approx(1.6666666666666667e-8)),
        (Parameter.BULK_REACTION_COEFFICIENT, pytest.approx(1.1574074074074073e-05)),
        (Parameter.WALL_REACTION_COEFFICIENT, pytest.approx(3.527777777777778e-06)),
        (Parameter.WATER_AGE, 3600.0),
    ],
)
def test_factor_for_parameters_cfs(param, expected):
    converter = Converter(FlowUnit.CFS, HeadlossFormula.HAZEN_WILLIAMS)
    factor = converter._factor(param)
    assert factor == expected


def test_unitnames_flow_unit_name():
    u = UnitNames()
    assert isinstance(u.flow_unit_name(), str)
    assert u.flow_unit_name() == "*flow*"


@pytest.mark.parametrize(
    ("param", "expected"),
    [
        (Parameter.FLOW, "*flow*"),
        (Parameter.EMITTER_COEFFICIENT, "*flow* / √m or *flow* / √psi"),
        (Parameter.PIPE_DIAMETER, "mm or inches"),
        (Parameter.ROUGHNESS_COEFFICIENT, "unitless, mm, or 10⁻³ ft"),
        (Parameter.TANK_DIAMETER, "m or ft"),
        (Parameter.ELEVATION, "m or ft"),
        (Parameter.HYDRAULIC_HEAD, "m or ft"),
        (Parameter.LENGTH, "m or ft"),
        (Parameter.UNIT_HEADLOSS, "m/1000 m or ft/1000 ft"),
        (Parameter.VELOCITY, "m/s or ft/s"),
        (Parameter.ENERGY, "kWh"),
        (Parameter.POWER, "kW or hp"),
        (Parameter.PRESSURE, "m or psi"),
        (Parameter.VOLUME, "m³ or ft³"),
        (Parameter.CONCENTRATION, "mg/L"),
        (Parameter.REACTION_RATE, "mg/L/day"),
        (Parameter.SOURCE_MASS_INJECTION, "mg/min"),
        (Parameter.BULK_REACTION_COEFFICIENT, " "),
        (Parameter.WALL_REACTION_COEFFICIENT, "mg/m²/day,  mg/ft²/day, m/day, or ft/day"),
        (Parameter.WATER_AGE, "hours"),
        (Parameter.UNITLESS, "unitless"),
        (Parameter.FRACTION, "fraction"),
        (Parameter.CURRENCY, "currency"),
    ],
)
def test_unitnames_get(param, expected):
    u = UnitNames()
    # Remove tr() wrapping for comparison
    result = u.get(param)
    assert expected in result


@pytest.mark.parametrize("param", list(Parameter))
def test_unitnames_all_params(param):
    u = UnitNames()
    result = u.get(param)
    assert isinstance(result, str), f"Expected string for {param}, got {type(result)}"


def test_specificunitnames_flow_unit_name():
    s = SpecificUnitNames(FlowUnit.LPS, HeadlossFormula.HAZEN_WILLIAMS)
    assert s.flow_unit_name() == "L/s"


@pytest.mark.parametrize(
    ("flow_unit", "headloss_formula"),
    [
        (FlowUnit.LPS, HeadlossFormula.HAZEN_WILLIAMS),
        (FlowUnit.CFS, HeadlossFormula.HAZEN_WILLIAMS),
        (FlowUnit.LPS, HeadlossFormula.DARCY_WEISBACH),
    ],
)
def test_specificunitnames_get_all(flow_unit, headloss_formula):
    s = SpecificUnitNames(flow_unit, headloss_formula)
    # Just check that get returns a string for all parameters
    for param in Parameter:
        result = s.get(param)

        assert isinstance(result, str), param
