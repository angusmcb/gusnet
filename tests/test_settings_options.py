from qgis.core import QgsExpressionContextUtils, QgsProject

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
from gusnet.pattern_curve import Pattern
from gusnet.settings import ProjectSettings


def setup_module(module):
    # ensure fresh project for tests in this module
    QgsProject.instance().clear()


def test_save_options_and_load_roundtrip():
    QgsProject.instance().clear()
    settings = ProjectSettings(project=QgsProject.instance())

    options = ModelOptions(
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

    settings.save_options(options)

    loaded = settings.load_options()

    # dataclass equality should hold after roundtrip
    assert isinstance(loaded, ModelOptions)
    assert loaded == options


def test_load_options_partial_values_use_defaults():
    QgsProject.instance().clear()
    # only set flow_unit variable directly in project scope
    # save the enum as save_options would (enum.value)
    QgsExpressionContextUtils.setProjectVariable(QgsProject.instance(), "gusnet_flow_unit", FlowUnit.GPM.value)

    settings = ProjectSettings()
    loaded = settings.load_options()

    assert loaded.flow_unit == FlowUnit.GPM
    # other fields should be defaults from ModelOptions
    defaults = DefaultOptions()
    assert loaded.headloss_formula == defaults.headloss_formula
    assert loaded.demand_type == defaults.demand_type
    assert loaded.emitter_exponent == defaults.emitter_exponent
    assert loaded.minimum_pressure == defaults.minimum_pressure
    assert loaded.required_pressure == defaults.required_pressure
    assert loaded.simulation_duration == defaults.simulation_duration
