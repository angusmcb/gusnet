from __future__ import annotations

import itertools
from collections.abc import Iterable, Mapping

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
from gusnet.network import Network
from gusnet.pattern_curve import Curve, Pattern


def verify_model(layers: Mapping[ModelLayer, Mapping[str, Iterable]], network: Network) -> None:
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
        layer_dict = layers.get(layer)
        if layer_dict is None:
            continue

        for field in layer.wq_fields():
            if field.field_group & FieldGroup.REQUIRED:
                try:
                    _check_required_field(layer_dict, layer, field)
                except VerificationError as e:
                    errors.append(e)

        for field in layer.wq_fields():
            if field not in layer_dict:
                continue

            if isinstance(field.type, Parameter):
                try:
                    _check_numeric_field_type(layer_dict, layer, field)
                except NumericFieldError as e:
                    errors.append(e)

            if field.type is SimpleFieldType.BOOL:
                try:
                    _check_boolean_field_type(layer_dict, layer, field)
                except BooleanFieldError as e:
                    errors.append(e)

            if field.type is SimpleFieldType.PATTERN:
                try:
                    [Pattern(val) for val in layer_dict[field] if val is not None]
                except ValueError as e:
                    errors.append(PatternError(e, layer, field))

            elif isinstance(field.type, CurveType) and field not in [Field.PUMP_CURVE, Field.HEADLOSS_CURVE]:
                try:
                    [Curve(val) for val in layer_dict[field] if val is not None]
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

    if ModelLayer.PIPES in layers:
        try:
            _check_pipe_length_exists(layers[ModelLayer.PIPES])
        except VerificationError as e:
            errors.append(e)

    try:
        _check_link_connects_to_nodes(network)
    except VerificationError as e:
        errors.append(e)

    try:
        _check_no_overlapping_nodes(network)
    except OverlappingNodesError as e:
        errors.append(e)

    try:
        _check_link_ends_not_same_node(network)
    except VerificationError as e:
        errors.append(e)

    if ModelLayer.JUNCTIONS in layers:
        try:
            _check_no_orphan_junctions(layers[ModelLayer.JUNCTIONS], network)
        except OrphanJunctionsError as e:
            errors.append(e)

    if errors:
        if len(errors) == 1:
            raise errors[0] from errors[0]
        else:
            raise MultipleVerificationError(errors)


class VerificationError(Exception):
    """Base class for model verification errors."""

    pass


class MultipleVerificationError(VerificationError):
    """Raised when multiple verification errors are found."""

    def __init__(self, errors: list[VerificationError]) -> None:
        intro = tr("Multiple verification errors were found:\n")
        combined_message = intro + "\n".join(str(e) for e in errors)
        super().__init__(combined_message)


def _check_junction_layer(layers: Mapping[ModelLayer, Mapping[str, Iterable]]) -> None:
    """Check that the junction layer exists and is not empty.

    Args:
        layers: Mapping of ModelLayer to DataFrame to check.

    Raises:
        NoJunctionError: If any required field is missing.
    """
    junctions = layers.get(ModelLayer.JUNCTIONS)
    if junctions is None or len(junctions) == 0:
        raise NoJunctionError


def _check_link_layers(layers: Mapping[ModelLayer, Mapping[str, Iterable]]) -> None:
    """Check that at least one link layer exists and is not empty.

    Args:
        layers: Mapping of ModelLayer to DataFrame to check.

    Raises:
        NoLinksError: If there are no links
    """
    link_layers = [ModelLayer.PIPES, ModelLayer.VALVES, ModelLayer.PUMPS]
    if not any(len(layers.get(layer, {})) > 0 for layer in link_layers):
        raise NoLinksError


def _check_reservoir_or_tank_exists(layers: Mapping[ModelLayer, Mapping[str, Iterable]]) -> None:
    """Check that at least one reservoir or tank layer exists and is not empty.

    Args:
        layers: Mapping of ModelLayer to DataFrame to check.

    Raises:
        NoReservoirOrTankError: If neither reservoirs nor tanks are present.
    """
    if not any(len(layers.get(layer, {})) > 0 for layer in [ModelLayer.RESERVOIRS, ModelLayer.TANKS]):
        raise NoReservoirOrTankError


def _find_duplicates(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    dupes: set[str] = set()
    for it in items:
        if it in seen:
            dupes.add(it)
        else:
            seen.add(it)
    return sorted(dupes)


def _check_duplicate_node_names(layers: Mapping[ModelLayer, Mapping[str, Iterable]]) -> None:
    names = itertools.chain(
        layers.get(ModelLayer.JUNCTIONS, {}).get(Field.NAME, []),
        layers.get(ModelLayer.RESERVOIRS, {}).get(Field.NAME, []),
        layers.get(ModelLayer.TANKS, {}).get(Field.NAME, []),
    )

    dupes = _find_duplicates(names)
    if dupes:
        raise DuplicateNodeNameError(dupes)


def _check_duplicate_link_names(layers: Mapping[ModelLayer, Mapping[str, Iterable]]) -> None:
    names = itertools.chain(
        layers.get(ModelLayer.PIPES, {}).get(Field.NAME, []),
        layers.get(ModelLayer.PUMPS, {}).get(Field.NAME, []),
        layers.get(ModelLayer.VALVES, {}).get(Field.NAME, []),
    )
    dupes = _find_duplicates(names)
    if dupes:
        raise DuplicateLinkNameError(dupes)


def _check_required_field(df: Mapping[str, Iterable], layer: ModelLayer, field: Field) -> None:
    """Check if a required field is present in the dataframe.

    Args:
        df: DataFrame to check.
        layer: ModelLayer to check against.
        field: Field to check for.
    Raises:
        RequiredFieldError: If the required field is missing.
    """

    if df and (field not in df or any(val is None for val in df[field])):
        raise RequiredFieldError(layer, field)


def _check_pipe_length_exists(pipe_df: Mapping[str, Iterable]) -> None:
    """Check that the LENGTH field exists and has no missing values.

    Args:
        df: DataFrame to check."""
    if Field.LENGTH not in pipe_df or any(val is None for val in pipe_df[Field.LENGTH]):
        raise PipeLengthMissingError


def _check_names(layers: Mapping[ModelLayer, Mapping[str, Iterable]]) -> None:
    """Check name field constraints across provided layers.

    Requirements:
    - If present, name values must be non-empty strings
    - No spaces allowed in names
    - Names must be shorter than 32 characters
    """

    for layer, layer_dict in layers.items():
        if Field.NAME not in layer_dict:
            continue

        names = layer_dict[Field.NAME]

        bad_names = [
            name
            for name in names
            if name is not None and (not name or not isinstance(name, str) or " " in name or len(name) > 31)
        ]

        if bad_names:
            raise NameFieldError(layer, bad_names)


def _check_numeric_field_type(df: Mapping[str, Iterable], layer: ModelLayer, field: Field) -> None:
    """Ensure the provided field contains numeric values when present.

    If the column is missing or all values are NA, this check is skipped.
    Raises `NumericFieldError` if the column exists and contains non-numeric values.
    """

    if field not in df:
        return

    try:
        [float(val) if val is not None else None for val in df[field]]
    except (ValueError, TypeError) as e:
        raise NumericFieldError(layer, field) from e


def _check_boolean_field_type(df: Mapping[str, Iterable], layer: ModelLayer, field: Field) -> None:
    """Ensure the provided field contains boolean values when present.

    If the column is missing or all values are NA, this check is skipped.
    Raises `BooleanFieldError` if the column exists and contains non-boolean values.
    """

    if field not in df:
        return

    try:
        [bool(float(val)) if val is not None else None for val in df[field]]
    except (ValueError, TypeError) as e:
        raise BooleanFieldError(layer, field) from e


def _check_model_not_empty(layers: Mapping[ModelLayer, Mapping[str, Iterable]]) -> None:
    """Ensure the provided `layers` mapping contains at least one non-empty layer.

    This is a fast-fail for completely empty imports. If the mapping is empty
    or contains only empty dicts, raise a combined verification error
    similar to previous behaviour so callers/tests that expect aggregated
    errors continue to work.
    """
    # If there is at least one non-empty dict, consider the model non-empty
    if not any(len(layer_dict) > 0 for layer_dict in layers.values()):
        raise EmptyModelError


def _check_valve_settings(valve_dict: Mapping[str, Iterable]) -> None:
    """Verify that valve settings are valid.

    Args:
        df: DataFrame of valve attributes.

    Raises:
        ValveSettingError: If any valve setting is invalid.
    """

    if Field.VALVE_TYPE not in valve_dict:
        return

    try:
        valve_types = [ValveType[str(v).upper()] if v is not None else None for v in valve_dict[Field.VALVE_TYPE]]
    except KeyError as e:
        raise ValveTypeError from e

    nones = itertools.repeat(None)
    pressures = valve_dict.get(Field.PRESSURE_SETTING, nones)
    flows = valve_dict.get(Field.FLOW_SETTING, nones)
    throttles = valve_dict.get(Field.THROTTLE_SETTING, nones)
    headloss_curves = valve_dict.get(Field.HEADLOSS_CURVE, nones)

    for valve_type, pressure, flow, throttle, curve in zip(valve_types, pressures, flows, throttles, headloss_curves):
        if valve_type is None:
            continue

        if valve_type in [ValveType.PRV, ValveType.PSV, ValveType.PBV]:
            if pressure is None:
                raise ValveSettingError(valve_type)

        elif valve_type is ValveType.FCV:
            if flow is None:
                raise ValveSettingError(valve_type)

        elif valve_type is ValveType.TCV:
            if throttle is None:
                raise ValveSettingError(valve_type)

        elif valve_type is ValveType.GPV:
            try:
                curve = Curve.factory(curve) if curve is not None else None
            except ValueError as e:
                raise CurveError(ModelLayer.VALVES, Field.HEADLOSS_CURVE, e) from e

            if curve is None:
                raise ValveSettingError(valve_type)


def _check_pump_parameters(pump_dict: Mapping[str, Iterable]) -> None:
    if not pump_dict:
        return

    if Field.PUMP_TYPE not in pump_dict:
        raise PumpTypeError

    try:
        pump_types = [PumpTypes[str(p).upper()] if p is not None else None for p in pump_dict[Field.PUMP_TYPE]]
    except KeyError as e:
        raise PumpTypeError from e

    nones = itertools.repeat(None)
    powers = pump_dict.get(Field.POWER, nones)
    curves = pump_dict.get(Field.PUMP_CURVE, nones)
    for pump_type, power, curve in zip(pump_types, powers, curves):
        if pump_type is None:
            continue

        if pump_type is PumpTypes.POWER:
            if power is None:
                raise PumpPowerError

            try:
                if float(power) <= 0:
                    raise PumpPowerError
            except (TypeError, ValueError):
                continue

        elif pump_type is PumpTypes.HEAD:
            try:
                curve = Curve.factory(curve) if curve is not None else None
            except ValueError as e:
                raise CurveError(ModelLayer.PUMPS, Field.PUMP_CURVE, e) from e

            if curve is None:
                raise PumpCurveMissingError


def _check_link_connects_to_nodes(network: Network) -> None:
    """Check that link is connected to two nodes."""

    missing_connection = [link for link, node in network.link_start_nodes.items() if node is None] + [
        link for link, node in network.link_end_nodes.items() if node is None
    ]

    if not missing_connection:
        return

    raise LinkNotConnectedToNodesError(missing_connection)


class LinkNotConnectedToNodesError(VerificationError):
    def __init__(self, links: list[str]):
        super().__init__(
            tr("The following links do not connect to a node at each end: {links}").format(links=", ".join(links))
        )


def _check_link_ends_not_same_node(network: Network) -> None:
    """Check that link does not connect to the same node on both ends."""

    has_matching_ends = [
        name for name, start in network.link_start_nodes.items() if start and network.link_end_nodes[name] == start
    ]

    if not has_matching_ends:
        return

    raise LinkEndsSameNodeError(has_matching_ends)


class LinkEndsSameNodeError(VerificationError):
    """Raised when a link connects to the same node on both ends."""

    def __init__(self, duplicate_links: list[str]):
        super().__init__(
            tr("{num_features} links have the same start and end nodes: {links}").format(
                num_features=len(duplicate_links), links=", ".join(duplicate_links)
            )
        )


def _check_no_orphan_junctions(junctions_layer: Mapping[str, Iterable], network: Network) -> None:
    """Only consider junctions as reservoirs/tanks may be unconnected intentionally."""
    connected_nodes = set(network.link_start_nodes.values()) | set(network.link_end_nodes.values())

    if not connected_nodes:
        # not worth testing if there are no links
        return

    if Field.NAME not in junctions_layer:
        return

    junction_names = junctions_layer[Field.NAME]

    orphan_junctions = [str(name) for name in junction_names if name is not None and name not in connected_nodes]

    if orphan_junctions:
        raise OrphanJunctionsError(orphan_junctions)


class OrphanJunctionsError(VerificationError):
    """Raised when there are orphan nodes in the model."""

    def __init__(self, orphan_nodes: list[str]):
        super().__init__(
            tr("The following junctions are not connected to any links: {nodes}").format(nodes=", ".join(orphan_nodes))
        )


def _check_no_overlapping_nodes(network: Network) -> None:
    if len(set(network.node_coordinates.values())) == len(network.node_coordinates):
        return

    seen_coords = []
    duplicate_coords = []
    for coords in network.node_coordinates.values():
        if coords in seen_coords:
            duplicate_coords.append(coords)
        else:
            seen_coords.append(coords)

    duplicate_node_names: list[list[str]] = []

    for duplicate in set(duplicate_coords):
        duplicate_node_names.append([name for name, coord in network.node_coordinates.items() if coord == duplicate])

    if duplicate_node_names:
        raise OverlappingNodesError(duplicate_node_names)


class OverlappingNodesError(VerificationError):
    """Raised when there are multiple nodes with the same coordinates."""

    def __init__(self, node_names: list[list[str]]):
        node_string = "; ".join([", ".join(group) for group in node_names])
        super().__init__(
            tr(
                "The following nodes have overlapping coordinates - it will not be possible to know which node each link connects to: {nodes}"  # noqa: E501
            ).format(nodes=node_string)
        )


class EmptyModelError(VerificationError):
    """Raised when the model contains no elements."""

    def __init__(self) -> None:
        super().__init__(tr("The model is empty."))


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


class PipeLengthMissingError(VerificationError):
    """Raised when the LENGTH field is missing from the pipes layer."""

    def __init__(self):
        super().__init__(
            tr("In Pipes, lengths could not be calculated and length field is missing or contains blanks.")
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
