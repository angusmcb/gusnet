from __future__ import annotations

import itertools
import logging
import math
from collections.abc import Mapping
from types import MappingProxyType
from typing import TYPE_CHECKING

from qgis.core import (
    NULL,
    Qgis,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransformContext,
    QgsDistanceArea,
    QgsFeature,
    QgsFeatureRequest,
    QgsFeatureSource,
    QgsGeometry,
    QgsUnitTypes,
    QgsWkbTypes,
)

from gusnet.elements import CurveType, Field, FlowUnit, ModelLayer, Parameter, SimpleFieldType
from gusnet.i18n import tr
from gusnet.network import Network
from gusnet.pattern_curve import Curve, Pattern
from gusnet.profiler import profile

if TYPE_CHECKING:  # pragma: no cover
    import pandas as pd


logger = logging.getLogger(__name__)

try:
    QGIS_METERS = Qgis.DistanceUnit.Meters
    QGIS_FEET = Qgis.DistanceUnit.Feet
except AttributeError:
    QGIS_METERS = QgsUnitTypes.DistanceMeters  # type: ignore[attr-defined]
    QGIS_FEET = QgsUnitTypes.DistanceFeet  # type: ignore[attr-defined]

SHAPEFILE_NAME_MAP = MappingProxyType({field[:10]: field for field in Field})


def read(
    feature_sources: Mapping[ModelLayer, QgsFeatureSource],
    crs: QgsCoordinateReferenceSystem | None,
    transform_context: QgsCoordinateTransformContext,
    ellipsoid: str,
    flow_unit: FlowUnit,
) -> tuple[Mapping[ModelLayer, Mapping[str, list]], Network]:
    node_attributes: dict[ModelLayer, dict] = {}
    link_attributes: dict[ModelLayer, dict] = {}
    node_geometries: dict[ModelLayer, list[QgsGeometry]] = {}
    link_geometries: dict[ModelLayer, list[QgsGeometry]] = {}

    with profile(tr("Getting features from QGIS")):
        for model_layer in ModelLayer:
            source = feature_sources.get(model_layer)
            if not source:
                continue

            attribute_dict, geometry_list = _source_to_df(source, crs, transform_context)
            if not attribute_dict:
                continue

            source_geom_type = QgsWkbTypes.geometryType(source.wkbType())
            if model_layer.is_node and source_geom_type != Qgis.GeometryType.Point:
                msg = tr("{layer} expects a point layer. Received: {received_type}").format(
                    layer=model_layer.friendly_name, received_type=QgsWkbTypes.geometryDisplayString(source_geom_type)
                )
                raise ReadFeatureError(msg)  #
            if not model_layer.is_node and source_geom_type != Qgis.GeometryType.Line:
                msg = tr("{layer} expects a line layer. Received: {received_type}").format(
                    layer=model_layer.friendly_name, received_type=QgsWkbTypes.geometryDisplayString(source_geom_type)
                )
                raise ReadFeatureError(msg)

            if model_layer.is_node:
                node_attributes[model_layer] = attribute_dict
                node_geometries[model_layer] = geometry_list
            else:
                link_attributes[model_layer] = attribute_dict
                link_geometries[model_layer] = geometry_list

    with profile(tr("Fixing names")):
        node_attributes = _do_names(node_attributes)
        link_attributes = _do_names(link_attributes)

    with profile(tr("Handling geometries")):
        net = Network()
        for layer, geometries in node_geometries.items():
            net.add_node_geometries(node_attributes[layer][Field.NAME], geometries)
        for layer, geometries in link_geometries.items():
            net.add_link_geometries(link_attributes[layer][Field.NAME], geometries)

    if ModelLayer.PIPES in link_attributes:
        if crs and crs.isValid():
            with profile(tr("Measuring Pipes")):
                link_attributes[ModelLayer.PIPES][Field.LENGTH] = _process_pipe_length(
                    link_attributes[ModelLayer.PIPES],
                    net.link_geometries,
                    crs,
                    transform_context,
                    ellipsoid,
                    flow_unit,
                )
        else:
            logger.warning(tr("Cannot calculate pipe lengths without a valid coordinate reference system."))

    convert_patterns_curves(node_attributes)
    convert_patterns_curves(link_attributes)

    attribute_mapping = MappingProxyType(
        {k: MappingProxyType(v) for k, v in (node_attributes | link_attributes).items()}
    )

    return attribute_mapping, net


def _source_to_df(
    source: QgsFeatureSource, crs: QgsCoordinateReferenceSystem | None, transform_context: QgsCoordinateTransformContext
) -> tuple[dict[str, list], list[QgsGeometry]]:
    column_names = [name.lower() for name in source.fields().names()]
    column_names = [SHAPEFILE_NAME_MAP.get(name, name) for name in column_names]

    feature_list: list[list] = []
    geometry_list: list[QgsGeometry] = []

    feature_request = QgsFeatureRequest()
    if crs and crs.isValid():
        feature_request.setDestinationCrs(crs, transform_context)

    ft: QgsFeature
    for ft in source.getFeatures(feature_request):  # type: ignore[union-attr]
        attrs = [attr if attr != NULL else None for attr in ft]  # is not faster than !=
        feature_list.append(attrs)
        geometry_list.append(ft.geometry())

    attribute_dict = {col: list(vals) for col, vals in zip(column_names, zip(*feature_list))}

    if QgsWkbTypes.isMultiType(source.wkbType()):
        for geom in geometry_list:
            geom.convertToSingleType()

    if geometry_list and not attribute_dict:
        attribute_dict = {Field.NAME: [None] * len(geometry_list)}

    return attribute_dict, geometry_list


def _fix_column_types(df: pd.DataFrame) -> pd.DataFrame:
    """For some file types, notably json, numbers might be imported as strings.

    Also, for boolean values that come in as number types (int or float), they must finish as nullable int.
        (wntr doesn't accept floats for bool)"""

    import pandas as pd

    for column_name, dtype in zip(df.columns, df.dtypes):
        try:
            field = Field(column_name)
        except ValueError:
            continue

        expected_type = field.type

        try:
            if isinstance(expected_type, Parameter) and not pd.api.types.is_numeric_dtype(dtype):
                df[column_name] = pd.to_numeric(df[column_name])

            elif expected_type is SimpleFieldType.BOOL and not pd.api.types.is_bool_dtype(dtype):
                df[column_name] = pd.to_numeric(df[column_name]).map(bool, na_action="ignore")

        except (ValueError, TypeError):
            continue

    return df


def _do_geometries(model_dicts: dict[ModelLayer, dict]) -> None:
    """Check and transform geometries.

    Check that all geometries are valid and convert node geometries to coordinate tuples and
    link geometries to vertex lists. Geometry must already be single part for links.

    Raises GeometryError if any problems are found."""
    errors: list[tuple[ModelLayer, list[str]]] = []

    for layer, layer_dict in model_dicts.items():
        if layer.is_node:
            node_result = [_point_geometry_to_tuple(geom) for geom in layer_dict["geometry"]]
            layer_dict["coordinates"] = node_result
            # Check for invalid geometries (contains NaN)
            problem_indices = [i for i, coord in enumerate(node_result) if coord is None or math.isnan(coord[0])]
        else:
            link_result = [_line_geometry_to_vertices(geom) for geom in layer_dict["geometry"]]
            layer_dict["vertices"] = link_result
            # Check for invalid geometries (None)
            problem_indices = [i for i, vert in enumerate(link_result) if vert is None]

        if problem_indices:
            problem_names = [layer_dict["name"][i] for i in problem_indices]
            errors.append((layer, problem_names))

    if errors:
        raise GeometryError(errors)


def _point_geometry_to_tuple(geometry: QgsGeometry) -> list[float] | None:
    try:
        point = geometry.asPoint()
        return [point.x(), point.y()]
    except (TypeError, ValueError):
        return [math.nan, math.nan]


def _line_geometry_to_vertices(geometry: QgsGeometry) -> list[tuple[float, float]] | None:
    try:
        return [(v.x(), v.y()) for v in geometry.asPolyline()[1:-1]]
    except (TypeError, ValueError):
        return None


def _process_pipe_length(
    pipe_dict: dict,
    link_geometries: Mapping[str, QgsGeometry],
    crs: QgsCoordinateReferenceSystem,
    transform_context: QgsCoordinateTransformContext,
    ellipsoid: str,
    flow_unit: FlowUnit,
) -> list:
    measurer = QgsDistanceArea()
    measurer.setSourceCrs(crs, transform_context)
    measurer.setEllipsoid(ellipsoid)

    calculated_lengths = [measurer.measureLength(link_geometries[name]) for name in pipe_dict[Field.NAME]]

    qgis_length_unit = QGIS_FEET if flow_unit.is_traditional else QGIS_METERS

    if measurer.lengthUnits() != qgis_length_unit:
        calculated_lengths = [
            measurer.convertLengthMeasurement(length, qgis_length_unit) for length in calculated_lengths
        ]

    calculated_lengths_no_nan = [length if not math.isnan(length) else None for length in calculated_lengths]

    if None in calculated_lengths_no_nan:
        logger.warning(tr("The length of one or more pipes could not be calculated."))

    attribute_lengths = pipe_dict.get(Field.LENGTH)

    if attribute_lengths is None or all(i is None for i in attribute_lengths):
        return calculated_lengths_no_nan

    _mismatch_warning(pipe_dict[Field.NAME], calculated_lengths_no_nan, attribute_lengths, flow_unit)

    return [
        att_length if att_length is not None else calc_length
        for att_length, calc_length in zip(attribute_lengths, calculated_lengths)
    ]


def _mismatch_warning(names: list, calculated_lengths: list, attribute_lengths: list, flow_unit: FlowUnit) -> None:
    if any(math.isnan(calculated_length) for calculated_length in calculated_lengths):
        return

    try:
        attribute_lengths = [float(length) if length is not None else None for length in attribute_lengths]
    except (TypeError, ValueError):
        return

    mismatch = [
        (name, att, calc)
        for name, att, calc in zip(names, attribute_lengths, calculated_lengths)
        if att is not None and not math.isclose(att, calc, rel_tol=0.05, abs_tol=10)
    ]

    if not mismatch:
        return

    unit_string = tr("feet") if flow_unit.is_traditional else tr("metres")

    mismatch_string_list = [
        f"{name} ({attribute_length:.0f} {unit_string} vs {calculated_length:.0f} {unit_string})"
        for name, attribute_length, calculated_length in mismatch[:5]
    ]

    mismatch_string = ", ".join(mismatch_string_list) + ("..." if len(mismatch) > 5 else "")

    msg = tr(
        "%n pipe(s) have very different attribute length vs measured length. This is pipe(s): {mismatches}",
        "",
        len(mismatch),
    ).format(mismatches=mismatch_string)

    logger.warning(msg)


# def _snap_links_to_nodes(
#     node_dicts: dict[ModelLayer, dict], link_dicts: dict[ModelLayer, dict]
# ) -> dict[ModelLayer, dict]:
#     """Snap the nodes to the links and return the updated node dataframe."""

#     spatial_index = SpatialIndex()

#     for node_dict in node_dicts.values():
#         spatial_index.add_nodes(node_dict["coordinates"], node_dict["name"])

#     for link_dict in link_dicts.values():
#         geometry, start_node, end_node = spatial_index.snap_links(link_dict["geometry"])

#         link_dict["geometry"] = geometry
#         link_dict["start_node_name"] = start_node
#         link_dict["end_node_name"] = end_node

#     return link_dicts


def _do_names(model_dicts: dict[ModelLayer, dict]) -> dict[ModelLayer, dict]:
    """Fill blank names, not duplicting between nodes/links"""

    existing_names: set[str] = set()
    names = {}
    for layer, layer_dict in model_dicts.items():
        if "name" in layer_dict:
            names[layer] = ["" if name is None else str(name).strip() for name in layer_dict["name"]]

            existing_names.update(names[layer])
        else:
            names[layer] = [""] * len(next(iter(layer_dict.values())))

    name_generator = map(str, itertools.count(1))
    valid_name_generator = filter(lambda name: name not in existing_names, name_generator)

    for layer, name_list in names.items():
        if "" in name_list:
            name_list = [name if name != "" else next(valid_name_generator) for name in name_list]

        model_dicts[layer]["name"] = name_list

    return model_dicts


def convert_patterns_curves(elements: dict[ModelLayer, dict]) -> None:
    for layer_dict in elements.values():
        for fieldname in layer_dict:
            try:
                parameter = Field(fieldname).type
            except ValueError:
                continue
            if parameter == SimpleFieldType.PATTERN:
                pattern_values = []
                for value in layer_dict[fieldname]:
                    if value is not None:
                        try:
                            pattern = Pattern(value)
                        except ValueError:
                            pattern = value
                        pattern_values.append(pattern if pattern != "" else None)
                    else:
                        pattern_values.append(None)
                layer_dict[fieldname] = pattern_values

            elif isinstance(parameter, CurveType):
                curve_values = []
                for value in layer_dict[fieldname]:
                    if value is not None:
                        try:
                            curve = Curve.factory(value)
                        except ValueError:
                            curve = value
                        curve_values.append(curve if curve != "" else None)
                    else:
                        curve_values.append(None)
                layer_dict[fieldname] = curve_values


class ReadFeatureError(Exception):
    pass


class PipeMeasuringError(ReadFeatureError):
    def __init__(self, number_of_problems: int):
        super().__init__(
            tr(
                "cannot calculate length of %n pipe(s) (probably due to a problem with the selected coordinate reference system)",  # noqa: E501
                "",
                number_of_problems,
            )
        )


class GeometryError(ReadFeatureError):
    def __init__(self, errors: list[tuple[ModelLayer, list[str]]]) -> None:
        messages = [tr("Geometry errors were found.")]
        for layer, names in errors:
            msg = tr(
                "In {layer} {number} features have invalid geometries: {names}",
            ).format(
                layer=layer.friendly_name,
                number=len(names),
                names=", ".join(names[0:10]) + ("" if len(names) <= 10 else ", ..."),
            )
            messages.append(msg)
        super().__init__("\n".join(messages))
