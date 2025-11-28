from __future__ import annotations

from typing import TYPE_CHECKING

from gusnet.elements import (
    CurveType,
    Field,
    FieldGroup,
    ModelLayer,
    Parameter,
    PumpTypes,
    SimpleFieldType,
    ValveType,
)
from gusnet.i18n import tr
from gusnet.pattern_curve import Curve, Pattern

if TYPE_CHECKING:  # pragma: no cover
    import pandas as pd


def verify_model(layers: dict[ModelLayer, pd.DataFrame]) -> None:
    """Verify that the provided dataframes contain all required fields.

    Args:
        layers: Mapping of ModelLayer to DataFrame to verify.

    Raises:
        RequiredFieldError: If any required field is missing.
    """

    _check_model_not_empty(layers)

    errors = []

    try:
        _check_junction_layer(layers)
    except VerificationError as e:
        errors.append(e)
    try:
        _check_link_layers(layers)
    except VerificationError as e:
        errors.append(e)
    try:
        _check_reservoir_or_tank_exists(layers)
    except VerificationError as e:
        errors.append(e)
    try:
        _check_duplicate_node_names(layers)
    except VerificationError as e:
        errors.append(e)
    try:
        _check_names(layers)
    except VerificationError as e:
        errors.append(e)
    try:
        _check_duplicate_link_names(layers)
    except VerificationError as e:
        errors.append(e)

    for layer in ModelLayer:
        df = layers.get(layer)
        if df is None:
            continue

        for field in layer.wq_fields():
            if field.field_group & FieldGroup.REQUIRED:
                try:
                    _check_required_field(df, layer, field)
                except VerificationError as e:
                    errors.append(e)

        for field in layer.wq_fields():
            if field not in df.columns:
                continue

            if isinstance(field.type, Parameter):
                try:
                    _check_numeric_field_type(df, layer, field)
                except NumericFieldError as e:
                    errors.append(e)

            if field.type is SimpleFieldType.BOOL:
                try:
                    _check_boolean_field_type(df, layer, field)
                except BooleanFieldError as e:
                    errors.append(e)

            if field.type is SimpleFieldType.PATTERN:
                try:
                    df[field].map(Pattern.factory, na_action="ignore")
                except ValueError as e:
                    errors.append(PatternError(e, layer, field))

            elif isinstance(field.type, CurveType) and field not in [Field.PUMP_CURVE, Field.HEADLOSS_CURVE]:
                try:
                    df[field].map(Curve.factory, na_action="ignore")
                except ValueError as e:
                    errors.append(CurveError(layer, field, e))

    if ModelLayer.VALVES in layers:
        try:
            _check_valve_settings(layers[ModelLayer.VALVES])
        except VerificationError as e:
            errors.append(e)

    if ModelLayer.PUMPS in layers:
        try:
            _check_pump_parameters(layers[ModelLayer.PUMPS])
        except VerificationError as e:
            errors.append(e)

    for link_layer in [ModelLayer.PIPES, ModelLayer.PUMPS, ModelLayer.VALVES]:
        if link_layer in layers:
            try:
                _check_link_ends_not_same_node(link_layer, layers[link_layer])
            except VerificationError as e:
                errors.append(e)

    try:
        _check_no_orphan_junctions(layers)
    except OrphanJunctionsError as e:
        errors.append(e)

    if errors:
        if len(errors) == 1:
            raise errors[0] from errors[0]
        else:
            raise MultipleVerificationError(errors)


def _check_junction_layer(layers: dict[ModelLayer, pd.DataFrame]) -> None:
    """Check that the junction layer exists and is not empty.

    Args:
        layers: Mapping of ModelLayer to DataFrame to check.

    Raises:
        NoJunctionError: If any required field is missing.
    """
    if ModelLayer.JUNCTIONS not in layers:
        raise NoJunctionError

    if layers[ModelLayer.JUNCTIONS].empty:
        raise NoJunctionError


def _check_link_layers(layers: dict[ModelLayer, pd.DataFrame]) -> None:
    """Check that at least one link layer exists and is not empty.

    Args:
        layers: Mapping of ModelLayer to DataFrame to check.

    Raises:
        NoLinksError: If there are no links
    """
    link_layers = [ModelLayer.PIPES, ModelLayer.VALVES, ModelLayer.PUMPS]
    if not any(layer in layers and not layers[layer].empty for layer in link_layers):
        raise NoLinksError


def _check_reservoir_or_tank_exists(layers: dict[ModelLayer, pd.DataFrame]) -> None:
    """Check that at least one reservoir or tank layer exists and is not empty.

    Args:
        layers: Mapping of ModelLayer to DataFrame to check.

    Raises:
        NoReservoirOrTankError: If neither reservoirs nor tanks are present.
    """
    if not (
        (ModelLayer.RESERVOIRS in layers and not layers[ModelLayer.RESERVOIRS].empty)
        or (ModelLayer.TANKS in layers and not layers[ModelLayer.TANKS].empty)
    ):
        raise NoReservoirOrTankError


def _collect_names_for_layers(layers: dict[ModelLayer, pd.DataFrame], layer_keys) -> list[str]:
    """Collect non-null stringified `Field.NAME` values from the given layers."""
    names: list[str] = []
    for layer in layer_keys:
        if layer in layers:
            df = layers[layer]
            if Field.NAME in df:
                series = df[Field.NAME].dropna()
                names.extend([str(v) for v in series.tolist()])
    return names


def _find_duplicates(items: list[str]) -> list[str]:
    seen: set[str] = set()
    dupes: set[str] = set()
    for it in items:
        if it in seen:
            dupes.add(it)
        else:
            seen.add(it)
    return sorted(dupes)


def _check_duplicate_node_names(layers: dict[ModelLayer, pd.DataFrame]) -> None:
    node_layers = [ModelLayer.JUNCTIONS, ModelLayer.RESERVOIRS, ModelLayer.TANKS]
    names = _collect_names_for_layers(layers, node_layers)
    dupes = _find_duplicates(names)
    if dupes:
        raise DuplicateNodeNameError(dupes)


def _check_duplicate_link_names(layers: dict[ModelLayer, pd.DataFrame]) -> None:
    link_layers = [ModelLayer.PIPES, ModelLayer.PUMPS, ModelLayer.VALVES]
    names = _collect_names_for_layers(layers, link_layers)
    dupes = _find_duplicates(names)
    if dupes:
        raise DuplicateLinkNameError(dupes)


def _check_required_field(df: pd.DataFrame, layer: ModelLayer, field: Field) -> None:
    """Check if a required field is present in the dataframe.

    Args:
        df: DataFrame to check.
        layer: ModelLayer to check against.
        field: Field to check for.
    Raises:
        RequiredFieldError: If the required field is missing.
    """

    if field not in df:
        raise RequiredFieldError(layer, field)

    if df[field].hasnans:
        raise RequiredFieldError(layer, field)


def _check_names(layers: dict[ModelLayer, pd.DataFrame]) -> None:
    """Check name field constraints across provided layers.

    Requirements:
    - If present, name values must be non-empty strings
    - No spaces allowed in names
    - Names must be shorter than 32 characters
    """
    from pandas.api.types import is_string_dtype

    for layer, df in layers.items():
        if Field.NAME not in df.columns:
            continue

        series = df[Field.NAME].dropna()
        if series.empty:
            continue

        if not is_string_dtype(series):
            non_string_mask = ~series.map(lambda v: isinstance(v, str))
            if non_string_mask.any():
                bad_names = series[non_string_mask].astype(str).tolist()
                raise NameFieldError(layer, bad_names)

        space_mask = series.str.contains(" ", regex=False)
        long_mask = ~series.str.len().between(1, 31)

        bad_mask = space_mask | long_mask

        if bad_mask.any():
            bad_names = series[bad_mask].tolist()
            raise NameFieldError(layer, bad_names)


def _check_numeric_field_type(df: pd.DataFrame, layer: ModelLayer, field: Field) -> None:
    """Ensure the provided field contains numeric values when present.

    If the column is missing or all values are NA, this check is skipped.
    Raises `NumericFieldError` if the column exists and contains non-numeric values.
    """

    import pandas as pd

    if field not in df:
        return

    series = df[field].dropna()
    if series.empty:
        return

    if not pd.api.types.is_numeric_dtype(series):
        raise NumericFieldError(layer, field)


def _check_boolean_field_type(df: pd.DataFrame, layer: ModelLayer, field: Field) -> None:
    """Ensure the provided field contains boolean values when present.

    If the column is missing or all values are NA, this check is skipped.
    Raises `BooleanFieldError` if the column exists and contains non-boolean values.
    """

    import pandas as pd

    if field not in df:
        return

    series = df[field].dropna()
    if series.empty:
        return

    try:
        series = series.astype("boolean")
    except TypeError as e:
        raise BooleanFieldError(layer, field) from e

    if not pd.api.types.is_bool_dtype(series):
        raise BooleanFieldError(layer, field)


def _check_model_not_empty(layers: dict[ModelLayer, pd.DataFrame]) -> None:
    """Ensure the provided `layers` mapping contains at least one non-empty layer.

    This is a fast-fail for completely empty imports. If the mapping is empty
    or contains only empty DataFrames, raise a combined verification error
    similar to previous behaviour so callers/tests that expect aggregated
    errors continue to work.
    """
    # If there is at least one non-empty dataframe, consider the model non-empty
    if not any(layer in layers and not layers[layer].empty for layer in layers):
        raise EmptyModelError


def _check_valve_settings(df: pd.DataFrame) -> None:
    """Verify that valve settings are valid.

    Args:
        df: DataFrame of valve attributes.

    Raises:
        ValveSettingError: If any valve setting is invalid.
    """

    try:
        valve_types = df[Field.VALVE_TYPE].str.upper()
    except (KeyError, AttributeError):
        raise ValveTypeError from None

    if not valve_types.isin(ValveType._member_names_).all():
        raise ValveTypeError from None

    for valve_type in ValveType:
        valve_mask = valve_types == valve_type.value

        if not valve_mask.any():
            continue

        if valve_type.setting_field.value not in df:
            raise ValveSettingError(valve_type)

        if df.loc[valve_mask, valve_type.setting_field.value].hasnans:
            raise ValveSettingError(valve_type)

    gpv_mask = valve_types == ValveType.GPV.value

    if gpv_mask.any():
        try:
            curves = df.loc[gpv_mask, Field.HEADLOSS_CURVE].map(Curve.factory, na_action="ignore")
        except ValueError as e:
            raise CurveError(ModelLayer.VALVES, Field.HEADLOSS_CURVE, e) from e
        if curves.hasnans:
            raise ValveSettingError(ValveType.GPV)


def _check_pump_parameters(df: pd.DataFrame) -> None:
    try:
        df[Field.PUMP_TYPE] = df[Field.PUMP_TYPE].str.upper()
    except (KeyError, AttributeError):
        raise PumpTypeError from None

    if not df[Field.PUMP_TYPE].isin(PumpTypes._member_names_).all():
        raise PumpTypeError

    power_pumps = df[Field.PUMP_TYPE] == PumpTypes.POWER.value
    head_pumps = df[Field.PUMP_TYPE] == PumpTypes.HEAD.value

    if power_pumps.any():
        if Field.POWER not in df:
            raise PumpPowerError
        if df.loc[power_pumps, Field.POWER].hasnans:
            raise PumpPowerError
        # The comparison may raise TypeError/ValueError if POWER contains non-numeric
        # values (e.g. strings). Per request, ignore such comparison errors rather
        # than letting them propagate — do not treat them as pump-power failures
        # here. Numeric-ness is checked elsewhere by `_check_numeric_field_type`.
        try:
            if (df.loc[power_pumps, Field.POWER] <= 0).any():
                raise PumpPowerError
        except (TypeError, ValueError):
            # Non-numeric values prevented numeric comparison; ignore as requested.
            pass

    if head_pumps.any():
        if Field.PUMP_CURVE not in df:
            raise PumpCurveMissingError

        try:
            head_curves = df.loc[head_pumps, Field.PUMP_CURVE].map(Curve.factory, na_action="ignore")
        except ValueError as e:
            raise CurveError(ModelLayer.PUMPS, Field.PUMP_CURVE, e) from e

        if head_curves.hasnans:
            raise PumpCurveMissingError


def _check_link_ends_not_same_node(layer: ModelLayer, df: pd.DataFrame) -> None:
    # Only accept explicit `start_node_name` and `end_node_name` columns.
    if "start_node_name" not in df.columns or "end_node_name" not in df.columns:
        return

    start_nodes = df["start_node_name"].astype(str)
    end_nodes = df["end_node_name"].astype(str)

    same_node_mask = start_nodes == end_nodes
    if same_node_mask.any():
        duplicate_links = df.loc[same_node_mask, Field.NAME].astype(str).tolist()
        raise LinkEndsSameNodeError(layer, duplicate_links)


def _check_no_orphan_junctions(layers: dict[ModelLayer, pd.DataFrame]) -> None:
    """Only consider junctions as reservoirs/tanks may be unconnected intentionally."""
    connected_nodes: set[str] = set()

    for link_layer in [ModelLayer.PIPES, ModelLayer.PUMPS, ModelLayer.VALVES]:
        if link_layer not in layers:
            continue

        df = layers[link_layer]
        if "start_node_name" in df.columns:
            connected_nodes.update(df["start_node_name"].dropna().astype(str).tolist())

        if "end_node_name" in df.columns:
            connected_nodes.update(df["end_node_name"].dropna().astype(str).tolist())

    if not connected_nodes:
        # not worth testing if there are no links
        return

    if ModelLayer.JUNCTIONS not in layers:
        return

    df = layers[ModelLayer.JUNCTIONS]

    if Field.NAME not in df.columns:
        return

    link_names = df[Field.NAME].dropna().astype(str).tolist()
    orphan_junctions = [name for name in link_names if name not in connected_nodes]

    if orphan_junctions:
        raise OrphanJunctionsError(orphan_junctions)


class VerificationError(Exception):
    """Base class for model verification errors."""

    pass


class MultipleVerificationError(VerificationError):
    """Raised when multiple verification errors are found."""

    def __init__(self, errors: list[VerificationError]) -> None:
        intro = tr("Multiple verification errors were found:\n")
        combined_message = intro + "\n".join(str(e) for e in errors)
        super().__init__(combined_message)


class EmptyModelError(VerificationError):
    """Raised when the model contains no elements."""

    def __init__(self) -> None:
        super().__init__(tr("The model is empty."))


class OrphanJunctionsError(VerificationError):
    """Raised when there are orphan nodes in the model."""

    def __init__(self, orphan_nodes: list[str]):
        super().__init__(
            tr("The following junctions are not connected to any links: {nodes}").format(nodes=", ".join(orphan_nodes))
        )


class LinkEndsSameNodeError(VerificationError):
    """Raised when a link connects to the same node on both ends."""

    def __init__(self, layer: ModelLayer, duplicate_links: list[str]):
        super().__init__(
            tr("In {layer_name} {num_features} features have the same start and end nodes: {links}").format(
                layer_name=layer.friendly_name, num_features=len(duplicate_links), links=", ".join(duplicate_links)
            )
        )


class NoJunctionError(VerificationError):
    """Raised when no junctions are present in the model."""

    def __init__(self) -> None:
        super().__init__(tr("The model must contain at least one junction."))


class NoLinksError(VerificationError):
    """Raised when no links are present in the model."""

    def __init__(self) -> None:
        super().__init__(tr("The model must contain at least one link (pipe, pump, or valve)."))


class NoReservoirOrTankError(VerificationError):
    """Raised when neither reservoirs nor tanks are present in the model."""

    def __init__(self) -> None:
        super().__init__(tr("The model must contain at least one reservoir or tank."))


class RequiredFieldError(VerificationError):
    """Raised when a required parameter is missing from the model."""

    def __init__(self, layer: ModelLayer, field: Field):
        super().__init__(
            tr("In {layer_type}, all elements must have {field_name} '{field_id}'").format(
                layer_type=layer.friendly_name, field_name=field.friendly_name, field_id=field.name.lower()
            )
        )


class NumericFieldError(VerificationError):
    def __init__(self, layer: ModelLayer, field: Field):
        super().__init__(
            tr("In {layer_type}, {field_name} ({field_id}) must be numeric").format(
                layer_type=layer.friendly_name, field_name=field.friendly_name, field_id=field.name.lower()
            )
        )


class BooleanFieldError(VerificationError):
    def __init__(self, layer: ModelLayer, field: Field):
        super().__init__(
            tr("In {layer_type}, {field_name} ({field_id}) must be boolean").format(
                layer_type=layer.friendly_name, field_name=field.friendly_name, field_id=field.name.lower()
            )
        )


class ValveTypeError(VerificationError):
    def __init__(self):
        super().__init__(
            tr(
                "Valve type ({valve_type}) must be set for all valves and must be one of the following values: {possible_values}"  # noqa: E501
            ).format(valve_type=Field.VALVE_TYPE, possible_values=", ".join(ValveType._member_names_))
        )


class ValveSettingError(VerificationError):
    def __init__(self, valve_type: ValveType):
        super().__init__(
            tr("{initial_setting_name} ({initial_setting}) must be set for all {valve_name}").format(
                initial_setting_name=valve_type.setting_field.friendly_name,
                initial_setting=valve_type.setting_field.name.lower(),
                valve_name=valve_type.friendly_name,
            )
        )


class PumpTypeError(VerificationError):
    def __init__(self):
        super().__init__(
            tr(
                "Pump type ({pump_type}) must be set for all pumps and must be one of the following values: {possible_values}"  # noqa: E501
            ).format(pump_type=Field.PUMP_TYPE.name.lower(), possible_values=", ".join(PumpTypes._member_names_))
        )


class PumpCurveMissingError(VerificationError):
    def __init__(self):
        super().__init__(
            tr("{pump_curve_name} ({pump_curve}) must be set for all pumps of type HEAD").format(
                pump_curve_name=Field.PUMP_CURVE.friendly_name, pump_curve=Field.PUMP_CURVE.name.lower()
            )
        )


class PumpPowerError(VerificationError):
    def __init__(self):
        super().__init__(
            tr("{pump_power_name} ({pump_power}) must be set for all pumps of type POWER").format(
                pump_power_name=Field.POWER.friendly_name, pump_power=Field.POWER.name.lower()
            )
        )


class PatternError(VerificationError):
    def __init__(self, pattern_string, layer: ModelLayer, field: Field):
        super().__init__(
            tr(
                "In {layer} problem reading {pattern_type}: {pattern_string} Patterns should be a string of numeric values separated by a space, or a list of numeric values."  # noqa: E501
            ).format(layer=layer.friendly_name, pattern_type=field.friendly_name, pattern_string=pattern_string)
        )


class CurveError(VerificationError):
    def __init__(self, layer: ModelLayer, field: Field, error: ValueError):
        error_detail = ""
        if hasattr(error, "__notes__") and error.__notes__:
            error_detail = error.__notes__[0]

        super().__init__(
            tr(
                'In {layer}, problem reading {field_name}  "{curve_string}". {error_detail} Curves should be of the form: (1, 2), (3.6, 4.7)'  # noqa: E501
            ).format(
                layer=layer.friendly_name, field_name=field.friendly_name, curve_string=error, error_detail=error_detail
            )
        )


class DuplicateNodeNameError(VerificationError):
    def __init__(self, duplicates: list[str]):
        dup_str = ", ".join(map(str, duplicates))
        super().__init__(tr("Duplicate node names found: {dupes}").format(dupes=dup_str))


class DuplicateLinkNameError(VerificationError):
    def __init__(self, duplicates: list[str]):
        dup_str = ", ".join(map(str, duplicates))
        super().__init__(tr("Duplicate link names found: {dupes}").format(dupes=dup_str))


class NameFieldError(VerificationError):
    def __init__(self, layer: ModelLayer, bad_names: list[str]):
        names = ", ".join(map(str, bad_names))
        super().__init__(
            tr(
                "In {layer_name}, the {field_name} values must be strings without spaces "
                "and under 32 characters. Problem values: {names}"
            ).format(layer_name=layer.friendly_name, field_name=Field.NAME.friendly_name, names=names)
        )
