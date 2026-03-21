from __future__ import annotations

import dataclasses
import datetime
import enum
import itertools
import os
import sys
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from types import MappingProxyType
from typing import Any

from gusnet.elements import (
    DEFAULT_OPTIONS,
    DemandType,
    Field,
    FlowUnit,
    HeadlossFormula,
    Model,
    ModelLayer,
    ModelOptions,
    PumpTypes,
    QualityParameter,
    WallReactionOrder,
)
from gusnet.i18n import tr
from gusnet.network import Network
from gusnet.pattern_curve import Curve, Pattern

if sys.version_info >= (3, 11):
    from enum import StrEnum
else:
    from gusnet.strenum import StrEnum  # noqa: F401


def read_inp_file(
    file_path: os.PathLike | str,
) -> Model:
    try:
        sections = read_sections_from_file(file_path)
    except FileNotFoundError as e:
        raise InpFileNotFoundError(file_path) from e

    try:
        patterns = _read_patterns(sections[Sections.PATTERNS])

        curves = _read_curves(sections[Sections.CURVES])

        status = _read_status(sections[Sections.STATUS])

        options = _read_options(
            sections[Sections.OPTIONS],
            sections[Sections.TIMES],
            sections[Sections.ENERGY],
            sections[Sections.REACTIONS],
            patterns,
        )

        junctions = _read_junctions(sections[Sections.JUNCTIONS], patterns)
        reservoirs = _read_reservoirs(sections[Sections.RESERVOIRS], patterns)
        tanks = _read_tanks(sections[Sections.TANKS], curves, sections[Sections.REACTIONS], sections[Sections.MIXING])

        node_quality = _read_quality(sections[Sections.QUALITY])
        _add_quality_to_nodes(junctions, node_quality)
        _add_quality_to_nodes(reservoirs, node_quality)
        _add_quality_to_nodes(tanks, node_quality)

        pipes = _read_pipes(sections[Sections.PIPES], sections[Sections.REACTIONS], status)
        pumps = _read_pumps(sections[Sections.PUMPS], curves, status)
        valves = _read_valves(sections[Sections.VALVES], curves, status)

        network = _get_network(sections)

    except Exception as e:
        raise InpFileReadError(e) from e

    model_layers = {
        ModelLayer.JUNCTIONS: junctions,
        ModelLayer.RESERVOIRS: reservoirs,
        ModelLayer.TANKS: tanks,
        ModelLayer.PIPES: pipes,
        ModelLayer.PUMPS: pumps,
        ModelLayer.VALVES: valves,
    }

    if all(not v for v in model_layers.values()):
        raise InpFileReadError(tr("No valid sections found in input file."))

    return Model(network, options, model_layers)


class Sections(enum.Enum):
    JUNCTIONS = "JUNCTIONS"
    RESERVOIRS = "RESERVOIRS"
    TANKS = "TANKS"
    PIPES = "PIPES"
    PUMPS = "PUMPS"
    VALVES = "VALVES"
    CURVES = "CURVES"
    PATTERNS = "PATTERNS"
    ENERGY = "ENERGY"
    STATUS = "STATUS"
    QUALITY = "QUALITY"
    REACTIONS = "REACTIONS"
    MIXING = "MIXING"
    OPTIONS = "OPTIONS"
    TIMES = "TIMES"
    COORDINATES = "COORDINATES"
    VERTICES = "VERTICES"


class Line(tuple[str, ...]):
    line_number: int

    def __new__(cls, *values: str, line_number: int):
        obj = super().__new__(cls, values)
        obj.line_number = line_number
        return obj


def read_sections_from_file(file_path: os.PathLike | str) -> MappingProxyType[Sections, tuple[Line, ...]]:
    with Path(file_path).open("r", encoding="utf-8") as file:
        lines = file.readlines()

        lines_without_comments = [line.split(";")[0].strip() for line in lines]

        sections: dict[Sections, list[Line]] = {section: [] for section in Sections}

        for line_number, line in enumerate(lines_without_comments, start=1):
            if not line:
                continue

            if line.startswith("[") and line.endswith("]"):
                section_string = line[1:-1].upper().strip()
                if section_string in [section.name for section in Sections]:
                    current_section = Sections[section_string]
                else:
                    current_section = None
            else:
                if current_section:
                    split_line = line.split()
                    sections[current_section].append(Line(*split_line, line_number=line_number))

    return MappingProxyType({section: tuple(lines) for section, lines in sections.items()})


def _make_table(lines: Iterable[Sequence[str | None]], titles: tuple) -> dict:
    columns = [col for col in itertools.zip_longest(*lines)]

    table = {title: column for title, column in zip(titles, columns)}

    return table


def _read_patterns(lines: Iterable[Sequence[str]]) -> MappingProxyType[str, Pattern]:
    pattern_multipliers: dict[str, list] = {}

    for line in lines:
        pattern_name = line[0]
        multipliers = line[1:]
        if pattern_name in pattern_multipliers:
            pattern_multipliers[pattern_name].extend(multipliers)
        else:
            pattern_multipliers[pattern_name] = list(multipliers)

    return MappingProxyType({name: Pattern(multipliers) for name, multipliers in pattern_multipliers.items()})


def _read_curves(lines: Iterable[Sequence[str]]) -> dict[str, Curve]:
    curve_points: dict[str, list[tuple[float, float]]] = {}

    for line in lines:
        curve_name = line[0]
        if curve_name not in curve_points:
            curve_points[curve_name] = []

        point = (float(line[1]), float(line[2]))

        curve_points[curve_name].append(point)

    return {name: Curve(points) for name, points in curve_points.items()}


def _read_status(lines: Iterable[Sequence[str]]) -> dict[str, str]:
    return {line[0]: line[1].upper() for line in lines if len(line) > 1}


def _read_junctions(lines: Iterable[Sequence[str]], patterns: Mapping[str, Pattern]) -> dict:
    junctions = _make_table(lines, (Field.NAME, Field.ELEVATION, Field.BASE_DEMAND, Field.DEMAND_PATTERN))
    if Field.BASE_DEMAND in junctions:
        junctions[Field.BASE_DEMAND] = [
            float(demand) if demand is not None and demand != "*" else None for demand in junctions[Field.BASE_DEMAND]
        ]
    if Field.DEMAND_PATTERN in junctions:
        junctions[Field.DEMAND_PATTERN] = [
            patterns[name] if name is not None else None for name in junctions[Field.DEMAND_PATTERN]
        ]

    return junctions


def _read_reservoirs(lines: Iterable[Sequence[str]], patterns: Mapping[str, Pattern]) -> dict:
    reservoirs = _make_table(lines, (Field.NAME, Field.BASE_HEAD, Field.HEAD_PATTERN))

    if Field.HEAD_PATTERN in reservoirs:
        reservoirs[Field.HEAD_PATTERN] = [
            patterns.get(name) if name is not None else None for name in reservoirs[Field.HEAD_PATTERN]
        ]

    return reservoirs


def _read_tanks(
    lines: Iterable[Sequence[str]],
    curves: Mapping[str, Curve],
    reaction_data: Iterable[Sequence[str]],
    mixing_data: Iterable[Sequence[str]],
) -> dict:
    tanks = _make_table(
        lines,
        (
            Field.NAME,
            Field.ELEVATION,
            Field.INIT_LEVEL,
            Field.MIN_LEVEL,
            Field.MAX_LEVEL,
            Field.TANK_DIAMETER,
            Field.MIN_VOL,
            Field.VOL_CURVE,
            Field.OVERFLOW,
        ),
    )
    if Field.VOL_CURVE in tanks:
        tanks[Field.VOL_CURVE] = [curves.get(name) if name is not None else None for name in tanks[Field.VOL_CURVE]]

    if tanks:
        mixing_type = {parts[0]: parts[1] for parts in mixing_data}
        comp_ratio = {
            parts[0]: float(parts[2]) for parts in mixing_data if len(parts) > 2 and parts[1].upper() == "2COMP"
        }

        tanks[Field.MIXING_MODEL] = [mixing_type.get(name) for name in tanks[Field.NAME]]
        tanks[Field.MIXING_FRACTION] = [comp_ratio.get(name) for name in tanks[Field.NAME]]

        reaction_order = {parts[1]: float(parts[2]) for parts in reaction_data if parts[0].lower() == "tank"}
        tanks[Field.BULK_COEFF] = [reaction_order.get(name, 0.0) for name in tanks[Field.NAME]]

    return tanks


def _read_pipes(
    lines: Iterable[Sequence[str]], reaction_data: Iterable[Sequence[str]], status: Mapping[str, str]
) -> dict:
    processed_lines: list[tuple] = []

    for line in lines:
        name = line[0]
        length = line[3]
        diameter = line[4]
        roughness = line[5]
        minor_loss = line[6] if len(line) > 6 else None
        initial_status_read = line[7].upper() if len(line) > 7 else None

        if initial_status_read == "CLOSED" or status.get(name) == "CLOSED":
            initial_status = "CLOSED"
            cv = False
        elif initial_status_read == "CV" or status.get(name) == "CV":
            initial_status = "OPEN"
            cv = True
        else:
            initial_status = "OPEN"
            cv = False

        processed_lines.append((name, length, diameter, roughness, minor_loss, initial_status, cv))

    pipes = _make_table(
        processed_lines,
        (
            Field.NAME,
            Field.LENGTH,
            Field.DIAMETER,
            Field.ROUGHNESS,
            Field.MINOR_LOSS,
            Field.INITIAL_STATUS,
            Field.CHECK_VALVE,
        ),
    )
    if pipes:
        bulk_reaction_order = {parts[1]: float(parts[2]) for parts in reaction_data if parts[0].lower() == "bulk"}
        wall_reaction_order = {parts[1]: float(parts[2]) for parts in reaction_data if parts[0].lower() == "wall"}

        pipes[Field.BULK_COEFF] = [bulk_reaction_order.get(name, 0.0) for name in pipes[Field.NAME]]
        pipes[Field.WALL_COEFF] = [wall_reaction_order.get(name, 0.0) for name in pipes[Field.NAME]]

    return pipes


def _read_pumps(lines: Iterable[Sequence[str]], curves: Mapping[str, Curve], status: Mapping[str, str]) -> dict:
    processed_lines: list[tuple[str | None, ...]] = []

    for line in lines:
        name = line[0]
        pump_type = head_curve = power = speed = efficiency = None
        for i in range(3, len(line), 2):
            if line[i] == "HEAD":
                pump_type = PumpTypes.HEAD.value
                head_curve = curves[line[i + 1]]
            elif line[i] == "POWER":
                pump_type = PumpTypes.POWER.value
                power = line[i + 1]
            elif line[i] == "EFFICIENCY":
                efficiency = curves[line[i + 1]]
            elif line[i] == "SPEED":
                speed = line[i + 1]

        pump_status = status.get(name, "OPEN").upper()

        if pump_status not in ("OPEN", "CLOSED"):
            speed = pump_status
            pump_status = "OPEN"

        processed_lines.append((name, pump_type, power, head_curve, speed, efficiency, pump_status))

    return _make_table(
        processed_lines,
        (
            Field.NAME,
            Field.PUMP_TYPE,
            Field.POWER,
            Field.PUMP_CURVE,
            Field.BASE_SPEED,
            Field.EFFICIENCY_CURVE,
            Field.INITIAL_STATUS,
        ),
    )


def _read_valves(lines: Iterable[Sequence[str]], curves: dict[str, Curve], status: Mapping[str, str]) -> dict:
    processed_lines: list[tuple[str | None, ...]] = []

    for line in lines:
        valve_type = pressure_setting = flow_setting = throttle_setting = headloss_curve = minor_loss = None

        name = line[0]

        valve_setting = line[5] if len(line) > 5 else None

        valve_status = status.get(name, "ACTIVE").upper()
        if valve_status not in ("ACTIVE", "OPEN", "CLOSED"):
            valve_setting = valve_status
            valve_status = "ACTIVE"

        valve_type = line[4].upper()
        if valve_type == "PRV" or valve_type == "PSV" or valve_type == "PBV":
            pressure_setting = valve_setting
        elif valve_type == "FCV":
            flow_setting = valve_setting
        elif valve_type == "TCV":
            throttle_setting = valve_setting
        elif valve_type == "GPV":
            headloss_curve = curves.get(valve_setting) if valve_setting is not None else None

        minor_loss = line[6] if len(line) > 6 else None

        processed_lines.append(
            (
                name,
                line[3],
                valve_type,
                pressure_setting,
                flow_setting,
                throttle_setting,
                headloss_curve,
                minor_loss,
                valve_status,
            )
        )

    return _make_table(
        processed_lines,
        (
            Field.NAME,
            Field.DIAMETER,
            Field.VALVE_TYPE,
            Field.PRESSURE_SETTING,
            Field.FLOW_SETTING,
            Field.THROTTLE_SETTING,
            Field.HEADLOSS_CURVE,
            Field.MINOR_LOSS,
            Field.VALVE_STATUS,
        ),
    )


def _list_to_timedelta(parts: Sequence[str]) -> datetime.timedelta:
    unit = parts[1].lower() if len(parts) == 2 else "hours"
    if unit in ("sec", "seconds"):
        return datetime.timedelta(seconds=float(parts[0]))
    elif unit in ("min", "minutes"):
        return datetime.timedelta(minutes=float(parts[0]))
    elif unit in ("hr", "hours"):
        hour_parts = parts[0].split(":")
        hours = float(hour_parts[0])
        minutes = float(hour_parts[1]) if len(hour_parts) > 1 else 0.0
        return datetime.timedelta(hours=hours, minutes=minutes)
    elif unit == "days":
        return datetime.timedelta(days=float(parts[0]))
    else:
        raise ValueError


@dataclasses.dataclass
class OptData:
    units: Sequence = (None,)
    headloss: Sequence = (None,)

    demand_model: Sequence = (None,)
    minimum_pressure: Sequence = (None,)
    required_pressure: Sequence = (None,)
    pressure_exponent: Sequence = (None,)

    demand_multiplier: Sequence = (None,)
    pattern: Sequence = (None,)

    emitter_exponent: Sequence = (None,)
    quality: Sequence = (None,)
    diffusivity: Sequence = (None,)
    tolerance: Sequence = (None,)


@dataclasses.dataclass
class TimeData:
    duration: Sequence = (None,)


@dataclasses.dataclass
class ReactionData:
    order_bulk: Sequence = (None,)
    order_wall: Sequence = (None,)
    order_tank: Sequence = (None,)
    global_bulk: Sequence = (None,)
    global_wall: Sequence = (None,)
    limiting_potential: Sequence = (None,)
    roughness_correlation: Sequence = (None,)


@dataclasses.dataclass
class EnergyData:
    global_price: Sequence = (None,)
    global_pattern: Sequence = (None,)
    global_effic: Sequence = (None,)
    demand_charge: Sequence = (None,)


def _fill_dataclass(dclass: Any, data_lines: Iterable[Sequence[str]]) -> None:
    field_names = set([f.name for f in dataclasses.fields(dclass)])
    for line in data_lines:
        key2 = "_".join(line[:2]).lower()
        if key2 in field_names and len(line) > 2:
            setattr(dclass, key2, line[2:])
            continue

        key = line[0].lower()
        if key in field_names and len(line) > 1:
            setattr(dclass, key, line[1:])


def _read_options(
    options_lines: Iterable[Sequence[str]],
    times_lines: Iterable[Sequence[str]],
    energy_lines: Iterable[Sequence[str]],
    reactions_lines: Iterable[Sequence[str]],
    patterns: Mapping[str, Pattern],
) -> ModelOptions:
    opt_data = OptData()
    _fill_dataclass(opt_data, options_lines)
    times_data = TimeData()
    _fill_dataclass(times_data, times_lines)
    energy_data = EnergyData()
    _fill_dataclass(energy_data, energy_lines)
    reaction_data = ReactionData()
    _fill_dataclass(reaction_data, reactions_lines)

    flow_unit = FlowUnit(opt_data.units[0] or FlowUnit.GPM)
    headloss = HeadlossFormula(opt_data.headloss[0] or HeadlossFormula.HAZEN_WILLIAMS)

    demand_model = DemandType(opt_data.demand_model[0] or DemandType.FIXED)

    minimum_pressure = float(opt_data.minimum_pressure[0] or 0.0)
    required_pressure = float(opt_data.required_pressure[0] or minimum_pressure + 0.1)
    pressure_exponent = float(opt_data.pressure_exponent[0] or 0.5)

    demand_multiplier = float(opt_data.demand_multiplier[0] or 1.0)
    default_pattern = patterns.get(opt_data.pattern[0] or "1", Pattern())

    emitter_exponent = float(opt_data.emitter_exponent[0] or 0.5)

    relative_diffusivity = float(opt_data.diffusivity[0] or 0.0)

    if opt_data.quality[0] is not None:
        if opt_data.quality[0].upper() not in QualityParameter.__members__:
            quality_value = QualityParameter.CHEMICAL
        else:
            quality_value = QualityParameter(opt_data.quality[0].upper())
    else:
        quality_value = QualityParameter.NONE

    trace_node = opt_data.quality[1] if quality_value is QualityParameter.TRACE and len(opt_data.quality) > 1 else ""
    quality_tolerance = float(opt_data.tolerance[0] or 0.01)

    simulation_duration = _list_to_timedelta(times_data.duration) if times_data.duration[0] else datetime.timedelta(0)

    energy_price = float(energy_data.global_price[0] or 0.0)
    energy_pattern = (
        patterns.get(energy_data.global_pattern[0], Pattern()) if energy_data.global_pattern[0] else Pattern()
    )
    energy_pump_efficiency = float(energy_data.global_effic[0] or 75)
    energy_demand_charge = float(energy_data.demand_charge[0] or 0.0)

    bulk_reaction_order = float(reaction_data.order_bulk[0] or 1.0)

    wall_reaction_order_float = float(reaction_data.order_wall[0] or 1.0)
    if wall_reaction_order_float == 1.0:
        wall_reaction_order = WallReactionOrder.ONE
    elif wall_reaction_order_float == 0.0:
        wall_reaction_order = WallReactionOrder.ZERO
    else:
        raise ValueError(tr("Invalid wall reaction order value: {value}").format(value=reaction_data.order_wall[0]))

    # tank_reaction_order = float(reaction_data.order_tank[0] or 1.0)
    global_bulk_coefficient = float(reaction_data.global_bulk[0] or 0.0)
    global_wall_coefficient = float(reaction_data.global_wall[0] or 0.0)
    limiting_concentration = float(reaction_data.limiting_potential[0] or 0.0)
    wall_coefficient_correlation = float(reaction_data.roughness_correlation[0] or 0.0)

    return ModelOptions(
        flow_unit=flow_unit,
        headloss_formula=headloss,
        simulation_duration=simulation_duration,
        demand_multiplier=demand_multiplier,
        default_pattern=default_pattern,
        emitter_exponent=emitter_exponent,
        demand_type=demand_model,
        minimum_pressure=minimum_pressure,
        required_pressure=required_pressure,
        pressure_exponent=pressure_exponent,
        energy_report=DEFAULT_OPTIONS.energy_report,
        energy_price=energy_price,
        energy_pattern=energy_pattern,
        energy_pump_efficiency=energy_pump_efficiency,
        energy_demand_charge=energy_demand_charge,
        quality_parameter=quality_value,
        mass_unit=DEFAULT_OPTIONS.mass_unit,
        relative_diffusivity=relative_diffusivity,
        trace_node=trace_node,
        quality_tolerance=quality_tolerance,
        bulk_reaction_order=bulk_reaction_order,
        wall_reaction_order=wall_reaction_order,
        global_bulk_coefficient=global_bulk_coefficient,
        global_wall_coefficient=global_wall_coefficient,
        limiting_concentration=limiting_concentration,
        wall_coefficient_correlation=wall_coefficient_correlation,
    )


def _read_quality(quality_lines: Iterable[Sequence[str]]) -> dict[str, float]:
    return {line[0]: float(line[1]) for line in quality_lines}


def _add_quality_to_nodes(nodes: dict[str, list], node_quality: dict[str, float]) -> None:
    if Field.NAME in nodes and node_quality:
        nodes[Field.INITIAL_QUALITY] = [node_quality.get(name) for name in nodes[Field.NAME]]


def _get_network(sections: Mapping[Sections, Iterable[Sequence[str]]]) -> Network:
    network = Network()

    coordinate_tuples = [(line[0], (float(line[1]), float(line[2]))) for line in sections[Sections.COORDINATES]]

    if not coordinate_tuples:
        return network

    network.add_nodes_from_points(*zip(*coordinate_tuples))

    connections = [
        line[0:3] for line in [*sections[Sections.PIPES], *sections[Sections.PUMPS], *sections[Sections.VALVES]]
    ]

    if not connections:
        return network

    names, starts, ends = zip(*connections)

    vertices_dict: dict[str, list[tuple[float, float]]] = {}
    for line in sections[Sections.VERTICES]:
        link_name = line[0]
        x = float(line[1])
        y = float(line[2])
        if link_name not in vertices_dict:
            vertices_dict[link_name] = []
        vertices_dict[link_name].append((x, y))

    vertices_list = [vertices_dict.get(name, []) for name in names]

    network.add_links_from_nodes_and_vertices(names, starts, ends, vertices_list)
    return network


def _coordinates_to_points(coord_lines: list[list[str]]) -> tuple[list[str], list[tuple[float, float]]]:
    names, xs, ys = zip(*coord_lines)

    points = list(zip(map(float, xs), map(float, ys)))

    return list(names), points


class InpFileReadError(Exception):
    def __init__(self, error: Any):
        super().__init__(tr("Error reading input file. {parent_error}").format(parent_error=error))


class InpFileNotFoundError(InpFileReadError, FileNotFoundError):
    def __init__(self, input_file: os.PathLike | str):
        super().__init__(tr(".inp file does not exist ({input_file})").format(input_file=str(input_file)))
