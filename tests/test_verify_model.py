import copy
import math

import numpy as np
import pandas as pd
import pytest

from gusnet.elements import Field, ModelLayer, Parameter, PumpTypes, SimpleFieldType
from gusnet.verify_model import (
    BooleanFieldError,
    CurveError,
    DuplicateLinkNameError,
    DuplicateNodeNameError,
    EmptyModelError,
    LinkEndsSameNodeError,
    MultipleVerificationError,
    NameFieldError,
    NoJunctionError,
    NoLinksError,
    NoReservoirOrTankError,
    NumericFieldError,
    OrphanJunctionsError,
    PatternError,
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
    _check_link_ends_not_same_node,
    _check_link_layers,
    _check_model_not_empty,
    _check_names,
    _check_no_orphan_junctions,
    _check_numeric_field_type,
    _check_pump_parameters,
    _check_required_field,
    _check_reservoir_or_tank_exists,
    _check_valve_settings,
    _collect_names_for_layers,
    verify_model,
)


def make_row(layer, overrides=None):
    """Return a dict with all `layer.wq_fields()` keys set to None, updated by `overrides`."""
    row = {f: None for f in layer.wq_fields()}
    if overrides:
        row.update(overrides)
    return row


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
            "start_node_name": "J1",
            "end_node_name": "R1",
        },
    )
    r_row = make_row(ModelLayer.RESERVOIRS, {Field.NAME: "R1", Field.BASE_HEAD: 10.0})

    return {
        ModelLayer.JUNCTIONS: pd.DataFrame([j_row]),
        ModelLayer.PIPES: pd.DataFrame([p_row]),
        ModelLayer.RESERVOIRS: pd.DataFrame([r_row]),
    }


def test_verify_minimal_good_layers_passes_verification(layers):
    verify_model(layers)


def test_verify_empty_model():
    layers = {}
    with pytest.raises(EmptyModelError):
        verify_model(layers)


def test_verify_empty_model_with_one_layer_empty():
    layers = {ModelLayer.JUNCTIONS: pd.DataFrame()}
    with pytest.raises(EmptyModelError):
        verify_model(layers)


def test_verify_no_links_raises_no_links_error(layers):
    # remove the pipe link so only junctions remain
    # keep the reservoir so the reservoir/tank check passes and
    # verify_model only raises for missing links
    layers = {
        ModelLayer.JUNCTIONS: layers[ModelLayer.JUNCTIONS],
        ModelLayer.RESERVOIRS: layers[ModelLayer.RESERVOIRS],
    }
    with pytest.raises(VerificationError, match="The model must contain at least one link"):
        verify_model(layers)


def test_verify_missing_required_field_raises_required_field_error(layers):
    # remove the required junction elevation field
    bad_j = pd.DataFrame([{Field.NAME: "J1"}])
    layers[ModelLayer.JUNCTIONS] = bad_j
    with pytest.raises(RequiredFieldError):
        verify_model(layers)


def test_verify_multiple_errors_aggregated_into_multiple_verification_error():
    # create a non-empty model that  misses junctions and links so
    # verify_model collects both NoJunctionError and NoLinksError and
    # aggregates them into a MultipleVerificationError.
    r = pd.DataFrame([{Field.NAME: "R1", Field.BASE_HEAD: 10.0}])
    layers = {ModelLayer.RESERVOIRS: r}
    with pytest.raises(MultipleVerificationError) as e:
        verify_model(layers)

    msg = str(e.value)
    assert "junction" in msg.lower()
    assert "link" in msg.lower()


def test_verify_valve_type_missing_column_raises_valve_type_error(layers):
    # include a valve_type column with a non-string value so
    # _verify_valve_settings raises ValveTypeError (AttributeError path)
    layers[ModelLayer.VALVES] = pd.DataFrame([{Field.NAME: "V1", Field.VALVE_TYPE: 1, Field.DIAMETER: 100.0}])
    with pytest.raises(ValveTypeError):
        verify_model(layers)


def test_verify_valve_setting_missing_for_type_raises_valve_setting_error(layers):
    # valve declared as PRV but missing pressure_setting column; include diameter
    layers[ModelLayer.VALVES] = pd.DataFrame([{Field.NAME: "V1", Field.VALVE_TYPE: "PRV", Field.DIAMETER: 50.0}])
    with pytest.raises(ValveSettingError):
        verify_model(layers)


def test_verify_valve_setting_nan_raises_valve_setting_error(layers):
    # valve declared as PRV with pressure_setting NaN
    layers[ModelLayer.VALVES] = pd.DataFrame(
        [{Field.NAME: "V1", Field.VALVE_TYPE: "PRV", Field.PRESSURE_SETTING: math.nan, Field.DIAMETER: 50.0}]
    )
    with pytest.raises(ValveSettingError):
        verify_model(layers)


def test_verify_pump_type_missing_column_raises_pump_type_error(layers):
    # Missing the required pump_type will produce a RequiredFieldError and
    # a PumpTypeError; verify_model aggregates these so expect
    # MultipleVerificationError here.
    layers[ModelLayer.PUMPS] = pd.DataFrame([{Field.NAME: "PU1"}])
    with pytest.raises(MultipleVerificationError):
        verify_model(layers)


def test_verify_pump_type_invalid_value_raises_pump_type_error(layers):
    pump_row = make_row(ModelLayer.PUMPS, {Field.NAME: "PU1", Field.PUMP_TYPE: "XXX"})
    layers[ModelLayer.PUMPS] = pd.DataFrame([pump_row])
    with pytest.raises(PumpTypeError):
        verify_model(layers)


def test_verify_power_pump_missing_power_raises_pump_power_error(layers):
    # include pattern fields used by verify_model to avoid KeyError
    pump_row = make_row(ModelLayer.PUMPS, {Field.NAME: "PU1", Field.PUMP_TYPE: PumpTypes.POWER.value})
    layers[ModelLayer.PUMPS] = pd.DataFrame([pump_row])
    with pytest.raises(PumpPowerError):
        verify_model(layers)


def test_verify_power_pump_zero_or_negative_power_raises_pump_power_error(layers):
    pump_row1 = make_row(ModelLayer.PUMPS, {Field.NAME: "PU1", Field.PUMP_TYPE: PumpTypes.POWER.value, Field.POWER: 0})
    pump_row2 = make_row(ModelLayer.PUMPS, {Field.NAME: "PU2", Field.PUMP_TYPE: PumpTypes.POWER.value, Field.POWER: -1})
    layers[ModelLayer.PUMPS] = pd.DataFrame([pump_row1, pump_row2])
    with pytest.raises(PumpPowerError):
        verify_model(layers)


def test_verify_head_pump_missing_curve_raises_pump_curve_error(layers):
    pump_row = make_row(ModelLayer.PUMPS, {Field.NAME: "PU1", Field.PUMP_TYPE: PumpTypes.HEAD.value})
    layers[ModelLayer.PUMPS] = pd.DataFrame([pump_row])
    with pytest.raises(PumpCurveMissingError):
        verify_model(layers)


def test_verify_model_passes_for_valid_minimal_model(layers):
    # add a valid valve (include full valve fields to avoid mapping KeyError)
    v_row = make_row(
        ModelLayer.VALVES,
        {Field.NAME: "V1", Field.VALVE_TYPE: "PRV", Field.PRESSURE_SETTING: 10.0, Field.DIAMETER: 50.0},
    )
    layers[ModelLayer.VALVES] = pd.DataFrame([v_row])
    # add a valid power pump
    layers[ModelLayer.PUMPS] = pd.DataFrame(
        [make_row(ModelLayer.PUMPS, {Field.NAME: "PU1", Field.PUMP_TYPE: PumpTypes.POWER.value, Field.POWER: 5.0})]
    )

    # Should not raise
    verify_model(copy.deepcopy(layers))


# Tests for internal functions
def test_check_junction_layer_accepts_valid():
    df = pd.DataFrame([{Field.NAME: "J1", Field.ELEVATION: 0.0, Field.DEMAND_PATTERN: None}])
    _check_junction_layer({ModelLayer.JUNCTIONS: df})


def test_check_junction_layer_raises_on_missing_or_empty():
    with pytest.raises(NoJunctionError):
        _check_junction_layer({})
    with pytest.raises(NoJunctionError):
        _check_junction_layer({ModelLayer.JUNCTIONS: pd.DataFrame()})


def test_check_reservoir_or_tank_exists_accepts_valid():
    # reservoir present -> should not raise
    r = pd.DataFrame([{Field.NAME: "R1", Field.BASE_HEAD: 10.0}])
    _check_reservoir_or_tank_exists({ModelLayer.RESERVOIRS: r})

    # tank present -> should not raise
    t = pd.DataFrame(
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
            {ModelLayer.JUNCTIONS: pd.DataFrame([{Field.NAME: "J1", Field.ELEVATION: 1.0}])}
        )

    # present but empty
    with pytest.raises(NoReservoirOrTankError):
        _check_reservoir_or_tank_exists({ModelLayer.RESERVOIRS: pd.DataFrame(), ModelLayer.TANKS: pd.DataFrame()})


def test_check_link_layers_accepts_at_least_one_link():
    layers = {
        ModelLayer.JUNCTIONS: pd.DataFrame([{Field.NAME: "J1", Field.ELEVATION: 1.0, Field.DEMAND_PATTERN: None}]),
        ModelLayer.PIPES: pd.DataFrame([{Field.NAME: "P1", Field.DIAMETER: 10.0, Field.ROUGHNESS: 0.01}]),
    }
    _check_link_layers(layers)


def test_check_link_layers_raises_when_no_links():
    layers = {
        ModelLayer.JUNCTIONS: pd.DataFrame([{Field.NAME: "J1", Field.ELEVATION: 1.0, Field.DEMAND_PATTERN: None}])
    }
    with pytest.raises(NoLinksError):
        _check_link_layers(layers)


def test_check_link_ends_not_same_node_raises_on_same_node():
    # start_node == end_node -> LinkEndsSameNodeError
    df = pd.DataFrame([{Field.NAME: "L1", "start_node_name": "J1", "end_node_name": "J1", Field.DIAMETER: 10.0}])
    with pytest.raises(LinkEndsSameNodeError) as exc:
        _check_link_ends_not_same_node(ModelLayer.PIPES, df)
    assert "L1" in str(exc.value)


def test_check_link_ends_not_same_node_accepts_valid_rows():
    df = pd.DataFrame([{Field.NAME: "L1", "start_node_name": "J1", "end_node_name": "J2", Field.DIAMETER: 10.0}])
    # should not raise
    _check_link_ends_not_same_node(ModelLayer.PIPES, df)


def test_check_no_orphan_nodes_detects_orphan(layers):
    # two junctions but only one is connected -> the other is orphan
    j_rows = [{Field.NAME: "J1", Field.ELEVATION: 1.0}, {Field.NAME: "J2", Field.ELEVATION: 2.0}]
    layers[ModelLayer.JUNCTIONS] = pd.DataFrame(j_rows)
    # pipe connects J1 to J1, leaving J2 orphaned
    p = pd.DataFrame(
        [
            {
                Field.NAME: "P1",
                "start_node_name": "J1",
                "end_node_name": "R1",
                Field.DIAMETER: 100.0,
                Field.ROUGHNESS: 0.01,
            }
        ]
    )
    layers[ModelLayer.PIPES] = p
    with pytest.raises(OrphanJunctionsError):
        _check_no_orphan_junctions(layers)


def test_check_no_orphan_nodes_accepts_connected(layers):
    j_rows = [{Field.NAME: "J1", Field.ELEVATION: 1.0}, {Field.NAME: "J2", Field.ELEVATION: 2.0}]
    layers[ModelLayer.JUNCTIONS] = pd.DataFrame(j_rows)
    # pipe connects J1 to J2 so no orphan exists
    p = pd.DataFrame(
        [
            {
                Field.NAME: "P1",
                "start_node_name": "J1",
                "end_node_name": "J2",
                Field.DIAMETER: 100.0,
                Field.ROUGHNESS: 0.01,
            }
        ]
    )
    layers[ModelLayer.PIPES] = p
    # should not raise
    _check_no_orphan_junctions(layers)


def test_verify_model_link_ends_same_node_appended_via_verify(layers):
    # Create a pipe that connects to the same junction on both ends
    # and include a reservoir so the model is not considered empty.
    j_row = {Field.NAME: "J1", Field.ELEVATION: 1.0}
    p_row = {Field.NAME: "P1", "start_node_name": "J1", "end_node_name": "J1", Field.DIAMETER: 100.0}
    r_row = {Field.NAME: "R1", Field.BASE_HEAD: 10.0}
    layers = {
        ModelLayer.JUNCTIONS: pd.DataFrame([j_row]),
        ModelLayer.PIPES: pd.DataFrame([p_row]),
        ModelLayer.RESERVOIRS: pd.DataFrame([r_row]),
    }
    with pytest.raises(MultipleVerificationError) as exc:
        verify_model(layers)
    # should mention the link that has same start/end
    assert "P1" in str(exc.value)


def test_verify_model_raises_no_reservoir_or_tank_and_appends(layers):
    # Provide junctions and a pipe but no reservoirs/tanks so the
    # _check_reservoir_or_tank_exists call inside verify_model raises.
    j_row = {Field.NAME: "J1", Field.ELEVATION: 1.0}
    p_row = {
        Field.NAME: "P1",
        Field.DIAMETER: 100.0,
        Field.ROUGHNESS: 0.01,
        "start_node_name": "J1",
        "end_node_name": "J2",
    }
    layers = {ModelLayer.JUNCTIONS: pd.DataFrame([j_row]), ModelLayer.PIPES: pd.DataFrame([p_row])}
    with pytest.raises(NoReservoirOrTankError):
        verify_model(layers)


def test_check_no_orphan_junctions_returns_on_no_links_or_missing_junctions():
    # No links -> function should simply return (no raise)
    j_df = pd.DataFrame([{Field.NAME: "J1", Field.ELEVATION: 1.0}])
    _check_no_orphan_junctions({ModelLayer.JUNCTIONS: j_df})

    # Links present but no junctions -> should return (no raise)
    p_df = pd.DataFrame([{Field.NAME: "P1", "start_node_name": "J1", "end_node_name": "J2", Field.DIAMETER: 10.0}])
    _check_no_orphan_junctions({ModelLayer.PIPES: p_df})


def test_verify_model_appends_orphan_error(layers):
    # Two junctions but only one is connected -> the other is orphan
    j_rows = [{Field.NAME: "J1", Field.ELEVATION: 1.0}, {Field.NAME: "J2", Field.ELEVATION: 2.0}]
    p = pd.DataFrame(
        [
            {
                Field.NAME: "P1",
                "start_node_name": "J1",
                "end_node_name": "R1",
                Field.DIAMETER: 100.0,
                Field.ROUGHNESS: 0.01,
            }
        ]
    )
    r = pd.DataFrame([{Field.NAME: "R1", Field.BASE_HEAD: 10.0}])
    layers = {ModelLayer.JUNCTIONS: pd.DataFrame(j_rows), ModelLayer.PIPES: p, ModelLayer.RESERVOIRS: r}
    with pytest.raises(OrphanJunctionsError):
        verify_model(layers)


def test_check_no_orphan_junctions_returns_if_junctions_missing_name_column():
    # Links present and junctions present but junctions lack Field.NAME -> should return
    p_df = pd.DataFrame(
        [
            {
                Field.NAME: "P1",
                "start_node_name": "J1",
                "end_node_name": "R1",
                Field.DIAMETER: 10.0,
                Field.ROUGHNESS: 0.01,
            }
        ]
    )
    # Junctions dataframe missing Field.NAME column
    j_df = pd.DataFrame([{Field.ELEVATION: 1.0}])
    _check_no_orphan_junctions({ModelLayer.PIPES: p_df, ModelLayer.JUNCTIONS: j_df})


def test_check_required_field_behaviour():
    df = pd.DataFrame([{Field.NAME: "N1", Field.ELEVATION: 2.0, Field.DEMAND_PATTERN: None}])
    # present should not raise
    _check_required_field(df, ModelLayer.JUNCTIONS, Field.ELEVATION)

    # missing column
    with pytest.raises(RequiredFieldError):
        _check_required_field(pd.DataFrame([{Field.NAME: "N1"}]), ModelLayer.JUNCTIONS, Field.ELEVATION)

    # NaN value
    df_nan = pd.DataFrame([{Field.NAME: "N1", Field.ELEVATION: float("nan")}])
    with pytest.raises(RequiredFieldError):
        _check_required_field(df_nan, ModelLayer.JUNCTIONS, Field.ELEVATION)


def test_check_valve_settings_various_paths():
    # missing valve_type column -> ValveTypeError
    with pytest.raises(ValveTypeError):
        _check_valve_settings(pd.DataFrame([{Field.NAME: "V1", Field.DIAMETER: 10.0, Field.HEADLOSS_CURVE: None}]))

    # non-string valve_type -> AttributeError path -> ValveTypeError
    with pytest.raises(ValveTypeError):
        _check_valve_settings(
            pd.DataFrame([{Field.NAME: "V1", Field.VALVE_TYPE: 1, Field.DIAMETER: 10.0, Field.HEADLOSS_CURVE: None}])
        )

    # invalid valve_type value -> ValveTypeError
    with pytest.raises(ValveTypeError):
        _check_valve_settings(
            pd.DataFrame(
                [{Field.NAME: "V1", Field.VALVE_TYPE: "XXX", Field.DIAMETER: 10.0, Field.HEADLOSS_CURVE: None}]
            )
        )

    # missing setting field for PRV -> ValveSettingError
    df = pd.DataFrame([{Field.NAME: "V1", Field.VALVE_TYPE: "PRV", Field.DIAMETER: 10.0, Field.HEADLOSS_CURVE: None}])
    with pytest.raises(ValveSettingError):
        _check_valve_settings(df)

    # NaN setting value for PRV -> ValveSettingError
    df2 = pd.DataFrame(
        [
            {
                Field.NAME: "V1",
                Field.VALVE_TYPE: "PRV",
                Field.PRESSURE_SETTING: float("nan"),
                Field.DIAMETER: 10.0,
                Field.HEADLOSS_CURVE: None,
            }
        ]
    )
    with pytest.raises(ValveSettingError):
        _check_valve_settings(df2)

    # valid valve row -> should not raise
    df_ok = pd.DataFrame(
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
    # missing pump_type column -> PumpTypeError
    with pytest.raises(PumpTypeError):
        _check_pump_parameters(pd.DataFrame([{Field.NAME: "PU1"}]))

    # invalid pump_type value -> PumpTypeError
    with pytest.raises(PumpTypeError):
        _check_pump_parameters(pd.DataFrame([{Field.NAME: "PU1", Field.PUMP_TYPE: "XXX"}]))

    # power pump missing power -> PumpPowerError
    with pytest.raises(PumpPowerError):
        _check_pump_parameters(pd.DataFrame([{Field.NAME: "PU1", Field.PUMP_TYPE: PumpTypes.POWER.value}]))

    # power pump with non-positive power -> PumpPowerError
    with pytest.raises(PumpPowerError):
        _check_pump_parameters(
            pd.DataFrame([{Field.NAME: "PU1", Field.PUMP_TYPE: PumpTypes.POWER.value, Field.POWER: 0}])
        )

    # head pump missing curve -> PumpCurveMissingError
    with pytest.raises(PumpCurveMissingError):
        _check_pump_parameters(pd.DataFrame([{Field.NAME: "PU1", Field.PUMP_TYPE: PumpTypes.HEAD.value}]))

    # valid power pump -> should not raise
    df_ok = pd.DataFrame([{Field.NAME: "PU1", Field.PUMP_TYPE: PumpTypes.POWER.value, Field.POWER: 10.0}])
    _check_pump_parameters(df_ok)


def test_verify_model_invalid_pattern_raises_pattern_error():
    # invalid demand pattern for junction should raise PatternError
    j = pd.DataFrame([{Field.NAME: "J1", Field.ELEVATION: 1.0, Field.DEMAND_PATTERN: "a b c"}])
    p = pd.DataFrame([{Field.NAME: "P1", Field.DIAMETER: 100.0, Field.ROUGHNESS: 0.01}])
    # include a reservoir so the reservoir/tank check does not also fail
    r = pd.DataFrame([make_row(ModelLayer.RESERVOIRS, {Field.NAME: "R1", Field.BASE_HEAD: 10.0})])
    layers = {ModelLayer.JUNCTIONS: j, ModelLayer.PIPES: p, ModelLayer.RESERVOIRS: r}
    with pytest.raises(PatternError):
        verify_model(layers)


def test_verify_model_tank_invalid_vol_curve_raises_curve_error():
    # valid required tank fields but invalid vol_curve string
    t = pd.DataFrame(
        [
            {
                Field.NAME: "T1",
                Field.ELEVATION: 0.0,
                Field.INIT_LEVEL: 1.0,
                Field.MIN_LEVEL: 0.0,
                Field.MAX_LEVEL: 2.0,
                Field.TANK_DIAMETER: 10.0,
                Field.VOL_CURVE: "not a curve",
            }
        ]
    )
    p = pd.DataFrame([{Field.NAME: "P1", Field.DIAMETER: 100.0, Field.ROUGHNESS: 0.01}])
    j_row = make_row(ModelLayer.JUNCTIONS, {Field.NAME: "J1", Field.ELEVATION: 1.0})
    layers = {ModelLayer.TANKS: t, ModelLayer.JUNCTIONS: pd.DataFrame([j_row]), ModelLayer.PIPES: p}
    with pytest.raises(CurveError):
        verify_model(layers)


def test_verify_model_valve_gpv_invalid_curve_raises_curve_error():
    # GPV with invalid headloss_curve string should raise CurveError
    v = pd.DataFrame(
        [{Field.NAME: "V1", Field.VALVE_TYPE: "GPV", Field.HEADLOSS_CURVE: "(not,a),(b,c)", Field.DIAMETER: 50.0}]
    )
    j_row = make_row(ModelLayer.JUNCTIONS, {Field.NAME: "J1", Field.ELEVATION: 1.0})
    r = pd.DataFrame([make_row(ModelLayer.RESERVOIRS, {Field.NAME: "R1", Field.BASE_HEAD: 10.0})])
    layers = {
        ModelLayer.VALVES: v,
        ModelLayer.JUNCTIONS: pd.DataFrame([j_row]),
        ModelLayer.PIPES: pd.DataFrame([{Field.NAME: "P1", Field.DIAMETER: 100.0, Field.ROUGHNESS: 0.01}]),
        ModelLayer.RESERVOIRS: r,
    }
    with pytest.raises(CurveError):
        verify_model(layers)


def test_verify_model_valve_gpv_empty_curve_raises_valve_setting_error():
    # GPV with empty curve should be treated as missing and raise ValveSettingError
    v = pd.DataFrame([{Field.NAME: "V1", Field.VALVE_TYPE: "GPV", Field.HEADLOSS_CURVE: "", Field.DIAMETER: 50.0}])
    j_row = make_row(ModelLayer.JUNCTIONS, {Field.NAME: "J1", Field.ELEVATION: 1.0})
    r = pd.DataFrame([make_row(ModelLayer.RESERVOIRS, {Field.NAME: "R1", Field.BASE_HEAD: 10.0})])
    layers = {
        ModelLayer.VALVES: v,
        ModelLayer.JUNCTIONS: pd.DataFrame([j_row]),
        ModelLayer.PIPES: pd.DataFrame([{Field.NAME: "P1", Field.DIAMETER: 100.0, Field.ROUGHNESS: 0.01}]),
        ModelLayer.RESERVOIRS: r,
    }
    with pytest.raises(ValveSettingError):
        verify_model(layers)


def test_verify_model_pump_head_curve_invalid_raises_curve_error():
    # HEAD pump with invalid pump_curve string should raise CurveError
    pump_row = make_row(
        ModelLayer.PUMPS, {Field.NAME: "PU1", Field.PUMP_TYPE: PumpTypes.HEAD.value, Field.PUMP_CURVE: "not a curve"}
    )
    pu = pd.DataFrame([pump_row])
    j_row = make_row(ModelLayer.JUNCTIONS, {Field.NAME: "J1", Field.ELEVATION: 1.0})
    r = pd.DataFrame([make_row(ModelLayer.RESERVOIRS, {Field.NAME: "R1", Field.BASE_HEAD: 10.0})])
    layers = {
        ModelLayer.PUMPS: pu,
        ModelLayer.JUNCTIONS: pd.DataFrame([j_row]),
        ModelLayer.PIPES: pd.DataFrame([{Field.NAME: "P1", Field.DIAMETER: 100.0, Field.ROUGHNESS: 0.01}]),
        ModelLayer.RESERVOIRS: r,
    }
    with pytest.raises(CurveError):
        verify_model(layers)


def test_verify_duplicate_node_names_raises_duplicate_name_error(layers):
    # make reservoir name duplicate of junction name to trigger node duplicate
    # set reservoir name to match junction
    layers[ModelLayer.RESERVOIRS].iloc[0, layers[ModelLayer.RESERVOIRS].columns.get_loc(Field.NAME)] = layers[
        ModelLayer.JUNCTIONS
    ].iloc[0, layers[ModelLayer.JUNCTIONS].columns.get_loc(Field.NAME)]
    with pytest.raises(DuplicateNodeNameError):
        verify_model(layers)


def test_check_duplicate_node_names_helper_raises_and_accepts(layers):
    # duplicate should raise
    layers[ModelLayer.RESERVOIRS].iloc[0, layers[ModelLayer.RESERVOIRS].columns.get_loc(Field.NAME)] = layers[
        ModelLayer.JUNCTIONS
    ].iloc[0, layers[ModelLayer.JUNCTIONS].columns.get_loc(Field.NAME)]
    with pytest.raises(DuplicateNodeNameError):
        _check_duplicate_node_names(layers)


def test_verify_duplicate_link_names_raises_duplicate_name_error(layers):
    # make pipe and valve share the same name -> link duplicate
    # pipe name is P1 in minimal layers
    v_row = make_row(
        ModelLayer.VALVES,
        {Field.NAME: "P1", Field.VALVE_TYPE: "PRV", Field.PRESSURE_SETTING: 5.0, Field.DIAMETER: 50.0},
    )
    layers[ModelLayer.VALVES] = pd.DataFrame([v_row])
    with pytest.raises(DuplicateLinkNameError):
        verify_model(layers)


def test_check_duplicate_link_names_helper_raises_and_accepts(layers):
    # duplicate should raise
    v_row = make_row(
        ModelLayer.VALVES,
        {Field.NAME: "P1", Field.VALVE_TYPE: "PRV", Field.PRESSURE_SETTING: 5.0, Field.DIAMETER: 50.0},
    )

    layers[ModelLayer.VALVES] = pd.DataFrame([v_row])
    with pytest.raises(DuplicateLinkNameError):
        _check_duplicate_link_names(layers)


def test_verify_both_node_and_link_duplicates_aggregated_into_multiple_verification_error(layers):
    # create node duplicate: reservoir name == junction name
    layers[ModelLayer.RESERVOIRS].iloc[0, layers[ModelLayer.RESERVOIRS].columns.get_loc(Field.NAME)] = layers[
        ModelLayer.JUNCTIONS
    ].iloc[0, layers[ModelLayer.JUNCTIONS].columns.get_loc(Field.NAME)]
    # create link duplicate: valves named same as pipe
    v_row = make_row(
        ModelLayer.VALVES,
        {Field.NAME: "P1", Field.VALVE_TYPE: "PRV", Field.PRESSURE_SETTING: 5.0, Field.DIAMETER: 50.0},
    )
    layers[ModelLayer.VALVES] = pd.DataFrame([v_row])

    with pytest.raises(MultipleVerificationError) as exc:
        verify_model(layers)

    msg = str(exc.value)
    assert "Duplicate node names found" in msg
    assert "Duplicate link names found" in msg


def test_check_model_not_empty_raises_on_empty_mapping():
    with pytest.raises(EmptyModelError):
        _check_model_not_empty({})


def test_check_model_not_empty_raises_when_all_layers_empty():
    layers = {ModelLayer.JUNCTIONS: pd.DataFrame(), ModelLayer.PIPES: pd.DataFrame()}
    with pytest.raises(EmptyModelError):
        _check_model_not_empty(layers)


def test_check_model_not_empty_accepts_non_empty_layer():
    layers = {ModelLayer.JUNCTIONS: pd.DataFrame([{Field.NAME: "J1", Field.ELEVATION: 1.0}])}
    # should not raise
    _check_model_not_empty(layers)


@pytest.mark.parametrize("bad_name", ["bad name"])
def test_verify_names_reject_whitespace(bad_name):
    j = pd.DataFrame([{Field.NAME: bad_name, Field.ELEVATION: 1.0}])
    p = pd.DataFrame(
        [
            {
                Field.NAME: "P1",
                Field.DIAMETER: 10.0,
                Field.ROUGHNESS: 0.01,
                "start_node_name": bad_name,
                "end_node_name": "R1",
            }
        ]
    )
    r = pd.DataFrame([{Field.NAME: "R1", Field.BASE_HEAD: 10.0}])
    layers = {ModelLayer.JUNCTIONS: j, ModelLayer.PIPES: p, ModelLayer.RESERVOIRS: r}
    with pytest.raises(NameFieldError):
        verify_model(layers)


@pytest.mark.parametrize("blank", ["", "   "])
def test_verify_names_reject_blank(blank):
    j = pd.DataFrame([{Field.NAME: blank, Field.ELEVATION: 1.0}])
    p = pd.DataFrame(
        [
            {
                Field.NAME: "P1",
                Field.DIAMETER: 10.0,
                Field.ROUGHNESS: 0.01,
                "start_node_name": blank,
                "end_node_name": "R1",
            }
        ]
    )
    r = pd.DataFrame([{Field.NAME: "R1", Field.BASE_HEAD: 10.0}])
    layers = {ModelLayer.JUNCTIONS: j, ModelLayer.PIPES: p, ModelLayer.RESERVOIRS: r}
    with pytest.raises(NameFieldError):
        verify_model(layers)


def test_verify_names_reject_long_name():
    long_name = "a" * 32
    j = pd.DataFrame([{Field.NAME: long_name, Field.ELEVATION: 1.0}])
    p = pd.DataFrame(
        [
            {
                Field.NAME: "P1",
                Field.DIAMETER: 10.0,
                Field.ROUGHNESS: 0.01,
                "start_node_name": long_name,
                "end_node_name": "R1",
            }
        ]
    )
    r = pd.DataFrame([{Field.NAME: "R1", Field.BASE_HEAD: 10.0}])
    layers = {ModelLayer.JUNCTIONS: j, ModelLayer.PIPES: p, ModelLayer.RESERVOIRS: r}
    with pytest.raises(NameFieldError):
        verify_model(layers)


def test_verify_names_accept_valid_and_nulls():
    j = pd.DataFrame([{Field.NAME: "J_OK", Field.ELEVATION: 1.0}, {Field.NAME: pd.NA, Field.ELEVATION: 2.0}])
    p = pd.DataFrame(
        [
            {
                Field.NAME: "P1",
                Field.DIAMETER: 10.0,
                Field.ROUGHNESS: 0.01,
                "start_node_name": "J_OK",
                "end_node_name": "R1",
            }
        ]
    )
    r = pd.DataFrame([{Field.NAME: "R1", Field.BASE_HEAD: 10.0}])
    layers = {ModelLayer.JUNCTIONS: j, ModelLayer.PIPES: p, ModelLayer.RESERVOIRS: r}
    # Should not raise
    verify_model(layers)


@pytest.mark.parametrize("bad_name", ["bad name"])
def test_check_names_reject_whitespace(bad_name):
    df = pd.DataFrame([{Field.NAME: bad_name}])
    with pytest.raises(NameFieldError, match=str(bad_name)):
        _check_names({ModelLayer.JUNCTIONS: df})


@pytest.mark.parametrize("blank", ["", "   "])
def test_check_names_reject_blank(blank):
    df = pd.DataFrame([{Field.NAME: blank}])
    with pytest.raises(NameFieldError):
        _check_names({ModelLayer.JUNCTIONS: df})


def test_check_names_reject_long_name():
    long_name = "a" * 32
    df = pd.DataFrame([{Field.NAME: long_name}])
    with pytest.raises(NameFieldError, match=long_name):
        _check_names({ModelLayer.JUNCTIONS: df})


def test_check_names_accepts_valid_and_nulls():
    df = pd.DataFrame([{Field.NAME: "J_OK"}, {Field.NAME: pd.NA}])
    # should not raise
    _check_names({ModelLayer.JUNCTIONS: df})


def test_check_names_ignores_missing_name_column():
    df = pd.DataFrame([{"elevation": 1.0}])
    # should not raise when Field.NAME isn't present
    _check_names({ModelLayer.JUNCTIONS: df})


def test_check_names_all_nulls_ignored():
    df = pd.DataFrame([{Field.NAME: pd.NA}, {Field.NAME: pd.NA}])
    # should not raise if all names are null
    _check_names({ModelLayer.JUNCTIONS: df})


def test_check_names_non_string_values():
    df = pd.DataFrame([{Field.NAME: 123}, {Field.NAME: "ValidName"}])
    with pytest.raises(NameFieldError, match="123"):
        _check_names({ModelLayer.JUNCTIONS: df})


def test_check_collect_names_for_layers_handles_missing_name_column():
    # If a layer exists but lacks Field.NAME, the collector should return empty list
    layers = {ModelLayer.PIPES: pd.DataFrame([{Field.DIAMETER: 10.0}])}
    names = _collect_names_for_layers(layers, [ModelLayer.PIPES])
    assert names == []


def test_check_valve_settings_gpv_nan_curve_raises():
    # GPV declared but headloss curve column contains NaN -> ValveSettingError
    df = pd.DataFrame(
        [{Field.NAME: "V1", Field.VALVE_TYPE: "GPV", Field.HEADLOSS_CURVE: float("nan"), Field.DIAMETER: 50.0}]
    )
    with pytest.raises(ValveSettingError):
        _check_valve_settings(df)


def test_check_pump_parameters_head_curve_nan_raises():
    # HEAD pump with PUMP_CURVE present but NaN should raise PumpCurveMissingError
    df = pd.DataFrame([{Field.NAME: "PU1", Field.PUMP_TYPE: PumpTypes.HEAD.value, Field.PUMP_CURVE: float("nan")}])
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
    df = pd.DataFrame(
        [{Field.NAME: "V1", Field.VALVE_TYPE: "GPV", Field.HEADLOSS_CURVE: "(1,2),(3,4)", Field.DIAMETER: 50.0}]
    )
    _check_valve_settings(df)


def test_check_pump_parameters_head_curve_valid_accepts():
    # HEAD pump with a valid pump curve string should not raise
    df = pd.DataFrame([{Field.NAME: "PU1", Field.PUMP_TYPE: PumpTypes.HEAD.value, Field.PUMP_CURVE: "(1,2),(3,4)"}])
    _check_pump_parameters(df)


def test_verify_model_curve_error_includes_notes_via_mapping(monkeypatch):
    # Monkeypatch Curve.factory to raise a ValueError with __notes__ set
    def bad_curve(s):
        e = ValueError("bad curve")
        e.__notes__ = ["note from parser"]
        raise e

    monkeypatch.setattr("gusnet.pattern_curve.Curve.factory", bad_curve)

    t = pd.DataFrame(
        [
            {
                Field.NAME: "T1",
                Field.ELEVATION: 0.0,
                Field.INIT_LEVEL: 1.0,
                Field.MIN_LEVEL: 0.0,
                Field.MAX_LEVEL: 2.0,
                Field.TANK_DIAMETER: 10.0,
                Field.VOL_CURVE: "not a curve",
            }
        ]
    )
    j_row = make_row(ModelLayer.JUNCTIONS, {Field.NAME: "J1", Field.ELEVATION: 1.0})
    # add a minimal pipe so the model has at least one link and
    # the tank curve error is the only expected error
    p_row = make_row(
        ModelLayer.PIPES,
        {
            Field.NAME: "P1",
            Field.DIAMETER: 100.0,
            Field.ROUGHNESS: 0.01,
            "start_node_name": "J1",
            "end_node_name": "T1",
        },
    )
    layers = {ModelLayer.TANKS: t, ModelLayer.JUNCTIONS: pd.DataFrame([j_row]), ModelLayer.PIPES: pd.DataFrame([p_row])}
    with pytest.raises(CurveError) as exc:
        verify_model(layers)
    assert "note from parser" in str(exc.value)


def test_check_numeric_field_type_raises_on_non_numeric():
    df = pd.DataFrame([{Field.NAME: "N1", Field.ELEVATION: "not-a-number"}])
    with pytest.raises(NumericFieldError):
        _check_numeric_field_type(df, ModelLayer.JUNCTIONS, Field.ELEVATION)


def test_check_numeric_field_type_skips_missing_or_all_na():
    # missing column -> should not raise
    df_missing = pd.DataFrame([{Field.NAME: "N1"}])
    _check_numeric_field_type(df_missing, ModelLayer.JUNCTIONS, Field.ELEVATION)

    # all NA -> should not raise
    df_na = pd.DataFrame([{Field.NAME: "N1", Field.ELEVATION: float("nan")}])
    _check_numeric_field_type(df_na, ModelLayer.JUNCTIONS, Field.ELEVATION)


@pytest.mark.parametrize("value", [True, False, [True, False], [True, False, np.nan], [1.0, 0.0]])
def test_check_boolean_field_type_accepts_boolean_values(value):
    df = pd.DataFrame({Field.OVERFLOW: pd.Series(value)})
    _check_boolean_field_type(df, ModelLayer.TANKS, Field.OVERFLOW)


def test_check_boolean_field_type_raises_on_non_boolean():
    # Field.OVERFLOW is a BOOL on TANKS
    df = pd.DataFrame([{Field.NAME: "T1", Field.OVERFLOW: "yes"}])
    with pytest.raises(BooleanFieldError):
        _check_boolean_field_type(df, ModelLayer.TANKS, Field.OVERFLOW)


def test_check_boolean_field_type_skips_missing_or_all_na():
    df_missing = pd.DataFrame([{Field.NAME: "T1"}])
    _check_boolean_field_type(df_missing, ModelLayer.TANKS, Field.OVERFLOW)

    df_na = pd.DataFrame([{Field.NAME: "T1", Field.OVERFLOW: float("nan")}])
    _check_boolean_field_type(df_na, ModelLayer.TANKS, Field.OVERFLOW)


def test_verify_model_raises_numeric_field_error_via_verify_model():
    # Create a minimal valid model where junction elevation is non-numeric
    j = pd.DataFrame([{Field.NAME: "J1", Field.ELEVATION: "bad"}])
    p = pd.DataFrame(
        [
            {
                Field.NAME: "P1",
                Field.DIAMETER: 100.0,
                Field.ROUGHNESS: 0.01,
                "start_node_name": "J1",
                "end_node_name": "R1",
            }
        ]
    )
    r = pd.DataFrame([{Field.NAME: "R1", Field.BASE_HEAD: 10.0}])
    layers = {ModelLayer.JUNCTIONS: j, ModelLayer.PIPES: p, ModelLayer.RESERVOIRS: r}
    with pytest.raises(NumericFieldError):
        verify_model(layers)


def test_verify_model_raises_boolean_field_error_via_verify_model():
    # Create a minimal valid model where tank OVERFLOW is non-boolean
    j = pd.DataFrame([{Field.NAME: "J1", Field.ELEVATION: 1.0}])
    p = pd.DataFrame(
        [
            {
                Field.NAME: "P1",
                Field.DIAMETER: 100.0,
                Field.ROUGHNESS: 0.01,
                "start_node_name": "J1",
                "end_node_name": "T1",
            }
        ]
    )
    t = pd.DataFrame(
        [
            {
                Field.NAME: "T1",
                Field.ELEVATION: 0.0,
                Field.INIT_LEVEL: 1.0,
                Field.MIN_LEVEL: 0.0,
                Field.MAX_LEVEL: 2.0,
                Field.TANK_DIAMETER: 10.0,
                Field.OVERFLOW: "yes",
            }
        ]
    )
    layers = {ModelLayer.JUNCTIONS: j, ModelLayer.PIPES: p, ModelLayer.TANKS: t}
    with pytest.raises(BooleanFieldError):
        verify_model(layers)


def test_verify_power_pump_power_non_numeric_raises_numeric_field_error():
    # If POWER contains a non-numeric string, verify_model should raise NumericFieldError
    j = pd.DataFrame([{Field.NAME: "J1", Field.ELEVATION: 1.0}])
    p = pd.DataFrame(
        [
            {
                Field.NAME: "P1",
                Field.DIAMETER: 100.0,
                Field.ROUGHNESS: 0.01,
                "start_node_name": "J1",
                "end_node_name": "R1",
            }
        ]
    )
    pump = pd.DataFrame([{Field.NAME: "PU1", Field.PUMP_TYPE: PumpTypes.POWER.value, Field.POWER: "not-a-number"}])
    r = pd.DataFrame([{Field.NAME: "R1", Field.BASE_HEAD: 10.0}])
    layers = {ModelLayer.JUNCTIONS: j, ModelLayer.PIPES: p, ModelLayer.PUMPS: pump, ModelLayer.RESERVOIRS: r}

    with pytest.raises(NumericFieldError):
        verify_model(layers)


def test_verify_all_parameter_fields_as_strings_only_raise_verification_errors():
    """Set every Parameter-typed field to a string and ensure verify_model only raises VerificationError.

    This guards against non-VerificationError exceptions leaking out when numeric comparisons
    or dtype checks encounter unexpected string values.
    """
    # Build one representative row per layer. For Parameter fields insert a non-numeric string.
    bad_value = "not-a-number"

    layers = {}
    for layer in ModelLayer:
        row = {}
        for field in layer.wq_fields():
            # Put the bad string into Parameter-typed fields
            if isinstance(field.type, Parameter):
                row[field] = bad_value
                continue

            # For known specific fields provide minimal valid entries
            if field is Field.NAME:
                row[field] = f"{layer.name}_1"
                continue

            if field is Field.PUMP_TYPE:
                row[field] = PumpTypes.POWER.value
                continue

            if field is Field.VALVE_TYPE:
                row[field] = "PRV"
                continue

            # default: None (many checks skip NA or None)
            row[field] = None

        layers[layer] = pd.DataFrame([row])

    # Ensure running verify_model raises a VerificationError (or subclass) and not e.g. TypeError
    with pytest.raises(VerificationError):
        verify_model(layers)


def test_verify_all_bool_fields_as_strings_only_raise_verification_errors():
    """Set every BOOL-typed field to a string and ensure verify_model only raises VerificationError.

    This guards against non-VerificationError exceptions leaking out when boolean checks
    encounter unexpected string values.
    """
    bad_value = "not-a-bool"

    layers = {}
    for layer in ModelLayer:
        row = {}
        for field in layer.wq_fields():
            if field.type is SimpleFieldType.BOOL:
                row[field] = bad_value
                continue

            # Provide valid map/type defaults to avoid unrelated errors
            if field is Field.PUMP_TYPE:
                row[field] = PumpTypes.POWER.value
                continue

            if field is Field.VALVE_TYPE:
                row[field] = "PRV"
                continue

            if field is Field.NAME:
                row[field] = f"{layer.name}_1"
                continue

            # default: None
            row[field] = None

        layers[layer] = pd.DataFrame([row])

    with pytest.raises(VerificationError):
        verify_model(layers)
