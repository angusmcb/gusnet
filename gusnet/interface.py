"""
This module contains the interfaces for for converting between WNTR and QGIS, both model layers and simulation results.
"""

from __future__ import annotations

import ast
import dataclasses
import enum
import functools
import importlib
import itertools
import logging
import math
import pathlib
import warnings
from typing import TYPE_CHECKING, Any, Literal

from qgis.core import (
    NULL,
    Qgis,
    QgsCoordinateReferenceSystem,
    QgsDistanceArea,
    QgsFeature,
    QgsFeatureRequest,
    QgsFeatureSink,
    QgsFeatureSource,
    QgsField,
    QgsFields,
    QgsGeometry,
    QgsPoint,
    QgsProject,
    QgsUnitTypes,
    QgsVectorLayer,
)
from qgis.PyQt.QtCore import QMetaType, QVariant

import gusnet.style
from gusnet.elements import (
    DefaultOptions,
    DemandType,
    Field,
    FieldGroup,
    FlowUnit,
    HeadlossFormula,
    MapFieldType,
    MassUnit,
    ModelLayer,
    ModelOptions,
    Parameter,
    PumpTypes,
    QualityParameter,
    ResultLayer,
    SimpleFieldType,
    ValveType,
    WallReactionOrder,
    _AbstractLayer,
)
from gusnet.i18n import tr
from gusnet.pattern_curve import Pattern
from gusnet.spatial_index import SnapError, SpatialIndex
from gusnet.units import Converter, SpecificUnitNames

if TYPE_CHECKING:  # pragma: no cover
    import wntr  # noqa
    import pandas as pd
    import numpy as np
    from collections.abc import Iterable

logger = logging.getLogger(__name__)

QGIS_VERSION_DISTANCE_UNIT_IN_QGIS = 33000
QGIS_DISTANCE_UNIT_METERS = (
    Qgis.DistanceUnit.Meters if Qgis.versionInt() >= QGIS_VERSION_DISTANCE_UNIT_IN_QGIS else QgsUnitTypes.DistanceMeters
)
USE_QMETATYPE = Qgis.versionInt() >= 33800


def needs_wntr_pandas(func):
    """This decorator loads numpy, pandas and wntr.

    Delayed loading means this module can be imported without throwing error if they don't exist"""

    @functools.wraps(func)
    def check_wntr(*args, **kwargs):
        if "wntr" not in globals():
            importlib.invalidate_caches()
            import numpy as np
            import pandas as pd
            import wntr

            globals()["wntr"] = wntr
            globals()["pd"] = pd
            globals()["np"] = np

        return func(*args, **kwargs)

    return check_wntr


@needs_wntr_pandas
def to_qgis(
    wn: wntr.network.WaterNetworkModel | pathlib.Path | str,
    results: wntr.sim.SimulationResults | None = None,
    crs: QgsCoordinateReferenceSystem | str | None = None,
    units: Literal["LPS", "LPM", "MLD", "CMH", "CFS", "GPM", "MGD", "IMGD", "AFD", "CMD"] | None = None,
    # layers: str | None = None,
    # fields: list | None = None,
    # filename: str | None = None,
) -> dict[str, QgsVectorLayer]:
    """Write from WNTR network model to QGIS Layers

    Args:
        wn: the water network model, or a path (string or path object) to an input file
        results: simulation results, if any.
        crs: The coordinate Reference System of the coordinates in the wntr model / .inp file.
        units: the set of units to write the layers using.

    """

    if isinstance(wn, (str, pathlib.Path)):
        wn = wntr.network.WaterNetworkModel(str(wn))

    options = options_from_wn(wn)

    if units:
        try:
            flow_unit = FlowUnit[units.upper()]
        except KeyError as e:
            raise FlowUnitError(e) from e

        options = dataclasses.replace(options, flow_unit=flow_unit)

        options_to_wn(options, wn)

    else:
        logger.warning(
            tr("No units specified. Will use the value from wn: {units_friendly_name}").format(
                units_friendly_name=options.flow_unit.friendly_name
            )
        )
    writer = Writer(wn, results)
    map_layers: dict[str, QgsVectorLayer] = {}

    if crs:
        crs_object = QgsCoordinateReferenceSystem(crs)
        if not crs_object.isValid():
            msg = tr("CRS {crs} is not valid.").format(crs=crs)
            raise ValueError(msg)
    else:
        crs_object = QgsCoordinateReferenceSystem()

    unit_names = SpecificUnitNames.from_options(options)

    model_layers: list[ModelLayer | ResultLayer] = list(ResultLayer if results else ModelLayer)
    for model_layer in model_layers:
        layer = QgsVectorLayer(
            "Point" if model_layer.is_node else "LineString",
            model_layer.friendly_name,
            "memory",
        )
        layer.setCrs(crs_object)
        data_provider = layer.dataProvider()
        data_provider.addAttributes(writer.get_qgsfields(model_layer))
        writer.write(model_layer, data_provider)

        layer.updateFields()
        layer.updateExtents()
        gusnet.style.style(
            layer, model_layer, theme="extended" if results and options.simulation_duration else None, units=unit_names
        )
        QgsProject.instance().addMapLayer(layer)
        map_layers[model_layer.name] = layer

    return map_layers


@needs_wntr_pandas
class Writer:
    """Writes to QGIS layers (feature sinks) from a WNTR water network model, and optionally WNTR simulation results.

    Args:
        wn: The WNTR water network model that we will write from
        results: The simulation results. Default is that there are no simulation results.
        units: The units that it should be written in values include ``"LPS"``, ``"GPM"`` etc.
            Default is to use the units within the WaterNetworkModel options

    """

    _EXTENDED_PERIOD = object()

    def __init__(
        self,
        wn: wntr.network.WaterNetworkModel,
        results: wntr.sim.SimulationResults | None = None,
    ) -> None:
        options = options_from_wn(wn)

        self._converter = Converter.from_options(options)

        if options.simulation_duration:
            self._timestep = self._EXTENDED_PERIOD
        else:
            self._timestep = 0

        self._dfs: dict[_AbstractLayer, pd.DataFrame] = {}
        if results:
            self._dfs = self._get_results_dfs(wn, results)
        else:
            self._dfs = self._get_model_dfs(wn)

        self._node_geometries, self._link_geometries = self._get_geometries(wn)

        field_group = FieldGroup.BASE | _get_field_groups(options)

        self.fields = [field for field in Field if field.field_group & field_group]
        """A list of field names to be written

        * The default set of fields will depend on ``wn`` and ``results``
        * When writing only those fields related to the layer bei_ng written will be used.
        """

    def _get_geometries(
        self, wn: wntr.network.WaterNetworkModel
    ) -> tuple[dict[str, QgsGeometry], dict[str, QgsGeometry]]:
        """Get the geometries of the nodes and links in the water network model.

        Args:
            wn: The WNTR water network model.

        Returns:
            A tuple of nodes, links. Each containing a dictionary mapping link names to their geometries.
        """

        nodes = {name: QgsGeometry(QgsPoint(*node.coordinates)) for name, node in wn.nodes()}

        links = {
            name: QgsGeometry.fromPolyline(
                [
                    nodes[link.start_node.name].constGet(),
                    *[QgsPoint(*vertex) for vertex in link.vertices],
                    nodes[link.end_node.name].constGet(),
                ]
            )
            for name, link in wn.links()
        }

        return nodes, links

    def get_qgsfields(self, layer: ModelLayer | ResultLayer) -> QgsFields:
        """Get the set of QgsFields that will be written by 'write'.

        This set of fields will need to be used when creating any sink/layer
        which will be written to by write_to_sink

        Args:
            layer: 'JUNCTIONS','PIPES','LINKS' etc.

        Returns:
            QgsFields: The set of fields to be written.
        """

        layer_df = self._dfs.get(layer, pd.DataFrame())

        field_names = [field.name for field in self.fields if field in layer.wq_fields()]
        field_names.extend(layer_df.columns.to_list())
        field_names = list(dict.fromkeys(field_names))  # de-duplicate

        layer_df = layer_df.convert_dtypes()
        dtypes = layer_df.dtypes

        qgs_fields = QgsFields()  # nice constructor didn't arrive until qgis 3.40

        for f in field_names:
            is_list_field = False
            try:
                field = Field[f.upper()]
                dtype = field.type
                is_list_field = bool(field.field_group & FieldGroup.LIST_IN_EXTENDED_PERIOD)
                comment = field.description

            except KeyError:
                dtype = dtypes[f]
                comment = ""

            if is_list_field and self._timestep is self._EXTENDED_PERIOD:
                qgs_field = QgsField(
                    f.lower(),
                    self._get_qgs_field_type(list),
                    subType=self._get_qgs_field_type(float),
                    comment=comment,
                )

            else:
                qgs_field = QgsField(
                    f.lower(),
                    self._get_qgs_field_type(dtype),
                    comment=comment,
                )

            qgs_fields.append(qgs_field)

        return qgs_fields

    def write(self, layer: ModelLayer | ResultLayer, sink: QgsFeatureSink) -> None:
        """Write a fields from a layer to a QGIS feature sink

        Args:
            layer: which layer should be written to the sink: 'JUNCTIONS','PIPES','LINKS' etc.
            sink: the sink to write to
        """
        field_names = self.get_qgsfields(layer).names()

        layer_df = self._dfs.get(layer, pd.DataFrame())

        missing_cols = list(set(field_names) - set(layer_df.columns))

        if missing_cols:
            layer_df[missing_cols] = NULL

        ordered_df = layer_df[field_names]

        attribute_list = ordered_df.to_numpy().tolist()
        name_list = ordered_df.index.to_list()

        geometries = self._node_geometries if layer.is_node else self._link_geometries

        for name, attributes in zip(name_list, attribute_list):
            f = QgsFeature()
            f.setGeometry(geometries[name])
            f.setAttributes(
                [value if not (isinstance(value, (int, float)) and math.isnan(value)) else NULL for value in attributes]
            )
            sink.addFeature(f, QgsFeatureSink.FastInsert)

    def _get_model_dfs(self, wn: wntr.network.WaterNetworkModel) -> dict[_AbstractLayer, pd.DataFrame]:
        wn_dict = wn.to_dict()

        dfs: dict[_AbstractLayer, pd.DataFrame] = {}

        df_nodes = pd.DataFrame(wn_dict["nodes"])
        df_nodes = df_nodes.drop(
            columns=["coordinates", "demand_timeseries_list", "leak", "leak_area", "leak_discharge_coeff"],
            errors="ignore",
        )
        if not df_nodes.empty:
            for layer in [ModelLayer.JUNCTIONS, ModelLayer.RESERVOIRS, ModelLayer.TANKS]:
                dfs[layer] = self._process_model_df(df_nodes[df_nodes["node_type"] == layer.field_type], layer, wn)

        df_links = pd.DataFrame(wn_dict["links"])
        df_links = df_links.drop(
            columns=["start_node_name", "end_node_name", "vertices", "initial_quality"], errors="ignore"
        )
        if not df_links.empty:
            for layer in [ModelLayer.PIPES, ModelLayer.PUMPS, ModelLayer.VALVES]:
                dfs[layer] = self._process_model_df(df_links[df_links["link_type"] == layer.field_type], layer, wn)

        return dfs

    def _process_model_df(
        self, df: pd.DataFrame, layer: ModelLayer, wn: wntr.network.WaterNetworkModel
    ) -> pd.DataFrame:
        patterns = _Patterns(wn)
        curves = _Curves(wn, self._converter)

        if df.empty:
            return pd.DataFrame()

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
            # Special case for demands
            df["base_demand"] = wn.query_node_attribute("base_demand", node_type=wntr.network.model.Junction)

            # 'demand_pattern' didn't exist on node prior to wntr 1.3.0 so we have to go searching:
            df["demand_pattern"] = wn.query_node_attribute(
                "demand_timeseries_list", node_type=wntr.network.model.Junction
            ).apply(lambda dtl: patterns.get_str_or_none(dtl.pattern_list()[0]))

        elif layer is ModelLayer.RESERVOIRS:
            if "head_pattern_name" in df:
                df["head_pattern"] = df["head_pattern_name"].apply(patterns.get_str_or_none)
                df = df.drop(columns="head_pattern_name")

        elif layer is ModelLayer.TANKS:
            if "vol_curve_name" in df:
                df["vol_curve"] = df["vol_curve_name"].apply(curves.get)
                df = df.drop(columns="vol_curve_name")

            df = df.rename(columns={"diameter": "tank_diameter"})

        elif layer is ModelLayer.PUMPS:
            # not all pumps will have a pump curve (power pumps)!
            if "pump_curve_name" in df:
                df["pump_curve"] = df["pump_curve_name"].apply(curves.get)
                df = df.drop(columns="pump_curve_name")

            if "speed_pattern_name" in df:
                df["speed_pattern"] = df["speed_pattern_name"].apply(patterns.get_str_or_none)
                df = df.drop(columns="speed_pattern_name")
            # 'energy pattern' is not called energy pattern name!
            if "energy_pattern" in df:
                df["energy_pattern"] = df["energy_pattern"].apply(patterns.get_str_or_none)

            if "efficiency_curve_name" in df:
                df["efficiency_curve"] = df["efficiency_curve_name"].apply(curves.get)
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
                df.loc[general_valves, "headloss_curve"] = df.loc[general_valves, "headloss_curve_name"].apply(
                    curves.get
                )

            df = df.rename(columns={"initial_status": "valve_status"})

        for fieldname in df:
            try:
                parameter = Field[str(fieldname).upper()].type
            except KeyError:
                continue
            if not isinstance(parameter, Parameter):
                continue
            df[fieldname] = self._converter.from_si(df[fieldname], parameter)

        return df

    def _get_results_dfs(
        self, wn: wntr.network.WaterNetworkModel, results: wntr.sim.SimulationResults
    ) -> dict[_AbstractLayer, pd.DataFrame]:
        node_dfs = results.node
        link_dfs = results.link

        link_dfs["unit_headloss"], link_dfs["headloss"] = self._fix_headloss_df(link_dfs[Field.HEADLOSS.value], wn)

        node_df = self._process_results_layer(ResultLayer.NODES, node_dfs)
        link_df = self._process_results_layer(ResultLayer.LINKS, link_dfs)

        return {ResultLayer.NODES: node_df, ResultLayer.LINKS: link_df}

    def _process_results_layer(self, layer: ResultLayer, results_dfs: dict[str, pd.DataFrame]) -> pd.DataFrame:
        output_series: list[pd.Series] = []

        for field in layer.wq_fields():
            df = results_dfs.get(field.value)

            if df is None or df.empty:
                continue

            if isinstance(field.type, Parameter):
                df = self._converter.from_si(df, field.type)

            if self._timestep is not self._EXTENDED_PERIOD:
                series = df.iloc[self._timestep]
                series.name = field.value
                output_series.append(series)
            else:
                lists = df.transpose().to_numpy().tolist()
                output_series.append(pd.Series(lists, index=df.columns, name=field.value))

        combined_df = pd.concat(output_series, axis=1)
        combined_df["name"] = combined_df.index.to_series()

        return combined_df

    def _fix_headloss_df(
        self, df: pd.DataFrame, wn: wntr.network.WaterNetworkModel
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        pipe_lengths = pd.Series({name: pipe.length for name, pipe in wn.pipes()})

        df = df.astype("float64")

        unit_headloss = df[pipe_lengths.index]

        valve_total_headloss = df.drop(pipe_lengths.index, axis=1, errors="ignore")

        pipe_total_headloss = unit_headloss * pipe_lengths

        total_headloss = pd.concat([valve_total_headloss, pipe_total_headloss], axis=1)

        return unit_headloss, total_headloss

    def _get_qgs_field_type(self, dtype: Any) -> QMetaType | QVariant:
        if dtype is list:  # Must be checked before string type
            return QMetaType.Type.QVariantList if USE_QMETATYPE else QVariant.List

        if (
            isinstance(dtype, MapFieldType)
            or dtype in [SimpleFieldType.STR, SimpleFieldType.PATTERN, SimpleFieldType.CURVE]
            or pd.api.types.is_string_dtype(dtype)
        ):
            return QMetaType.Type.QString if USE_QMETATYPE else QVariant.String

        if isinstance(dtype, Parameter) or pd.api.types.is_float_dtype(dtype):
            return QMetaType.Type.Double if USE_QMETATYPE else QVariant.Double

        if dtype is SimpleFieldType.BOOL or pd.api.types.is_bool_dtype(dtype):
            return QMetaType.Type.Bool if USE_QMETATYPE else QVariant.Bool

        if pd.api.types.is_integer_dtype(dtype):
            return QMetaType.Type.Int if USE_QMETATYPE else QVariant.Int

        raise KeyError(f"Couldn't get qgs field type for {dtype}")  # noqa: EM102, TRY003 # pragma: no cover


class _Patterns:
    def __init__(self, wn: wntr.network.model.WaterNetworkModel) -> None:
        self._next_name = functools.partial(
            next, filter(lambda n: n not in wn.pattern_name_list, map(str, itertools.count(2)))
        )
        self._existing_patterns: dict[Pattern, str] = {}
        self._wn = wn

    def add(self, pattern: Pattern | Iterable[float] | str | None) -> str | None:
        """Takes a Pattern object, or a string or iterable describing the pattern.
        Adds it to the wntr wn, and returns the new pattern name.
        Returns None if the pattern is empty."""

        if not isinstance(pattern, Pattern):
            pattern = Pattern(pattern)

        if not pattern:
            return None

        if existing_pattern_name := self._existing_patterns.get(pattern):
            return existing_pattern_name

        name = self._next_name()
        self._wn.add_pattern(name=name, pattern=list(pattern))
        self._existing_patterns[pattern] = name
        return name

    def add_all(self, pattern_series: pd.Series, layer: ModelLayer, pattern_type: Field) -> pd.Series:
        try:
            return pattern_series.map(self.add, na_action="ignore")
        except ValueError as e:
            raise PatternError(e, layer, pattern_type) from None

    def get(self, pattern_name: wntr.network.Pattern | str | None) -> Pattern:
        if not pattern_name:
            return Pattern()
        elif isinstance(pattern_name, str):
            pattern = self._wn.get_pattern(pattern_name)
        else:
            pattern = pattern_name

        return Pattern(pattern.multipliers)

    def get_str_or_none(self, pattern_name: wntr.network.Pattern | str | None) -> str | None:
        return str(self.get(pattern_name)) or None

    # @staticmethod
    # def read_pattern(pattern: Any) -> tuple[float]:
    #     pattern_in = pattern
    #     if isinstance(pattern, str):
    #         pattern = pattern.strip().split()

    #     try:
    #         pattern_tuple = tuple(float(item) for item in pattern)
    #     except (ValueError, TypeError) as e:
    #         raise ValueError(pattern_in) from e

    #     # if len(pattern_tuple) == 0:
    #     #     return None

    #     return pattern_tuple


class _Curves:
    def __init__(self, wn: wntr.network.WaterNetworkModel, converter: Converter) -> None:
        self._wn = wn
        self._name_iterator = map(str, itertools.count(1))
        self._converter = converter

    class Type(enum.Enum):
        # Curve type with values (name, x parameter, y parameter)

        HEAD = "HEAD", Parameter.FLOW, Parameter.HYDRAULIC_HEAD
        EFFICIENCY = "EFFICIENCY", Parameter.FLOW, Parameter.UNITLESS  # flow vs percentage
        VOLUME = "VOLUME", Parameter.LENGTH, Parameter.VOLUME
        HEADLOSS = "HEADLOSS", Parameter.FLOW, Parameter.HYDRAULIC_HEAD

    def _add_one(self, curve_string: Any, curve_type: _Curves.Type) -> str | None:
        try:
            curve_points = self.read_curve(curve_string)
        except CurveReadError as e:
            raise CurveError(curve_string, curve_type, e) from e

        if not curve_points:
            return None

        curve_points = self._convert_points(curve_points, curve_type, self._converter.to_si)

        name = next(self._name_iterator)

        self._wn.add_curve(name=name, curve_type=curve_type.value[0], xy_tuples_list=curve_points)

        return name

    def _add_all(self, curve_series: pd.Series, curve_type: _Curves.Type) -> pd.Series | None:
        curve_map = {curve: self._add_one(curve, curve_type) for curve in curve_series.dropna().unique()}
        return curve_series.map(curve_map, na_action="ignore")

    add_head = functools.partialmethod(_add_all, curve_type=Type.HEAD)
    add_efficiency = functools.partialmethod(_add_all, curve_type=Type.EFFICIENCY)
    add_volume = functools.partialmethod(_add_all, curve_type=Type.VOLUME)
    add_headloss = functools.partialmethod(_add_all, curve_type=Type.HEADLOSS)

    def get(self, curve_name: str) -> str | None:
        curve: wntr.network.elements.Curve = self._wn.get_curve(curve_name)

        converted_points = self._convert_points(curve.points, _Curves.Type[curve.curve_type], self._converter.from_si)

        return repr(converted_points)

    def _convert_points(self, points: list, curve_type: _Curves.Type, conversion_function) -> list[tuple[float, float]]:
        converted_points: list[tuple[float, float]] = []

        for point in points:
            x = conversion_function(point[0], curve_type.value[1])
            y = conversion_function(point[1], curve_type.value[2])
            converted_points.append((x, y))

        return converted_points

    @staticmethod
    def read_curve(curve_string: Any) -> list[tuple[float, float]] | None:
        """Read a curve from a string"""
        if not isinstance(curve_string, str):
            msg = "Curve must be a string"
            raise CurveReadError(msg)

        if curve_string.strip() == "":
            return None

        try:
            curve_points_input: list = ast.literal_eval(curve_string)
        except Exception:
            msg = "Couldn't convert string to list of points"
            raise CurveReadError(msg) from None

        try:
            curve_points_length = len(curve_points_input)
        except TypeError:
            msg = "Couldn't convert string to list of points"
            raise CurveReadError(msg) from None

        if curve_points_length == 2:
            try:
                return [(float(curve_points_input[0]), float(curve_points_input[1]))]
            except (ValueError, TypeError):
                pass

        curve_points = []

        for point in curve_points_input:
            try:
                point_length = len(point)
            except TypeError:
                msg = f"Point '{point}' is not an x, y tuple"
                raise CurveReadError(msg) from None
            if point_length != 2:
                msg = f"Point '{point}' is not an x, y tuple"
                raise CurveReadError(msg)

            try:
                x = float(point[0])
            except (ValueError, TypeError):
                msg = f"In point '{point}', '{point[0]} is not a number"
                raise CurveReadError(msg) from None
            try:
                y = float(point[1])
            except (ValueError, TypeError):
                msg = f"In point '{point}', '{point[0]} is not a number"
                raise CurveReadError(msg) from None

            curve_points.append((x, y))

        if not len(curve_points):
            msg = "There are no points in the curve"
            raise CurveReadError(msg)

        return curve_points


class CurveReadError(Exception):
    pass


@needs_wntr_pandas
def from_qgis(
    layers: dict[Literal["JUNCTIONS", "RESERVOIRS", "TANKS", "PIPES", "VALVES", "PUMPS"], QgsFeatureSource],
    units: Literal["LPS", "LPM", "MLD", "CMH", "CFS", "GPM", "MGD", "IMGD", "AFD", "CMD"],
    headloss: Literal["H-W", "D-W", "C-M"] | None = None,
    wn: wntr.network.WaterNetworkModel | None = None,
    project: QgsProject | None = None,
    crs: QgsCoordinateReferenceSystem | str | None = None,
) -> wntr.network.WaterNetworkModel:
    """Read from QGIS layers or feature sources to a WNTR ``WaterNetworkModel``

    Args:
        layers: layers to read from
        units: The flow unit set that the layers being read use.
        headloss: the headloss formula to use
            (H-W for Hazen Williams, D-W for Darcy Weisbach, or C-M for Chezy-Manning).
            Must be set if there is no wn.
            If wn is provided, headloss in wn.options.hydraulic.headloss will be used instead.
        wn: The `WaterNetworkModel` that the layers will be read into. Will create a new model if `None`.
        project: QgsProject instance, if `None` the current `QgsProject.instance()` will be used.
        crs: All geometry will be transformed into this coordinate reference system.
            If not set the geometry of the first layer will be used.

    """

    if wn:
        if headloss:
            msg = tr(
                "Cannot set headloss when wn is set. Set the headloss in the wn.options.hydraulic.headloss instead"
            )
            raise ValueError(msg)

        options = options_from_wn(wn)

    else:
        wn = wntr.network.WaterNetworkModel()

        if not headloss:
            msg = tr("headloss must be set if wn is not set: possible values are: H-W, D-W, C-M")
            raise ValueError(msg)

        headloss_formula = HeadlossFormula(headloss)

        options = dataclasses.replace(DefaultOptions(), headloss_formula=headloss_formula)

    try:
        unit = FlowUnit[units.upper()]
    except KeyError as e:
        raise FlowUnitError(e) from e

    options = dataclasses.replace(options, flow_unit=unit)

    options_to_wn(options, wn)

    unit_conversion = Converter.from_options(options)

    if crs:
        crs = QgsCoordinateReferenceSystem(crs)

    reader = _FromGis(unit_conversion, project, crs=crs)

    try:
        model_layers = {}
        for layer_name, layer in layers.items():
            model_layers.update({ModelLayer(str(layer_name).upper()): layer})
    except ValueError:
        msg = tr("'{layer_name}' is not a valid layer type.").format(layer_name=layer_name)
        raise ValueError(msg) from None

    reader.add_features_to_network_model(model_layers, wn)

    return wn


def to_wntr(
    model_layers: dict[ModelLayer, QgsFeatureSource],
    options: ModelOptions,
    project: QgsProject,
    crs: QgsCoordinateReferenceSystem | None,
) -> wntr.network.WaterNetworkModel:
    wn = wntr.network.WaterNetworkModel()
    options_to_wn(options, wn)
    converter = Converter.from_options(options)
    reader = _FromGis(converter, project, crs=crs)
    reader.add_features_to_network_model(model_layers, wn)
    return wn


@needs_wntr_pandas
class _FromGis:
    """Read from QGIS feature sources / layers to a WNTR model"""

    def __init__(
        self,
        converter: Converter,
        project: QgsProject | None = None,
        crs: QgsCoordinateReferenceSystem | None = None,
        # transform_context: QgsCoordinateTransformContext | None = None,
        # ellipsoid: str | None = "EPSG:7030",
    ):
        if not project:
            project = QgsProject.instance()

        # self._transform_context = (
        #     transform_context if transform_context is not None else QgsCoordinateTransformContext()
        # )
        # self._ellipsoid = ellipsoid
        self._transform_context = project.transformContext()
        self._ellipsoid = project.ellipsoid()
        self._converter = converter
        self.crs = crs

    @property
    def crs(self) -> QgsCoordinateReferenceSystem | None:
        "The coordinate reference system source features will be transformed to"
        return self._crs

    @crs.setter
    def crs(self, crs: QgsCoordinateReferenceSystem | None):
        self._crs = crs
        if crs:
            self._measurer = QgsDistanceArea()
            self._measurer.setSourceCrs(crs, self._transform_context)
            self._measurer.setEllipsoid(self._ellipsoid)

    def add_features_to_network_model(
        self, feature_sources: dict[ModelLayer, QgsFeatureSource], wn: wntr.network.WaterNetworkModel
    ) -> None:
        """Do the conversion to WNTR

        Args:
            feature_sources: dictionary of layers/feature sources from which to take features
            wn: The model to which features should be added

        Raises:
            NetworkModelError: if the network cannot be created
        """

        self.patterns = _Patterns(wn)
        self.curves = _Curves(wn, self._converter)

        node_dfs: list[pd.DataFrame] = []
        link_dfs: list[pd.DataFrame] = []

        shapefile_name_map = {wq_field.value[:10]: wq_field.value for wq_field in Field}

        for model_layer in ModelLayer:
            source = feature_sources.get(model_layer)
            if source is None:
                continue

            if not self.crs:
                self.crs = source.sourceCrs()

            df = self._source_to_df(source)

            if df.empty:
                continue

            null_geometry = df["geometry"].map(lambda geometry: geometry.isNull()).sum()
            if null_geometry:
                raise NullGeometryError(null_geometry, model_layer)

            df = df.rename(columns=shapefile_name_map)

            self._check_for_required_fields(df, model_layer)

            df = self._fix_column_types(df)

            df = self._convert_dataframe(df)

            if model_layer is ModelLayer.JUNCTIONS:
                df = self._process_junctions(df)
            elif model_layer is ModelLayer.RESERVOIRS:
                df = self._process_reservoirs(df)
            elif model_layer is ModelLayer.TANKS:
                df = self._process_tanks(df)
            elif model_layer is ModelLayer.PUMPS:
                df = self._do_pump_patterns_curves(df)
            elif model_layer is ModelLayer.VALVES:
                df = self._do_valve_patterns_curves(df)

            if model_layer in [ModelLayer.JUNCTIONS, ModelLayer.RESERVOIRS, ModelLayer.TANKS]:
                df["node_type"] = model_layer.field_type
                node_dfs.append(df)
            else:
                df["link_type"] = model_layer.field_type
                link_dfs.append(df)

        try:
            node_df = pd.concat(node_dfs, sort=False, ignore_index=True)
        except ValueError:
            msg = tr("There are no nodes in the model")
            raise NetworkModelError(msg) from ValueError
        try:
            link_df = pd.concat(link_dfs, sort=False, ignore_index=True)
        except ValueError:
            msg = tr("There are no links in the model")
            raise NetworkModelError(msg) from ValueError

        node_df["name"] = self._fill_names(node_df)
        link_df["name"] = self._fill_names(link_df)

        self._check_for_duplicate_names(node_df["name"])
        self._check_for_duplicate_names(link_df["name"])

        link_df = self.snap_links_to_nodes(node_df, link_df)

        node_df = self._process_node_geometry(node_df)
        link_df = self._process_link_geometry(link_df)

        return self._to_wntr(wn, node_df, link_df)

    def _to_dict(self, df: pd.DataFrame) -> list[dict]:
        columns = df.columns.tolist()
        return [
            {k: v for k, v in zip(columns, m) if not (v is pd.NA or v != v or v is None)}  # noqa: PLR0124
            for m in df.itertuples(index=False, name=None)
        ]

    def _to_wntr(
        self, wn: wntr.network.WaterNetworkModel, node_df: pd.DataFrame, link_df: pd.DataFrame
    ) -> wntr.network.WaterNetworkModel:
        """Convert the node and link dataframes to a WNTR WaterNetworkModel"""
        wn_dict: dict[str, Any] = {}
        wn_dict["nodes"] = self._to_dict(node_df)
        wn_dict["links"] = self._to_dict(link_df)

        logging.getLogger("wntr.network.io").setLevel(logging.CRITICAL)
        try:
            return wntr.network.from_dict(wn_dict, wn)
        except Exception as e:
            raise WntrError(e) from e

    def _source_to_df(self, source: QgsFeatureSource):
        column_names = [name.lower() for name in source.fields().names()]
        column_names.append("geometry")

        feature_list: list[list] = []
        feature_request = QgsFeatureRequest().setDestinationCrs(self.crs, self._transform_context)
        ft: QgsFeature
        for ft in source.getFeatures(feature_request):
            attrs = [attr if attr != NULL else np.nan for attr in ft]
            geometry = ft.geometry()
            geometry.convertToSingleType()
            attrs.append(geometry)
            feature_list.append(attrs)
        return pd.DataFrame(feature_list, columns=column_names)

    def _fix_column_types(self, source_df: pd.DataFrame) -> pd.DataFrame:
        """For some file types, notably json, numbers might be imported as strings.

        Also, for boolean values that come in as number types (int or float), they must finish as nullable int.
          (wntr doesn't accept floats for bool)"""
        for column_name in source_df.columns:
            try:
                expected_type = Field[column_name.upper()].type
            except KeyError:
                continue

            try:
                if expected_type is float or isinstance(expected_type, Parameter):
                    source_df[column_name] = pd.to_numeric(source_df[column_name])
                elif expected_type is SimpleFieldType.BOOL:
                    source_df[column_name] = pd.to_numeric(source_df[column_name]).astype("Int64").astype("object")
            except (ValueError, TypeError) as e:
                msg = tr("Problem in column {column_name}: {exception}").format(column_name=column_name, exception=e)
                raise NetworkModelError(msg) from None
        return source_df

    def _convert_dataframe(self, source_df: pd.DataFrame) -> pd.DataFrame:
        for fieldname in source_df.select_dtypes(include=[np.number]):
            try:
                parameter = Field[str(fieldname).upper()].type
            except KeyError:
                continue
            if not isinstance(parameter, Parameter):
                continue
            source_df[fieldname] = self._converter.to_si(source_df[fieldname], parameter)
        return source_df

    def snap_links_to_nodes(self, node_df, link_df) -> pd.DataFrame:
        """Snap the nodes to the links and return the updated node dataframe."""

        spatial_index = SpatialIndex()

        try:
            spatial_index.add_nodes(node_df["geometry"], node_df["name"])

            snapped_links = spatial_index.snap_links(link_df["geometry"], link_df["name"])

            link_df[["geometry", "start_node_name", "end_node_name"]] = snapped_links
        except SnapError as e:
            raise NetworkModelError(e) from e

        return link_df

    def _process_node_geometry(self, df: pd.DataFrame) -> pd.DataFrame:
        def get_point_coordinates(geometry: QgsGeometry) -> tuple[float, float]:
            point = geometry.constGet()
            return point.x(), point.y()

        df["coordinates"] = df["geometry"].apply(get_point_coordinates)

        return df.drop(columns="geometry")

    def _process_link_geometry(self, link_df: pd.DataFrame) -> pd.DataFrame:
        link_df["vertices"] = link_df["geometry"].apply(
            lambda geometry: [(v.x(), v.y()) for v in geometry.asPolyline()[1:-1]]
        )

        pipes = link_df["link_type"] == ModelLayer.PIPES.field_type
        link_df.loc[pipes, "length"] = self._process_pipe_length(link_df.loc[pipes])

        return link_df.drop(columns="geometry")

    def _process_pipe_length(self, pipe_df: pd.DataFrame) -> pd.Series:
        calculated_lengths = pipe_df["geometry"].map(self._measurer.measureLength).astype("float")

        if self._measurer.lengthUnits() != QGIS_DISTANCE_UNIT_METERS:
            calculated_lengths = calculated_lengths.apply(
                self._measurer.convertLengthMeasurement, args=(QGIS_DISTANCE_UNIT_METERS,)
            )

        if calculated_lengths.isna().any():
            raise PipeMeasuringError(calculated_lengths.isna().sum())

        attribute_lengths = pipe_df.get("length")

        if attribute_lengths is None:
            return calculated_lengths

        else:
            mismatch = self._get_mismatches(calculated_lengths, attribute_lengths)

            if mismatch.any():
                self.mismatch_warning(pipe_df["name"], calculated_lengths, attribute_lengths)

            return attribute_lengths.fillna(calculated_lengths)

    def _get_mismatches(self, calculated_lengths: pd.Series, attribute_lengths: pd.Series) -> pd.Series:
        """Get a boolean series indicating which rows have a mismatch between calculated and attribute lengths."""

        return attribute_lengths.notna() & ~np.isclose(
            calculated_lengths,
            attribute_lengths,
            rtol=0.05,
            atol=10,
        )

    def mismatch_warning(self, names: pd.Series, calculated_lengths: pd.Series, attribute_lengths: pd.Series):
        mismatch = self._get_mismatches(calculated_lengths, attribute_lengths)
        examples = pd.concat(
            [names, calculated_lengths, attribute_lengths],
            axis=1,
            ignore_index=True,
        )
        examples.columns = pd.Index(["name", "attribute_length", "calculated_length"])
        examples = examples.loc[mismatch]
        examples = examples.head(5)
        number_of_mismatches = mismatch.sum()
        msg = tr(
            "%n pipe(s) have very different attribute length vs measured length. First five are: ",
            "",
            number_of_mismatches,
        )
        msg += ", ".join(
            examples.apply(
                tr("{name} ({attribute_length:.0f} metres vs {calculated_length:.0f} metres)").format_map, axis=1
            )
        )
        logger.warning(msg)

    def _fill_names(self, df: pd.DataFrame) -> pd.Series:
        if "name" in df.columns:
            name_series = df["name"].astype("string").str.strip()
        else:
            name_series = pd.Series(index=df.index, dtype="string")

        existing_names = set(name_series.dropna())
        mask = (name_series.isna()) | (name_series == "")
        number_of_names_required = mask.sum()

        if number_of_names_required:
            name_iterator = map(str, itertools.count(1))
            valid_name_iterator = filter(lambda name: name not in existing_names, name_iterator)
            new_names = np.array(list(itertools.islice(valid_name_iterator, number_of_names_required)))

            name_series[mask] = new_names

        return name_series

    def _process_junctions(self, df: pd.DataFrame) -> pd.DataFrame:
        if "demand_pattern" in df:
            df["demand_pattern_name"] = self.patterns.add_all(
                df.get("demand_pattern"), ModelLayer.JUNCTIONS, Field.DEMAND_PATTERN
            )
        else:
            df["demand_pattern_name"] = None

        if "base_demand" in df.columns:
            has_demand = df["base_demand"].notna()

            def make_demand_list(row):
                return [
                    {
                        "base_val": row["base_demand"],
                        "pattern_name": (row["demand_pattern_name"] if pd.notna(row["demand_pattern_name"]) else None),
                    }
                ]

            df.loc[has_demand, "demand_timeseries_list"] = df.loc[has_demand].apply(make_demand_list, axis=1)

        return df.drop(columns=["base_demand", "demand_pattern", "demand_pattern_name"], errors="ignore")

    def _process_tanks(self, df: pd.DataFrame) -> pd.DataFrame:
        if "vol_curve" in df:
            df["vol_curve_name"] = self.curves.add_volume(df["vol_curve"])

            df = df.drop(columns=["vol_curve"])

        if "tank_diameter" in df:
            df["diameter"] = df["tank_diameter"]
            df = df.drop(columns=["tank_diameter"])

        return df

    def _process_reservoirs(self, df: pd.DataFrame) -> pd.DataFrame:
        if "head_pattern" in df:
            df["head_pattern_name"] = self.patterns.add_all(
                df.get("head_pattern"), ModelLayer.RESERVOIRS, Field.HEAD_PATTERN
            )

            df = df.drop(columns=["head_pattern"])

        return df

    def _do_valve_patterns_curves(self, df: pd.DataFrame) -> pd.DataFrame:
        try:
            df[Field.VALVE_TYPE.value] = df[Field.VALVE_TYPE.value].str.upper()
        except (KeyError, AttributeError):
            raise ValveTypeError from None

        if not df[Field.VALVE_TYPE.value].isin(ValveType._member_names_).all():
            raise ValveTypeError from None

        for valve_type in [ValveType.PRV, ValveType.PSV, ValveType.PBV, ValveType.FCV, ValveType.TCV]:
            valve_mask = df[Field.VALVE_TYPE.value] == valve_type.name

            if not valve_mask.any():
                continue

            if valve_type.setting_field.value not in df:
                raise ValveSettingError(valve_type)

            if df.loc[valve_mask, valve_type.setting_field.value].hasnans:
                raise ValveSettingError(valve_type)

            df.loc[valve_mask, "initial_setting"] = df.loc[valve_mask, valve_type.setting_field.value]

        gpvs = df[Field.VALVE_TYPE.value] == ValveType.GPV.name

        if gpvs.any():
            if "headloss_curve" not in df:
                raise ValveSettingError(ValveType.GPV)

            df.loc[gpvs, "headloss_curve_name"] = self.curves.add_headloss(df.loc[gpvs, "headloss_curve"])

            if df.loc[gpvs, "headloss_curve_name"].hasnans:
                raise ValveSettingError(ValveType.GPV)

        df = df.rename(columns={"valve_status": "initial_status"})

        return df.drop(
            columns=["headloss_curve", "pump_curve", "speed_pattern"],
            errors="ignore",
        )

    def _do_pump_patterns_curves(self, df: pd.DataFrame) -> pd.DataFrame:
        try:
            df[Field.PUMP_TYPE.value] = df[Field.PUMP_TYPE.value].str.upper()
        except (KeyError, AttributeError):
            raise PumpTypeError from None

        if not df[Field.PUMP_TYPE.value].isin(PumpTypes._member_names_).all():
            raise PumpTypeError

        power_pumps = df[Field.PUMP_TYPE.value] == PumpTypes.POWER.name
        head_pumps = df[Field.PUMP_TYPE.value] == PumpTypes.HEAD.name

        if power_pumps.any():
            if Field.POWER.value not in df:
                raise PumpPowerError
            if df.loc[power_pumps, Field.POWER.value].hasnans:
                raise PumpPowerError
            if (df.loc[power_pumps, Field.POWER.value] <= 0).any():
                raise PumpPowerError

        if head_pumps.any():
            if Field.PUMP_CURVE.value not in df:
                raise PumpCurveMissingError

            df["pump_curve_name"] = self.curves.add_head(df[Field.PUMP_CURVE.value])

            if df.loc[head_pumps, "pump_curve_name"].hasnans:
                raise PumpCurveMissingError

        if "speed_pattern" in df:
            df["speed_pattern_name"] = self.patterns.add_all(
                df.get("speed_pattern"), ModelLayer.PUMPS, Field.SPEED_PATTERN
            )

        if "energy_pattern" in df:
            df["energy_pattern"] = self.patterns.add_all(
                df.get("energy_pattern"), ModelLayer.PUMPS, Field.ENERGY_PATTERN
            )

        if "efficiency_curve" in df:
            df["efficiency_curve_name"] = self.curves.add_efficiency(df["efficiency_curve"])

        return df.drop(
            columns=["headloss_curve", "pump_curve", "speed_pattern", "efficiency_curve"],
            errors="ignore",
        )

    def _check_for_required_fields(self, df: pd.DataFrame, layer: ModelLayer) -> None:
        """Check if all required fields for the layer are present in the dataframe.

        Args:
            df: DataFrame to check.
            layer: ModelLayer to check against.

        Raises:
            RequiredFieldError: If any required field is missing.
        """

        for field in layer.wq_fields():
            if not field.field_group & FieldGroup.REQUIRED:
                continue
            if field.value not in df:
                raise RequiredFieldError(layer, field)
            if df[field.value].hasnans:
                raise RequiredFieldError(layer, field)

    def _check_for_duplicate_names(self, name_series: pd.Series) -> None:
        """Check for duplicate 'name' entries in the dataframe.

        Args:
            name_series: Series to check for duplicates.

        Raises:
            NetworkModelError: If duplicates are found.
        """

        duplicates = name_series.duplicated()

        if not duplicates.any():
            return

        msg = tr("Duplicate names found: ") + ", ".join(name_series[duplicates].unique())
        raise NetworkModelError(msg)


@needs_wntr_pandas
def check_network(wn: wntr.network.WaterNetworkModel) -> None:
    """Checks for simple errors in the network that will otherwise not get good error messages from wntr/epanet

    This is a utility function. WNTR will already error on any of these problems, but the messages WNTR gives
    are not always so clear.

    Args:
        wn: WaterNetworkModel to check

    Raises:
        NetworkModelError: if any checks fail

    Example:
        >>> wn = wntr.network.WaterNetworkModel()
        >>> wn.add_junction("j1")
        >>> wn.add_junction("j2")
        >>> wn.add_pipe("p1", "j1", "j2")
        >>> check_network(wn)
        Traceback (most recent call last):
        ...
        gusnet.interface.NetworkModelError: At least one tank or reservoir is required

        >>> wn = wntr.network.WaterNetworkModel()
        >>> wn.add_junction("j1")
        >>> wn.add_junction("j2")
        >>> wn.add_tank("t1")
        >>> wn.add_pipe("p1", "j1", "j2")
        >>> check_network(wn)
        Traceback (most recent call last):
        ...
        gusnet.interface.NetworkModelError: the following nodes are not connected to any links: t1


    """
    if not wn.num_links and not wn.num_nodes:
        msg = tr("The model is empty, no nodes or links found.")
        raise NetworkModelError(msg)

    if not wn.num_junctions:
        msg = tr("At least one junction is necessary")
        raise NetworkModelError(msg)

    if not wn.num_tanks and not wn.num_reservoirs:
        msg = tr("At least one tank or reservoir is required")
        raise NetworkModelError(msg)

    if not wn.num_links:
        msg = tr("At least one link (pipe, pump or valve) is necessary")
        raise NetworkModelError(msg)

    orphan_nodes = wn.nodes.unused()
    if len(orphan_nodes):
        msg = tr("the following nodes are not connected to any links: {orphan_node_list}").format(
            orphan_node_list=", ".join(orphan_nodes)
        )
        raise NetworkModelError(msg)


def describe_network(wn: wntr.network.WaterNetworkModel) -> tuple[str, str]:
    """Returns an html and text string describing the network model.

    Args:
        wn: WaterNetworkModel to describe

    Returns:
        A tuple with a html and text string description.
    """
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


@needs_wntr_pandas
def describe_pipes(wn: wntr.network.WaterNetworkModel) -> tuple[str, str]:
    options = options_from_wn(wn)
    converter = Converter.from_options(options)
    unit_names = SpecificUnitNames.from_options(options)

    pipe_df = pd.DataFrame(
        ((pipe.length, pipe.diameter, pipe.roughness) for _, pipe in wn.pipes()),
        columns=["length", "diameter", "roughness"],
    )
    pipe_df["length"] = converter.from_si(pipe_df["length"], Parameter.LENGTH)
    pipe_df["diameter"] = converter.from_si(pipe_df["diameter"], Parameter.PIPE_DIAMETER)
    pipe_df["roughness"] = converter.from_si(pipe_df["roughness"], Parameter.ROUGHNESS_COEFFICIENT)

    formatted_df = pd.concat(
        [
            pipe_df.groupby("diameter").agg({"length": ["count", "sum", "min", "max"], "roughness": ["min", "max"]}),
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


@needs_wntr_pandas
def _get_field_groups(options: ModelOptions) -> FieldGroup:
    """Utility function for guessing what types of analysis a specific wn will undertake,
    and therefore which field types should be included."""

    field_groups = FieldGroup(0)

    if options.quality_parameter is not QualityParameter.NONE:
        field_groups = field_groups | FieldGroup.WATER_QUALITY_ANALYSIS

    if options.energy_report:
        field_groups = field_groups | FieldGroup.ENERGY

    if options.demand_type is DemandType.PRESSURE_DEPENDENT:
        field_groups = field_groups | FieldGroup.PRESSURE_DEPENDENT_DEMAND

    return field_groups


@needs_wntr_pandas
def options_from_wn(wn: wntr.network.WaterNetworkModel) -> ModelOptions:
    o: wntr.network.Options = wn.options

    patterns = _Patterns(wn)

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
        energy_pattern=patterns.get(o.energy.global_pattern),
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


@needs_wntr_pandas
def options_to_wn(options: ModelOptions, wn: wntr.network.WaterNetworkModel) -> None:
    o: wntr.network.Options = wn.options

    patterns = _Patterns(wn)

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
    o.energy.global_pattern = patterns.add(options.energy_pattern)
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


class NetworkModelError(Exception):
    # def __init__(self, exception):
    #     super().__init__(f"error preparing model; {exception}")
    pass


class PatternError(NetworkModelError, ValueError):
    def __init__(self, pattern_string, layer: ModelLayer, pattern_type: Field):
        super().__init__(
            tr(
                "in {layer} problem reading {pattern_type}: {pattern_string} Patterns should be a string of numeric values separated by a space, or a list of numeric values."  # noqa: E501
            ).format(layer=layer.friendly_name, pattern_type=pattern_type.friendly_name, pattern_string=pattern_string)
        )


class CurveError(NetworkModelError, ValueError):
    def __init__(self, curve_string, curve_type: _Curves.Type, curve_error: CurveReadError):
        curve_name = ""
        if curve_type is _Curves.Type.HEAD:
            curve_name = tr("pump head")
        elif curve_type is _Curves.Type.EFFICIENCY:
            curve_name = tr("pump efficiency")
        elif curve_type is _Curves.Type.HEADLOSS:
            curve_name = tr("general purpose valve headloss")
        elif curve_type is _Curves.Type.VOLUME:
            curve_name = tr("tank volume")

        super().__init__(
            tr(
                'problem reading {curve_name} curve "{curve_string}". {error_detail} Curves should be of the form: (1, 2), (3.6, 4.7)'  # noqa: E501
            ).format(curve_name=curve_name, curve_string=curve_string, error_detail=curve_error.args[0])
        )


class WntrError(NetworkModelError):
    def __init__(self, exception):
        super().__init__(
            tr("error from WNTR. {exception_name}: {exception}").format(
                exception_name=type(exception).__name__, exception=exception
            )
        )


class FlowUnitError(NetworkModelError, ValueError):
    def __init__(self, exception):
        super().__init__(
            tr("{exception} is not a known set of units. Possible units are: ").format(exception=exception)
            + ", ".join(FlowUnit._member_names_)
        )


class GenericRequiredFieldError(NetworkModelError):
    pass


class ValveError(NetworkModelError):
    pass


class ValveTypeError(ValveError, GenericRequiredFieldError):
    def __init__(self):
        super().__init__(
            tr(
                "Valve type ({valve_type}) must be set for all valves and must be one of the following values: {possible_values}"  # noqa: E501
            ).format(valve_type=Field.VALVE_TYPE.name.lower(), possible_values=", ".join(ValveType._member_names_))
        )


class ValveSettingError(ValveError, GenericRequiredFieldError):
    def __init__(self, valve_type: ValveType):
        super().__init__(
            tr("{initial_setting_name} ({initial_setting}) must be set for all {valve_name}").format(
                initial_setting_name=valve_type.setting_field.friendly_name,
                initial_setting=valve_type.setting_field.name.lower(),
                valve_name=valve_type.friendly_name,
            )
        )


class RequiredFieldError(GenericRequiredFieldError):
    """Raised when a required parameter is missing from the model."""

    def __init__(self, layer: ModelLayer, field: Field):
        super().__init__(
            tr("In {layer_type}, all elements must have {field_name} '{field_id}'").format(
                layer_type=layer.friendly_name, field_name=field.friendly_name, field_id=field.name.lower()
            )
        )


class PumpError(NetworkModelError):
    pass


class PumpTypeError(PumpError, GenericRequiredFieldError):
    def __init__(self):
        super().__init__(
            tr(
                "Pump type ({pump_type}) must be set for all pumps and must be one of the following values: {possible_values}"  # noqa: E501
            ).format(pump_type=Field.PUMP_TYPE.name.lower(), possible_values=", ".join(PumpTypes._member_names_))
        )


class PumpCurveMissingError(PumpError, GenericRequiredFieldError):
    def __init__(self):
        super().__init__(
            tr("{pump_curve_name} ({pump_curve}) must be set for all pumps of type HEAD").format(
                pump_curve_name=Field.PUMP_CURVE.friendly_name, pump_curve=Field.PUMP_CURVE.name.lower()
            )
        )


class PumpPowerError(PumpError, GenericRequiredFieldError):
    def __init__(self):
        super().__init__(
            tr("{pump_power_name} ({pump_power}) must be set for all pumps of type POWER").format(
                pump_power_name=Field.POWER.friendly_name, pump_power=Field.POWER.name.lower()
            )
        )


class NullGeometryError(NetworkModelError):
    def __init__(self, null_geometry_count: int, layer: ModelLayer) -> None:
        super().__init__(
            tr(
                "There are %n feature(s) in {layer_name} with no geometry. Please check the geometry of your features.",
                "",
                null_geometry_count,
            ).format(layer_name=layer.friendly_name)
        )


class PipeMeasuringError(NetworkModelError):
    def __init__(self, number_of_problems: int):
        super().__init__(
            tr(
                "cannot calculate length of %n pipe(s) (probably due to a problem with the selected coordinate reference system)",  # noqa: E501
                "",
                number_of_problems,
            )
        )
