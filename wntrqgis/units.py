from __future__ import annotations

import enum
from typing import TYPE_CHECKING

from wntrqgis.elements import FlowUnit, HeadlossFormula, Parameter
from wntrqgis.i18n import tr

if TYPE_CHECKING:
    import numpy as np
    import pandas as pd
    import wntr


class MassUnits(enum.Enum):
    r"""Mass units used by EPANET, plus SI conversion factor.

    Mass units are defined in the EPANET INP file when the QUALITY option is
    set to a chemical. This is parsed to obtain the mass part of the concentration units,
    and is used to set this enumerated type.

    .. rubric:: Enum Members

    ============  ============================================
    :attr:`~mg`   miligrams; EPANET as "mg/L" or "mg/min"
    :attr:`~ug`   micrograms; EPANET as "ug/L" or "ug/min"
    :attr:`~g`    grams
    :attr:`~kg`   kilograms; WNTR standard
    ============  ============================================

    .. rubric:: Enum Member Attributes

    .. autosummary::
        factor

    """

    mg = (1, 0.000001)
    ug = (2, 0.000000001)
    g = (3, 0.001)
    kg = (4, 1.0)

    @property
    def factor(self):
        """float : The scaling factor to convert to kg."""
        value = super().value
        return value[1]


class Converter:
    """Manages conversion to and from SI units

    Args:
        flow_units: The set of units which will be converted to/from
        headloss_formula: Used to determine how to handle conversion of the roughness coefficient
    """

    def __init__(
        self,
        flow_units: FlowUnit,
        headloss_formula: HeadlossFormula,
    ):
        self.flow_units = flow_units
        self.headloss_formula = headloss_formula
        self.mass_units = MassUnits.mg
        self.wall_reaction_order = 1

    @classmethod
    def from_wn(cls, wn: wntr.network.WaterNetworkModel):
        flow_units = FlowUnit[wn.options.hydraulic.inpfile_units.upper()]
        headloss_formula = HeadlossFormula(wn.options.hydraulic.headloss)
        converter = cls(flow_units, headloss_formula)
        return converter

    def to_si(
        self,
        value: float | np.ndarray[float] | pd.Series[float] | pd.DataFrame,
        parameter: Parameter,
    ) -> float | np.ndarray[float] | pd.Series[float] | pd.DataFrame:
        return value * self._factor(parameter)

    def from_si(
        self,
        value: float | np.ndarray[float] | pd.Series[float] | pd.DataFrame,
        parameter: Parameter,
    ) -> float | np.ndarray[float] | pd.Series[float] | pd.DataFrame:
        return value / self._factor(parameter)

    def _factor(
        self,
        parameter: Parameter,
    ) -> float:
        if parameter is Parameter.FLOW:
            return self._flow_unit_factor()

        if parameter is Parameter.EMITTER_COEFFICIENT:
            if self.traditional:
                # flowunit/sqrt(psi) to flowunit/sqrt(m), i.e.,
                # flowunit/sqrt(psi) * sqrt(psi/ft / m/ft ) = flowunit/sqrt(m)
                return self._flow_unit_factor() * (0.4333 / 0.3048) ** 0.5
            else:
                return self._flow_unit_factor()

        elif parameter is Parameter.PIPE_DIAMETER:
            if self.traditional:
                return 0.0254  # in to m
            else:
                return 0.001  # mm to m

        elif parameter is Parameter.ROUGHNESS_COEFFICIENT:
            if self.headloss_formula is HeadlossFormula.DARCY_WEISBACH:
                if self.traditional:
                    return 0.001 * 0.3048  # 1e-3 ft to m
                else:
                    return 0.001  # mm to m
            else:
                return 1.0

        elif parameter in [Parameter.TANK_DIAMETER, Parameter.ELEVATION, Parameter.HYDRAULIC_HEAD, Parameter.LENGTH]:
            if self.traditional:
                return 0.3048  # ft to m
            else:
                return 1.0

        elif parameter is Parameter.UNIT_HEADLOSS:
            return 0.001  # m/1000m or ft/1000ft to unitless

        elif parameter is Parameter.VELOCITY:
            if self.traditional:
                return 0.3048  # ft/s to m/s
            else:
                return 1.0

        elif parameter is Parameter.ENERGY:
            return 3600000.0  # kW*hr to J

        elif parameter is Parameter.POWER:
            if self.traditional:
                return 745.699872  # hp to W (Nm/s)
            else:
                return 1000.0  # kW to W (Nm/s)

        elif parameter is Parameter.PRESSURE:
            if self.traditional:
                # psi to m, i.e., psi * (m/ft / psi/ft) = m
                return 0.3048 / 0.4333
            else:
                return 1.0

        elif parameter is Parameter.VOLUME:
            if self.traditional:
                return 0.3048**3  # ft3 to m3
            else:
                return 1.0

        elif parameter is Parameter.CONCENTRATION:
            return self.mass_units.factor / 0.001  # MASS /L to kg/m3

        elif parameter is Parameter.REACTION_RATE:
            return (self.mass_units.factor / 0.001) / (24 * 3600)  # 1/day to 1/s

        elif parameter is Parameter.SOURCE_MASS_INJECTION:
            return self.mass_units.factor / 60.0  # MASS /min to kg/s

        elif parameter is Parameter.BULK_REACTION_COEFFICIENT:
            return 1 / 86400.0  # per day to per second

        elif parameter is Parameter.WALL_REACTION_COEFFICIENT and self.wall_reaction_order == 0:
            if self.traditional:
                return self.mass_units.factor * 0.092903 / 86400.0  # M/ft2/d to SI
            else:
                return self.mass_units.factor / 86400.0  # M/m2/day to M/m2/s

        elif parameter is Parameter.WALL_REACTION_COEFFICIENT and self.wall_reaction_order == 1:
            if self.traditional:
                return 0.3048 / 86400.0  # ft/d to m/s
            else:
                return 1.0 / 86400.0  # m/day to m/s

        elif parameter is Parameter.WATER_AGE:
            return 3600.0  # hr to s

        elif parameter in [Parameter.UNITLESS, Parameter.FRACTION, Parameter.CURRENCY]:
            return 1.0

        raise ValueError(parameter)  # pragma: no cover

    def _flow_unit_factor(self) -> float:
        flow_units = self.flow_units
        if flow_units is FlowUnit.CFS:
            factor = 0.0283168466
        elif flow_units is FlowUnit.GPM:
            factor = 0.003785411784 / 60.0
        elif flow_units is FlowUnit.MGD:
            factor = 1e6 * 0.003785411784 / 86400.0
        elif flow_units is FlowUnit.IMGD:
            factor = 1e6 * 0.00454609 / 86400.0
        elif flow_units is FlowUnit.AFD:
            factor = 1233.48184 / 86400.0
        elif flow_units is FlowUnit.LPS:
            factor = 0.001
        elif flow_units is FlowUnit.LPM:
            factor = 0.001 / 60.0
        elif flow_units is FlowUnit.MLD:
            factor = 1e6 * 0.001 / 86400.0
        elif flow_units is FlowUnit.CMH:
            factor = 1.0 / 3600.0
        elif flow_units is FlowUnit.CMD:
            factor = 1.0 / 86400.0
        else:
            raise ValueError(flow_units)  # pragma: no cover

        return factor

    @property
    def traditional(self):
        return self.flow_units in [FlowUnit.CFS, FlowUnit.GPM, FlowUnit.MGD, FlowUnit.IMGD, FlowUnit.AFD]


class UnitNames:
    def flow_unit_name(self) -> str:
        """str: The name of the flow unit"""
        return tr("*flow*")

    def mass_unit_name(self) -> str:
        """str: The name of the mass unit"""
        return tr("*mass*")

    def get(self, parameter: Parameter) -> str:
        if parameter is Parameter.FLOW:
            return self.flow_unit_name()
        if parameter is Parameter.EMITTER_COEFFICIENT:
            return tr("{flow_unit} / √m or {flow_unit} / √psi").format(flow_unit=self.flow_unit_name())
        elif parameter is Parameter.PIPE_DIAMETER:
            return tr("mm or inches")
        elif parameter is Parameter.ROUGHNESS_COEFFICIENT:
            return tr("unitless, mm, or 10⁻³ ft")
        elif parameter in [Parameter.TANK_DIAMETER, Parameter.ELEVATION, Parameter.HYDRAULIC_HEAD, Parameter.LENGTH]:
            return tr("m or ft")
        elif parameter is Parameter.UNIT_HEADLOSS:
            return tr("m/1000 m or ft/1000 ft")
        elif parameter is Parameter.VELOCITY:
            return tr("m/s or ft/s")
        elif parameter is Parameter.ENERGY:
            return tr("kWh")
        elif parameter is Parameter.POWER:
            return tr("kW or hp")
        elif parameter is Parameter.PRESSURE:
            return tr("m or psi")
        elif parameter is Parameter.VOLUME:
            return tr("m³ or ft³")
        elif parameter is Parameter.CONCENTRATION:
            return tr("mg/L")
        elif parameter is Parameter.REACTION_RATE:
            return tr("mg/L/day")
        elif parameter is Parameter.SOURCE_MASS_INJECTION:
            return tr("mg/min")
        elif parameter is Parameter.BULK_REACTION_COEFFICIENT:
            return tr(" ")
        elif parameter is Parameter.WALL_REACTION_COEFFICIENT:
            return tr("mg/m²/day,  mg/ft²/day, m/day, or ft/day")
        elif parameter is Parameter.WATER_AGE:
            return tr("hours")
        elif parameter is Parameter.UNITLESS:
            return tr("unitless")
        elif parameter is Parameter.FRACTION:
            return tr("fraction")
        elif parameter is Parameter.CURRENCY:
            return tr("currency")

        raise ValueError(parameter)  # pragma: no cover


class SpecificUnitNames(Converter, UnitNames):
    def flow_unit_name(self) -> str:
        """str: The name of the flow unit"""

        flow_unit = self.flow_units

        if flow_unit is FlowUnit.LPS:
            return tr("L/s")
        if flow_unit is FlowUnit.LPM:
            return tr("L/min")
        if flow_unit is FlowUnit.MLD:
            return tr("ML/day")
        if flow_unit is FlowUnit.CMH:
            return tr("m³/hour")
        if flow_unit is FlowUnit.CMD:
            return tr("m³/day")
        if flow_unit is FlowUnit.CFS:
            return tr("ft³/s")
        if flow_unit is FlowUnit.GPM:
            return tr("gal/min")
        if flow_unit is FlowUnit.MGD:
            return tr("MG/day")
        if flow_unit is FlowUnit.IMGD:
            return tr("imp gal/day")
        if flow_unit is FlowUnit.AFD:
            return tr("Acre-ft/day")
        raise ValueError

    def mass_unit_name(self):
        mass_unit = self.mass_units
        if mass_unit is MassUnits.mg:
            return tr("mg")
        if mass_unit is MassUnits.ug:
            return tr("ug")
        if mass_unit is MassUnits.g:
            return tr("g")
        if mass_unit is MassUnits.kg:
            return tr("kg")
        raise ValueError(mass_unit)  # pragma: no cover

    def get(
        self,
        parameter: Parameter,
    ) -> str:
        if parameter is Parameter.FLOW:
            return self.flow_unit_name()

        if parameter is Parameter.EMITTER_COEFFICIENT:
            if self.traditional:
                return tr("{flow_unit}/√psi").format(flow_unit=self.flow_unit_name())
            else:
                return tr("{flow_unit}/√m").format(flow_unit=self.flow_unit_name())

        elif parameter is Parameter.PIPE_DIAMETER:
            if self.traditional:
                return tr("in")
            else:
                return tr("mm")

        elif parameter is Parameter.ROUGHNESS_COEFFICIENT:
            if self.headloss_formula is HeadlossFormula.DARCY_WEISBACH:
                if self.traditional:
                    return tr("10⁻³ ft")  # 1e-3 ft to m
                else:
                    return tr("mm")  # mm to m
            else:
                return tr("unitless")

        elif parameter in [Parameter.TANK_DIAMETER, Parameter.ELEVATION, Parameter.HYDRAULIC_HEAD, Parameter.LENGTH]:
            if self.traditional:
                return tr("ft")  # ft to m
            else:
                return tr("m")

        elif parameter is Parameter.UNIT_HEADLOSS:
            if self.traditional:
                return tr("ft/1000 ft  ")  # ft to m
            else:
                return tr("m/1000 m")  # m/1000m or ft/1000ft to unitless

        elif parameter is Parameter.VELOCITY:
            if self.traditional:
                return tr("ft/s")
            else:
                return tr("m/s")

        elif parameter is Parameter.ENERGY:
            return tr("kWhr")

        elif parameter is Parameter.POWER:
            if self.traditional:
                return tr("hp")  # hp to W (Nm/s)
            else:
                return tr("kW")  # kW to W (Nm/s)

        elif parameter is Parameter.PRESSURE:
            if self.traditional:
                # psi to m, i.e., psi * (m/ft / psi/ft) = m
                return tr("psi")
            else:
                return tr("m")

        elif parameter is Parameter.VOLUME:
            if self.traditional:
                return tr("ft³")
            else:
                return tr("m³")

        mass = self.mass_unit_name()

        if parameter is Parameter.CONCENTRATION:
            return tr("{mass_unit}/L").format(mass_unit=mass)

        elif parameter is Parameter.REACTION_RATE:
            return tr("{mass_unit}/L/day").format(mass_unit=mass)

        elif parameter is Parameter.SOURCE_MASS_INJECTION:
            return tr("{mass_unit}/min").format(mass_unit=mass)  # MASS /min to kg/s

        elif parameter is Parameter.BULK_REACTION_COEFFICIENT:
            return "  "

        elif parameter is Parameter.WALL_REACTION_COEFFICIENT and self.wall_reaction_order == 0:
            if self.traditional:
                return tr("{mass_unit}/ft²/day").format(mass_unit=mass)  # M/ft2/d to SI
            else:
                return tr("{mass_unit}/m²/day").format(mass_unit=mass)  # M/m2/day to M/m2/s

        elif parameter is Parameter.WALL_REACTION_COEFFICIENT and self.wall_reaction_order == 1:
            if self.traditional:
                return tr("ft/day")  # ft/d to m/s
            else:
                return tr("m/day")  # m/day to m/s

        elif parameter is Parameter.WATER_AGE:
            return tr("hours")
        elif parameter is Parameter.UNITLESS:
            return tr("unitless")
        elif parameter is Parameter.FRACTION:
            return tr("fraction")
        elif parameter is Parameter.CURRENCY:
            return tr("currency")

        raise ValueError(parameter)  # pragma: no cover
