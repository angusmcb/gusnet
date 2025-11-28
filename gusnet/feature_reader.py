from __future__ import annotations

import itertools
import logging
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
)

from gusnet.elements import Field, FlowUnit, ModelLayer, Parameter, SimpleFieldType
from gusnet.i18n import tr
from gusnet.spatial_index import SnapError, SpatialIndex

if TYPE_CHECKING:  # pragma: no cover
    import pandas as pd


logger = logging.getLogger(__name__)

QGIS_USE_DISTANCE_UNIT = Qgis.versionInt() >= 33000
QGIS_METERS = Qgis.DistanceUnit.Meters if QGIS_USE_DISTANCE_UNIT else QgsUnitTypes.DistanceMeters
QGIS_FEET = Qgis.DistanceUnit.Feet if QGIS_USE_DISTANCE_UNIT else QgsUnitTypes.DistanceFeet

SHAPEFILE_NAME_MAP = {field[:10]: field for field in Field}


def read(
    feature_sources: dict[ModelLayer, QgsFeatureSource],
    crs: QgsCoordinateReferenceSystem | None,
    transform_context: QgsCoordinateTransformContext,
    ellipsoid: str,
    flow_unit: FlowUnit,
) -> dict[ModelLayer, pd.DataFrame]:
    node_dfs: dict[ModelLayer, pd.DataFrame] = {}
    link_dfs: dict[ModelLayer, pd.DataFrame] = {}

    for model_layer in ModelLayer:
        source = feature_sources.get(model_layer)
        if source is None:
            continue

        df = _source_to_df(source, crs, transform_context)

        if df.empty:
            continue

        df = _fix_column_types(df)

        if model_layer.is_node:
            node_dfs[model_layer] = df
        else:
            link_dfs[model_layer] = df

    node_dfs = _do_names(node_dfs)
    link_dfs = _do_names(link_dfs)

    _do_geometries(node_dfs | link_dfs)

    if node_dfs and link_dfs:
        link_dfs = _snap_links_to_nodes(node_dfs, link_dfs)

    if ModelLayer.PIPES in link_dfs:
        link_dfs[ModelLayer.PIPES]["length"] = _process_pipe_length(
            link_dfs[ModelLayer.PIPES], crs, transform_context, ellipsoid, flow_unit
        )

    return node_dfs | link_dfs


def _source_to_df(
    source: QgsFeatureSource, crs: QgsCoordinateReferenceSystem, transform_context: QgsCoordinateTransformContext
) -> pd.DataFrame:
    import numpy as np
    import pandas as pd

    column_names = [name.lower() for name in source.fields().names()]
    column_names = [SHAPEFILE_NAME_MAP.get(name, name) for name in column_names]
    column_names.append("geometry")

    feature_list: list[list] = []
    feature_request = QgsFeatureRequest().setDestinationCrs(crs, transform_context)
    ft: QgsFeature
    for ft in source.getFeatures(feature_request):
        attrs = [attr if attr is not NULL else np.nan for attr in ft]  # is not faster than !=
        geometry = ft.geometry()
        if geometry.isMultipart():
            geometry.convertToSingleType()
        attrs.append(geometry)
        feature_list.append(attrs)

    return pd.DataFrame(feature_list, columns=column_names)


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


def _do_geometries(dfs: dict[ModelLayer, pd.DataFrame]) -> pd.DataFrame:
    """Check and transform geometries.

    Check that all geometries are valid and convert node geometries to coordinate tuples and
    link geometries to vertex lists. Geometry must already be single part for links.

    Raises GeometryError if any problems are found."""
    errors: list[tuple[ModelLayer, list[str]]] = []

    for layer, df in dfs.items():
        if layer.is_node:
            result = df["geometry"].map(_point_geometry_to_tuple)
            df["coordinates"] = result
        else:
            result = df["geometry"].map(_line_geometry_to_vertices)
            df["vertices"] = result

        problems = result.isna()
        if problems.any():
            errors.append((layer, df["name"][problems].tolist()))

    if errors:
        raise GeometryError(errors)


def _point_geometry_to_tuple(geometry: QgsGeometry) -> tuple[float, float] | None:
    try:
        point = geometry.asPoint()
        return point.x(), point.y()
    except (TypeError, ValueError):
        return None


def _line_geometry_to_vertices(geometry: QgsGeometry) -> list[tuple[float, float]] | None:
    try:
        return [(v.x(), v.y()) for v in geometry.asPolyline()[1:-1]]
    except (TypeError, ValueError):
        return None


def _process_pipe_length(
    pipe_df: pd.DataFrame,
    crs: QgsCoordinateReferenceSystem,
    transform_context: QgsCoordinateTransformContext,
    ellipsoid: str,
    flow_unit: FlowUnit,
) -> pd.Series:
    measurer = QgsDistanceArea()
    measurer.setSourceCrs(crs, transform_context)
    measurer.setEllipsoid(ellipsoid)

    calculated_lengths = pipe_df["geometry"].map(measurer.measureLength).astype("float")

    qgis_length_unit = QGIS_FEET if flow_unit.is_traditional else QGIS_METERS

    if measurer.lengthUnits() != qgis_length_unit:
        calculated_lengths = calculated_lengths.apply(measurer.convertLengthMeasurement, args=(qgis_length_unit,))

    if calculated_lengths.isna().any():
        raise PipeMeasuringError(calculated_lengths.isna().sum())

    attribute_lengths = pipe_df.get("length")

    if attribute_lengths is None:
        return calculated_lengths

    else:
        mismatch = _get_mismatches(calculated_lengths, attribute_lengths)

        if mismatch.any():
            _mismatch_warning(pipe_df["name"], calculated_lengths, attribute_lengths, flow_unit)

        return attribute_lengths.fillna(calculated_lengths)


def _get_mismatches(calculated_lengths: pd.Series, attribute_lengths: pd.Series) -> pd.Series:
    """Get a boolean series indicating which rows have a mismatch between calculated and attribute lengths."""
    import numpy as np

    return attribute_lengths.notna() & ~np.isclose(
        calculated_lengths,
        attribute_lengths,
        rtol=0.05,
        atol=10,
    )


def _mismatch_warning(
    names: pd.Series, calculated_lengths: pd.Series, attribute_lengths: pd.Series, flow_unit: FlowUnit
) -> None:
    import pandas as pd

    unit_string = "feet" if flow_unit.is_traditional else "metres"

    mismatch = _get_mismatches(calculated_lengths, attribute_lengths)
    examples = pd.concat(
        [names, calculated_lengths, attribute_lengths],
        axis=1,
        ignore_index=True,
    )
    examples.columns = pd.Index(["name", "attribute_length", "calculated_length"])
    examples = examples.loc[mismatch].head(5)
    msg = tr(
        "%n pipe(s) have very different attribute length vs measured length. First five are: ",
        "",
        mismatch.sum(),
    )
    msg += ", ".join(
        examples.apply(
            tr(
                f"{{name}} ({{attribute_length:.0f}} {unit_string} vs {{calculated_length:.0f}} {unit_string})"
            ).format_map,
            axis=1,
        )
    )
    logger.warning(msg)


def _snap_links_to_nodes(
    node_dfs: dict[ModelLayer, pd.DataFrame], link_dfs: dict[ModelLayer, pd.DataFrame]
) -> dict[ModelLayer, pd.DataFrame]:
    """Snap the nodes to the links and return the updated node dataframe."""

    spatial_index = SpatialIndex()

    for node_df in node_dfs.values():
        spatial_index.add_nodes(node_df["geometry"], node_df["name"])

    output_link_df = {}

    for layer, link_df in link_dfs.items():
        try:
            snapped_links = spatial_index.snap_links(link_df["geometry"], link_df["name"])
        except SnapError as e:
            raise ReadFeatureError(e) from e

        link_df[["geometry", "start_node_name", "end_node_name"]] = snapped_links
        output_link_df[layer] = link_df

    return output_link_df


def _do_names(dfs: dict[ModelLayer, pd.DataFrame]) -> dict[ModelLayer, pd.DataFrame]:
    import numpy as np
    import pandas as pd

    existing_names = set()
    names = {}
    for layer, df in dfs.items():
        if "name" in df.columns:
            names[layer] = df["name"].astype("string").str.strip().replace("", None)
            existing_names.update(names[layer].dropna())
        else:
            names[layer] = pd.Series(index=df.index, dtype="string")

    name_generator = map(str, itertools.count(1))
    valid_name_generator = filter(lambda name: name not in existing_names, name_generator)

    for layer, name_series in names.items():
        mask = name_series.isna()

        if mask.any():
            new_names = np.array(list(itertools.islice(valid_name_generator, mask.sum())))
            name_series[mask] = new_names

        dfs[layer]["name"] = name_series

    return dfs


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
