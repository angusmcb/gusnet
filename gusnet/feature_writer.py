from __future__ import annotations

import itertools
import math
from typing import TYPE_CHECKING, Any, cast

from qgis.core import NULL, Qgis, QgsFeature, QgsFeatureSink, QgsField, QgsFields, QgsGeometry
from qgis.PyQt.QtCore import QMetaType, QVariant

from gusnet.elements import CurveType, Field, FieldGroup, MapFieldType, Parameter, SimpleFieldType

if TYPE_CHECKING:  # pragma: no cover
    import pandas as pd

USE_QMETATYPE = Qgis.versionInt() >= 33800

LIST_TYPE = QMetaType.Type.QVariantList if USE_QMETATYPE else QVariant.List
DOUBLE_TYPE = QMetaType.Type.Double if USE_QMETATYPE else QVariant.Double
INT_TYPE = QMetaType.Type.Int if USE_QMETATYPE else QVariant.Int
STRING_TYPE = QMetaType.Type.QString if USE_QMETATYPE else QVariant.String
BOOL_TYPE = QMetaType.Type.Bool if USE_QMETATYPE else QVariant.Bool


def get_qgs_fields(fields: list[Field], df: pd.DataFrame | None = None, use_list_types: bool = False) -> QgsFields:  # noqa: FBT001, FBT002
    """Build a QgsFields schema for writing features.

    The returned QgsFields contains one QgsField for each entry in ``fields``
    and for any additional columns present in the supplied pandas ``df`` that
    are not already represented by the provided ``fields`` (comparison is
    case-insensitive).

    Args:
        fields: Sequence of domain `Field` objects describing known fields.
        df: pandas DataFrame whose columns should also be included (if not
            already present).
        use_list_types: Whether to convert certain fields to list-typed
            QgsFields when supported. Used for extended period data.

    Returns:
        QgsFields: a QGIS fields collection suitable for creating a layer
        or provider that matches the data written by ``write``.
    """

    qgs_fields = QgsFields()  # nice constructor didn't arrive until qgis 3.40

    for field in fields:
        if use_list_types and field.field_group & FieldGroup.LIST_IN_EXTENDED_PERIOD:
            qf = QgsField(
                field.value,
                cast(QMetaType.Type, LIST_TYPE),
                subType=cast(QMetaType.Type, DOUBLE_TYPE),
                comment=field.description,
            )
        else:
            qf = QgsField(field.value, _qgs_field_type_from_field(field), comment=field.description)
        qgs_fields.append(qf)

    if df is None:
        return qgs_fields

    for series_name in df.columns:
        if series_name in qgs_fields.names():
            continue

        series = df[series_name]

        series = series.convert_dtypes(convert_string=False)

        qf = QgsField(series_name, _qgs_field_type_from_pandas(series.dtype))
        qgs_fields.append(qf)

    return qgs_fields


def write(
    sink: QgsFeatureSink,
    fields: QgsFields,
    attributes: pd.DataFrame,
    geometries: dict[str, QgsGeometry] | pd.Series,
) -> None:
    """Write features to a QGIS feature sink (or provider).

    This function creates and adds QgsFeature objects to ``sink`` using the
    schema provided in ``fields`` and the attribute values in ``attributes``.

    Args:
        sink: a QGIS feature sink or data provider implementing
            ``addFeature``.
        fields: QgsFields describing the schema to be written.
        attributes: pandas DataFrame of attribute values indexed by feature id.
        geometries: mapping of index -> QgsGeometry for each feature.
    """
    null_iterator = itertools.repeat(NULL)

    ordered_attributes = [attributes.get(field_name, null_iterator) for field_name in fields.names()]

    for name, feature_attributes in zip(attributes.index, zip(*ordered_attributes)):
        f = QgsFeature()
        f.setGeometry(geometries[name])
        attributes_with_null = [
            value if not (isinstance(value, float) and math.isnan(value)) else NULL for value in feature_attributes
        ]
        f.setAttributes(attributes_with_null)
        sink.addFeature(f, QgsFeatureSink.Flag.FastInsert)


def _qgs_field_type_from_pandas(dtype: Any) -> QMetaType.Type | QVariant.Type:
    """Map a pandas dtype to the corresponding QGIS field type constant.

    Args:
        dtype: a pandas dtype object (e.g. Series.dtype or pandas nullable dtypes).

    Returns:
        QMetaType or QVariant constant representing the QGIS field type.

    Raises:
        KeyError: if the dtype cannot be mapped to a known QGIS type.
    """
    import pandas as pd

    if pd.api.types.is_string_dtype(dtype):
        return STRING_TYPE
    if pd.api.types.is_integer_dtype(dtype):
        return INT_TYPE
    if pd.api.types.is_float_dtype(dtype):
        return DOUBLE_TYPE
    if pd.api.types.is_bool_dtype(dtype):
        return BOOL_TYPE

    raise KeyError(f"Couldn't get qgs field type for {dtype}")  # noqa: EM102, TRY003 # pragma: no cover


def _qgs_field_type_from_field(field: Field) -> QMetaType.Type | QVariant.Type:
    """Return the QGIS field type constant for a `Field`.

    The function inspects the domain-specific ``field.type`` value and maps
    it to a QGIS type constant used when creating a ``QgsField``.

    Does not work on extended type fields (e.g. list types); those must be
    handled separately.

    Args:
        field: a domain ``Field`` instance (or enum) whose ``type`` attribute
            determines the resulting QGIS type.

    Returns:
        QMetaType or QVariant constant representing the QGIS field type.

    Raises:
        KeyError: when the provided field type cannot be mapped.
    """

    dtype = field.type

    if dtype in [SimpleFieldType.STR, SimpleFieldType.PATTERN] or isinstance(dtype, (MapFieldType, CurveType)):
        return STRING_TYPE

    if isinstance(dtype, Parameter):
        return DOUBLE_TYPE

    if dtype is SimpleFieldType.BOOL:
        return BOOL_TYPE

    raise KeyError(f"Couldn't get qgs field type for {field}")  # noqa: EM102, TRY003 # pragma: no cover
