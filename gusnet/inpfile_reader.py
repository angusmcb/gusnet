from __future__ import annotations

import dataclasses
import datetime
import enum
import itertools
import os
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from types import MappingProxyType
from typing import Any

from gusnet.elements import (
    DEFAULT_OPTIONS,
    DemandType,
    Field,
    FlowUnit,
    HeadlossFormula,
    ModelLayer,
    ModelOptions,
    PumpTypes,
    QualityParameter,
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
) -> tuple[Mapping[ModelLayer, Mapping], Network, ModelOptions]:
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
        tanks = _read_tanks(sections[Sections.TANKS], curves)

        node_quality = _read_quality(sections[Sections.QUALITY])
        _add_quality_to_nodes(junctions, node_quality)
        _add_quality_to_nodes(reservoirs, node_quality)
        _add_quality_to_nodes(tanks, node_quality)

        pipes = _make_table(
            sections[Sections.PIPES],
            (
                Field.NAME,
                "_from",
                "_to",
                Field.LENGTH,
                Field.DIAMETER,
                Field.ROUGHNESS,
                Field.MINOR_LOSS,
                Field.INITIAL_STATUS,
            ),
        )

        pumps = _read_pumps(sections[Sections.PUMPS], curves, status)

        valves = _read_valves(sections[Sections.VALVES], curves, status)

        model_layers = {}
        if junctions:
            model_layers[ModelLayer.JUNCTIONS] = junctions
        if reservoirs:
            model_layers[ModelLayer.RESERVOIRS] = reservoirs
        if tanks:
            model_layers[ModelLayer.TANKS] = tanks
        if pipes:
            model_layers[ModelLayer.PIPES] = pipes
        if pumps:
            model_layers[ModelLayer.PUMPS] = pumps
        if valves:
            model_layers[ModelLayer.VALVES] = valves

        network = _get_network(sections)

    except Exception as e:
        raise InpFileReadError(e) from e

    model_layer_mapping = MappingProxyType({k: MappingProxyType(v) for k, v in model_layers.items()})

    return model_layer_mapping, network, options


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


def read_sections_from_file(file_path: os.PathLike | str) -> dict[Sections, list[list[str]]]:
    with Path(file_path).open("r", encoding="utf-8") as file:
        lines = file.readlines()

        lines_without_comments = [line.split(";")[0].strip() for line in lines]

        non_empty_lines = [line for line in lines_without_comments if line]

        sections: dict[Sections, list[list[str]]] = {section: [] for section in Sections}

        for line in non_empty_lines:
            if line.startswith("[") and line.endswith("]"):
                section_string = line[1:-1].upper()
                if section_string in Sections:
                    current_section = Sections[section_string]
                    sections[current_section] = []
                else:
                    current_section = None
            else:
                if current_section:
                    split_line = line.split()
                    sections[current_section].append(split_line)

    return sections


def _make_table(lines: list[list], titles: tuple) -> dict:
    columns = [col for col in itertools.zip_longest(*lines)]

    table = {title: column for title, column in zip(titles, columns)}

    return table


def _read_patterns(lines: list[list[str]]) -> dict[str, Pattern]:
    pattern_multipliers: dict[str, list] = {}

    for line in lines:
        pattern_name = line[0]
        multipliers = line[1:]
        if pattern_name in pattern_multipliers:
            pattern_multipliers[pattern_name].extend(multipliers)
        else:
            pattern_multipliers[pattern_name] = multipliers

    return {name: Pattern(multipliers) for name, multipliers in pattern_multipliers.items()}


def _read_curves(lines: list[list[str]]) -> dict[str, Curve]:
    curve_points: dict[str, list[tuple[float, float]]] = {}

    for line in lines:
        curve_name = line[0]
        if curve_name not in curve_points:
            curve_points[curve_name] = []

        point = (float(line[1]), float(line[2]))

        curve_points[curve_name].append(point)

    return {name: Curve(points) for name, points in curve_points.items()}


def _read_status(lines: list[list[str]]) -> dict[str, str]:
    status_dict = {}
    for line in lines:
        name = line[0]
        status = line[1]
        status_dict[name] = status
    return status_dict


def _read_junctions(lines: list[list[str]], patterns: dict[str, Pattern]) -> dict:
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


def _read_reservoirs(lines: list[list[str]], patterns: dict[str, Pattern]) -> dict:
    reservoirs = _make_table(lines, (Field.NAME, Field.BASE_HEAD, Field.HEAD_PATTERN))

    if Field.HEAD_PATTERN in reservoirs:
        reservoirs[Field.HEAD_PATTERN] = [
            patterns.get(name) if name is not None else None for name in reservoirs[Field.HEAD_PATTERN]
        ]

    return reservoirs


def _read_tanks(lines: list[list[str]], curves: dict[str, Curve]) -> dict:
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

    return tanks


def _read_pumps(lines: list[list[str]], curves: Mapping[str, Curve], status: Mapping[str, str]) -> dict:
    processed_lines = []

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

        pump_status = status.get(name, None)

        processed_lines.append([name, pump_type, power, head_curve, speed, efficiency, pump_status])

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


def _read_valves(lines: list[list[str]], curves: dict[str, Curve], status: Mapping[str, str]) -> dict:
    processed_lines = []

    for line in lines:
        valve_type = pressure_setting = flow_setting = throttle_setting = headloss_curve = minor_loss = None

        name = line[0]

        valve_type = line[4].upper()
        if valve_type == "PRV" or valve_type == "PSV" or valve_type == "PBV":
            pressure_setting = line[5]
        elif valve_type == "FCV":
            flow_setting = line[5]
        elif valve_type == "TCV":
            throttle_setting = line[5]
        elif valve_type == "GPV":
            headloss_curve = curves.get(line[5]) if line[5] is not None else None

        minor_loss = line[6] if len(line) > 6 else None

        valve_status = status.get(name, None)

        processed_lines.append(
            [
                name,
                line[3],
                valve_type,
                pressure_setting,
                flow_setting,
                throttle_setting,
                headloss_curve,
                minor_loss,
                valve_status,
            ]
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


class OptKey(enum.Enum):
    UNITS = "units"
    HEADLOSS = "headloss"
    DEMAND_MODEL = "demand model"
    MINIMUM_PRESSURE = "minimum pressure"
    REQUIRED_PRESSURE = "required pressure"
    PRESSURE_EXPONENT = "pressure exponent"
    DEMAND_MULTIPLIER = "demand multiplier"
    PATTERN = "pattern"
    EMITTER_EXPONENT = "emitter exponent"
    QUALITY = "quality"
    DIFFUSIVITY = "diffusivity"
    DURATION = "duration"
    QUALITY_TIMESTEP = "quality timestep"


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


EMPTY_DEFAULT = tuple([None])


@dataclasses.dataclass
class OptData:
    units: Sequence = tuple([FlowUnit.GPM.value])
    headloss: Sequence = tuple([HeadlossFormula.HAZEN_WILLIAMS.value])

    demand_model: Sequence = tuple([DemandType.FIXED.value])
    minimum_pressure: Sequence = tuple([0])
    required_prewsure: Sequence = tuple([None])
    pressure_expontent: Sequence = tuple([0.5])

    demand_multiplier: Sequence = tuple([1.0])
    pattern: Sequence = tuple(["1"])


@dataclasses.dataclass
class TimeData:
    duration: Sequence = tuple([None])


def _fill_dataclass(dclass: Any, data_lines: list[list[str]]) -> None:
    field_names = [f.name for f in dataclasses.fields(dclass)]
    for line in data_lines:
        key2 = "_".join(line[:2]).lower()
        if key2 in field_names and len(line) > 2:
            setattr(dclass, key2, line[2:])
            continue

        key = line[0].lower()
        if key in field_names and len(line) > 1:
            setattr(dclass, key, line[1:])


def _read_options(
    options_lines: list[list[str]],
    times_lines: list[list[str]],
    energy_lines: list[list[str]],
    reactions_lines: list[list[str]],
    patterns: dict[str, Pattern],
) -> ModelOptions:
    all_lines = options_lines + times_lines + energy_lines + reactions_lines

    opt_data = OptData()
    _fill_dataclass(opt_data, options_lines)
    times_data = TimeData()
    _fill_dataclass(times_data, times_lines)

    opt_dict: dict[OptKey, list[str]] = {}
    for line in all_lines:
        # prefer two word keys if they exist
        key2 = " ".join(line[:2]).lower()
        if key2 in OptKey:
            opt_dict[OptKey(key2)] = line[2:]
            continue

        key = line[0].lower()
        if key in OptKey:
            opt_dict[OptKey(key)] = line[1:]

    flow_unit = FlowUnit(opt_data.units[0] or FlowUnit.GPM)
    headloss = HeadlossFormula(opt_data.headloss[0] or HeadlossFormula.HAZEN_WILLIAMS)

    demand_model = DemandType(opt_data.demand_model[0])

    minimum_pressure = float(opt_data.minimum_pressure[0])
    required_pressure = float(opt_data.required_prewsure[0] or minimum_pressure + 0.1)
    pressure_exponent = float(opt_data.pressure_expontent[0])

    demand_multiplier = float(opt_data.demand_multiplier[0])
    default_pattern = patterns.get(opt_data.pattern[0], Pattern())

    emitter_exponent = float(opt_dict[OptKey.EMITTER_EXPONENT][0]) if OptKey.EMITTER_EXPONENT in opt_dict else 0.5

    relative_diffusivity = float(opt_dict[OptKey.DIFFUSIVITY][0] if OptKey.DIFFUSIVITY in opt_dict else 0.0)

    if OptKey.QUALITY in opt_dict:
        if opt_dict[OptKey.QUALITY][0].upper() not in QualityParameter.__members__:
            quality_value = QualityParameter.CHEMICAL
        else:
            quality_value = QualityParameter(opt_dict[OptKey.QUALITY][0].upper())
    else:
        quality_value = QualityParameter.NONE

    trace_node = (
        opt_dict[OptKey.QUALITY][1]
        if quality_value is QualityParameter.TRACE and OptKey.QUALITY in opt_dict and len(opt_dict[OptKey.QUALITY]) > 1
        else ""
    )
    simulation_duration = _list_to_timedelta(times_data.duration) if times_data.duration[0] else datetime.timedelta(0)

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
        energy_price=DEFAULT_OPTIONS.energy_price,
        energy_pattern=DEFAULT_OPTIONS.energy_pattern,
        energy_pump_efficiency=DEFAULT_OPTIONS.energy_pump_efficiency,
        energy_demand_charge=DEFAULT_OPTIONS.energy_demand_charge,
        quality_parameter=quality_value,
        mass_unit=DEFAULT_OPTIONS.mass_unit,
        relative_diffusivity=relative_diffusivity,
        trace_node=trace_node,
        quality_tolerance=DEFAULT_OPTIONS.quality_tolerance,
        bulk_reaction_order=DEFAULT_OPTIONS.bulk_reaction_order,
        wall_reaction_order=DEFAULT_OPTIONS.wall_reaction_order,
        global_bulk_coefficient=DEFAULT_OPTIONS.global_bulk_coefficient,
        global_wall_coefficient=DEFAULT_OPTIONS.global_wall_coefficient,
        limiting_concentration=DEFAULT_OPTIONS.limiting_concentration,
        wall_coefficient_correlation=DEFAULT_OPTIONS.wall_coefficient_correlation,
    )


def _read_quality(quality_lines: list[list[str]]) -> dict[str, float]:
    return {line[0]: float(line[1]) for line in quality_lines}


def _add_quality_to_nodes(nodes: dict[str, list], node_quality: dict[str, float]) -> None:
    if Field.NAME in nodes and node_quality:
        nodes[Field.INITIAL_QUALITY] = [node_quality.get(name) for name in nodes[Field.NAME]]


def _get_network(sections: dict[Sections, list[list[str]]]) -> Network:
    network = Network()

    coordinate_tuples = [(line[0], (float(line[1]), float(line[2]))) for line in sections[Sections.COORDINATES]]

    network.add_nodes_from_points(*zip(*coordinate_tuples))

    connections = [
        line[0:3] for line in [*sections[Sections.PIPES], *sections[Sections.PUMPS], *sections[Sections.VALVES]]
    ]
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


if __name__ == "__main__":
    inp_path = Path(__file__).parent / "resources" / "examples" / "ky10.inp"
    sections, network, dclass = read_inp_file(inp_path)
    for section, lines in sections.items():
        print(f"Section: {section}")
        for line in list(lines.values()):
            print(f"  {line}")
        print()
    print("Network:")
    print(dclass)
