"""Tests for feature_writer module."""

import math
from unittest.mock import Mock

import pytest
from qgis.core import NULL, Qgis, QgsField, QgsFields, QgsGeometry, QgsPointXY, QgsVectorLayer
from qgis.PyQt.QtCore import QMetaType, QVariant

from gusnet.elements import CurveType, Field, FieldGroup, MapFieldType, Parameter, SimpleFieldType
from gusnet.feature_writer import (
    BOOL_TYPE,
    DOUBLE_TYPE,
    INT_TYPE,
    LIST_TYPE,
    STRING_TYPE,
    USE_QMETATYPE,
    _qgs_field_type_from_field,
    _qgs_field_type_from_pandas,
    get_qgs_fields,
    write,
)


class TestConstants:
    """Test the constants and version-dependent type handling."""

    def test_use_qmetatype_constant(self):
        """Test that USE_QMETATYPE is correctly determined based on QGIS version."""
        expected = Qgis.versionInt() >= 33800
        assert expected == USE_QMETATYPE

    def test_type_constants_with_qmetatype(self, monkeypatch):
        """Test type constants when USE_QMETATYPE is True."""
        monkeypatch.setattr("gusnet.feature_writer.USE_QMETATYPE", True)
        # Import the module again to test the constants
        import importlib

        from gusnet import feature_writer

        importlib.reload(feature_writer)

        assert QMetaType.Type.QVariantList == feature_writer.LIST_TYPE
        assert QMetaType.Type.Double == feature_writer.DOUBLE_TYPE
        assert QMetaType.Type.Int == feature_writer.INT_TYPE
        assert QMetaType.Type.QString == feature_writer.STRING_TYPE
        assert QMetaType.Type.Bool == feature_writer.BOOL_TYPE

    def test_type_constants_without_qmetatype(self, monkeypatch):
        """Test type constants when USE_QMETATYPE is False."""
        monkeypatch.setattr("gusnet.feature_writer.USE_QMETATYPE", False)
        # Import the module again to test the constants
        import importlib

        from gusnet import feature_writer

        importlib.reload(feature_writer)

        assert QVariant.List == feature_writer.LIST_TYPE
        assert QVariant.Double == feature_writer.DOUBLE_TYPE
        assert QVariant.Int == feature_writer.INT_TYPE
        assert QVariant.String == feature_writer.STRING_TYPE
        assert QVariant.Bool == feature_writer.BOOL_TYPE


@pytest.mark.needs_pandas
class TestQgsFieldTypeFromPandas:
    """Test the _qgs_field_type_from_pandas function."""

    def test_string_dtype(self):
        """Test string dtype conversion."""
        import pandas as pd

        dtype = pd.StringDtype()
        result = _qgs_field_type_from_pandas(dtype)
        assert result == STRING_TYPE

    def test_object_dtype_with_strings(self):
        """Test object dtype that contains strings."""
        import pandas as pd

        series = pd.Series(["a", "b", "c"])
        result = _qgs_field_type_from_pandas(series.dtype)
        assert result == STRING_TYPE

    def test_float_dtype(self):
        """Test float dtype conversion."""
        import pandas as pd

        dtype = pd.Float64Dtype()
        result = _qgs_field_type_from_pandas(dtype)
        assert result == DOUBLE_TYPE

    def test_numpy_float_dtype(self):
        """Test numpy float dtype conversion."""
        import pandas as pd

        series = pd.Series([1.0, 2.0, 3.0])
        result = _qgs_field_type_from_pandas(series.dtype)
        assert result == DOUBLE_TYPE

    def test_bool_dtype(self):
        """Test bool dtype conversion."""
        import pandas as pd

        dtype = pd.BooleanDtype()
        result = _qgs_field_type_from_pandas(dtype)
        assert result == BOOL_TYPE

    def test_numpy_bool_dtype(self):
        """Test numpy bool dtype conversion."""
        import pandas as pd

        series = pd.Series([True, False, True])
        result = _qgs_field_type_from_pandas(series.dtype)
        assert result == BOOL_TYPE

    def test_int_dtype(self):
        """Test int dtype conversion."""
        import pandas as pd

        dtype = pd.Int64Dtype()
        result = _qgs_field_type_from_pandas(dtype)
        assert result == INT_TYPE

    def test_numpy_int_dtype(self):
        """Test numpy int dtype conversion."""
        import pandas as pd

        series = pd.Series([1, 2, 3])
        result = _qgs_field_type_from_pandas(series.dtype)
        assert result == INT_TYPE

    def test_unsupported_dtype(self):
        """Test that unsupported dtypes raise KeyError."""
        # Create a complex dtype that should not be supported
        import pandas as pd

        series = pd.Series([1 + 2j, 3 + 4j])
        with pytest.raises(KeyError, match="Couldn't get qgs field type for"):
            _qgs_field_type_from_pandas(series.dtype)


class TestQgsFieldTypeFromField:
    """Test the _qgs_field_type_from_field function."""

    def test_string_field_type(self):
        """Test SimpleFieldType.STR conversion."""
        field = Mock()
        field.type = SimpleFieldType.STR
        result = _qgs_field_type_from_field(field)
        assert result == STRING_TYPE

    def test_pattern_field_type(self):
        """Test SimpleFieldType.PATTERN conversion."""
        field = Mock()
        field.type = SimpleFieldType.PATTERN
        result = _qgs_field_type_from_field(field)
        assert result == STRING_TYPE

    def test_curve_field_type(self):
        """Test SimpleFieldType.CURVE conversion."""
        field = Mock()
        field.type = CurveType.HEADLOSS
        result = _qgs_field_type_from_field(field)
        assert result == STRING_TYPE

    def test_map_field_type(self):
        """Test MapFieldType conversion."""
        field = Mock()
        field.type = MapFieldType.PUMP_TYPE
        result = _qgs_field_type_from_field(field)
        assert result == STRING_TYPE

    def test_parameter_field_type(self):
        """Test Parameter conversion."""
        field = Mock()
        field.type = Parameter.ELEVATION
        result = _qgs_field_type_from_field(field)
        assert result == DOUBLE_TYPE

    def test_bool_field_type(self):
        """Test SimpleFieldType.BOOL conversion."""
        field = Mock()
        field.type = SimpleFieldType.BOOL
        result = _qgs_field_type_from_field(field)
        assert result == BOOL_TYPE

    def test_unsupported_field_type(self):
        """Test that unsupported field types raise KeyError."""
        field = Mock()
        field.type = "unsupported_type"
        with pytest.raises(KeyError, match="Couldn't get qgs field type for"):
            _qgs_field_type_from_field(field)


@pytest.mark.needs_pandas
class TestGetQgsFields:
    """Test the get_qgs_fields function."""

    def test_basic_fields_creation(self):
        import pandas as pd

        """Test basic QgsFields creation with simple fields."""
        # Create mock fields
        field1 = Mock()
        field1.value = "test_field1"
        field1.description = "Test field 1"
        field1.field_group = FieldGroup.BASE
        field1.type = SimpleFieldType.STR

        field2 = Mock()
        field2.value = "test_field2"
        field2.description = "Test field 2"
        field2.field_group = FieldGroup.BASE
        field2.type = Parameter.ELEVATION

        fields = [field1, field2]

        # Create a simple DataFrame
        df = pd.DataFrame({"extra_col": [1, 2, 3], "another_col": ["a", "b", "c"]})

        result = get_qgs_fields(fields, use_list_types=False, df=df)

        assert isinstance(result, QgsFields)
        field_names = result.names()

        # Check that our mock fields are included
        assert "test_field1" in field_names
        assert "test_field2" in field_names

        # Check that DataFrame columns are included
        assert "extra_col" in field_names
        assert "another_col" in field_names

    def test_list_type_fields(self):
        """Test QgsFields creation with list type fields."""
        import pandas as pd

        # Create a field that should become a list type
        field1 = Mock()
        field1.value = "list_field"
        field1.description = "List field"
        field1.field_group = FieldGroup.LIST_IN_EXTENDED_PERIOD
        field1.type = Parameter.ELEVATION

        fields = [field1]
        df = pd.DataFrame({"col1": [1, 2, 3]})

        result = get_qgs_fields(fields, use_list_types=True, df=df)

        # Find the list field
        list_field = None
        for i in range(result.count()):
            qgs_field = result.at(i)
            if qgs_field.name() == "list_field":
                list_field = qgs_field
                break

        assert list_field is not None
        assert list_field.type() == LIST_TYPE

    def test_duplicate_field_names(self):
        """Test that duplicate field names from DataFrame are not added twice."""
        import pandas as pd

        # Create a field with the same name as a DataFrame column
        field1 = Mock()
        field1.value = "duplicate_col"
        field1.description = "Duplicate field"
        field1.field_group = FieldGroup.BASE
        field1.type = SimpleFieldType.STR

        fields = [field1]
        df = pd.DataFrame({"duplicate_col": [1, 2, 3], "other_col": ["a", "b", "c"]})

        result = get_qgs_fields(fields, use_list_types=False, df=df)

        field_names = result.names()
        # Should only appear once
        assert field_names.count("duplicate_col") == 1
        assert "other_col" in field_names

    def test_empty_fields_and_dataframe(self):
        """Test with empty fields and DataFrame."""
        import pandas as pd

        fields = []
        df = pd.DataFrame()

        result = get_qgs_fields(fields, use_list_types=False, df=df)

        assert isinstance(result, QgsFields)
        assert result.count() == 0


class TestWrite:
    """Test the write function."""

    def test_basic_write_functionality(self):
        """Test basic writing of features to a real QgsVectorLayer sink."""
        # Create QgsFields
        fields = QgsFields()
        fields.append(QgsField("name", STRING_TYPE))
        fields.append(QgsField("value", DOUBLE_TYPE))

        # Create an in-memory vector layer
        layer = QgsVectorLayer("Point?field=name:string&field=value:double", "test", "memory")
        provider = layer.dataProvider()

        attributes = {"name": ["feature1", "feature2"], "value": [10.5, 20.3]}

        # Create geometries
        geom1 = QgsGeometry.fromPointXY(QgsPointXY(0, 0))
        geom2 = QgsGeometry.fromPointXY(QgsPointXY(1, 1))
        geometries = {"feature1": geom1, "feature2": geom2}

        write(provider, fields, attributes, geometries)

        # Fetch features from the layer
        features = list(layer.getFeatures())
        assert len(features) == 2

        # Check the first feature
        attrs = [f for f in features if f[0] == "feature1"]
        assert len(attrs) == 1
        feature1 = attrs[0]
        assert feature1[0] == "feature1"
        assert feature1[1] == 10.5
        assert feature1.geometry().equals(geom1)

        # Check the second feature
        attrs = [f for f in features if f[0] == "feature2"]
        assert len(attrs) == 1
        feature2 = attrs[0]
        assert feature2[0] == "feature2"
        assert feature2[1] == 20.3
        assert feature2.geometry().equals(geom2)

    def test_missing_columns_filled_with_null(self):
        """Test that missing columns are filled with NULL values."""
        # Create a real layer and provider to act as sink
        layer = QgsVectorLayer("Point?field=name:string&field=missing_col:double", "test_missing", "memory")
        provider = layer.dataProvider()

        fields = QgsFields()
        fields.append(QgsField("name", STRING_TYPE))
        fields.append(QgsField("missing_col", DOUBLE_TYPE))

        # DataFrame only has 'name' column, missing 'missing_col'
        attributes = {"name": ["feature1"]}

        geom1 = QgsGeometry.fromPointXY(QgsPointXY(0, 0))
        geometries = {"feature1": geom1}

        write(provider, fields, attributes, geometries)

        # Fetch feature and check missing column is NULL
        features = list(layer.getFeatures())
        assert len(features) == 1
        feat = features[0]
        idx = layer.fields().indexFromName("missing_col")
        assert feat[0] == "feature1"
        assert feat.attribute(idx) in [NULL, None]

    def test_none_values_converted_to_null(self):
        """Test that NaN values are converted to NULL."""
        layer = QgsVectorLayer("Point?field=name:string&field=value:double", "test_nan", "memory")
        provider = layer.dataProvider()

        fields = QgsFields()
        fields.append(QgsField("name", STRING_TYPE))
        fields.append(QgsField("value", DOUBLE_TYPE))

        # Include NaN values
        attributes = {"name": ["feature1", "feature2"], "value": [10.5, None]}

        geom1 = QgsGeometry.fromPointXY(QgsPointXY(0, 0))
        geom2 = QgsGeometry.fromPointXY(QgsPointXY(1, 1))
        geometries = {"feature1": geom1, "feature2": geom2}
        write(provider, fields, attributes, geometries)

        features = list(layer.getFeatures())
        assert len(features) == 2
        # find feature2 and check value is NULL
        feat2 = next(f for f in features if f[0] == "feature2")
        idx = layer.fields().indexFromName("value")
        assert feat2.attribute(idx) in [NULL, None]

    @pytest.mark.skip(reason="Doesn't work in all versions - but not sure of utility of test")
    @pytest.mark.needs_pandas
    def test_pd_na_values_converted_to_null(self):
        """Test that pandas `pd.NA` values are converted to NULL when written."""
        import pandas as pd

        layer = QgsVectorLayer("Point?field=val:double", "test_pd_na", "memory")
        provider = layer.dataProvider()

        fields = QgsFields()
        fields.append(QgsField("val", DOUBLE_TYPE))

        # Use pandas NA in a nullable Float64 dtype
        attributes = pd.DataFrame({"val": pd.Series([pd.NA], dtype="Float64")}, index=["id1"])

        geom1 = QgsGeometry.fromPointXY(QgsPointXY(0, 0))
        geometries = {"id1": geom1}

        write(provider, fields, attributes, geometries)

        features = list(layer.getFeatures())
        assert len(features) == 1
        feat = features[0]
        idx = layer.fields().indexFromName("val")
        assert feat.attribute(idx) in [NULL, None]

    def test_column_ordering_matches_fields(self):
        """Test that DataFrame columns are reordered to match fields."""
        layer = QgsVectorLayer("Point?field=name:string&field=col2:string&field=col1:double", "test_order", "memory")
        provider = layer.dataProvider()

        fields = QgsFields()
        fields.append(QgsField("name", STRING_TYPE))
        fields.append(QgsField("col2", STRING_TYPE))
        fields.append(QgsField("col1", DOUBLE_TYPE))

        # dict has columns in different order
        attributes = {"name": ["id1"], "col1": [10.5], "col2": ["test"]}

        geom1 = QgsGeometry.fromPointXY(QgsPointXY(0, 0))
        geometries = {"id1": geom1}

        write(provider, fields, attributes, geometries)

        features = list(layer.getFeatures())
        assert len(features) == 1
        feat = features[0]
        # check values by field name
        assert feat["col2"] == "test"
        assert feat["col1"] == 10.5

    def test_empty_attributes(self):
        """Test writing with an empty DataFrame."""
        # Use a real in-memory layer as the sink
        layer = QgsVectorLayer("Point?field=name:string", "empty_df", "memory")
        provider = layer.dataProvider()

        fields = QgsFields()
        fields.append(QgsField("name", STRING_TYPE))

        attributes = {"name": []}
        geometries = {}

        write(provider, fields, attributes, geometries)

        # No features should be added
        features = list(layer.getFeatures())
        assert len(features) == 0

    def test_various_data_types(self):
        """Test writing with various data types."""
        # Use a real layer/provider to validate attribute types round-trip
        layer = QgsVectorLayer(
            "Point?field=str_col:string&field=int_col:int&field=float_col:double&field=bool_col:bool",
            "various_types",
            "memory",
        )
        provider = layer.dataProvider()

        fields = QgsFields()
        fields.append(QgsField("str_col", STRING_TYPE))
        fields.append(QgsField("int_col", INT_TYPE))
        fields.append(QgsField("float_col", DOUBLE_TYPE))
        fields.append(QgsField("bool_col", BOOL_TYPE))

        attributes = {
            "name": ["id1"],
            "str_col": ["test"],
            "int_col": [42],
            "float_col": [3.14],
            "bool_col": [True],
        }

        geom1 = QgsGeometry.fromPointXY(QgsPointXY(0, 0))
        geometries = {"id1": geom1}

        write(provider, fields, attributes, geometries)

        features = list(layer.getFeatures())
        assert len(features) == 1
        feat = features[0]
        assert feat["str_col"] == "test"
        assert feat["int_col"] == 42
        assert abs(feat["float_col"] - 3.14) < 1e-9
        assert feat["bool_col"] in (True, 1)


class TestIntegration:
    """Integration tests combining multiple functions."""

    @pytest.mark.needs_pandas
    def test_full_workflow_with_real_field_enum(self):
        """Test the full workflow using actual Field enum values."""
        import pandas as pd

        # Use real Field enum values
        fields = [Field.NAME, Field.ELEVATION, Field.BASE_DEMAND]

        # Create DataFrame with matching and additional columns
        df = pd.DataFrame(
            {
                "name": ["junction1", "junction2"],
                "elevation": [100.0, 110.0],
                "extra_data": [1, 2],
            }
        )

        # Get QgsFields
        qgs_fields = get_qgs_fields(fields, use_list_types=False, df=df)

        # Verify fields were created correctly
        field_names = qgs_fields.names()
        assert "name" in field_names
        assert "elevation" in field_names
        # Field names may appear in different cases depending on source; compare lowercased
        lower_names = [n.lower() for n in field_names]
        assert "base_demand" in lower_names
        assert "extra_data" in field_names

        # Test writing (prepare data for write function)
        attributes = {
            "name": ["junction1", "junction2"],
            "elevation": [100.0, 110.0],
            "base_demand": [10.0, 15.0],
            "extra_data": [1, 2],
        }

        geom1 = QgsGeometry.fromPointXY(QgsPointXY(0, 0))
        geom2 = QgsGeometry.fromPointXY(QgsPointXY(1, 1))
        geometries = {"junction1": geom1, "junction2": geom2}

        # Create a layer matching the qgs_fields and use its provider
        layer = QgsVectorLayer("Point?", "full_workflow", "memory")
        provider = layer.dataProvider()
        # add fields from qgs_fields to the provider
        provider.addAttributes([qgs_fields.at(i) for i in range(qgs_fields.count())])
        layer.updateFields()

        write(provider, qgs_fields, attributes, geometries)

        # Verify features were written
        features = list(layer.getFeatures())
        assert len(features) == 2

    @pytest.mark.needs_pandas
    def test_list_type_integration(self):
        """Test integration with list-type fields."""
        import pandas as pd

        # Create a mock field that should become a list type
        list_field = Mock()
        list_field.value = "time_series_data"
        list_field.description = "Time series data"
        list_field.field_group = FieldGroup.LIST_IN_EXTENDED_PERIOD
        list_field.type = Parameter.PRESSURE

        fields = [list_field]
        df = pd.DataFrame({"regular_col": [1, 2]})

        qgs_fields = get_qgs_fields(fields, use_list_types=True, df=df)

        # Find the list field and verify it has the correct type
        list_qgs_field = None
        for i in range(qgs_fields.count()):
            field = qgs_fields.at(i)
            if field.name() == "time_series_data":
                list_qgs_field = field
                break

        assert list_qgs_field is not None
        assert list_qgs_field.type() == LIST_TYPE


@pytest.mark.parametrize("field_enum", [Field.NAME, Field.ELEVATION, Field.BASE_DEMAND])
def test_real_field_enum_compatibility(field_enum):
    """Test that real Field enum values work with the type conversion functions."""
    result = _qgs_field_type_from_field(field_enum)
    assert result in [STRING_TYPE, DOUBLE_TYPE, INT_TYPE, BOOL_TYPE, LIST_TYPE]


class TestErrorHandling:
    """Test error handling and edge cases."""

    def test_math_nan_handling(self):
        """Test that math.nan is properly handled."""
        layer = QgsVectorLayer("Point?field=value:double", "math_nan", "memory")
        provider = layer.dataProvider()

        fields = QgsFields()
        fields.append(QgsField("value", DOUBLE_TYPE))

        # Use math.nan specifically
        attributes = {"name": ["id1"], "value": [math.nan]}

        geom1 = QgsGeometry.fromPointXY(QgsPointXY(0, 0))
        geometries = {"id1": geom1}

        write(provider, fields, attributes, geometries)

        features = list(layer.getFeatures())
        assert len(features) == 1
        feat = features[0]
        idx = layer.fields().indexFromName("value")
        assert feat.attribute(idx) in [NULL, None]

    def test_inf_values_not_converted(self):
        """Test that infinite values are not converted to NULL."""
        layer = QgsVectorLayer("Point?field=value:double", "inf_values", "memory")
        provider = layer.dataProvider()

        fields = QgsFields()
        fields.append(QgsField("value", DOUBLE_TYPE))

        # Use positive infinity
        attributes = {"name": ["id1"], "value": [float("inf")]}

        geom1 = QgsGeometry.fromPointXY(QgsPointXY(0, 0))
        geometries = {"id1": geom1}

        write(provider, fields, attributes, geometries)

        features = list(layer.getFeatures())
        assert len(features) == 1
        feat = features[0]
        idx = layer.fields().indexFromName("value")
        assert feat.attribute(idx) == float("inf")

    def test_string_nan_not_converted(self):
        """Test that string 'nan' is not converted to NULL."""
        layer = QgsVectorLayer("Point?field=text:string", "string_nan", "memory")
        provider = layer.dataProvider()

        fields = QgsFields()
        fields.append(QgsField("text", STRING_TYPE))

        # String 'nan' should not be converted
        attributes = {"name": ["id1"], "text": ["nan"]}

        geom1 = QgsGeometry.fromPointXY(QgsPointXY(0, 0))
        geometries = {"id1": geom1}

        write(provider, fields, attributes, geometries)

        features = list(layer.getFeatures())
        assert len(features) == 1
        feat = features[0]
        idx = layer.fields().indexFromName("text")
        assert feat.attribute(idx) == "nan"
