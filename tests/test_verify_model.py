import pytest

from gusnet.elements import Field, ModelLayer, PumpTypes
from gusnet.network import Network
from gusnet.verify_model import (
    BooleanFieldError,
    CurveError,
    DuplicateLinkNameError,
    DuplicateNodeNameError,
    EmptyModelError,
    LinkEndsSameNodeError,
    LinkNotConnectedToNodesError,
    MultipleVerificationError,
    NameFieldError,
    NoJunctionError,
    NoLinksError,
    NoReservoirOrTankError,
    NumericFieldError,
    OrphanJunctionsError,
    PumpCurveMissingError,
    PumpPowerError,
    PumpTypeError,
    RequiredFieldError,
    ValveSettingError,
    ValveTypeError,
    VerificationError,
    _check_boolean_field_type,
    _check_duplicate_link_names,
    _check_duplicate_node_names,
    _check_junction_layer,
    _check_link_connects_to_nodes,
    _check_link_ends_not_same_node,
    _check_link_layers,
    _check_model_not_empty,
    _check_names,
    _check_no_orphan_junctions,
    _check_numeric_field_type,
    _check_pipe_length_exists,
    _check_pump_parameters,
    _check_required_field,
    _check_reservoir_or_tank_exists,
    _check_valve_settings,
    verify_model,
)


def make_row(layer, overrides=None):
    """Return a dict with all `layer.wq_fields()` keys set to None, updated by `overrides`."""
    row = {f: None for f in layer.wq_fields()}
    # For link layers, add default node connections if not provided
    if layer in [ModelLayer.PIPES, ModelLayer.PUMPS, ModelLayer.VALVES]:
        row["start_node_name"] = "DefaultStart"
        row["end_node_name"] = "DefaultEnd"
    if overrides:
        row.update(overrides)
    return row


def make_dict_of_lists(rows):
    """Convert a list of dict rows to dict of lists format.

    Args:
        rows: List of dicts with same keys

    Returns:
        Dict of lists where each key maps to a list of values
    """
    if not rows:
        return {}
    keys = rows[0].keys()
    return {key: [row.get(key) for row in rows] for key in keys}


@pytest.fixture
def layers():
    """Return a minimal set of layers that pass basic checks.

    JUNCTIONS: must be present and non-empty with required fields (e.g. elevation)
    PIPES: used to satisfy link existence and contains required pipe fields
    """
    # Make rows that include all possible fields for the layer to avoid KeyError
    j_row = make_row(ModelLayer.JUNCTIONS, {Field.NAME: "J1", Field.ELEVATION: 1.0})
    p_row = make_row(
        ModelLayer.PIPES,
        {
            Field.NAME: "P1",
            Field.DIAMETER: 100.0,
            Field.ROUGHNESS: 0.01,
            Field.LENGTH: 100.0,
            "start_node_name": "J1",
            "end_node_name": "R1",
        },
    )
    r_row = make_row(ModelLayer.RESERVOIRS, {Field.NAME: "R1", Field.BASE_HEAD: 10.0})

    # Convert to dict of lists format
    def row_to_dict_of_lists(row):
        return {key: [value] for key, value in row.items()}

    return {
        ModelLayer.JUNCTIONS: row_to_dict_of_lists(j_row),
        ModelLayer.PIPES: row_to_dict_of_lists(p_row),
        ModelLayer.RESERVOIRS: row_to_dict_of_lists(r_row),
    }


@pytest.fixture
def network():
    """Return a minimal valid network to go with layers()"""
    net = Network()
    net.add_nodes_from_points(["J1", "R1"], [(0.0, 0.0), (1.0, 1.0)])
    net.add_links_from_nodes_and_vertices(["P1"], ["J1"], ["R1"], [[(2, 0.0), (1.0, 2.0)]])
    return net


def test_verify_minimal_good_layers_passes_verification(layers, network):
    verify_model(layers, network)


def test_verify_empty_model():
    layers = {}
    network = Network()
    with pytest.raises(EmptyModelError):
        verify_model(layers, network)


def test_verify_empty_model_with_one_layer_empty():
    layers = {ModelLayer.JUNCTIONS: {}}
    network = Network()
    with pytest.raises(EmptyModelError):
        verify_model(layers, network)


def test_verify_no_links_raises_no_links_error(layers, network):
    # remove the pipe link so only junctions remain
    # keep the reservoir so the reservoir/tank check passes and
    # verify_model only raises for missing links
    layers = {
        ModelLayer.JUNCTIONS: layers[ModelLayer.JUNCTIONS],
        ModelLayer.RESERVOIRS: layers[ModelLayer.RESERVOIRS],
    }
    with pytest.raises(VerificationError, match="The model must contain at least one link"):
        verify_model(layers, network)


def test_verify_missing_required_field_raises_required_field_error(layers, network):
    # remove the required junction elevation field
    bad_j = make_dict_of_lists([{Field.NAME: "J1"}])
    layers[ModelLayer.JUNCTIONS] = bad_j
    with pytest.raises(RequiredFieldError):
        verify_model(layers, network)


def test_verify_multiple_errors_aggregated_into_multiple_verification_error(network):
    # create a non-empty model that  misses junctions and links so
    # verify_model collects both NoJunctionError and NoLinksError and
    # aggregates them into a MultipleVerificationError.
    r = make_dict_of_lists([{Field.NAME: "R1", Field.BASE_HEAD: 10.0}])
    layers = {ModelLayer.RESERVOIRS: r}
    with pytest.raises(MultipleVerificationError) as e:
        verify_model(layers, network)

    msg = str(e.value)
    assert "junction" in msg.lower()
    assert "link" in msg.lower()


# Tests for internal functions
def test_check_junction_layer_accepts_valid():
    df = make_dict_of_lists([{Field.NAME: "J1", Field.ELEVATION: 0.0, Field.DEMAND_PATTERN: None}])
    _check_junction_layer({ModelLayer.JUNCTIONS: df})


def test_check_junction_layer_raises_on_missing_or_empty():
    with pytest.raises(NoJunctionError):
        _check_junction_layer({})
    with pytest.raises(NoJunctionError):
        _check_junction_layer({ModelLayer.JUNCTIONS: {}})


def test_check_reservoir_or_tank_exists_accepts_valid():
    # reservoir present -> should not raise
    r = make_dict_of_lists([{Field.NAME: "R1", Field.BASE_HEAD: 10.0}])
    _check_reservoir_or_tank_exists({ModelLayer.RESERVOIRS: r})

    # tank present -> should not raise
    t = make_dict_of_lists(
        [
            {
                Field.NAME: "T1",
                Field.ELEVATION: 0.0,
                Field.INIT_LEVEL: 1.0,
                Field.MIN_LEVEL: 0.0,
                Field.MAX_LEVEL: 2.0,
                Field.TANK_DIAMETER: 10.0,
            }
        ]
    )
    _check_reservoir_or_tank_exists({ModelLayer.TANKS: t})


def test_check_reservoir_or_tank_exists_raises_when_missing_or_empty():
    # neither reservoirs nor tanks present
    with pytest.raises(NoReservoirOrTankError):
        _check_reservoir_or_tank_exists(
            {ModelLayer.JUNCTIONS: make_dict_of_lists([{Field.NAME: "J1", Field.ELEVATION: 1.0}])}
        )

    # present but empty
    with pytest.raises(NoReservoirOrTankError):
        _check_reservoir_or_tank_exists({ModelLayer.RESERVOIRS: {}, ModelLayer.TANKS: {}})


def test_check_link_layers_accepts_at_least_one_link():
    layers = {
        ModelLayer.JUNCTIONS: make_dict_of_lists(
            [{Field.NAME: "J1", Field.ELEVATION: 1.0, Field.DEMAND_PATTERN: None}]
        ),
        ModelLayer.PIPES: make_dict_of_lists(
            [
                {
                    Field.NAME: "P1",
                    Field.DIAMETER: 10.0,
                    Field.ROUGHNESS: 0.01,
                    "start_node_name": "J1",
                    "end_node_name": "J1",
                }
            ]
        ),
    }
    _check_link_layers(layers)


def test_check_link_layers_raises_when_no_links():
    layers = {
        ModelLayer.JUNCTIONS: make_dict_of_lists([{Field.NAME: "J1", Field.ELEVATION: 1.0, Field.DEMAND_PATTERN: None}])
    }
    with pytest.raises(NoLinksError):
        _check_link_layers(layers)


def test_check_link_connects_to_nodes_raises_when_start_node_missing():
    net = Network()
    net.add_nodes_from_points(["1", "2", "3"], [(0, 0), (0, 0), (0, 0)])
    net.add_links_from_nodes_and_vertices(["10", "11"], ["1", None], ["2", "3"], [[], []])

    with pytest.raises(LinkNotConnectedToNodesError, match="11"):
        _check_link_connects_to_nodes(net)


def test_check_link_connects_to_nodes_raises_when_end_node_missing():
    net = Network()
    net.add_nodes_from_points(["1", "2", "3"], [(0, 0), (0, 0), (0, 0)])
    net.add_links_from_nodes_and_vertices(["10", "11"], ["1", "2"], ["2", None], [[], []])

    with pytest.raises(LinkNotConnectedToNodesError, match="11"):
        _check_link_connects_to_nodes(net)


def test_check_link_connects_to_nodes_raises_when_both_nodes_missing():
    net = Network()
    net.add_nodes_from_points(["1", "2", "3"], [(0, 0), (0, 0), (0, 0)])
    net.add_links_from_nodes_and_vertices(["10", "11"], ["1", None], ["2", None], [[], []])

    with pytest.raises(LinkNotConnectedToNodesError, match="11"):
        _check_link_connects_to_nodes(net)


def test_check_link_connects_to_nodes_accepts_valid_rows():
    net = Network()
    net.add_nodes_from_points(["1", "2", "3"], [(0, 0), (0, 0), (0, 0)])
    net.add_links_from_nodes_and_vertices(["10", "11"], ["1", "2"], ["2", "3"], [[], []])

    # should not raise
    _check_link_connects_to_nodes(net)


def test_check_link_connects_to_nodes_multiple_links_some_invalid():
    net = Network()
    net.add_nodes_from_points(["1", "2", "3"], [(0, 0), (0, 0), (0, 0)])
    net.add_links_from_nodes_and_vertices(["10", "11"], [None, "2"], ["2", None], [[], []])

    with pytest.raises(LinkNotConnectedToNodesError, match=r"10.*11"):
        _check_link_connects_to_nodes(net)


def test_check_link_ends_not_same_node_raises_on_same_node():
    net = Network()
    net.add_nodes_from_points(["1", "2", "3"], [(0, 0), (0, 0), (0, 0)])
    net.add_links_from_nodes_and_vertices(["10", "11"], ["1", "2"], ["2", "2"], [[], []])

    with pytest.raises(LinkEndsSameNodeError, match="11"):
        _check_link_ends_not_same_node(net)


def test_check_link_ends_not_same_node_does_not_raise_on_none():
    net = Network()
    net.add_nodes_from_points(["1", "2", "3"], [(0, 0), (0, 0), (0, 0)])
    net.add_links_from_nodes_and_vertices(["10", "11"], ["1", None], ["2", None], [[], []])

    _check_link_ends_not_same_node(net)


def test_check_link_ends_not_same_node_accepts_valid_rows():
    net = Network()
    net.add_nodes_from_points(["1", "2", "3"], [(0, 0), (0, 0), (0, 0)])
    net.add_links_from_nodes_and_vertices(["10", "11"], ["1", "2"], ["2", "3"], [[], []])

    _check_link_ends_not_same_node(net)


def test_check_no_orphan_nodes_detects_orphan():
    # two junctions but only one is connected -> the other is orphan
    j_rows = [{Field.NAME: "J1", Field.ELEVATION: 1.0}, {Field.NAME: "J2", Field.ELEVATION: 2.0}]
    junctions = make_dict_of_lists(j_rows)

    net = Network()
    net.add_nodes_from_points(["J1", "J2", "R1"], [(0, 0), (0, 0), (0, 0)])
    net.add_links_from_nodes_and_vertices(["P1"], ["J1"], ["R1"], [[]])

    with pytest.raises(OrphanJunctionsError):
        _check_no_orphan_junctions(junctions, net)


def test_check_no_orphan_nodes_accepts_connected(layers):
    j_rows = [{Field.NAME: "J1", Field.ELEVATION: 1.0}, {Field.NAME: "J2", Field.ELEVATION: 2.0}]
    junctions = make_dict_of_lists(j_rows)

    net = Network()
    net.add_nodes_from_points(["J1", "J2", "R1"], [(0, 0), (0, 0), (0, 0)])
    net.add_links_from_nodes_and_vertices(["P1"], ["J1"], ["J2"], [[]])

    # should not raise
    _check_no_orphan_junctions(junctions, net)


def test_check_no_orphan_junctions_returns_on_no_links_or_missing_junctions():
    net = Network()
    net.add_nodes_from_points(["J1", "J2", "R1"], [(0, 0), (0, 0), (0, 0)])
    net.add_links_from_nodes_and_vertices(["P1"], ["J1"], ["J2"], [[]])

    # should not raise
    _check_no_orphan_junctions({}, net)


def test_check_no_orphan_junctions_does_not_raise_if_junctions_missing_name_column():
    j_rows = [{Field.ELEVATION: 1.0}, {Field.ELEVATION: 2.0}]
    junctions = make_dict_of_lists(j_rows)

    net = Network()
    net.add_nodes_from_points(["J1", "J2", "R1"], [(0, 0), (0, 0), (0, 0)])
    net.add_links_from_nodes_and_vertices(["P1"], ["J1"], ["J2"], [[]])

    _check_no_orphan_junctions(junctions, net)


def test_check_required_field_behaviour():
    df = make_dict_of_lists([{Field.NAME: "N1", Field.ELEVATION: 2.0, Field.DEMAND_PATTERN: None}])
    # present should not raise
    _check_required_field(df, ModelLayer.JUNCTIONS, Field.ELEVATION)

    # missing column
    with pytest.raises(RequiredFieldError):
        _check_required_field(make_dict_of_lists([{Field.NAME: "N1"}]), ModelLayer.JUNCTIONS, Field.ELEVATION)

    # None value
    df_nan = make_dict_of_lists([{Field.NAME: "N1", Field.ELEVATION: None}])
    with pytest.raises(RequiredFieldError):
        _check_required_field(df_nan, ModelLayer.JUNCTIONS, Field.ELEVATION)

    # non-string valve_type -> AttributeError path -> ValveTypeError
    with pytest.raises(ValveTypeError):
        _check_valve_settings(
            make_dict_of_lists(
                [{Field.NAME: "V1", Field.VALVE_TYPE: 1, Field.DIAMETER: 10.0, Field.HEADLOSS_CURVE: None}]
            )
        )

    # invalid valve_type value -> ValveTypeError
    with pytest.raises(ValveTypeError):
        _check_valve_settings(
            make_dict_of_lists(
                [{Field.NAME: "V1", Field.VALVE_TYPE: "XXX", Field.DIAMETER: 10.0, Field.HEADLOSS_CURVE: None}]
            )
        )

    # missing setting field for PRV -> ValveSettingError
    df = make_dict_of_lists(
        [{Field.NAME: "V1", Field.VALVE_TYPE: "PRV", Field.DIAMETER: 10.0, Field.HEADLOSS_CURVE: None}]
    )
    with pytest.raises(ValveSettingError):
        _check_valve_settings(df)

    # NaN setting value for PRV -> ValveSettingError
    df2 = make_dict_of_lists(
        [
            {
                Field.NAME: "V1",
                Field.VALVE_TYPE: "PRV",
                Field.PRESSURE_SETTING: None,
                Field.DIAMETER: 10.0,
                Field.HEADLOSS_CURVE: None,
            }
        ]
    )
    with pytest.raises(ValveSettingError):
        _check_valve_settings(df2)

    # valid valve row -> should not raise
    df_ok = make_dict_of_lists(
        [
            {
                Field.NAME: "V1",
                Field.VALVE_TYPE: "PRV",
                Field.PRESSURE_SETTING: 5.0,
                Field.DIAMETER: 10.0,
                Field.HEADLOSS_CURVE: None,
            }
        ]
    )
    _check_valve_settings(df_ok)


def test_check_pump_parameters_various_paths():
    # invalid pump_type value -> PumpTypeError
    with pytest.raises(PumpTypeError):
        _check_pump_parameters(make_dict_of_lists([{Field.NAME: "PU1", Field.PUMP_TYPE: "XXX"}]))

    # power pump missing power -> PumpPowerError
    with pytest.raises(PumpPowerError):
        _check_pump_parameters(make_dict_of_lists([{Field.NAME: "PU1", Field.PUMP_TYPE: PumpTypes.POWER.value}]))

    # power pump with non-positive power -> PumpPowerError
    with pytest.raises(PumpPowerError):
        _check_pump_parameters(
            make_dict_of_lists([{Field.NAME: "PU1", Field.PUMP_TYPE: PumpTypes.POWER.value, Field.POWER: 0}])
        )

    # head pump missing curve -> PumpCurveMissingError
    with pytest.raises(PumpCurveMissingError):
        _check_pump_parameters(make_dict_of_lists([{Field.NAME: "PU1", Field.PUMP_TYPE: PumpTypes.HEAD.value}]))

    # valid power pump -> should not raise
    df_ok = make_dict_of_lists([{Field.NAME: "PU1", Field.PUMP_TYPE: PumpTypes.POWER.value, Field.POWER: 10.0}])
    _check_pump_parameters(df_ok)


def test_check_duplicate_node_names_helper_raises_and_accepts(layers):
    # duplicate should raise
    layers = {
        ModelLayer.JUNCTIONS: {Field.NAME: ["N1", "N2", "N3"], Field.ELEVATION: [1.0, 2.0, 3.0]},
        ModelLayer.TANKS: {Field.NAME: ["N2"]},
    }
    with pytest.raises(DuplicateNodeNameError):
        _check_duplicate_node_names(layers)


def test_check_duplicate_link_names_helper_raises_and_accepts(layers):
    # duplicate should raise
    v_row = make_row(
        ModelLayer.VALVES,
        {Field.NAME: "P1", Field.VALVE_TYPE: "PRV", Field.PRESSURE_SETTING: 5.0, Field.DIAMETER: 50.0},
    )

    layers[ModelLayer.VALVES] = make_dict_of_lists([v_row])
    with pytest.raises(DuplicateLinkNameError):
        _check_duplicate_link_names(layers)


def test_check_model_not_empty_raises_on_empty_mapping():
    with pytest.raises(EmptyModelError):
        _check_model_not_empty({})


def test_check_model_not_empty_raises_when_all_layers_empty():
    layers = {ModelLayer.JUNCTIONS: {}, ModelLayer.PIPES: {}}
    with pytest.raises(EmptyModelError):
        _check_model_not_empty(layers)


def test_check_model_not_empty_accepts_non_empty_layer():
    layers = {ModelLayer.JUNCTIONS: make_dict_of_lists([{Field.NAME: "J1", Field.ELEVATION: 1.0}])}
    # should not raise
    _check_model_not_empty(layers)


def test_check_pipe_length_exists_behaviour():
    # missing LENGTH column -> PipeLengthMissingError
    df_missing = make_dict_of_lists([{Field.NAME: "P1", Field.DIAMETER: 10.0}])
    from gusnet.verify_model import PipeLengthMissingError

    with pytest.raises(PipeLengthMissingError):
        _check_pipe_length_exists(df_missing)

    # LENGTH present but NaN -> PipeLengthMissingError
    df_nan = make_dict_of_lists([{Field.NAME: "P1", Field.LENGTH: None}])
    with pytest.raises(PipeLengthMissingError):
        _check_pipe_length_exists(df_nan)

    # Valid LENGTH -> should not raise
    df_ok = make_dict_of_lists([{Field.NAME: "P1", Field.LENGTH: 50.0}])
    _check_pipe_length_exists(df_ok)


@pytest.mark.parametrize("bad_name", ["bad name"])
def test_check_names_reject_whitespace(bad_name):
    df = make_dict_of_lists([{Field.NAME: bad_name}])
    with pytest.raises(NameFieldError, match=str(bad_name)):
        _check_names({ModelLayer.JUNCTIONS: df})


@pytest.mark.parametrize("blank", ["", "   "])
def test_check_names_reject_blank(blank):
    df = make_dict_of_lists([{Field.NAME: blank}])
    with pytest.raises(NameFieldError):
        _check_names({ModelLayer.JUNCTIONS: df})


def test_check_names_reject_long_name():
    long_name = "a" * 32
    df = make_dict_of_lists([{Field.NAME: long_name}])
    with pytest.raises(NameFieldError, match=long_name):
        _check_names({ModelLayer.JUNCTIONS: df})


def test_check_names_accepts_valid_and_nulls():
    df = make_dict_of_lists([{Field.NAME: "J_OK"}, {Field.NAME: None}])
    # should not raise
    _check_names({ModelLayer.JUNCTIONS: df})


def test_check_names_ignores_missing_name_column():
    df = make_dict_of_lists([{"elevation": 1.0}])
    # should not raise when Field.NAME isn't present
    _check_names({ModelLayer.JUNCTIONS: df})


def test_check_names_all_nulls_ignored():
    df = make_dict_of_lists([{Field.NAME: None}, {Field.NAME: None}])
    # should not raise if all names are null
    _check_names({ModelLayer.JUNCTIONS: df})


def test_check_names_non_string_values():
    df = make_dict_of_lists([{Field.NAME: 123}])
    with pytest.raises(NameFieldError, match="123"):
        _check_names({ModelLayer.JUNCTIONS: df})


def test_check_valve_settings_gpv_none_curve_raises():
    # GPV declared but headloss curve column contains None -> ValveSettingError
    df = make_dict_of_lists(
        [{Field.NAME: "V1", Field.VALVE_TYPE: "GPV", Field.HEADLOSS_CURVE: None, Field.DIAMETER: 50.0}]
    )
    with pytest.raises(ValveSettingError):
        _check_valve_settings(df)


def test_check_pump_parameters_head_curve_none_raises():
    # HEAD pump with PUMP_CURVE present but None should raise PumpCurveMissingError
    df = make_dict_of_lists([{Field.NAME: "PU1", Field.PUMP_TYPE: PumpTypes.HEAD.value, Field.PUMP_CURVE: None}])
    with pytest.raises(PumpCurveMissingError):
        _check_pump_parameters(df)


def test_check_curve_error_includes_exception_notes():
    # Create a ValueError with __notes__ set to exercise the CurveError error_detail branch
    err = ValueError("parse problem")
    err.__notes__ = ["detailed note"]
    ce = CurveError(ModelLayer.TANKS, Field.VOL_CURVE, err)
    assert "detailed note" in str(ce)


def test_check_valve_settings_gpv_valid_string_accepts():
    # GPV with a valid headloss curve string should not raise
    df = make_dict_of_lists(
        [{Field.NAME: "V1", Field.VALVE_TYPE: "GPV", Field.HEADLOSS_CURVE: "(1,2),(3,4)", Field.DIAMETER: 50.0}]
    )
    _check_valve_settings(df)


def test_check_pump_parameters_head_curve_valid_accepts():
    # HEAD pump with a valid pump curve string should not raise
    df = make_dict_of_lists(
        [{Field.NAME: "PU1", Field.PUMP_TYPE: PumpTypes.HEAD.value, Field.PUMP_CURVE: "(1,2),(3,4)"}]
    )
    _check_pump_parameters(df)


def test_check_numeric_field_type_raises_on_non_numeric():
    df = make_dict_of_lists([{Field.NAME: "N1", Field.ELEVATION: "not-a-number"}])
    with pytest.raises(NumericFieldError):
        _check_numeric_field_type(df, ModelLayer.JUNCTIONS, Field.ELEVATION)


def test_check_numeric_field_type_skips_missing_or_all_na():
    # missing column -> should not raise
    df_missing = make_dict_of_lists([{Field.NAME: "N1"}])
    _check_numeric_field_type(df_missing, ModelLayer.JUNCTIONS, Field.ELEVATION)

    # all NA -> should not raise
    df_na = make_dict_of_lists([{Field.NAME: "N1", Field.ELEVATION: float("nan")}])
    _check_numeric_field_type(df_na, ModelLayer.JUNCTIONS, Field.ELEVATION)


@pytest.mark.parametrize("value", [[True, False], [True, False, None], [1.0, 0.0], ["1.0", "0.0"]])
def test_check_boolean_field_type_accepts_boolean_values(value):
    _check_boolean_field_type({"overflow": value}, ModelLayer.TANKS, Field.OVERFLOW)


def test_check_boolean_field_type_raises_on_non_boolean():
    # Field.OVERFLOW is a BOOL on TANKS
    df = make_dict_of_lists([{Field.NAME: "T1", Field.OVERFLOW: "yes"}])
    with pytest.raises(BooleanFieldError):
        _check_boolean_field_type(df, ModelLayer.TANKS, Field.OVERFLOW)


def test_check_boolean_field_type_skips_missing_or_all_none():
    df_missing = make_dict_of_lists([{Field.NAME: "T1"}])
    _check_boolean_field_type(df_missing, ModelLayer.TANKS, Field.OVERFLOW)

    df_none = make_dict_of_lists([{Field.NAME: "T1", Field.OVERFLOW: None}])
    _check_boolean_field_type(df_none, ModelLayer.TANKS, Field.OVERFLOW)
