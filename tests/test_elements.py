import pytest

from gusnet.elements import (
    DemandType,
    Field,
    FieldType,
    FlowUnit,
    HeadlossFormula,
    InitialStatus,
    ModelLayer,
    PumpTypes,
    ResultLayer,
    TankMixingModel,
    ValveType,
)


@pytest.mark.parametrize(
    "enum",
    [
        FlowUnit,
        HeadlossFormula,
        PumpTypes,
        InitialStatus,
        ValveType,
        TankMixingModel,
        ModelLayer,
        ResultLayer,
        Field,
        DemandType,
    ],
)
def test_friendly_name(enum):
    for member in enum:
        assert member.friendly_name, f"{member.name} is missing a friendly_name"


@pytest.mark.parametrize(
    "enum",
    [
        FlowUnit,
        HeadlossFormula,
        PumpTypes,
        InitialStatus,
        ValveType,
        TankMixingModel,
        ModelLayer,
        ResultLayer,
        Field,
        DemandType,
    ],
)
def test_translated_name(enum, monkeypatch: pytest.MonkeyPatch):
    translated_string = "xxx"
    monkeypatch.setattr("gusnet.elements.tr", lambda *args: translated_string)
    for member in enum:
        assert member.friendly_name == translated_string, f"{member.name}.friendly_name is not translated"


def test_field_name_matches_value():
    for field in Field:
        assert field.name.lower() == field.value


@pytest.mark.parametrize("field", list(Field))
def test_field_types(field: Field):
    assert isinstance(field.type, FieldType), f"{field.name}.value is not a FieldType"


@pytest.mark.parametrize("flow_unit", list(FlowUnit))
def test_check_flow_unit_valid_in_wntr(flow_unit: FlowUnit):
    import wntr

    wn = wntr.network.WaterNetworkModel()

    wn.options.hydraulic.inpfile_units = flow_unit.name

    assert wn.options.hydraulic.inpfile_units == flow_unit.name


@pytest.mark.filterwarnings("ignore:Changing the headloss")
@pytest.mark.parametrize("headloss_formula", list(HeadlossFormula))
def test_check_headloss_formula_valid_in_wntr(headloss_formula: HeadlossFormula):
    import wntr

    wn = wntr.network.WaterNetworkModel()

    wn.options.hydraulic.headloss = headloss_formula.value

    assert wn.options.hydraulic.headloss == headloss_formula.value


def test_layer_str_enum():
    assert hash(ModelLayer.JUNCTIONS) == hash("JUNCTIONS")
    assert str(ModelLayer.JUNCTIONS) == "JUNCTIONS"
    assert ModelLayer.JUNCTIONS == "JUNCTIONS"
    assert isinstance(ModelLayer.JUNCTIONS, str)
