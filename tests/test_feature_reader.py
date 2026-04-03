import functools
import math
from unittest.mock import patch

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
    _mismatch_warning,
    _process_pipe_length,
    _source_to_df,
)

wkt = functools.partial(QgsGeometry.fromWkt)


def test_process_pipe_length_calculated_no_attribute():
    # When no `length` attribute is present, function should return a list of floats
    crs = QgsCoordinateReferenceSystem("EPSG:4326")
    transform_context = QgsCoordinateTransformContext()

    pipe_dict = {"name": ["l1", "l2"]}
    geom_dict = {"l1": wkt("LINESTRING (0 0, 1 0)"), "l2": wkt("LINESTRING (0 0, 0 1)")}
    res = _process_pipe_length(pipe_dict, geom_dict, crs, transform_context, "WGS84", FlowUnit.LPS)

    assert len(res) == 2
    assert all(isinstance(x, float) for x in res)
    assert all(x is not None for x in res)


def test_process_pipe_length_uses_attribute_and_fillna():
    # When `length` attribute partially present, values should use attribute where present
    crs = QgsCoordinateReferenceSystem("EPSG:4326")
    transform_context = QgsCoordinateTransformContext()

    geom0 = wkt("LINESTRING (0 0, 1 0)")
    geom1 = wkt("LINESTRING (0 0, 0 1)")

    pipe_dict = {"name": ["p1", "p2"], "length": [50.0, None]}
    geom_dict = {"p1": geom0, "p2": geom1}
    res = _process_pipe_length(pipe_dict, geom_dict, crs, transform_context, "WGS84", FlowUnit.GPM)

    # first value uses attribute (50.0)
    assert pytest.approx(res[0]) == 50.0
    # second value should be numeric and not None (filled from calculated length)
    assert res[1] is not None
    assert isinstance(res[1], float)


def test_process_pipe_length_utm_crs_exact():
    # UTM projected CRS uses metres — a line 100 units long should measure 100 metres
    crs = QgsCoordinateReferenceSystem("EPSG:32633")
    transform_context = QgsCoordinateTransformContext()

    pipe_dict = {"name": ["p1"]}
    geom_dict = {"p1": wkt("LINESTRING (0 0, 100 0)")}

    res_metres = _process_pipe_length(pipe_dict, geom_dict, crs, transform_context, "WGS84", FlowUnit.LPS)

    assert pytest.approx(res_metres[0], rel=1e-2) == 100.0

    res_feet = _process_pipe_length(pipe_dict, geom_dict, crs, transform_context, "WGS84", FlowUnit.GPM)

    assert pytest.approx(res_feet[0], rel=1e-2) == 328  # 100 metres in feet


def test_process_pipe_length_feet_crs_exact():
    # Projected CRS using feet as linear units — a line 100 units long should measure 100 feet
    crs = QgsCoordinateReferenceSystem("EPSG:2272")
    transform_context = QgsCoordinateTransformContext()

    pipe_dict = {"name": ["p1"]}
    geom_dict = {"p1": wkt("LINESTRING (0 0, 100 0)")}

    res_metres = _process_pipe_length(pipe_dict, geom_dict, crs, transform_context, "WGS84", FlowUnit.LPS)

    assert pytest.approx(30.48, rel=1e-2) == res_metres[0]  # 100 feet in metres

    res_feet = _process_pipe_length(pipe_dict, geom_dict, crs, transform_context, "WGS84", FlowUnit.GPM)

    assert pytest.approx(100, rel=1e-2) == res_feet[0]


@pytest.mark.parametrize(
    ("input_val", "expected_output"),
    [
        # ([pd.NA], ["1"]),
        # ([np.nan], ["1"]),
        ([None], ["1"]),
        ([""], ["1"]),
        (["   "], ["1"]),
        # ([pd.NA, pd.NA, pd.NA], ["1", "2", "3"]),
        # ([np.nan, np.nan, np.nan], ["1", "2", "3"]),
        ([None, None, None], ["1", "2", "3"]),
        (["", "", ""], ["1", "2", "3"]),
        (["  ", "  ", "  "], ["1", "2", "3"]),
        # (["a", pd.NA, "b", "", "   "], ["a", "1", "b", "2", "3"]),
        # (["1", "2", pd.NA, "3", ""], ["1", "2", "4", "3", "5"]),
        (["1", "2", "3", "4"], ["1", "2", "3", "4"]),
        (["a", 1, None, 2.0, ""], ["a", "1", "2", "2.0", "3"]),
        ([4, 3, 2, 1], ["4", "3", "2", "1"]),
        ([True, False], ["True", "False"]),
        (["a ", "", " b", "a b"], ["a", "1", "b", "a b"]),
        ([None] * 1000, [str(i) for i in range(1, 1001)]),
        (["name_with_underscores", None, " another name "], ["name_with_underscores", "1", "another name"]),
        (["dup", "dup", "dup"], ["dup", "dup", "dup"]),
    ],
)
def test_fill_names_all_ok(input_val, expected_output):
    names = _do_names({"any": {"name": input_val}})

    assert names["any"]["name"] == expected_output


def test_fill_names_with_no_name_field():
    layers = {ModelLayer.JUNCTIONS: {"elevation": [10, 20, 30]}, ModelLayer.TANKS: {"capacity": [1000, 2000]}}

    layers_with_names = _do_names(layers)

    assert layers_with_names[ModelLayer.JUNCTIONS]["name"] == ["1", "2", "3"]
    assert layers_with_names[ModelLayer.TANKS]["name"] == ["4", "5"]


@pytest.mark.needs_pandas
def test_source_to_df_basic_handling():
    import pandas as pd

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

    data_dict, _ = _source_to_df(layer, crs, transform_context)
    df = pd.DataFrame(data_dict)

    assert list(df.columns) == ["name", "value"]
    assert df.loc[0, "name"] == "A"
    assert df.loc[0, "value"] == 1


def test_source_to_df_null_and_multipart_converted():
    # kept for backwards compatibility; replaced by two focused tests
    pass


def test_source_to_df_multipart_converted():
    uri = "MultiPoint?field=name:string(20)&field=value:string(20)"
    layer = QgsVectorLayer(uri, "test_points_multi", "memory")
    provider = layer.dataProvider()

    feat = QgsFeature()
    feat.setGeometry(wkt("MULTIPOINT ((1 2), (3 4))"))
    feat.setAttributes(["n1", "x"])
    provider.addFeatures([feat])

    crs = QgsCoordinateReferenceSystem()
    transform_context = QgsCoordinateTransformContext()

    _, geom_out = _source_to_df(layer, crs, transform_context)

    assert isinstance(geom_out[0], QgsGeometry)
    assert not geom_out[0].isMultipart()


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

    data_dict, _ = _source_to_df(layer, crs, transform_context)

    # first row: name and measure should be None
    assert data_dict["name"][0] is None  # was NULL -> None
    assert data_dict["value"][0] == "x"
    assert data_dict["measure"][0] is None  # double NULL -> None

    # second row: values preserved
    assert data_dict["name"][1] == "n2"
    assert data_dict["value"][1] == "y"
    assert data_dict["measure"][1] == 3.14


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

    data_dict, _ = _source_to_df(layer, crs, transform_context)

    assert full_name in data_dict
    assert str(data_dict[full_name][0]) == "42"


def test_do_geometries_node_and_link_conversion():
    node_dict = {"name": ["n1"], "geometry": [QgsGeometry.fromWkt("POINT (1 2)")]}
    link_dict = {"name": ["l1"], "geometry": [QgsGeometry.fromWkt("LINESTRING (0 0, 1 1, 2 2, 3 3)")]}
    dicts = {ModelLayer.JUNCTIONS: node_dict, ModelLayer.PIPES: link_dict}

    _do_geometries(dicts)

    assert node_dict["coordinates"][0] == [1.0, 2.0]
    assert link_dict["vertices"][0] == [(1.0, 1.0), (2.0, 2.0)]


@pytest.mark.parametrize("bad_geometry", [QgsGeometry(), QgsGeometry.fromWkt("LINESTRING (0 0, 1 1)")])
def test_do_geometries_raises_geometry_error_on_invalid(bad_geometry):
    # various invalid geometry objects should cause a GeometryError listing the feature name
    bad_dict = {"name": ["bad_node"], "geometry": [bad_geometry]}

    dicts = {ModelLayer.JUNCTIONS: bad_dict}

    with pytest.raises(GeometryError, match="bad_node"):
        _do_geometries(dicts)


@pytest.mark.parametrize("bad_geometry", [QgsGeometry(), QgsGeometry.fromWkt("POINT (0 0)")])
def test_do_geometries_raises_on_bad_link_geometry(bad_geometry):
    bad_dict = {"name": ["bad_link"], "geometry": [bad_geometry]}

    dicts = {ModelLayer.PIPES: bad_dict}

    with pytest.raises(GeometryError, match="bad_link"):
        _do_geometries(dicts)


def test_mismatch_warning_no_warning_when_lengths_match():
    """When calculated and attribute lengths are close, no warning should be issued"""
    names = ["pipe1", "pipe2", "pipe3"]
    calculated_lengths = [100.0, 200.0, 300.0]
    attribute_lengths = [101.0, 199.0, 302.0]  # Within tolerance (5% or 10 units)

    with patch("gusnet.feature_reader.logger.warning") as mock_warning:
        _mismatch_warning(names, calculated_lengths, attribute_lengths, FlowUnit.LPS)
        mock_warning.assert_not_called()


def test_mismatch_warning_issued_when_lengths_differ():
    """When calculated and attribute lengths differ significantly, warning should be issued"""
    names = ["pipe1", "pipe2", "pipe3"]
    calculated_lengths = [100.0, 200.0, 300.0]
    attribute_lengths = [50.0, 400.0, 300.0]  # pipe1 and pipe2 differ significantly

    with patch("gusnet.feature_reader.logger.warning") as mock_warning:
        _mismatch_warning(names, calculated_lengths, attribute_lengths, FlowUnit.LPS)
        mock_warning.assert_called_once()

        # Check the warning message contains info about 2 pipes
        call_args = mock_warning.call_args[0][0]
        assert "2 pipes" in call_args
        assert "pipe1" in call_args
        assert "pipe2" in call_args


def test_mismatch_warning_uses_correct_units_metric():
    """Warning should display metres for metric units"""
    names = ["pipe1"]
    calculated_lengths = [100.0]
    attribute_lengths = [50.0]

    with patch("gusnet.feature_reader.logger.warning") as mock_warning:
        _mismatch_warning(names, calculated_lengths, attribute_lengths, FlowUnit.LPS)
        mock_warning.assert_called_once()

        call_args = mock_warning.call_args[0][0]
        # Should contain "metres" or translated equivalent
        assert "50" in call_args  # attribute length
        assert "100" in call_args  # calculated length


def test_mismatch_warning_uses_correct_units_imperial():
    """Warning should display feet for imperial units"""
    names = ["pipe1"]
    calculated_lengths = [100.0]
    attribute_lengths = [50.0]

    with patch("gusnet.feature_reader.logger.warning") as mock_warning:
        _mismatch_warning(names, calculated_lengths, attribute_lengths, FlowUnit.GPM)
        mock_warning.assert_called_once()

        call_args = mock_warning.call_args[0][0]
        # Should contain "feet" or translated equivalent
        assert "50" in call_args
        assert "100" in call_args


def test_mismatch_warning_handles_none_values():
    """None values in attribute_lengths should be skipped"""
    names = ["pipe1", "pipe2", "pipe3"]
    calculated_lengths = [100.0, 200.0, 300.0]
    attribute_lengths = [None, 50.0, None]  # Only pipe2 has attribute, and it differs

    with patch("gusnet.feature_reader.logger.warning") as mock_warning:
        _mismatch_warning(names, calculated_lengths, attribute_lengths, FlowUnit.LPS)
        mock_warning.assert_called_once()

        call_args = mock_warning.call_args[0][0]
        assert "A pipe"
        assert "pipe2" in call_args
        assert "pipe1" not in call_args
        assert "pipe3" not in call_args


def test_mismatch_warning_no_warning_when_all_none():
    """No warning when all attribute_lengths are None"""
    names = ["pipe1", "pipe2"]
    calculated_lengths = [100.0, 200.0]
    attribute_lengths = [None, None]

    with patch("gusnet.feature_reader.logger.warning") as mock_warning:
        _mismatch_warning(names, calculated_lengths, attribute_lengths, FlowUnit.LPS)
        mock_warning.assert_not_called()


def test_mismatch_warning_no_warning_when_calculated_has_nan():
    """No warning when calculated_lengths contains NaN (invalid geometry)"""

    names = ["pipe1", "pipe2"]
    calculated_lengths = [100.0, math.nan]
    attribute_lengths = [50.0, 200.0]  # Would normally trigger warning

    with patch("gusnet.feature_reader.logger.warning") as mock_warning:
        _mismatch_warning(names, calculated_lengths, attribute_lengths, FlowUnit.LPS)
        mock_warning.assert_not_called()


def test_mismatch_warning_limits_to_five_examples():
    """Warning should only show first 5 mismatches and add ellipsis"""
    names = [f"pipe{i}" for i in range(10)]
    calculated_lengths = [100.0] * 10
    attribute_lengths = [50.0] * 10  # All differ significantly

    with patch("gusnet.feature_reader.logger.warning") as mock_warning:
        _mismatch_warning(names, calculated_lengths, attribute_lengths, FlowUnit.LPS)
        mock_warning.assert_called_once()

        call_args = mock_warning.call_args[0][0]
        assert "10 pipes" in call_args
        # Should show pipes 0-4
        for i in range(5):
            assert f"pipe{i}" in call_args
        # Should not show pipe5-9 individually
        assert "pipe5" not in call_args
        # Should have ellipsis
        assert "..." in call_args


def test_mismatch_warning_exact_five_no_ellipsis():
    """With exactly 5 mismatches, no ellipsis should be added"""
    names = [f"pipe{i}" for i in range(5)]
    calculated_lengths = [100.0] * 5
    attribute_lengths = [50.0] * 5

    with patch("gusnet.feature_reader.logger.warning") as mock_warning:
        _mismatch_warning(names, calculated_lengths, attribute_lengths, FlowUnit.LPS)
        mock_warning.assert_called_once()

        call_args = mock_warning.call_args[0][0]
        # All 5 should be shown
        for i in range(5):
            assert f"pipe{i}" in call_args
        # No ellipsis for exactly 5
        assert not call_args.rstrip().endswith("...")


def test_mismatch_warning_within_absolute_tolerance():
    """Lengths within 10 units should not trigger warning"""
    names = ["pipe1", "pipe2"]
    calculated_lengths = [100.0, 200.0]
    attribute_lengths = [105.0, 195.0]  # Within 10 units

    with patch("gusnet.feature_reader.logger.warning") as mock_warning:
        _mismatch_warning(names, calculated_lengths, attribute_lengths, FlowUnit.LPS)
        mock_warning.assert_not_called()


def test_mismatch_warning_within_relative_tolerance():
    """Lengths within 5% should not trigger warning"""
    names = ["pipe1"]
    calculated_lengths = [1000.0]
    attribute_lengths = [1040.0]  # 4% difference, within 5% tolerance

    with patch("gusnet.feature_reader.logger.warning") as mock_warning:
        _mismatch_warning(names, calculated_lengths, attribute_lengths, FlowUnit.LPS)
        mock_warning.assert_not_called()


def test_mismatch_warning_outside_both_tolerances():
    """Lengths outside both tolerances should trigger warning"""
    names = ["pipe1"]
    calculated_lengths = [1000.0]
    attribute_lengths = [1200.0]  # 20% difference and >10 units

    with patch("gusnet.feature_reader.logger.warning") as mock_warning:
        _mismatch_warning(names, calculated_lengths, attribute_lengths, FlowUnit.LPS)
        mock_warning.assert_called_once()


def test_mismatch_warning_handles_string_attribute_lengths():
    """String values in attribute_lengths should be converted to float"""
    names = ["pipe1", "pipe2"]
    calculated_lengths = [100.0, 200.0]
    attribute_lengths = ["50.0", "400.0"]  # Strings that can be converted

    with patch("gusnet.feature_reader.logger.warning") as mock_warning:
        _mismatch_warning(names, calculated_lengths, attribute_lengths, FlowUnit.LPS)
        mock_warning.assert_called_once()

        call_args = mock_warning.call_args[0][0]
        assert "pipe1" in call_args
        assert "pipe2" in call_args


def test_mismatch_warning_handles_invalid_string_gracefully():
    """Invalid strings in attribute_lengths should cause early return"""
    names = ["pipe1"]
    calculated_lengths = [100.0]
    attribute_lengths = ["invalid"]

    with patch("gusnet.feature_reader.logger.warning") as mock_warning:
        _mismatch_warning(names, calculated_lengths, attribute_lengths, FlowUnit.LPS)
        mock_warning.assert_not_called()
