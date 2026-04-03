"""
Set of elements which describe parts of the network

Note:
    This module does not import WNTR, so can safely be run before checking if WNTR is installed.
"""

from __future__ import annotations

import dataclasses
import datetime
import sys
from abc import abstractmethod
from collections.abc import Collection, Mapping
from enum import Enum, Flag, auto
from typing import TYPE_CHECKING, Any, TypedDict

from qgis.core import Qgis, QgsProcessing

from gusnet.i18n import tr
from gusnet.network import Network
from gusnet.pattern_curve import Pattern

if sys.version_info >= (3, 11):
    from enum import StrEnum
else:
    from gusnet.strenum import StrEnum


class EnumWithName(Enum):
    """Abstract enum for value maps"""

    @property
    @abstractmethod
    def friendly_name(self):
        """A human readable name for the enum value"""


class FlowUnit(EnumWithName):
    LPS = "LPS"
    LPM = "LPM"
    MLD = "MLD"
    CMH = "CMH"
    CMD = "CMD"
    CFS = "CFS"
    GPM = "GPM"
    MGD = "MGD"
    IMGD = "IMGD"
    AFD = "AFD"

    @property
    def friendly_name(self):
        if self is FlowUnit.LPS:
            return tr("Litres per Second")
        if self is FlowUnit.LPM:
            return tr("Litres per Minute")
        if self is FlowUnit.MLD:
            return tr("Mega Litres Per Day")
        if self is FlowUnit.CMH:
            return tr("Cubic Metres per Hour")
        if self is FlowUnit.CMD:
            return tr("Cubic Metres per Day")
        if self is FlowUnit.CFS:
            return tr("Cubic Feet per Second")
        if self is FlowUnit.GPM:
            return tr("Gallons per Minute")
        if self is FlowUnit.MGD:
            return tr("Mega Gallons per Day")
        if self is FlowUnit.IMGD:
            return tr("Imperial Mega Gallons per Day")
        if self is FlowUnit.AFD:
            return tr("Acre-feet per Day")

        raise ValueError  # pragma: no cover

    @property
    def is_traditional(self) -> bool:
        """Is the flow unit a traditional US unit?"""
        return self in _TRADITIONAL_FLOW_UNITS


_TRADITIONAL_FLOW_UNITS = {FlowUnit.CFS, FlowUnit.GPM, FlowUnit.MGD, FlowUnit.IMGD, FlowUnit.AFD}


class MassUnit(EnumWithName):
    MG = "mg/L"
    UG = "ug/L"

    @property
    def friendly_name(self):
        if self is MassUnit.MG:
            return tr("mg")
        if self is MassUnit.UG:
            return tr("μg")

        raise ValueError  # pragma: no cover


class HeadlossFormula(EnumWithName):
    HAZEN_WILLIAMS = "H-W"
    DARCY_WEISBACH = "D-W"
    CHEZY_MANNING = "C-M"

    @property
    def friendly_name(self):
        if self is HeadlossFormula.HAZEN_WILLIAMS:
            return tr("Hazen-Williams")
        if self is HeadlossFormula.DARCY_WEISBACH:
            return tr("Darcy-Weisbach")
        if self is HeadlossFormula.CHEZY_MANNING:
            return tr("Chezy-Manning")
        raise ValueError  # pragma: no cover


class DemandType(EnumWithName):
    FIXED = "DDA"
    PRESSURE_DEPENDENT = "PDA"

    @property
    def friendly_name(self):
        if self is DemandType.FIXED:
            return tr("Fixed Demand")
        if self is DemandType.PRESSURE_DEPENDENT:
            return tr("Pressure Dependent Demand")
        raise ValueError


class QualityParameter(EnumWithName):
    NONE = "NONE"
    AGE = "AGE"
    CHEMICAL = "CHEMICAL"
    TRACE = "TRACE"

    @property
    def friendly_name(self):
        if self is QualityParameter.NONE:
            return tr("None")
        if self is QualityParameter.AGE:
            return tr("Water Age")
        if self is QualityParameter.CHEMICAL:
            return tr("Chemical Concentration")
        if self is QualityParameter.TRACE:
            return tr("Trace Node")
        raise ValueError  # pragma: no cover


class PumpTypes(EnumWithName):
    POWER = "POWER"
    HEAD = "HEAD"

    @property
    def friendly_name(self):
        if self is PumpTypes.POWER:
            return tr("Power")
        if self is PumpTypes.HEAD:
            return tr("Head")
        raise ValueError  # pragma: no cover


class TankMixingModel(EnumWithName):
    FULLY_MIXED = "MIXED"
    MIX2 = "2COMP"
    FIFO = "FIFO"
    LIFO = "LIFO"

    @property
    def friendly_name(self):
        if self is TankMixingModel.FULLY_MIXED:
            return tr("Fully Mixed")
        if self is TankMixingModel.MIX2:
            return tr("Two Compartment Mixing")
        if self is TankMixingModel.FIFO:
            return tr("First In First Out (FIFO)")
        if self is TankMixingModel.LIFO:
            return tr("Last In First Out (LIFO)")
        raise ValueError  # pragma: no cover


class InitialStatus(EnumWithName):
    OPEN = "Open"
    CLOSED = "Closed"

    @property
    def friendly_name(self) -> str:
        if self is InitialStatus.OPEN:
            return tr("Open")
        if self is InitialStatus.CLOSED:
            return tr("Closed")
        raise ValueError  # pragma: no cover


class ValveStatus(EnumWithName):
    ACTIVE = "Active"
    OPEN = "Open"
    CLOSED = "Closed"

    @property
    def friendly_name(self) -> str:
        if self is ValveStatus.OPEN:
            return tr("Open")
        if self is ValveStatus.ACTIVE:
            return tr("Active")
        if self is ValveStatus.CLOSED:
            return tr("Closed")
        raise ValueError  # pragma: no cover


class ValveType(EnumWithName):
    PRV = "PRV"
    PSV = "PSV"
    PBV = "PBV"
    FCV = "FCV"
    TCV = "TCV"
    GPV = "GPV"

    @property
    def friendly_name(self):
        if self is ValveType.PRV:
            return tr("Pressure Reducing Valve")
        if self is ValveType.PSV:
            return tr("Pressure Sustaining Valve")
        if self is ValveType.PBV:
            return tr("Pressure Breaking Valve")
        if self is ValveType.FCV:
            return tr("Flow Control Valve")
        if self is ValveType.TCV:
            return tr("Throttle Control Valve")
        if self is ValveType.GPV:
            return tr("General Purpose Valve")
        raise ValueError  # pragma: no cover

    @property
    def setting_field(self) -> Field:
        if self in [ValveType.PRV, ValveType.PSV, ValveType.PBV]:
            return Field.PRESSURE_SETTING
        if self is ValveType.FCV:
            return Field.FLOW_SETTING
        if self is ValveType.TCV:
            return Field.THROTTLE_SETTING
        if self is ValveType.GPV:
            return Field.HEADLOSS_CURVE
        raise ValueError  # pragma: no cover


class WallReactionOrder(EnumWithName):
    ZERO = 0
    ONE = 1

    @property
    def friendly_name(self) -> str:
        if self is WallReactionOrder.ZERO:
            return tr("Zero")
        if self is WallReactionOrder.ONE:
            return tr("One")


class FieldType(Enum):
    """Abstract Enum for Field Types"""


class MapFieldType(FieldType):
    PUMP_TYPE = PumpTypes
    VALVE_TYPE = ValveType
    TANK_MIXING_MODEL = TankMixingModel
    INITIAL_STATUS = InitialStatus
    VALVE_STATUS = ValveStatus


class SimpleFieldType(FieldType):
    STR = auto()
    BOOL = auto()
    PATTERN = auto()


class Parameter(FieldType):
    LENGTH = 999
    ELEVATION = 999
    HYDRAULIC_HEAD = 999
    TANK_DIAMETER = 999
    PRESSURE = auto()
    CONCENTRATION = auto()
    PIPE_DIAMETER = auto()
    FLOW = auto()
    VELOCITY = auto()
    UNIT_HEADLOSS = auto()
    POWER = auto()
    VOLUME = auto()
    EMITTER_COEFFICIENT = auto()
    ROUGHNESS_COEFFICIENT = auto()
    ENERGY = auto()
    REACTION_RATE = auto()
    BULK_REACTION_COEFFICIENT = auto()
    WALL_REACTION_COEFFICIENT = auto()
    SOURCE_MASS_INJECTION = auto()
    WATER_AGE = auto()
    UNITLESS = auto()
    FRACTION = auto()
    CURRENCY = auto()


class CurveType(FieldType):
    HEAD = "HEAD", (Parameter.FLOW, Parameter.HYDRAULIC_HEAD)
    EFFICIENCY = "EFFICIENCY", (Parameter.FLOW, Parameter.UNITLESS)  # flow vs percentage
    VOLUME = "VOLUME", (Parameter.LENGTH, Parameter.VOLUME)
    HEADLOSS = "HEADLOSS", (Parameter.FLOW, Parameter.HYDRAULIC_HEAD)


class FieldGroup(Flag):
    BASE = auto()
    WATER_QUALITY_ANALYSIS = auto()
    ENERGY = auto()
    EXTRA = auto()
    REQUIRED = auto()
    LIST_IN_EXTENDED_PERIOD = auto()


class _AbstractLayer(StrEnum):
    """Abstract enum for layer enums"""

    @property
    def results_name(self):
        """Name of the layer in the results"""
        return "RESULT_" + self.name

    @property
    def is_node(self) -> bool:  # pragma: no cover
        raise NotImplementedError

    @property
    def wkb_type(self) -> Qgis.WkbType:
        return Qgis.WkbType.Point if self.is_node else Qgis.WkbType.LineString

    def wq_fields(self) -> list[Field]:
        raise NotImplementedError


class ModelLayer(_AbstractLayer):
    JUNCTIONS = "JUNCTIONS"
    RESERVOIRS = "RESERVOIRS"
    TANKS = "TANKS"
    PIPES = "PIPES"
    PUMPS = "PUMPS"
    VALVES = "VALVES"

    @property
    def field_type(self):
        if self is ModelLayer.JUNCTIONS:
            return "Junction"
        if self is ModelLayer.RESERVOIRS:
            return "Reservoir"
        if self is ModelLayer.TANKS:
            return "Tank"
        if self is ModelLayer.PIPES:
            return "Pipe"
        if self is ModelLayer.PUMPS:
            return "Pump"
        if self is ModelLayer.VALVES:
            return "Valve"
        raise ValueError  # pragma: no cover

    @property
    def friendly_name(self):
        if self is ModelLayer.JUNCTIONS:
            return tr("Junctions")
        if self is ModelLayer.RESERVOIRS:
            return tr("Reservoirs")
        if self is ModelLayer.TANKS:
            return tr("Tanks")
        if self is ModelLayer.PIPES:
            return tr("Pipes")
        if self is ModelLayer.PUMPS:
            return tr("Pumps")
        if self is ModelLayer.VALVES:
            return tr("Valves")
        raise ValueError  # pragma: no cover

    @property
    def is_node(self) -> bool:
        """Layer is a node or a link?"""
        return self in [ModelLayer.JUNCTIONS, ModelLayer.RESERVOIRS, ModelLayer.TANKS]

    @property
    def acceptable_processing_vectors(self):
        return [QgsProcessing.TypeVectorPoint] if self.is_node else [QgsProcessing.TypeVectorLine]

    def wq_fields(self) -> list[Field]:
        """Mapping of fields associated with each layer"""

        field_dict = {
            ModelLayer.JUNCTIONS: [
                Field.NAME,
                Field.ELEVATION,
                Field.BASE_DEMAND,
                Field.DEMAND_PATTERN,
                Field.EMITTER_COEFFICIENT,
                Field.INITIAL_QUALITY,
            ],
            ModelLayer.TANKS: [
                Field.NAME,
                Field.ELEVATION,
                Field.INIT_LEVEL,
                Field.MIN_LEVEL,
                Field.MAX_LEVEL,
                Field.TANK_DIAMETER,
                Field.MIN_VOL,
                Field.VOL_CURVE,
                Field.OVERFLOW,
                Field.INITIAL_QUALITY,
                Field.MIXING_MODEL,
                Field.MIXING_FRACTION,
                Field.BULK_COEFF,
            ],
            ModelLayer.RESERVOIRS: [
                Field.NAME,
                Field.BASE_HEAD,
                Field.HEAD_PATTERN,
                Field.INITIAL_QUALITY,
            ],
            ModelLayer.PIPES: [
                Field.NAME,
                Field.LENGTH,
                Field.DIAMETER,
                Field.ROUGHNESS,
                Field.MINOR_LOSS,
                Field.INITIAL_STATUS,
                Field.CHECK_VALVE,
                Field.BULK_COEFF,
                Field.WALL_COEFF,
            ],
            ModelLayer.PUMPS: [
                Field.NAME,
                Field.PUMP_TYPE,
                Field.PUMP_CURVE,
                Field.POWER,
                Field.BASE_SPEED,
                Field.SPEED_PATTERN,
                Field.INITIAL_STATUS,
                Field.EFFICIENCY_CURVE,
                Field.ENERGY_PRICE,
                Field.ENERGY_PATTERN,
            ],
            ModelLayer.VALVES: [
                Field.NAME,
                Field.VALVE_TYPE,
                Field.PRESSURE_SETTING,
                Field.FLOW_SETTING,
                Field.THROTTLE_SETTING,
                Field.HEADLOSS_CURVE,
                Field.DIAMETER,
                Field.MINOR_LOSS,
                Field.VALVE_STATUS,
            ],
        }
        return field_dict[self]


class ResultLayer(_AbstractLayer):
    NODES = "NODES"
    LINKS = "LINKS"

    @property
    def friendly_name(self):
        if self is ResultLayer.NODES:
            return tr("Nodes")
        if self is ResultLayer.LINKS:
            return tr("Links")
        raise ValueError  # pragma: no cover

    @property
    def is_node(self) -> bool:
        return self is ResultLayer.NODES

    def wq_fields(self):
        if self is ResultLayer.NODES:
            return [
                Field.NAME,
                Field.DEMAND,
                Field.HEAD,
                Field.PRESSURE,
                Field.QUALITY,
            ]
        return [
            Field.NAME,
            Field.FLOWRATE,
            Field.HEADLOSS,
            Field.UNIT_HEADLOSS,
            Field.VELOCITY,
            Field.QUALITY,
            Field.REACTION_RATE,
        ]


class Field(StrEnum):
    def __new__(cls, *args):
        value = str(args[0])
        member = str.__new__(cls, value)
        member._value_ = value
        return member

    def __init__(self, *args):
        self._type = args[1]
        self._field_group = args[2]

    @property
    def type(self) -> FieldType:
        return self._type

    @property
    def field_group(self) -> FieldGroup:
        """The field group(s) the field is part of"""
        return self._field_group

    NAME = "name", SimpleFieldType.STR, FieldGroup.BASE
    ELEVATION = "elevation", Parameter.ELEVATION, FieldGroup.BASE | FieldGroup.REQUIRED
    BASE_DEMAND = "base_demand", Parameter.FLOW, FieldGroup.BASE
    DEMAND_PATTERN = "demand_pattern", SimpleFieldType.PATTERN, FieldGroup.BASE
    EMITTER_COEFFICIENT = "emitter_coefficient", Parameter.EMITTER_COEFFICIENT, FieldGroup.BASE
    INIT_LEVEL = "init_level", Parameter.HYDRAULIC_HEAD, FieldGroup.BASE | FieldGroup.REQUIRED
    MIN_LEVEL = "min_level", Parameter.HYDRAULIC_HEAD, FieldGroup.BASE | FieldGroup.REQUIRED
    MAX_LEVEL = "max_level", Parameter.HYDRAULIC_HEAD, FieldGroup.BASE | FieldGroup.REQUIRED

    VALVE_TYPE = "valve_type", MapFieldType.VALVE_TYPE, FieldGroup.BASE | FieldGroup.REQUIRED
    PRESSURE_SETTING = "pressure_setting", Parameter.PRESSURE, FieldGroup.BASE
    FLOW_SETTING = "flow_setting", Parameter.FLOW, FieldGroup.BASE
    THROTTLE_SETTING = "throttle_setting", Parameter.UNITLESS, FieldGroup.BASE
    HEADLOSS_CURVE = "headloss_curve", CurveType.HEADLOSS, FieldGroup.BASE

    DIAMETER = "diameter", Parameter.PIPE_DIAMETER, FieldGroup.BASE | FieldGroup.REQUIRED
    TANK_DIAMETER = "tank_diameter", Parameter.TANK_DIAMETER, FieldGroup.BASE | FieldGroup.REQUIRED
    MIN_VOL = "min_vol", Parameter.VOLUME, FieldGroup.BASE | FieldGroup.REQUIRED
    VOL_CURVE = "vol_curve", CurveType.VOLUME, FieldGroup.BASE
    OVERFLOW = "overflow", SimpleFieldType.BOOL, FieldGroup.BASE
    BASE_HEAD = "base_head", Parameter.ELEVATION, FieldGroup.BASE | FieldGroup.REQUIRED
    HEAD_PATTERN = "head_pattern", SimpleFieldType.PATTERN, FieldGroup.BASE
    LENGTH = "length", Parameter.LENGTH, FieldGroup.BASE
    ROUGHNESS = "roughness", Parameter.ROUGHNESS_COEFFICIENT, FieldGroup.BASE | FieldGroup.REQUIRED
    MINOR_LOSS = "minor_loss", Parameter.UNITLESS, FieldGroup.BASE
    CHECK_VALVE = "check_valve", SimpleFieldType.BOOL, FieldGroup.BASE
    PUMP_TYPE = "pump_type", MapFieldType.PUMP_TYPE, FieldGroup.BASE | FieldGroup.REQUIRED
    PUMP_CURVE = "pump_curve", CurveType.HEAD, FieldGroup.BASE
    POWER = "power", Parameter.POWER, FieldGroup.BASE
    BASE_SPEED = "base_speed", Parameter.FRACTION, FieldGroup.BASE
    SPEED_PATTERN = "speed_pattern", SimpleFieldType.PATTERN, FieldGroup.BASE
    INITIAL_STATUS = "initial_status", MapFieldType.INITIAL_STATUS, FieldGroup.BASE
    VALVE_STATUS = "valve_status", MapFieldType.VALVE_STATUS, FieldGroup.BASE

    INITIAL_QUALITY = "initial_quality", Parameter.CONCENTRATION, FieldGroup.WATER_QUALITY_ANALYSIS
    MIXING_MODEL = "mixing_model", MapFieldType.TANK_MIXING_MODEL, FieldGroup.WATER_QUALITY_ANALYSIS
    MIXING_FRACTION = "mixing_fraction", Parameter.FRACTION, FieldGroup.WATER_QUALITY_ANALYSIS
    BULK_COEFF = "bulk_coeff", Parameter.BULK_REACTION_COEFFICIENT, FieldGroup.WATER_QUALITY_ANALYSIS
    WALL_COEFF = "wall_coeff", Parameter.WALL_REACTION_COEFFICIENT, FieldGroup.WATER_QUALITY_ANALYSIS

    EFFICIENCY_CURVE = "efficiency_curve", CurveType.EFFICIENCY, FieldGroup.ENERGY
    ENERGY_PRICE = "energy_price", Parameter.CURRENCY, FieldGroup.ENERGY
    ENERGY_PATTERN = "energy_pattern", SimpleFieldType.PATTERN, FieldGroup.ENERGY

    DEMAND = "demand", Parameter.FLOW, FieldGroup.BASE | FieldGroup.LIST_IN_EXTENDED_PERIOD
    HEAD = "head", Parameter.HYDRAULIC_HEAD, FieldGroup.BASE | FieldGroup.LIST_IN_EXTENDED_PERIOD
    PRESSURE = "pressure", Parameter.PRESSURE, FieldGroup.BASE | FieldGroup.LIST_IN_EXTENDED_PERIOD

    FLOWRATE = "flowrate", Parameter.FLOW, FieldGroup.BASE | FieldGroup.LIST_IN_EXTENDED_PERIOD
    HEADLOSS = "headloss", Parameter.HYDRAULIC_HEAD, FieldGroup.BASE | FieldGroup.LIST_IN_EXTENDED_PERIOD
    UNIT_HEADLOSS = "unit_headloss", Parameter.UNIT_HEADLOSS, FieldGroup.BASE | FieldGroup.LIST_IN_EXTENDED_PERIOD
    VELOCITY = "velocity", Parameter.VELOCITY, FieldGroup.BASE | FieldGroup.LIST_IN_EXTENDED_PERIOD

    QUALITY = "quality", Parameter.CONCENTRATION, FieldGroup.WATER_QUALITY_ANALYSIS | FieldGroup.LIST_IN_EXTENDED_PERIOD
    REACTION_RATE = (
        "reaction_rate",
        Parameter.REACTION_RATE,
        FieldGroup.WATER_QUALITY_ANALYSIS | FieldGroup.LIST_IN_EXTENDED_PERIOD,
    )

    @property
    def friendly_name(self):
        if self is Field.NAME:
            return tr("Name")
        if self is Field.ELEVATION:
            return tr("Elevation")
        if self is Field.BASE_DEMAND:
            return tr("Base Demand")
        if self is Field.DEMAND_PATTERN:
            return tr("Demand Pattern")
        if self is Field.EMITTER_COEFFICIENT:
            return tr("Emitter Coefficient")
        if self is Field.INIT_LEVEL:
            return tr("Initial Level")
        if self is Field.MIN_LEVEL:
            return tr("Minimum Level")
        if self is Field.MAX_LEVEL:
            return tr("Maximum Level")
        if self is Field.VALVE_TYPE:
            return tr("Valve Type")
        if self is Field.PRESSURE_SETTING:
            return tr("Pressure Setting (for PRVs, PBVs, and PSVs)")
        if self is Field.FLOW_SETTING:
            return tr("Flow Setting (for FCVs)")
        if self is Field.THROTTLE_SETTING:
            return tr("Throttle Setting (for TCVs)")
        if self is Field.HEADLOSS_CURVE:
            return tr("Headloss Curve (for GPVs)")
        if self is Field.DIAMETER:
            return tr("Diameter")
        if self is Field.TANK_DIAMETER:
            return tr("Diameter")
        if self is Field.MIN_VOL:
            return tr("Minimum Volume")
        if self is Field.VOL_CURVE:
            return tr("Volume Curve")
        if self is Field.OVERFLOW:
            return tr("Overflow")
        if self is Field.BASE_HEAD:
            return tr("Base Head")
        if self is Field.HEAD_PATTERN:
            return tr("Head Pattern")
        if self is Field.LENGTH:
            return tr("Length")
        if self is Field.ROUGHNESS:
            return tr("Roughness")
        if self is Field.MINOR_LOSS:
            return tr("Minor Loss Coefficient")
        if self is Field.CHECK_VALVE:
            return tr("Check Valve")
        if self is Field.PUMP_TYPE:
            return tr("Pump Type")
        if self is Field.PUMP_CURVE:
            return tr("Pump Curve (for 'head' pumps)")
        if self is Field.POWER:
            return tr("Power (for 'power' pumps)")
        if self is Field.BASE_SPEED:
            return tr("Base Speed")
        if self is Field.SPEED_PATTERN:
            return tr("Speed Pattern")
        if self is Field.INITIAL_STATUS:
            return tr("Initial Status")
        if self is Field.VALVE_STATUS:
            return tr("Valve Status")

        if self is Field.INITIAL_QUALITY:
            return tr("Initial Quality")
        if self is Field.MIXING_FRACTION:
            return tr("Mixing Fraction")
        if self is Field.MIXING_MODEL:
            return tr("Mixing Model")
        if self is Field.BULK_COEFF:
            return tr("Bulk Reaction Rate Coefficient")
        if self is Field.WALL_COEFF:
            return tr("Wall Reaction Rate Coefficient")
        if self is Field.EFFICIENCY_CURVE:
            return tr("Efficiency Curve")
        if self is Field.ENERGY_PATTERN:
            return tr("Energy Pattern")
        if self is Field.ENERGY_PRICE:
            return tr("Energy Price")

        if self is Field.DEMAND:
            return tr("Demand")
        if self is Field.HEAD:
            return tr("Head")
        if self is Field.PRESSURE:
            return tr("Pressure")
        if self is Field.FLOWRATE:
            return tr("Flowrate")
        if self is Field.HEADLOSS:
            return tr("Headloss")
        if self is Field.UNIT_HEADLOSS:
            return tr("Unit Headloss")
        if self is Field.VELOCITY:
            return tr("Velocity")
        if self is Field.QUALITY:
            return tr("Quality")
        if self is Field.REACTION_RATE:
            return tr("Reaction Rate")
        raise ValueError  # pragma: no cover

    @property
    def description(self):
        if self is Field.NAME:
            return tr("Element identifier. If provided, it must be less than 32 characters and not contain any spaces.")
        if self is Field.ELEVATION:
            return tr("Height above datum. This is in metres or feet.")
        if self is Field.BASE_DEMAND:
            return tr("The demand for the element. Can be negative for inflows.")
        if self is Field.DEMAND_PATTERN:
            return tr("Time-varying multiplier pattern for base demand")
        if self is Field.EMITTER_COEFFICIENT:
            return tr("Coefficient for flow through emitter at junction")
        if self is Field.INIT_LEVEL:
            return tr("Initial water level in tank")
        if self is Field.MIN_LEVEL:
            return tr("Minimum allowable water level in tank")
        if self is Field.MAX_LEVEL:
            return tr("Maximum allowable water level in tank")
        if self is Field.VALVE_TYPE:
            return tr("Type of valve (PRV, PSV, PBV, FCV, TCV, GPV)")
        if self is Field.PRESSURE_SETTING:
            return tr("Pressure setting for PRV, PBV, and PSV")
        if self is Field.FLOW_SETTING:
            return tr("Flow setting for FCV")
        if self is Field.THROTTLE_SETTING:
            return tr("Throttle setting for TCV")
        if self is Field.DIAMETER:
            return tr("Internal diameter of pipe")
        if self is Field.TANK_DIAMETER:
            return tr("Diameter of tank")
        if self is Field.MIN_VOL:
            return tr("Minimum volume of water in tank")
        if self is Field.VOL_CURVE:
            return tr("Volume curve relating tank level to volume")
        if self is Field.OVERFLOW:
            return tr("Whether tank can overflow when full")
        if self is Field.BASE_HEAD:
            return tr("Hydraulic head at reservoir")
        if self is Field.HEAD_PATTERN:
            return tr("Time-varying pattern for reservoir head")
        if self is Field.LENGTH:
            return tr("Physical length of pipe. If left blank this will be calculated automatically")
        if self is Field.ROUGHNESS:
            return tr("Pipe roughness coefficient for headloss calculation")
        if self is Field.MINOR_LOSS:
            return tr("Minor loss coefficient for fittings and bends")
        if self is Field.CHECK_VALVE:
            return tr("Whether pipe has check valve to prevent backflow")
        if self is Field.PUMP_TYPE:
            return tr("How is pump described (by power or by head curve)")
        if self is Field.PUMP_CURVE:
            return tr("Flow vs head curve for pump")
        if self is Field.POWER:
            return tr("Power rating of pump")
        if self is Field.BASE_SPEED:
            return tr("Base rotational speed of pump")
        if self is Field.SPEED_PATTERN:
            return tr("Time-varying pattern for pump speed")
        if self is Field.INITIAL_STATUS:
            return tr("Initial operating status")
        if self is Field.VALVE_STATUS:
            return tr("Initial valve status (active, open, closed)")
        if self is Field.HEADLOSS_CURVE:
            return tr("Head loss curve (flow vs head loss) for general purpose valve")
        if self is Field.INITIAL_QUALITY:
            return tr("Initial water quality concentration for water quality analysis")
        if self is Field.MIXING_FRACTION:
            return tr("Fraction of tank volume for mixing model for two-compartment mixing model")
        if self is Field.MIXING_MODEL:
            return tr("Tank mixing model type for water quality analysis")
        if self is Field.BULK_COEFF:
            return tr("Bulk reaction rate coefficient for water quality analysis")
        if self is Field.WALL_COEFF:
            return tr("Wall reaction rate coefficient for water quality analysis")
        if self is Field.EFFICIENCY_CURVE:
            return tr("Pump efficiency curve (flow vs efficiency) for energy use analysis")
        if self is Field.ENERGY_PATTERN:
            return tr("Time-varying pattern for energy price")
        if self is Field.ENERGY_PRICE:
            return tr("Energy price per kW hour for energy use analysis")

        if self is Field.DEMAND:
            return tr("Water demand at node")
        if self is Field.HEAD:
            return tr("Hydraulic head at node")
        if self is Field.PRESSURE:
            return tr("Water pressure at node")
        if self is Field.FLOWRATE:
            return tr("Water flow rate through link")
        if self is Field.HEADLOSS:
            return tr("Head loss across link")
        if self is Field.UNIT_HEADLOSS:
            return tr("Head loss proportional to length of pipe")
        if self is Field.VELOCITY:
            return tr("Water velocity in link")
        if self is Field.QUALITY:
            return tr("Water quality concentration")
        if self is Field.REACTION_RATE:
            return tr("Rate of water quality reaction")
        raise ValueError  # pragma: no cover


class OptionsFieldMetadata(TypedDict, total=False):
    description: str
    advanced: bool
    minimum: float
    maximum: float
    decimals: int
    help_text: str


@dataclasses.dataclass(frozen=True)
class ModelOptions:
    """A frozen dataclass that stores the set of options that will be used for the model."""

    flow_units: FlowUnit = dataclasses.field(
        metadata=OptionsFieldMetadata(
            description=tr("Flow units for the model"),
            help_text=tr(
                "Flow units will determine the units of other units used in the model as well."
                "Selecting a metric-based unit set means everything will be metric, wheras selecting an imperial measure means everything will be imperial."  # noqa: E501
            ),
        )
    )

    headloss_formula: HeadlossFormula = dataclasses.field(
        metadata=OptionsFieldMetadata(
            description=tr("Formula to use for headloss calculations"),
        )
    )

    simulation_duration: datetime.timedelta = dataclasses.field(
        metadata=OptionsFieldMetadata(
            description=tr("Duration of the simulation in hours (or 0 for single period)"),
            minimum=0,
            decimals=2,
        )
    )

    demand_multiplier: float = dataclasses.field(
        metadata=OptionsFieldMetadata(
            description=tr("Global multiplier for all demands in the model"),
            decimals=3,
            minimum=0.001,
            advanced=True,
        )
    )

    default_pattern: Pattern = dataclasses.field(
        metadata=OptionsFieldMetadata(
            description=tr("Default pattern to use for any pattern fields left blank"),
            advanced=True,
        )
    )

    emitter_exponent: float = dataclasses.field(
        metadata=OptionsFieldMetadata(
            description=tr("Exponent for emitter calculations"),
            decimals=3,
            minimum=0.001,
            advanced=True,
        )
    )

    ### FOR PRESSURE DEPENDENT DEMANDS

    demand_model: DemandType = dataclasses.field(
        metadata=OptionsFieldMetadata(
            description=tr("Whether to model demands as fixed or pressure dependent"),
            advanced=True,
        )
    )
    minimum_pressure: float = dataclasses.field(
        metadata=OptionsFieldMetadata(
            description=tr("Minimum pressure for pressure dependent demand calculations"),
            decimals=2,
            advanced=True,
        )
    )
    required_pressure: float = dataclasses.field(
        metadata=OptionsFieldMetadata(
            description=tr("Required pressure for pressure dependent demand calculations"),
            decimals=2,
            advanced=True,
        )
    )
    pressure_exponent: float = dataclasses.field(
        metadata=OptionsFieldMetadata(
            description=tr("Exponent for pressure dependent demand calculations"),
            decimals=2,
            advanced=True,
        )
    )

    ### FOR ENERGY REPORTING

    # energy_report: bool = dataclasses.field(
    #     metadata=OptionsFieldMetadata(
    #         description=tr("Whether to generate an energy report"),
    #         advanced=True,
    #     )
    # )
    energy_price: float = dataclasses.field(
        metadata=OptionsFieldMetadata(
            description=tr("Price of energy per kW hour for energy calculations"),
            decimals=2,
            advanced=True,
        )
    )
    energy_price_pattern: Pattern = dataclasses.field(
        metadata=OptionsFieldMetadata(
            description=tr("Pattern of price multiplier to use for energy calculations"),
            advanced=True,
        )
    )
    energy_pump_efficiency: float = dataclasses.field(
        metadata=OptionsFieldMetadata(
            description=tr("Global efficiency of pumps for energy calculations - as a percentage"),
            decimals=1,
            advanced=True,
        )
    )
    energy_demand_charge: float = dataclasses.field(
        metadata=OptionsFieldMetadata(
            description=tr("Demand charge for energy calculations"),
            decimals=2,
            advanced=True,
        )
    )

    ### FOR WATER QUALITY

    quality_parameter: QualityParameter = dataclasses.field(
        metadata=OptionsFieldMetadata(
            description=tr("Type of water quality analysis to do"),
            advanced=True,
        )
    )
    mass_units: MassUnit = dataclasses.field(
        metadata=OptionsFieldMetadata(
            description=tr("Mass unit to use for water quality analysis"),
            advanced=True,
        )
    )
    relative_diffusivity: float = dataclasses.field(
        metadata=OptionsFieldMetadata(
            description=tr("Relative diffusivity for water quality analysis"),
            decimals=2,
            advanced=True,
        )
    )
    trace_node: str = dataclasses.field(
        metadata=OptionsFieldMetadata(
            description=tr("Node to track for trace analysis (if quality parameter is TRACE)"),
            advanced=True,
        )
    )
    quality_tolerance: float = dataclasses.field(
        metadata=OptionsFieldMetadata(
            description=tr("Tolerance for water quality convergence in extended period simulations"),
            decimals=2,
            advanced=True,
        )
    )

    bulk_reaction_order: float = dataclasses.field(
        metadata=OptionsFieldMetadata(
            description=tr("Order of the bulk reaction for water quality analysis"),
            decimals=2,
            advanced=True,
        )
    )
    wall_reaction_order: WallReactionOrder = dataclasses.field(
        metadata=OptionsFieldMetadata(
            description=tr("Order of the wall reaction for water quality analysis"),
            advanced=True,
        )
    )
    global_bulk_coefficient: float = dataclasses.field(
        metadata=OptionsFieldMetadata(
            description=tr("Global bulk coefficient for water quality analysis"),
            decimals=2,
            advanced=True,
        )
    )
    global_wall_coefficient: float = dataclasses.field(
        metadata=OptionsFieldMetadata(
            description=tr("Global wall coefficient for water quality analysis"),
            decimals=2,
            advanced=True,
        )
    )

    limiting_concentration: float = dataclasses.field(
        metadata=OptionsFieldMetadata(
            description=tr(
                "Limiting concentration for water quality analysis (concentration below which reactions are assumed to stop)"  # noqa: E501
            ),
            decimals=2,
            advanced=True,
        )
    )
    wall_coefficient_correlation: float = dataclasses.field(
        metadata=OptionsFieldMetadata(
            description=tr(
                "Correlation for calculating wall reaction coefficient based on pipe diameter (if 0, wall coefficient will be constant)"  # noqa: E501
            ),
            decimals=2,
            advanced=True,
        )
    )


DEFAULT_OPTIONS = ModelOptions(
    flow_units=FlowUnit.LPS,
    headloss_formula=HeadlossFormula.HAZEN_WILLIAMS,
    simulation_duration=datetime.timedelta(0),
    demand_multiplier=1.0,
    default_pattern=Pattern(),
    emitter_exponent=0.5,
    demand_model=DemandType.FIXED,
    minimum_pressure=0.0,
    required_pressure=0.1,
    pressure_exponent=0.5,
    energy_price=0.0,
    energy_price_pattern=Pattern(),
    energy_pump_efficiency=75.0,
    energy_demand_charge=0.0,
    quality_parameter=QualityParameter.NONE,
    mass_units=MassUnit.MG,
    relative_diffusivity=1.0,
    trace_node="",
    quality_tolerance=0.01,
    bulk_reaction_order=1.0,
    wall_reaction_order=WallReactionOrder.ONE,
    global_bulk_coefficient=0.0,
    global_wall_coefficient=0.0,
    limiting_concentration=0.0,
    wall_coefficient_correlation=0.0,
)


if TYPE_CHECKING:
    LayerAttributes = Mapping[Field | str, Collection[Any]]
    ModelAttributes = Mapping[ModelLayer, LayerAttributes]


@dataclasses.dataclass(frozen=True)
class Model:
    network: Network
    options: ModelOptions
    attributes: ModelAttributes

    # def __post_init__(self):
    #     object.__setattr__(
    #         self,
    #         "attributes",
    #         MappingProxyType(
    #             {
    #                 layer_type: MappingProxyType(copy.deepcopy(attributes))
    #                 for layer_type, attributes in self.attributes.items()
    #             }
    #         ),
    #     )
