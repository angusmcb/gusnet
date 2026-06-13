import datetime

from qgis.core import QgsExpressionContextUtils, QgsProject

from gusnet.elements import (
    DEFAULT_OPTIONS,
    DemandType,
    FlowUnit,
    HeadlossFormula,
    MassUnit,
    ModelOptions,
    QualityParameter,
    WallReactionOrder,
)
from gusnet.pattern_curve import Pattern
from gusnet.settings import save_options, saved_options


def test_save_options_and_load_roundtrip(qgis_new_project):
    options = ModelOptions(
        flow_units=FlowUnit.CFS,
        headloss_formula=HeadlossFormula.DARCY_WEISBACH,
        simulation_duration=datetime.timedelta(hours=5),
        demand_multiplier=-2.0,
        default_pattern=Pattern([3, 2, 1]),
        emitter_exponent=1.0,
        demand_model=DemandType.PRESSURE_DEPENDENT,
        minimum_pressure=0.1,
        required_pressure=0.2,
        pressure_exponent=0.6,
        energy_price=0.1,
        energy_price_pattern=Pattern([1, 2, 3]),
        energy_pump_efficiency=80.0,
        energy_demand_charge=2.0,
        quality_parameter=QualityParameter.CHEMICAL,
        mass_units=MassUnit.UG,
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

    save_options(options)

    loaded = saved_options()

    # dataclass equality should hold after roundtrip
    assert isinstance(loaded, ModelOptions)
    assert loaded == options


def test_load_options_partial_values_use_defaults(qgis_new_project):
    # only set flow_unit variable directly in project scope
    # save the enum as save_options would (enum.value)
    QgsExpressionContextUtils.setProjectVariable(QgsProject.instance(), "gusnet_flow_units", FlowUnit.GPM.value)

    loaded = saved_options()

    assert loaded.flow_units == FlowUnit.GPM
    # other fields should be defaults from ModelOptions
    defaults = DEFAULT_OPTIONS
    assert loaded.headloss_formula == defaults.headloss_formula
    assert loaded.demand_model == defaults.demand_model
    assert loaded.emitter_exponent == defaults.emitter_exponent
    assert loaded.minimum_pressure == defaults.minimum_pressure
    assert loaded.required_pressure == defaults.required_pressure
    assert loaded.simulation_duration == defaults.simulation_duration
