import functools
import math

import numpy as np
import pandas as pd
import pytest
from qgis.core import (
    NULL,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransformContext,
    QgsFeature,
    QgsGeometry,
    QgsVectorLayer,
)

from gusnet.elements import FlowUnit, ModelLayer
from gusnet.feature_reader import (
    GeometryError,
    _do_geometries,
    _do_names,
    _process_pipe_length,
    _source_to_df,
)

wkt = functools.partial(QgsGeometry.fromWkt)


def test_process_pipe_length_calculated_no_attribute():
    # When no `length` attribute is present, function should return a numeric series
    crs = QgsCoordinateReferenceSystem("EPSG:4326")
    transform_context = QgsCoordinateTransformContext()

    pipe_df = pd.DataFrame({"geometry": [wkt("LINESTRING (0 0, 1 0)"), wkt("LINESTRING (0 0, 0 1)")]})

    res = _process_pipe_length(pipe_df, crs, transform_context, "WGS84", FlowUnit.LPS)

    assert len(res) == 2
    assert res.dtype == float or pd.api.types.is_float_dtype(res)
    assert res.notna().all()


def test_process_pipe_length_uses_attribute_and_fillna():
    # When `length` attribute partially present, values should use attribute where present
    crs = QgsCoordinateReferenceSystem("EPSG:4326")
    transform_context = QgsCoordinateTransformContext()

    geom0 = wkt("LINESTRING (0 0, 1 0)")
    geom1 = wkt("LINESTRING (0 0, 0 1)")

    pipe_df = pd.DataFrame({"name": ["p1", "p2"], "geometry": [geom0, geom1], "length": [50.0, float("nan")]})

    res = _process_pipe_length(pipe_df, crs, transform_context, "WGS84", FlowUnit.GPM)

    # first value uses attribute (50.0)
    assert pytest.approx(res.iloc[0]) == 50.0
    # second value should be numeric and not NaN (filled from calculated length)
    assert res.iloc[1] == res.iloc[1]


def test_process_pipe_length_utm_crs_exact():
    # UTM projected CRS uses metres — a line 100 units long should measure 100 metres
    crs = QgsCoordinateReferenceSystem("EPSG:32633")
    transform_context = QgsCoordinateTransformContext()

    pipe_df = pd.DataFrame({"geometry": [wkt("LINESTRING (0 0, 100 0)")]})

    res_metres = _process_pipe_length(pipe_df, crs, transform_context, "WGS84", FlowUnit.LPS)

    assert pytest.approx(res_metres.iloc[0], rel=1e-2) == 100.0

    res_feet = _process_pipe_length(pipe_df, crs, transform_context, "WGS84", FlowUnit.GPM)

    assert pytest.approx(res_feet.iloc[0], rel=1e-2) == 328  # 100 metres in feet


def test_process_pipe_length_feet_crs_exact():
    # Projected CRS using feet as linear units — a line 100 units long should measure 100 feet
    crs = QgsCoordinateReferenceSystem("EPSG:2272")
    transform_context = QgsCoordinateTransformContext()

    pipe_df = pd.DataFrame({"geometry": [wkt("LINESTRING (0 0, 100 0)")]})

    res_metres = _process_pipe_length(pipe_df, crs, transform_context, "WGS84", FlowUnit.LPS)

    assert pytest.approx(30.48, rel=1e-2) == res_metres.iloc[0]  # 100 feet in metres

    res_feet = _process_pipe_length(pipe_df, crs, transform_context, "WGS84", FlowUnit.GPM)

    assert pytest.approx(100, rel=1e-2) == res_feet.iloc[0]


@pytest.mark.parametrize(
    ("input_val", "expected_output"),
    [
        ([pd.NA], ["1"]),
        ([np.nan], ["1"]),
        ([None], ["1"]),
        ([""], ["1"]),
        (["   "], ["1"]),
        ([pd.NA, pd.NA, pd.NA], ["1", "2", "3"]),
        ([np.nan, np.nan, np.nan], ["1", "2", "3"]),
        ([None, None, None], ["1", "2", "3"]),
        (["", "", ""], ["1", "2", "3"]),
        (["  ", "  ", "  "], ["1", "2", "3"]),
        (["a", pd.NA, "b", "", "   "], ["a", "1", "b", "2", "3"]),
        (["1", "2", pd.NA, "3", ""], ["1", "2", "4", "3", "5"]),
        (["1", "2", "3", "4"], ["1", "2", "3", "4"]),
        (["a", 1, None, 2.0, ""], ["a", "1", "2", "2.0", "3"]),
        ([4, 3, 2, 1], ["4", "3", "2", "1"]),
        ([True, False], ["True", "False"]),
        (["a ", "", " b", "a b"], ["a", "1", "b", "a b"]),
        ([pd.NA] * 100000, [str(i) for i in range(1, 100001)]),
        (["name_with_underscores", None, " another name "], ["name_with_underscores", "1", "another name"]),
        (["dup", "dup", "dup"], ["dup", "dup", "dup"]),
    ],
)
def test_fill_names_all_ok(input_val, expected_output):
    df = pd.DataFrame({"name": input_val})

    names = _do_names({"any": df})

    assert names["any"]["name"].to_list() == expected_output


def test_source_to_df_basic_and_geometry_handling():
    # create a memory point layer with two fields: name (string) and value (double)
    uri = "Point?field=name:string(20)&field=value:double"
    layer = QgsVectorLayer(uri, "test_points", "memory")
    provider = layer.dataProvider()

    feat = QgsFeature()
    feat.setGeometry(QgsGeometry.fromWkt("POINT (1 2)"))
    feat.setAttributes(["A", 1])
    provider.addFeatures([feat])

    crs = QgsCoordinateReferenceSystem()
    transform_context = QgsCoordinateTransformContext()

    df = _source_to_df(layer, crs, transform_context)

    assert list(df.columns) == ["name", "value", "geometry"]
    assert df.loc[0, "name"] == "A"
    assert df.loc[0, "value"] == 1
    assert isinstance(df.loc[0, "geometry"], QgsGeometry)


def test_source_to_df_null_and_multipart_converted():
    # kept for backwards compatibility; replaced by two focused tests
    pass


def test_source_to_df_multipart_converted():
    uri = "Point?field=name:string(20)&field=value:string(20)"
    layer = QgsVectorLayer(uri, "test_points_multi", "memory")
    provider = layer.dataProvider()

    feat = QgsFeature()
    feat.setGeometry(wkt("MULTIPOINT ((1 2), (3 4))"))
    feat.setAttributes(["n1", "x"])
    provider.addFeatures([feat])

    crs = QgsCoordinateReferenceSystem()
    transform_context = QgsCoordinateTransformContext()

    df = _source_to_df(layer, crs, transform_context)

    geom_out = df.loc[0, "geometry"]
    assert isinstance(geom_out, QgsGeometry)
    assert not geom_out.isMultipart()


def test_source_to_df_null_converted():
    # include a third (double) field and a second feature without NULLs
    uri = "Point?field=name:string(20)&field=value:string(20)&field=measure:double"
    layer = QgsVectorLayer(uri, "test_points_null", "memory")
    provider = layer.dataProvider()

    # feature with NULLs in name and measure
    feat1 = QgsFeature()
    feat1.setGeometry(QgsGeometry.fromWkt("POINT (1 2)"))
    feat1.setAttributes([NULL, "x", NULL])

    # feature without NULLs
    feat2 = QgsFeature()
    feat2.setGeometry(QgsGeometry.fromWkt("POINT (2 3)"))
    feat2.setAttributes(["n2", "y", 3.14])

    provider.addFeatures([feat1, feat2])

    crs = QgsCoordinateReferenceSystem()
    transform_context = QgsCoordinateTransformContext()

    df = _source_to_df(layer, crs, transform_context)

    # first row: name and measure should be NaN
    assert math.isnan(df.loc[0, "name"])  # was NULL -> np.nan
    assert df.loc[0, "value"] == "x"
    assert math.isnan(df.loc[0, "measure"])  # double NULL -> np.nan

    # second row: values preserved
    assert df.loc[1, "name"] == "n2"
    assert df.loc[1, "value"] == "y"
    assert df.loc[1, "measure"] == 3.14


def test_shapefile_name_map_remaps_truncated_names():
    truncated = "emitter_co"
    full_name = "emitter_coefficient"

    uri = f"Point?field={truncated}:string(40)"
    layer = QgsVectorLayer(uri, "test_trunc", "memory")
    provider = layer.dataProvider()

    feat = QgsFeature()
    feat.setGeometry(QgsGeometry.fromWkt("POINT (0 0)"))
    feat.setAttributes([42])
    provider.addFeatures([feat])

    crs = QgsCoordinateReferenceSystem()
    transform_context = QgsCoordinateTransformContext()

    df = _source_to_df(layer, crs, transform_context)

    assert full_name in df.columns
    assert str(df.loc[0, full_name]) == "42"


def test_do_geometries_node_and_link_conversion():
    node_df = pd.DataFrame({"name": ["n1"], "geometry": [QgsGeometry.fromWkt("POINT (1 2)")]})
    link_df = pd.DataFrame({"name": ["l1"], "geometry": [QgsGeometry.fromWkt("LINESTRING (0 0, 1 1, 2 2, 3 3)")]})
    dfs = {ModelLayer.JUNCTIONS: node_df, ModelLayer.PIPES: link_df}

    _do_geometries(dfs)

    assert node_df.loc[0, "coordinates"] == (1.0, 2.0)
    assert link_df.loc[0, "vertices"] == [(1.0, 1.0), (2.0, 2.0)]


@pytest.mark.parametrize("bad_geometry", [QgsGeometry(), QgsGeometry.fromWkt("LINESTRING (0 0, 1 1)")])
def test_do_geometries_raises_geometry_error_on_invalid(bad_geometry):
    # various invalid geometry objects should cause a GeometryError listing the feature name
    bad_df = pd.DataFrame({"name": ["bad_node"], "geometry": [bad_geometry]})

    dfs = {ModelLayer.JUNCTIONS: bad_df}

    with pytest.raises(GeometryError, match="bad_node"):
        _do_geometries(dfs)


@pytest.mark.parametrize("bad_geometry", [QgsGeometry(), QgsGeometry.fromWkt("POINT (0 0)")])
def test_do_geometries_raises_on_bad_link_geometry(bad_geometry):
    bad_df = pd.DataFrame({"name": ["bad_link"], "geometry": [bad_geometry]})

    dfs = {ModelLayer.PIPES: bad_df}

    with pytest.raises(GeometryError, match="bad_link"):
        _do_geometries(dfs)
