import types

import pytest

from gusnet.elements import Field
from gusnet.units import Converter
from gusnet.wntr_wrapper import WntrWrapper

pytestmark = [pytest.mark.needs_wntr, pytest.mark.needs_pandas]


# Add a tiny mock converter used by tests that want an identity conversion.
class _DummyConverter(Converter):
    def __init__(self):
        pass

    def from_si(self, df, param):
        return df


def make_wn_with_pipe(use_dummy_converter: bool = True) -> WntrWrapper:
    """Create a simple WntrModel with a single pipe named `pipe1` from `J1` to `J2`.

    The pipe length defaults to 10.0; tests that need a different length can modify
    `model._wn` after receiving the model.

    Parameters
    - use_dummy_converter: if True the returned model will have a no-op converter
      (`from_si` returns the input unchanged). If False, the model keeps the
      real converter so tests can exercise unit conversions (e.g. GPM).
    """
    import wntr

    wn = wntr.network.WaterNetworkModel()
    wn.add_junction("J1", base_demand=0, elevation=0)
    wn.add_junction("J2", base_demand=0, elevation=0)
    wn.add_pipe("pipe1", "J1", "J2", length=10.0, diameter=100.0, roughness=0.01)
    model = WntrWrapper(wn)

    # By default tests want a predictable, identity converter so we don't need to
    # replicate unit conversion math in every assertion. Allow tests to opt-out
    # and exercise the real `Converter` by passing `use_dummy_converter=False`.
    if use_dummy_converter:
        # assign a mock converter instance rather than replacing a method on the real converter
        model._converter = _DummyConverter()

    return model


def test_get_results_single_period_headloss_simple():
    import pandas as pd

    model = make_wn_with_pipe()

    # Build headloss DataFrame: single timestep with a pump and a pipe
    headloss_df = pd.DataFrame([[2.0, 0.1]], columns=["pump1", "pipe1"], index=[0])
    # Provide minimal node results so node processing has at least one field
    node_df = pd.DataFrame([[10.0]], columns=["J1"], index=[0])
    model._wntr_results = types.SimpleNamespace(
        node={Field.HEAD.value: node_df}, link={Field.HEADLOSS.value: headloss_df}
    )

    # Default options have simulation_duration == 0; no override required

    results = model.get_results()

    assert results == {
        "LINKS": {
            "headloss": [6.561679790026246, 3.280839895013123],
            "name": ["pump1", "pipe1"],
            "unit_headloss": [None, 100.0],
        },
        "NODES": {"head": [32.808398950131235], "name": ["J1"]},
    }


def test_get_results_multi_period_lists():
    import pandas as pd

    model = make_wn_with_pipe()

    # Two timesteps
    headloss_df = pd.DataFrame([[2.0, 0.1], [3.0, 0.2]], columns=["pump1", "pipe1"], index=[0, 1])
    # minimal node head results for two timesteps
    node_df = pd.DataFrame([[10.0], [11.0]], columns=["J1"], index=[0, 1])
    model._wntr_results = types.SimpleNamespace(
        node={Field.HEAD.value: node_df}, link={Field.HEADLOSS.value: headloss_df}
    )

    # Indicate multi-period run
    model._options = types.SimpleNamespace(simulation_duration=1)

    results = model.get_results()

    assert results == {
        "LINKS": {
            "headloss": [[6.561679790026246, 9.84251968503937], [3.280839895013123, 6.561679790026246]],
            "name": ["pump1", "pipe1"],
            "unit_headloss": [None, [100.0, 200.0]],
        },
        "NODES": {"head": [[32.808398950131235, 36.08923884514436]], "name": ["J1"]},
    }


def test_zero_length_pipe_handled_gracefully():
    import pandas as pd

    # Create a pipe with zero length — total headloss should become zero for pipe entries
    model = make_wn_with_pipe()
    # set the pipe length to zero for this test
    for name, pipe in model._wn.pipes():
        if name == "pipe1":
            pipe.length = 0.0
    # Mock get_converter to return dummy converter
    dummy_converter = _DummyConverter()
    model.get_converter = lambda flow_unit=None: dummy_converter

    headloss_df = pd.DataFrame([[1.0]], columns=["pipe1"], index=[0])
    node_df = pd.DataFrame([[10.0]], columns=["J1"], index=[0])
    model._wntr_results = types.SimpleNamespace(
        node={Field.HEAD.value: node_df}, link={Field.HEADLOSS.value: headloss_df}
    )

    results = model.get_results()
    links_dict = results["LINKS"]

    # unit headloss 1.0 * length 0.0 -> total 0.0 for the created `pipe1`
    pipe1_index = links_dict["name"].index("pipe1")
    assert pytest.approx(0.0) == links_dict[Field.HEADLOSS.value][pipe1_index]


def test_missing_pipe_length_column_results_in_no_unit_headloss():
    import pandas as pd

    # If a headloss DataFrame contains a link not present in wn.pipes(), unit_headloss will not include it
    model = make_wn_with_pipe()
    # Mock get_converter to return dummy converter
    dummy_converter = _DummyConverter()
    model.get_converter = lambda flow_unit=None: dummy_converter

    # headloss includes an extra link 'unknown_pipe' which is not in wn.pipes()
    headloss_df = pd.DataFrame([[0.1, 0.5]], columns=["pipe1", "unknown_pipe"], index=[0])
    node_df = pd.DataFrame([[10.0]], columns=["J1"], index=[0])
    model._wntr_results = types.SimpleNamespace(
        node={Field.HEAD.value: node_df}, link={Field.HEADLOSS.value: headloss_df}
    )

    results = model.get_results()
    links_dict = results["LINKS"]

    # unknown_pipe cannot have unit_headloss applied (no length known).
    # Its total headloss should be present from the raw value.
    unknown_pipe_index = links_dict["name"].index("unknown_pipe")
    assert pytest.approx(0.5) == links_dict[Field.HEADLOSS.value][unknown_pipe_index]


def test_links_all_fields_handled():
    import pandas as pd

    # Setup model with one pipe (length 10)
    model = make_wn_with_pipe()
    # Mock get_converter to return dummy converter
    dummy_converter = _DummyConverter()
    model.get_converter = lambda flow_unit=None: dummy_converter

    cols = ["pipe1", "pump1", "valve1"]

    # Prepare field data for links
    flow_df = pd.DataFrame([[100.0, 200.0, 300.0]], columns=cols, index=[0])
    headloss_df = pd.DataFrame([[0.1, 3.0, 4.0]], columns=cols, index=[0])
    velocity_df = pd.DataFrame([[1.0, 2.0, 3.0]], columns=cols, index=[0])
    quality_df = pd.DataFrame([[0.1, 0.2, 0.3]], columns=cols, index=[0])
    reaction_df = pd.DataFrame([[0.01, 0.02, 0.03]], columns=cols, index=[0])

    node_df = pd.DataFrame([[10.0]], columns=["J1"], index=[0])

    link_map = {
        Field.FLOWRATE.value: flow_df,
        Field.HEADLOSS.value: headloss_df,
        Field.VELOCITY.value: velocity_df,
        Field.QUALITY.value: quality_df,
        Field.REACTION_RATE.value: reaction_df,
    }

    model._wntr_results = types.SimpleNamespace(node={Field.HEAD.value: node_df}, link=link_map)

    results = model.get_results()
    links_dict = results["LINKS"]

    # Verify presence and correctness of values for each link field
    pipe1_index = links_dict["name"].index("pipe1")
    pump1_index = links_dict["name"].index("pump1")
    valve1_index = links_dict["name"].index("valve1")

    # Check flowrate values match the input
    assert links_dict[Field.FLOWRATE.value][pipe1_index] == 100.0
    assert links_dict[Field.FLOWRATE.value][pump1_index] == 200.0
    assert links_dict[Field.FLOWRATE.value][valve1_index] == 300.0

    # Check velocity values match the input
    assert links_dict[Field.VELOCITY.value][pipe1_index] == 1.0
    assert links_dict[Field.VELOCITY.value][pump1_index] == 2.0
    assert links_dict[Field.VELOCITY.value][valve1_index] == 3.0

    # Check quality values match the input
    assert links_dict[Field.QUALITY.value][pipe1_index] == 0.1
    assert links_dict[Field.QUALITY.value][pump1_index] == 0.2
    assert links_dict[Field.QUALITY.value][valve1_index] == 0.3

    # Check reaction rate values match the input
    assert links_dict[Field.REACTION_RATE.value][pipe1_index] == 0.01
    assert links_dict[Field.REACTION_RATE.value][pump1_index] == 0.02
    assert links_dict[Field.REACTION_RATE.value][valve1_index] == 0.03

    # For headloss, check that pipe1's value is correctly scaled by length (0.1 * 10 = 1.0)
    # and that pump/valve values are present (even if in different order due to _fix_headloss_df)
    headloss_values = links_dict[Field.HEADLOSS.value]
    assert 1.0 in [pytest.approx(v) for v in headloss_values]  # pipe1: 0.1 * 10
    assert 3.0 in headloss_values  # pump1
    assert 4.0 in headloss_values  # valve1


def test_real_converter_flow_conversion_single_period():
    """Verify that when using the real Converter with FlowUnit.GPM, flow values
    returned by `get_results` are converted from SI to GPM."""
    import pandas as pd

    from gusnet.elements import FlowUnit
    from gusnet.units import Converter

    model = make_wn_with_pipe(use_dummy_converter=False)

    # Attach a real converter configured for GPM
    model._converter = Converter(
        FlowUnit.GPM,
        model.options.headloss_formula,
        model.options.mass_unit,
        model.options.wall_reaction_order,
    )

    # Single timestep flow for pipe1 (m3/s). Choose 0.001 m3/s (~15.85 GPM)
    flow_df = pd.DataFrame([[0.001]], columns=["pipe1"], index=[0])
    headloss_df = pd.DataFrame([[0.0]], columns=["pipe1"], index=[0])
    node_df = pd.DataFrame([[10.0]], columns=["J1"], index=[0])

    model.set_results(
        types.SimpleNamespace(
            node={Field.HEAD.value: node_df}, link={Field.FLOWRATE.value: flow_df, Field.HEADLOSS.value: headloss_df}
        )
    )

    results = model.get_results()
    links_dict = results["LINKS"]

    # Compute expected converted value numerically (m3/s -> GPM): GPM = m3/s / (0.003785411784/60)
    factor = 0.003785411784 / 60.0
    expected = 0.001 / factor

    pipe1_index = links_dict["name"].index("pipe1")
    assert pytest.approx(expected) == links_dict[Field.FLOWRATE.value][pipe1_index]


def test_real_converter_flow_conversion_multi_period():
    """Verify multi-period (lists) flow conversion with the real GPM converter."""
    import pandas as pd

    from gusnet.elements import FlowUnit
    from gusnet.units import Converter

    model = make_wn_with_pipe(use_dummy_converter=False)
    model._converter = Converter(
        FlowUnit.GPM,
        model.options.headloss_formula,
        model.options.mass_unit,
        model.options.wall_reaction_order,
    )

    # Two timesteps
    flow_df = pd.DataFrame([[0.001], [0.002]], columns=["pipe1"], index=[0, 1])
    headloss_df = pd.DataFrame([[0.0], [0.0]], columns=["pipe1"], index=[0, 1])
    node_df = pd.DataFrame([[10.0], [11.0]], columns=["J1"], index=[0, 1])

    model._wntr_results = types.SimpleNamespace(
        node={Field.HEAD.value: node_df}, link={Field.FLOWRATE.value: flow_df, Field.HEADLOSS.value: headloss_df}
    )

    # Indicate multi-period run
    model._options = types.SimpleNamespace(simulation_duration=1)

    results = model.get_results()
    links_dict = results["LINKS"]

    factor = 0.003785411784 / 60.0
    expected_list = [0.001 / factor, 0.002 / factor]

    pipe1_index = links_dict["name"].index("pipe1")
    assert links_dict[Field.FLOWRATE.value][pipe1_index] == expected_list

    cols = ["J1", "J2"]
    demand_df = pd.DataFrame([[1.0, 2.0]], columns=cols, index=[0])
    head_df = pd.DataFrame([[10.0, 11.0]], columns=cols, index=[0])
    pressure_df = pd.DataFrame([[5.0, 6.0]], columns=cols, index=[0])
    quality_df = pd.DataFrame([[0.0, 0.1]], columns=cols, index=[0])

    node_map = {
        Field.DEMAND.value: demand_df,
        Field.HEAD.value: head_df,
        Field.PRESSURE.value: pressure_df,
        Field.QUALITY.value: quality_df,
    }

    # Process nodes as single-period results for scalar expectations
    model._options = types.SimpleNamespace(simulation_duration=0)

    model.set_results(
        types.SimpleNamespace(
            node=node_map,
            link={Field.HEADLOSS.value: pd.DataFrame([[0.0]], columns=["pipe1"], index=[0])},
        )
    )

    results = model.get_results()
    nodes_dict = results["NODES"]

    # demand value of 1.0 (SI) converts to GPM numerically: 1.0 / (0.003785411784/60)
    expected_demand = 1.0 / (0.003785411784 / 60.0)
    j1_index = nodes_dict["name"].index("J1")
    assert pytest.approx(expected_demand) == nodes_dict[Field.DEMAND.value][j1_index]
    # Head values are converted from m to ft when using a traditional flow unit (GPM)
    expected_head = 10.0 / 0.3048
    assert pytest.approx(expected_head) == nodes_dict[Field.HEAD.value][j1_index]
    # Pressure is converted by the converter's pressure factor; compute numeric expectation
    pressure_factor = 0.3048 / 0.4333
    expected_pressure = 5.0 / pressure_factor
    assert pytest.approx(expected_pressure) == nodes_dict[Field.PRESSURE.value][j1_index]
    # Concentration (quality) converts from mg/L to kg/m3 via factor 0.001 -> 0.1 / 0.001 == 100.0
    expected_quality = 0.1 / 0.001
    j2_index = nodes_dict["name"].index("J2")
    assert pytest.approx(expected_quality) == nodes_dict[Field.QUALITY.value][j2_index]
