"""
This module contains the interfaces for for converting between WNTR and QGIS, both model layers and simulation results.
"""

from __future__ import annotations

import functools
import itertools
import logging
import math
import pathlib
import warnings
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from qgis.core import Qgis, QgsGeometry, QgsPoint, QgsUnitTypes

from gusnet.elements import (
    CurveType,
    DefaultOptions,
    DemandType,
    Field,
    FieldGroup,
    FlowUnit,
    HeadlossFormula,
    MassUnit,
    ModelLayer,
    ModelOptions,
    Parameter,
    PumpTypes,
    QualityParameter,
    ResultLayer,
    ValveType,
    WallReactionOrder,
    _AbstractLayer,
)
from gusnet.i18n import tr
from gusnet.pattern_curve import Curve, Pattern
from gusnet.units import Converter, SpecificUnitNames

if TYPE_CHECKING:  # pragma: no cover
    import wntr  # noqa
    import pandas as pd
    from collections.abc import Iterable

logger = logging.getLogger(__name__)

QGIS_USE_DISTANCE_UNIT = Qgis.versionInt() >= 33000
QGIS_METERS = Qgis.DistanceUnit.Meters if QGIS_USE_DISTANCE_UNIT else QgsUnitTypes.DistanceMeters
QGIS_FEET = Qgis.DistanceUnit.Feet if QGIS_USE_DISTANCE_UNIT else QgsUnitTypes.DistanceFeet


class WntrModel:
    _wn: wntr.network.WaterNetworkModel
    _options: ModelOptions
    _converter: Converter
    _existing_patterns: dict[Pattern, str]
    _elements: dict[ModelLayer, pd.DataFrame] | None = None
    _node_geometry: dict[str, QgsGeometry] | pd.Series[QgsGeometry] | None = None
    _link_geometry: dict[str, QgsGeometry] | pd.Series[QgsGeometry] | None = None
    _wntr_results: wntr.sim.SimulationResults | None = None
    _processed_results: dict[ResultLayer, pd.DataFrame] | None = None

    def __init__(self, wn: wntr.network.WaterNetworkModel | pathlib.Path | str | None = None):
        import wntr

        if wn:
            if isinstance(wn, (str, pathlib.Path)):
                wn = wntr.network.WaterNetworkModel(str(wn))

            self._wn = wn
            options = self.options_from_wn()
        else:
            self._wn = wntr.network.WaterNetworkModel()
            options = DefaultOptions()

        self._next_pattern_name = functools.partial(
            next, filter(lambda n: n not in self._wn.pattern_name_list, map(str, itertools.count(2)))
        )
        self._next_curve_name = functools.partial(
            next, filter(lambda n: n not in self._wn.curve_name_list, map(str, itertools.count(1)))
        )
        self._existing_patterns = {Pattern(pat.multipliers): name for name, pat in self._wn.patterns()}

        self.options = options

    @property
    def wn(self) -> wntr.network.WaterNetworkModel:
        return self._wn

    @property
    def options(self) -> ModelOptions:
        return self._options

    @options.setter
    def options(self, options: ModelOptions) -> None:
        self.options_to_wn(options)
        self._converter = Converter.from_options(options)
        self._options = options

    def suggested_fields(self, layer: _AbstractLayer | None = None) -> list[Field]:
        field_groups = FieldGroup.BASE | _get_field_groups(self.options)

        if layer:
            return [field for field in layer.wq_fields() if field.field_group & field_groups]
        else:
            return [field for field in Field if field.field_group & field_groups]

    def add_elements(self, node_df: pd.DataFrame, link_df: pd.DataFrame) -> None:
        """Convert the node and link dataframes to a WNTR WaterNetworkModel"""

        wn_dict: dict[str, Any] = {}
        wn_dict["nodes"] = _to_dict(node_df)
        wn_dict["links"] = _to_dict(link_df)

        logging.getLogger("wntr.network.io").setLevel(logging.CRITICAL)
        try:
            self._wn.from_dict(wn_dict)
        except Exception as e:
            raise WntrError(e) from e

    def add_pattern(self, pattern: Pattern | Iterable[float] | str | None) -> str | None:
        """Takes a Pattern object, or a string or iterable describing the pattern.
        Adds it to the wntr wn, and returns the new pattern name.
        Returns None if the pattern is empty.

        Raises ValueError if the pattern is malformed"""

        if not isinstance(pattern, Pattern):
            pattern = Pattern(pattern)

        if not pattern:
            return None

        if existing_pattern_name := self._existing_patterns.get(pattern):
            return existing_pattern_name

        name = self._next_pattern_name()
        self._add_finalised_pattern(name, pattern)
        self._existing_patterns[pattern] = name
        return name

    def _add_finalised_pattern(self, name: str, pattern: Pattern) -> None:
        """Adds a pattern that has already been finalised with a name."""
        self._wn.add_pattern(name=name, pattern=list(pattern))

    def get_pattern(self, pattern_name: wntr.network.Pattern | str | None) -> Pattern:
        if not pattern_name:
            return Pattern()
        elif isinstance(pattern_name, str):
            pattern = self._wn.get_pattern(pattern_name)
        else:
            pattern = pattern_name

        return Pattern(pattern.multipliers)

    # required for older python/qgis verisons
    def get_pattern_str(self, pattern_name: wntr.network.Pattern | str | None) -> str:
        return str(self.get_pattern(pattern_name))

    def add_curve(self, curve: str, curve_type: CurveType) -> str | None:
        if not isinstance(curve, Curve):
            curve = Curve(curve)

        if not curve:
            return None

        name = self._next_curve_name()

        self._add_finalised_curve(name, curve_type, curve)
        return name

    def _add_finalised_curve(self, name: str, curve_type: CurveType, curve: Curve) -> None:
        """Adds a curve that has already been finalised with a name."""
        curve_points = _convert_curve_points(list(curve), curve_type, self._converter.to_si)

        self._wn.add_curve(name=name, curve_type=curve_type.name, xy_tuples_list=curve_points)

    add_head_curve = functools.partialmethod(add_curve, curve_type=CurveType.HEAD)
    add_efficiency_curve = functools.partialmethod(add_curve, curve_type=CurveType.EFFICIENCY)
    add_volume_curve = functools.partialmethod(add_curve, curve_type=CurveType.VOLUME)
    add_headloss_curve = functools.partialmethod(add_curve, curve_type=CurveType.HEADLOSS)

    def get_curve(self, curve_name: str) -> Curve:
        wntr_curve: wntr.network.elements.Curve = self._wn.get_curve(curve_name)

        curve_type = CurveType[wntr_curve.curve_type]

        converted_points = _convert_curve_points(wntr_curve.points, curve_type, self._converter.from_si)

        return Curve(converted_points)

    def get_curve_str(self, curve_name: str) -> str:
        return str(self.get_curve(curve_name))

    @property
    def node_geometries(self) -> dict[str, QgsGeometry] | pd.Series[QgsGeometry]:
        if self._node_geometry is not None:
            return self._node_geometry

        nodes = {name: QgsGeometry(QgsPoint(*node.coordinates)) for name, node in self._wn.nodes()}
        self._node_geometry = nodes
        return nodes

    @property
    def link_geometries(self) -> dict[str, QgsGeometry] | pd.Series[QgsGeometry]:
        if self._link_geometry is not None:
            return self._link_geometry

        nodes = self.node_geometries
        self._link_geometry = {
            name: QgsGeometry.fromPolyline(
                [
                    nodes[link.start_node.name].constGet(),
                    *[QgsPoint(*vertex) for vertex in link.vertices],
                    nodes[link.end_node.name].constGet(),
                ]
            )
            for name, link in self._wn.links()
        }

        return self._link_geometry

    def set_node_geometry(self, node_geometry: dict[str, QgsGeometry] | pd.Series[QgsGeometry]) -> None:
        node_registry = self._wn.nodes

        for name, geometry in node_geometry.items():
            node = node_registry[name]
            point = geometry.constGet()
            node.coordinates = (point.x(), point.y())

        self._node_geometry = node_geometry
        self._link_geometry = None  # invalidate link geometry cache

    def set_link_geometry(self, link_geometry: dict[str, QgsGeometry]) -> None:
        link_registry = self._wn.links

        for name, geometry in link_geometry.items():
            link = link_registry[name]
            link.vertices = [(v.x(), v.y()) for v in geometry.asPolyline()[1:-1]]

        self._link_geometry = link_geometry

    def run(self, output_file_prefix: str = "temp") -> None:
        import wntr

        sim = wntr.sim.EpanetSimulator(self._wn)
        try:
            self.set_results(sim.run_sim(file_prefix=output_file_prefix))
        except wntr.epanet.exceptions.EpanetException as e:
            raise EpanetError(e) from e

    def get_elements(self) -> dict[ModelLayer, pd.DataFrame]:
        if self._elements:
            return self._elements

        import pandas as pd

        wn_dict = self._wn.to_dict()

        dfs: dict[ModelLayer, pd.DataFrame] = {}

        df_nodes = pd.DataFrame(wn_dict["nodes"])
        df_nodes = df_nodes.drop(
            columns=["coordinates", "demand_timeseries_list", "leak", "leak_area", "leak_discharge_coeff"],
            errors="ignore",
        )
        if not df_nodes.empty:
            for layer in [ModelLayer.JUNCTIONS, ModelLayer.RESERVOIRS, ModelLayer.TANKS]:
                mask = df_nodes["node_type"] == layer.field_type
                if mask.any():
                    dfs[layer] = self._process_model_df_from_wntr(df_nodes[mask], layer)

        df_links = pd.DataFrame(wn_dict["links"])
        df_links = df_links.drop(
            columns=["start_node_name", "end_node_name", "vertices", "initial_quality"], errors="ignore"
        )
        if not df_links.empty:
            for layer in [ModelLayer.PIPES, ModelLayer.PUMPS, ModelLayer.VALVES]:
                mask = df_links["link_type"] == layer.field_type
                if mask.any():
                    dfs[layer] = self._process_model_df_from_wntr(df_links[mask], layer)

        self._elements = dfs
        return self._elements

    def _process_model_df_from_wntr(self, df: pd.DataFrame, layer: ModelLayer) -> pd.DataFrame | None:
        df = df.drop(columns=["link_type", "node_type"], errors="ignore")

        df = df.dropna(axis=1, how="all")

        df = df.set_index("name", drop=False)

        if (
            layer in [ModelLayer.JUNCTIONS, ModelLayer.RESERVOIRS, ModelLayer.TANKS]
            and "initial_quality" in df
            and (df["initial_quality"] == 0.0).all()
        ):
            df = df.drop(columns=["initial_quality"])

        if layer is ModelLayer.JUNCTIONS:
            import wntr

            # Special case for demands
            df["base_demand"] = self._wn.query_node_attribute("base_demand", node_type=wntr.network.model.Junction)

            # 'demand_pattern' didn't exist on node prior to wntr 1.3.0 so we have to go searching:
            demand_pattern = self._wn.query_node_attribute(
                "demand_timeseries_list", node_type=wntr.network.model.Junction
            ).map(lambda dtl: dtl.pattern_list()[0] or None)
            df["demand_pattern"] = demand_pattern.map(self.get_pattern_str, na_action="ignore")

        elif layer is ModelLayer.RESERVOIRS:
            if "head_pattern_name" in df:
                df["head_pattern"] = df["head_pattern_name"].map(self.get_pattern_str, na_action="ignore")
                df = df.drop(columns="head_pattern_name")

        elif layer is ModelLayer.TANKS:
            if "vol_curve_name" in df:
                df["vol_curve"] = df["vol_curve_name"].map(self.get_curve_str, na_action="ignore")
                df = df.drop(columns="vol_curve_name")

            df = df.rename(columns={"diameter": "tank_diameter"})

        elif layer is ModelLayer.PUMPS:
            # not all pumps will have a pump curve (power pumps)!
            if "pump_curve_name" in df:
                df["pump_curve"] = df["pump_curve_name"].map(self.get_curve_str, na_action="ignore")
                df = df.drop(columns="pump_curve_name")

            if "speed_pattern_name" in df:
                df["speed_pattern"] = df["speed_pattern_name"].map(self.get_pattern, na_action="ignore")
                df = df.drop(columns="speed_pattern_name")
            # 'energy pattern' is not called energy pattern name!
            if "energy_pattern" in df:
                df["energy_pattern"] = df["energy_pattern"].map(self.get_pattern_str, na_action="ignore")
            if "efficiency_curve_name" in df:
                df["efficiency_curve"] = df["efficiency_curve_name"].map(self.get_curve_str, na_action="ignore")
                df = df.drop(columns="efficiency_curve_name")

        elif layer is ModelLayer.VALVES:
            pressure_valves = df["valve_type"].isin(["PRV", "PSV", "PBV"])
            flow_valves = df["valve_type"] == "FCV"
            throttle_valves = df["valve_type"] == "TCV"
            general_valves = df["valve_type"] == "GPV"

            if "initial_setting" in df:
                df.loc[pressure_valves, "pressure_setting"] = df.loc[pressure_valves, "initial_setting"]
                df.loc[flow_valves, "flow_setting"] = df.loc[flow_valves, "initial_setting"]
                df.loc[throttle_valves, "throttle_setting"] = df.loc[throttle_valves, "initial_setting"]
                df = df.drop(columns="initial_setting")

            if "headloss_curve" in df:
                df.loc[general_valves, "headloss_curve"] = df.loc[general_valves, "headloss_curve_name"].map(
                    self.get_curve_str, na_action="ignore"
                )

            df = df.rename(columns={"initial_status": "valve_status"})

        df = _convert_dataframe(df, self._converter.from_si)

        return df

    def set_elements(self, elements: dict[ModelLayer, pd.DataFrame]) -> None:
        """Convert the node and link dataframes to a WNTR WaterNetworkModel"""

        wn_dict: dict[str, list[dict]] = {"nodes": [], "links": []}
        for layer, df in elements.items():
            model_layer = ModelLayer(layer)

            df = _convert_dataframe(df, self._converter.to_si)

            if model_layer is ModelLayer.JUNCTIONS:
                df = self._process_junctions(df)
            elif model_layer is ModelLayer.TANKS:
                df = self._process_tanks(df)
            elif model_layer is ModelLayer.RESERVOIRS:
                df = self._process_reservoirs(df)
            elif model_layer is ModelLayer.VALVES:
                df = self._do_valve_patterns_curves(df)
            elif model_layer is ModelLayer.PUMPS:
                df = self._do_pump_patterns_curves(df)

            df["node_type" if model_layer.is_node else "link_type"] = model_layer.field_type

            wn_dict["nodes" if model_layer.is_node else "links"].extend(_to_dict(df))

        logging.getLogger("wntr.network.io").setLevel(logging.CRITICAL)
        try:
            self._wn.from_dict(wn_dict)
        except Exception as e:
            raise WntrError(e) from e

    def _process_junctions(self, df: pd.DataFrame) -> pd.DataFrame:
        import numpy as np
        import pandas as pd

        if Field.BASE_DEMAND not in df.columns:
            df[Field.BASE_DEMAND] = np.nan

        if Field.DEMAND_PATTERN in df.columns:
            df[Field.DEMAND_PATTERN] = df[Field.DEMAND_PATTERN].map(Pattern.factory, na_action="ignore")
        else:
            df[Field.DEMAND_PATTERN] = np.nan

        timeseries_list: list[list | float] = []

        for base_val, pattern_name in zip(df[Field.BASE_DEMAND], df[Field.DEMAND_PATTERN]):
            has_base_demand = not math.isnan(base_val) and base_val is not pd.NA
            has_pattern = isinstance(pattern_name, Pattern)
            if has_base_demand or has_pattern:
                base_val = base_val if has_base_demand else 0.0
                pattern_name = self.add_pattern(pattern_name) if has_pattern else None
                timeseries_list.append([{"base_val": base_val, "pattern_name": pattern_name}])
            else:
                timeseries_list.append(np.nan)

        df["demand_timeseries_list"] = timeseries_list

        return df.drop(columns=[Field.BASE_DEMAND, Field.DEMAND_PATTERN])

    def _process_tanks(self, df: pd.DataFrame) -> pd.DataFrame:
        if Field.VOL_CURVE in df:
            df["vol_curve_name"] = df[Field.VOL_CURVE].map(self.add_volume_curve, na_action="ignore")

            df = df.drop(columns=[Field.VOL_CURVE])

        df = df.rename(columns={Field.TANK_DIAMETER: "diameter"})

        return df

    def _process_reservoirs(self, df: pd.DataFrame) -> pd.DataFrame:
        if Field.HEAD_PATTERN in df:
            df["head_pattern_name"] = df[Field.HEAD_PATTERN].map(self.add_pattern, na_action="ignore")

            df = df.drop(columns=[Field.HEAD_PATTERN])

        return df

    def _do_valve_patterns_curves(self, df: pd.DataFrame) -> pd.DataFrame:
        df[Field.VALVE_TYPE] = df[Field.VALVE_TYPE].str.upper()

        for valve_type in [ValveType.PRV, ValveType.PSV, ValveType.PBV, ValveType.FCV, ValveType.TCV]:
            valve_mask = df[Field.VALVE_TYPE] == valve_type.name

            if not valve_mask.any():
                continue

            df.loc[valve_mask, "initial_setting"] = df.loc[valve_mask, valve_type.setting_field]

        gpvs = df[Field.VALVE_TYPE] == ValveType.GPV.name

        if gpvs.any():
            df.loc[gpvs, "headloss_curve_name"] = df.loc[gpvs, Field.HEADLOSS_CURVE].map(
                self.add_headloss_curve, na_action="ignore"
            )

        df = df.rename(columns={Field.VALVE_STATUS: "initial_status"})

        return df.drop(columns=[valve_type.setting_field for valve_type in ValveType], errors="ignore")

    def _do_pump_patterns_curves(self, df: pd.DataFrame) -> pd.DataFrame:
        df[Field.PUMP_TYPE] = df[Field.PUMP_TYPE].str.upper()

        head_pumps = df[Field.PUMP_TYPE] == PumpTypes.HEAD.name
        if head_pumps.any():
            df.loc[head_pumps, "pump_curve_name"] = df.loc[head_pumps, Field.PUMP_CURVE].map(
                self.add_head_curve, na_action="ignore"
            )

        if Field.SPEED_PATTERN in df:
            df["speed_pattern_name"] = df[Field.SPEED_PATTERN].map(self.add_pattern, na_action="ignore")

        if Field.ENERGY_PATTERN in df:
            df["energy_pattern"] = df[Field.ENERGY_PATTERN].map(self.add_pattern, na_action="ignore")

        if Field.EFFICIENCY_CURVE in df:
            df["efficiency_curve_name"] = df[Field.EFFICIENCY_CURVE].map(self.add_efficiency_curve, na_action="ignore")

        return df.drop(
            columns=[Field.PUMP_CURVE, Field.SPEED_PATTERN, Field.EFFICIENCY_CURVE],
            errors="ignore",
        )

    def set_results(self, results: wntr.sim.SimulationResults) -> None:
        self._wntr_results = results
        self._processed_results = None

    def get_results(self) -> dict[ResultLayer, pd.DataFrame]:
        if self._processed_results:
            return self._processed_results

        if not self._wntr_results:
            raise ValueError(tr("No simulation results are available. Set results first."))

        node_dfs = self._wntr_results.node
        link_dfs = self._wntr_results.link

        pipe_lengths = self._get_pipe_lengths()
        link_dfs["unit_headloss"], link_dfs["headloss"] = _fix_headloss_df(link_dfs[Field.HEADLOSS.value], pipe_lengths)

        node_df = self._process_results_layer(ResultLayer.NODES, node_dfs)
        link_df = self._process_results_layer(ResultLayer.LINKS, link_dfs)

        self._processed_results = {ResultLayer.NODES: node_df, ResultLayer.LINKS: link_df}
        return self._processed_results

    def _get_pipe_lengths(self) -> pd.Series:
        import pandas as pd

        return pd.Series({name: pipe.length for name, pipe in self._wn.pipes()})

    def _process_results_layer(self, layer: ResultLayer, results_dfs: dict[str, pd.DataFrame]) -> pd.DataFrame:
        import pandas as pd

        output_series: list[pd.Series] = []

        for field in layer.wq_fields():
            df = results_dfs.get(field.value)

            if df is None or df.empty:
                continue

            if isinstance(field.type, Parameter):
                df = self._converter.from_si(df, field.type)

            if self.options.simulation_duration == 0:
                series = df.iloc[0]
                series.name = field.value
                output_series.append(series)
            else:
                lists = df.transpose().to_numpy().tolist()
                output_series.append(pd.Series(lists, index=df.columns, name=field.value))

        combined_df = pd.concat(output_series, axis=1)
        combined_df["name"] = combined_df.index.to_series()

        return combined_df

    def write_inp_file(self, file_path: str | pathlib.Path) -> None:
        import wntr

        wntr.network.write_inpfile(self.wn, str(file_path))

    def options_from_wn(self) -> ModelOptions:
        o: wntr.network.Options = self.wn.options

        flow_unit = FlowUnit(o.hydraulic.inpfile_units)
        headloss_formula = HeadlossFormula(o.hydraulic.headloss)
        mass_unit = MassUnit(o.quality.inpfile_units)

        converter = Converter(flow_unit, headloss_formula, mass_unit)

        return ModelOptions(
            flow_unit=flow_unit,
            headloss_formula=headloss_formula,
            simulation_duration=o.time.duration / 3600,
            demand_multiplier=o.hydraulic.demand_multiplier,
            emitter_exponent=o.hydraulic.emitter_exponent,
            demand_type=DemandType(o.hydraulic.demand_model),
            minimum_pressure=converter.from_si(o.hydraulic.minimum_pressure, Parameter.HYDRAULIC_HEAD),
            required_pressure=converter.from_si(o.hydraulic.required_pressure, Parameter.HYDRAULIC_HEAD),
            pressure_exponent=o.hydraulic.pressure_exponent,
            energy_report=str(o.report.energy).upper() == "YES",
            energy_price=float(o.energy.global_price),
            energy_pattern=self.get_pattern(o.energy.global_pattern),
            energy_pump_efficiency=float(o.energy.global_efficiency or 75),  # hacky fix
            energy_demand_charge=float(o.energy.demand_charge or 0.0),
            quality_parameter=QualityParameter(o.quality.parameter),
            mass_unit=mass_unit,
            relative_diffusivity=o.quality.diffusivity,
            trace_node=(o.quality.trace_node or ""),
            quality_tolerance=o.quality.tolerance,
            bulk_reaction_order=o.reaction.bulk_order,
            wall_reaction_order=WallReactionOrder(o.reaction.wall_order),
            global_bulk_coefficient=o.reaction.bulk_coeff,
            global_wall_coefficient=o.reaction.wall_coeff,
            limiting_concentration=float(o.reaction.limiting_potential or 0),
            wall_coefficient_correlation=float(o.reaction.roughness_correl or 0),
        )

    def options_to_wn(self, options: ModelOptions) -> None:
        o: wntr.network.Options = self.wn.options

        converter = Converter.from_options(options)

        with warnings.catch_warnings():
            warnings.filterwarnings(
                "ignore",
                category=UserWarning,
                message="Changing the headloss formula from H-W to D-W will not change",
            )
            o.hydraulic.headloss = options.headloss_formula.value

        o.hydraulic.inpfile_units = options.flow_unit.value
        o.time.duration = int(options.simulation_duration * 3600)
        o.hydraulic.demand_multiplier = options.demand_multiplier
        o.hydraulic.emitter_exponent = options.emitter_exponent
        o.hydraulic.demand_model = options.demand_type.value
        o.hydraulic.minimum_pressure = converter.to_si(options.minimum_pressure, Parameter.HYDRAULIC_HEAD)
        o.hydraulic.required_pressure = converter.to_si(options.required_pressure, Parameter.HYDRAULIC_HEAD)
        o.hydraulic.pressure_exponent = options.pressure_exponent
        o.report.energy = "YES" if options.energy_report else "NO"
        o.energy.global_price = options.energy_price
        o.energy.global_pattern = self.add_pattern(options.energy_pattern)
        o.energy.global_efficiency = options.energy_pump_efficiency
        o.energy.demand_charge = options.energy_demand_charge
        o.quality.parameter = options.quality_parameter.value
        o.quality.inpfile_units = options.mass_unit.value
        o.quality.diffusivity = options.relative_diffusivity
        o.quality.trace_node = options.trace_node or None
        o.quality.tolerance = options.quality_tolerance
        o.reaction.bulk_order = options.bulk_reaction_order
        o.reaction.wall_order = options.wall_reaction_order.value
        o.reaction.bulk_coeff = options.global_bulk_coefficient
        o.reaction.wall_coeff = options.global_wall_coefficient
        o.reaction.limiting_potential = options.limiting_concentration or None
        o.reaction.roughness_correl = options.wall_coefficient_correlation or None

    def describe_network(self) -> tuple[str, str]:
        """Returns an html and text string describing the network model.

        Args:
            wn: WaterNetworkModel to describe

        Returns:
            A tuple with a html and text string description.
        """
        wn = self.wn

        title = tr("Network Summary")
        counts = {
            ModelLayer.JUNCTIONS.friendly_name: wn.num_junctions,
            ModelLayer.TANKS.friendly_name: wn.num_tanks,
            ModelLayer.RESERVOIRS.friendly_name: wn.num_reservoirs,
            ModelLayer.PIPES.friendly_name: wn.num_pipes,
            ValveType.PRV.friendly_name: len(list(wn.prvs())),
            ValveType.PSV.friendly_name: len(list(wn.psvs())),
            ValveType.PBV.friendly_name: len(list(wn.pbvs())),
            ValveType.FCV.friendly_name: len(list(wn.fcvs())),
            ValveType.TCV.friendly_name: len(list(wn.tcvs())),
            ValveType.GPV.friendly_name: len(list(wn.gpvs())),
            tr("Pumps defined by power"): len(list(wn.power_pumps())),
            tr("Pumps defined by head curve"): len(list(wn.head_pumps())),
        }

        text = title + "\n"
        text += "\n".join((str(count) + " " + part) for part, count in counts.items() if count > 0)

        html = "<b>" + title + "</b>"
        html += "<table border='1'>"
        html += "<thead><tr><th>" + tr("Element") + "</th><th>" + tr("Count") + "</th></tr></thead>"
        html += "<tbody>"
        for part, count in counts.items():
            if count > 0:
                html += f"<tr><td>{part}</td><td>{count}</td></tr>"
        html += "</tbody></table>"

        return html, text

    def describe_pipes(self) -> tuple[str, str]:
        import pandas as pd

        options = self.options
        converter = Converter.from_options(options)
        unit_names = SpecificUnitNames.from_options(options)

        pipe_df = pd.DataFrame(
            ((pipe.length, pipe.diameter, pipe.roughness) for _, pipe in self.wn.pipes()),
            columns=["length", "diameter", "roughness"],
        )
        pipe_df["length"] = converter.from_si(pipe_df["length"], Parameter.LENGTH)
        pipe_df["diameter"] = converter.from_si(pipe_df["diameter"], Parameter.PIPE_DIAMETER)
        pipe_df["roughness"] = converter.from_si(pipe_df["roughness"], Parameter.ROUGHNESS_COEFFICIENT)

        formatted_df = pd.concat(
            [
                pipe_df.groupby("diameter").agg(
                    {"length": ["count", "sum", "min", "max"], "roughness": ["min", "max"]}
                ),
                pipe_df.groupby(lambda _: True)
                .agg({"length": ["sum", "count", "min", "max"], "roughness": ["min", "max"]})
                .rename(index={1.0: tr("All Pipes")}),
            ]
        ).round()

        length_title = Field.LENGTH.friendly_name + " (" + unit_names.get(Parameter.LENGTH) + ")"
        roughness_title = Field.ROUGHNESS.friendly_name + " (" + unit_names.get(Parameter.ROUGHNESS_COEFFICIENT) + ")"
        diameter_title = Field.DIAMETER.friendly_name + " (" + unit_names.get(Parameter.PIPE_DIAMETER) + ")"

        index = pd.MultiIndex.from_tuples(
            [
                ("", tr("Count")),
                (length_title, tr("Total")),
                (length_title, tr("Min")),
                (length_title, tr("Max")),
                (roughness_title, tr("Min")),
                (roughness_title, tr("Max")),
            ],
        )

        formatted_df.columns = index
        formatted_df.index.name = diameter_title

        def format_number(num):
            if isinstance(num, float):
                return f"{num:,.4f}".rstrip("0").rstrip(".").rjust(10, " ").replace(" ", "&nbsp;").replace(",", " ")
            return num

        formatted_df.index = formatted_df.index.map(format_number)
        formatted_df = formatted_df.astype(float)

        html = "<b>Pipe Summary</b>"
        html += formatted_df.to_html(col_space=75, float_format=format_number, escape=False).replace("\n", "")

        text = tr("Total pipe length: {pipe_length} {unit}").format(
            pipe_length=format_number(pipe_df["length"].sum()), unit=unit_names.get(Parameter.LENGTH)
        )

        return html, text


def _fix_headloss_df(df: pd.DataFrame, pipe_lengths: pd.Series) -> tuple[pd.DataFrame, pd.DataFrame]:
    import pandas as pd

    df = df.astype("float64")
    unit_headloss = df[pipe_lengths.index]

    valve_total_headloss = df.drop(pipe_lengths.index, axis=1, errors="ignore")
    pipe_total_headloss = unit_headloss * pipe_lengths
    total_headloss = pd.concat([valve_total_headloss, pipe_total_headloss], axis=1)

    return unit_headloss, total_headloss


def _convert_dataframe(source_df: pd.DataFrame, conversion_function: Callable) -> pd.DataFrame:
    for fieldname in source_df.columns:
        try:
            parameter = Field(fieldname).type
        except ValueError:
            continue
        if not isinstance(parameter, Parameter):
            continue

        source_df[fieldname] = conversion_function(source_df[fieldname], parameter)
    return source_df


def _convert_curve_points(
    points: list, curve_type: CurveType, conversion_function: Callable
) -> list[tuple[float, float]]:
    converted_points: list[tuple[float, float]] = []

    x_param, y_param = curve_type.value[1]

    for point in points:
        x = conversion_function(point[0], x_param)
        y = conversion_function(point[1], y_param)
        converted_points.append((x, y))

    return converted_points


def _to_dict(df: pd.DataFrame) -> list[dict]:
    import pandas as pd

    def is_valid(v):
        return not (v is pd.NA or v != v or v is None)  # noqa: PLR0124

    speedy_data = df.to_numpy().tolist()
    columns = df.columns.tolist()
    return [{k: v for k, v in zip(columns, m) if is_valid(v)} for m in speedy_data]


def _get_field_groups(options: ModelOptions) -> FieldGroup:
    """Utility function for guessing what types of analysis a specific wn will undertake,
    and therefore which field types should be included."""

    field_groups = FieldGroup(0)

    if options.quality_parameter is not QualityParameter.NONE:
        field_groups = field_groups | FieldGroup.WATER_QUALITY_ANALYSIS

    if options.energy_report:
        field_groups = field_groups | FieldGroup.ENERGY

    return field_groups


class NetworkModelError(Exception):
    pass


class WntrError(NetworkModelError):
    def __init__(self, exception):
        super().__init__(
            tr("Error from WNTR. {exception_name}: {exception}").format(
                exception_name=type(exception).__name__, exception=exception
            )
        )


class EpanetError(NetworkModelError):
    def __init__(self, exception):
        super().__init__(tr("Error from EPANET: {exception}").format(exception=exception))
