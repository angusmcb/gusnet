from __future__ import annotations

import dataclasses
from copy import deepcopy
from typing import TYPE_CHECKING

import pytest

from gusnet.elements import (
    DefaultOptions,
    DemandType,
    FlowUnit,
    HeadlossFormula,
    MassUnit,
    ModelOptions,
    QualityParameter,
    WallReactionOrder,
)
from gusnet.interface import options_from_wn, options_to_wn
from gusnet.pattern_curve import Pattern

if TYPE_CHECKING:  # pragma: no cover
    import wntr


# Use pytest to filter the specific UserWarning raised by WNTR when changing
# headloss formula (message starts with "Changing the headloss formula from ...").
# This silences the warning for tests in this module without using the warnings
# module directly.
pytestmark = [pytest.mark.filterwarnings("ignore:Changing the headloss formula from .*:UserWarning")]


@pytest.fixture
def wn():
    # Import wntr inside the fixture so tests don't import it at module import time
    import wntr

    return wntr.network.WaterNetworkModel()


def test_options_from_wn_reads_values(wn: wntr.network.WaterNetworkModel):
    # Use a real WaterNetworkModel so any incompatibility in options_from_wn is visible
    wn.add_pattern("my_energy_pattern", [1, 2, 3])

    o = wn.options

    # Set a variety of non-default values using values accepted by wntr
    o.hydraulic.inpfile_units = "GPM"
    o.hydraulic.headloss = "D-W"
    o.time.duration = 3 * 3600
    o.hydraulic.demand_multiplier = 1.5
    o.hydraulic.emitter_exponent = 0.7
    o.hydraulic.demand_model = "PDD"
    o.hydraulic.minimum_pressure = 2.0
    o.hydraulic.required_pressure = 4.0
    o.hydraulic.pressure_exponent = 1.2
    o.energy.global_price = 0.11
    o.energy.global_pattern = "my_energy_pattern"
    o.energy.global_efficiency = 0.9
    o.energy.demand_charge = 5.0

    # Call the function under test using the real object; let failures surface if code is incorrect
    opts = options_from_wn(wn)

    assert opts.flow_unit is FlowUnit.GPM
    assert opts.headloss_formula is HeadlossFormula.DARCY_WEISBACH
    assert pytest.approx(opts.simulation_duration, rel=1e-6) == 3.0
    assert pytest.approx(opts.demand_multiplier, rel=1e-6) == 1.5
    assert pytest.approx(opts.emitter_exponent, rel=1e-6) == 0.7
    assert opts.demand_type is DemandType.PRESSURE_DEPENDENT
    assert pytest.approx(opts.minimum_pressure, rel=1e-6) == 6.5616797900  # CONVERSION
    assert pytest.approx(opts.required_pressure, rel=1e-6) == 13.1233595800  # CONVERSION
    assert pytest.approx(opts.pressure_exponent, rel=1e-6) == 1.2
    assert pytest.approx(opts.energy_price, rel=1e-6) == 0.11
    assert opts.energy_pattern == Pattern([1, 2, 3])
    assert pytest.approx(opts.energy_pump_efficiency, rel=1e-6) == 0.9
    assert pytest.approx(opts.energy_demand_charge, rel=1e-6) == 5.0


def test_options_to_wn_writes_values(wn: wntr.network.WaterNetworkModel):
    # Create a ModelOptions with distinct values
    opts = ModelOptions(
        flow_unit=FlowUnit.CFS,
        headloss_formula=HeadlossFormula.DARCY_WEISBACH,
        simulation_duration=1.0,
        demand_multiplier=-2.0,
        emitter_exponent=1.0,
        demand_type=DemandType.PRESSURE_DEPENDENT,
        minimum_pressure=0.1,
        required_pressure=0.2,
        pressure_exponent=0.6,
        energy_report=True,
        energy_price=0.1,
        energy_pattern=Pattern([1, 2, 3]),
        energy_pump_efficiency=80.0,
        energy_demand_charge=2.0,
        quality_parameter=QualityParameter.CHEMICAL,
        mass_unit=MassUnit.UG,
        relative_diffusivity=1.1,
        trace_node="12",
        quality_tolerance=0.2,
        bulk_reaction_order=9.0,
        wall_reaction_order=WallReactionOrder.ZERO,
        global_bulk_coefficient=0.1,
        global_wall_coefficient=0.1,
        limiting_concentration=0.1,
        wall_coefficient_correlation=0.1,
    )

    options_to_wn(opts, wn)

    o = wn.options
    assert o.hydraulic.inpfile_units == opts.flow_unit.name
    assert o.hydraulic.headloss == opts.headloss_formula.value
    assert o.time.duration == int(opts.simulation_duration * 3600)
    assert pytest.approx(o.hydraulic.demand_multiplier, rel=1e-6) == opts.demand_multiplier
    assert pytest.approx(o.hydraulic.emitter_exponent, rel=1e-6) == opts.emitter_exponent
    # WNTR may represent demand model strings slightly differently; check for expected token
    assert opts.demand_type.value in o.hydraulic.demand_model
    assert pytest.approx(o.hydraulic.minimum_pressure, rel=1e-6) == opts.minimum_pressure / 3.28084
    assert pytest.approx(o.hydraulic.required_pressure, rel=1e-6) == opts.required_pressure / 3.28084
    assert pytest.approx(o.hydraulic.pressure_exponent, rel=1e-6) == opts.pressure_exponent
    assert pytest.approx(o.energy.global_price, rel=1e-6) == opts.energy_price
    # energy.global_pattern may be stored as string; ensure value matches
    assert o.energy.global_pattern == "2"
    assert pytest.approx(o.energy.global_efficiency, rel=1e-6) == opts.energy_pump_efficiency
    assert pytest.approx(o.energy.demand_charge, rel=1e-6) == opts.energy_demand_charge


def test_options_round_trip(wn: wntr.network.WaterNetworkModel):
    """Write ModelOptions to a WaterNetworkModel then read them back and expect the values to match."""

    opts = ModelOptions(
        flow_unit=FlowUnit.CFS,
        headloss_formula=HeadlossFormula.DARCY_WEISBACH,
        simulation_duration=1.0,
        demand_multiplier=-2.0,
        emitter_exponent=1.0,
        demand_type=DemandType.PRESSURE_DEPENDENT,
        minimum_pressure=0.1,
        required_pressure=0.2,
        pressure_exponent=0.6,
        energy_report=True,
        energy_price=0.1,
        energy_pattern=Pattern([1, 2, 3]),
        energy_pump_efficiency=80.0,
        energy_demand_charge=2.0,
        quality_parameter=QualityParameter.CHEMICAL,
        mass_unit=MassUnit.UG,
        relative_diffusivity=1.1,
        trace_node="12",
        quality_tolerance=0.2,
        bulk_reaction_order=9.0,
        wall_reaction_order=WallReactionOrder.ZERO,
        global_bulk_coefficient=0.1,
        global_wall_coefficient=0.1,
        limiting_concentration=0.1,
        wall_coefficient_correlation=0.1,
    )

    options_to_wn(opts, wn)
    read_opts = options_from_wn(wn)

    assert read_opts.flow_unit is opts.flow_unit
    assert read_opts.headloss_formula is opts.headloss_formula
    assert pytest.approx(read_opts.simulation_duration, rel=1e-6) == opts.simulation_duration
    assert pytest.approx(read_opts.demand_multiplier, rel=1e-6) == opts.demand_multiplier
    assert pytest.approx(read_opts.emitter_exponent, rel=1e-6) == opts.emitter_exponent
    assert read_opts.demand_type is opts.demand_type
    assert pytest.approx(read_opts.minimum_pressure, rel=1e-6) == opts.minimum_pressure
    assert pytest.approx(read_opts.required_pressure, rel=1e-6) == opts.required_pressure
    assert pytest.approx(read_opts.pressure_exponent, rel=1e-6) == opts.pressure_exponent
    assert pytest.approx(read_opts.energy_price, rel=1e-6) == opts.energy_price
    assert read_opts.energy_pattern == opts.energy_pattern
    assert pytest.approx(read_opts.energy_pump_efficiency, rel=1e-6) == opts.energy_pump_efficiency
    assert pytest.approx(read_opts.energy_demand_charge, rel=1e-6) == opts.energy_demand_charge


@pytest.mark.parametrize("headloss", list(HeadlossFormula))
def test_headloss_mappings(headloss, wn: wntr.network.WaterNetworkModel):
    """Ensure all HeadlossFormula enum members round-trip through the wn options."""

    opts = dataclasses.replace(DefaultOptions(), headloss_formula=headloss)
    options_to_wn(opts, wn)

    # read back
    read_opts = options_from_wn(wn)

    assert opts == read_opts
    assert read_opts.headloss_formula is headloss


@pytest.mark.parametrize("flow_unit", list(FlowUnit))
def test_flowunit_mappings(flow_unit, wn: wntr.network.WaterNetworkModel):
    """Ensure all FlowUnit enum members round-trip through the wn options."""

    opts = dataclasses.replace(DefaultOptions(), flow_unit=flow_unit)
    options_to_wn(opts, wn)

    read_opts = options_from_wn(wn)

    assert opts == read_opts
    assert read_opts.flow_unit is flow_unit


@pytest.mark.parametrize("demand", list(DemandType))
def test_demandtype_mappings(demand, wn: wntr.network.WaterNetworkModel):
    """Ensure all DemandType enum members round-trip through the wn options."""

    opts = dataclasses.replace(DefaultOptions(), demand_type=demand)
    options_to_wn(opts, wn)

    read_opts = options_from_wn(wn)

    assert opts == read_opts
    assert read_opts.demand_type is demand


def test_wn_defaults(wn: wntr.network.WaterNetworkModel):
    """Ensure that the default WNTR options round-trip correctly."""

    options_from_wn(wn)


def test_wn_roundtrip(wn: wntr.network.WaterNetworkModel):
    """Ensure that the default WNTR options round-trip correctly."""

    original_opts = deepcopy(wn.options)

    # Get WNTR defaults
    default_opts = options_from_wn(wn)

    # Write them back to WNTR
    options_to_wn(default_opts, wn)

    # little fudge
    wn.options.energy.global_price = 0
    wn.options.energy.demand_charge = None
    wn.options.energy.global_efficiency = None

    # Compare wn options one by one to get better error messages
    assert wn.options.hydraulic == original_opts.hydraulic
    assert wn.options.time == original_opts.time
    assert wn.options.energy == original_opts.energy
    assert wn.options.quality == original_opts.quality

    assert wn.options == original_opts
