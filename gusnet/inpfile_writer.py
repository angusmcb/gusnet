from __future__ import annotations

import itertools
import os
from collections.abc import Iterable, Mapping
from pathlib import Path

from gusnet.elements import CurveType, Field, ModelLayer, ModelOptions, QualityParameter, SimpleFieldType, ValveType
from gusnet.network import Network
from gusnet.pattern_curve import Curve, Pattern


def write_inp_file(
    elements: Mapping[ModelLayer, Mapping],
    options: ModelOptions,
    network: Network,
    file_path: os.PathLike | str,
    temp_hydraulics_file: os.PathLike | str | None = None,
) -> None:
    patterns = find_patterns(elements, options)
    curves = find_curves(elements)

    inp_file_dict = get_line_dict(elements, options, patterns, curves, network, temp_hydraulics_file)

    inp_file_writer(file_path, inp_file_dict)


def get_line_dict(
    elements: Mapping[ModelLayer, Mapping],
    options: ModelOptions,
    patterns: Mapping[Pattern, str],
    curves: Mapping[CurveType, Mapping[Curve, str]],
    network: Network,
    temp_hydraulics_file: os.PathLike | str | None,
) -> dict:
    inp_file_dict: dict[str, Iterable[str] | None] = {}

    junctions = elements.get(ModelLayer.JUNCTIONS)
    reservoirs = elements.get(ModelLayer.RESERVOIRS)
    tanks = elements.get(ModelLayer.TANKS)
    pipes = elements.get(ModelLayer.PIPES)
    pumps = elements.get(ModelLayer.PUMPS)
    valves = elements.get(ModelLayer.VALVES)

    inp_file_dict["JUNCTIONS"] = inp_file_junctions(junctions, patterns) if junctions is not None else None
    inp_file_dict["RESERVOIRS"] = inp_file_reservoirs(reservoirs, patterns) if reservoirs is not None else None
    inp_file_dict["TANKS"] = inp_file_tanks(tanks, curves) if tanks is not None else None
    inp_file_dict["PIPES"] = (
        inp_file_pipes(pipes, network.link_start_nodes, network.link_end_nodes) if pipes is not None else None
    )
    inp_file_dict["PUMPS"] = (
        inp_file_pumps(pumps, patterns, curves, network.link_start_nodes, network.link_end_nodes)
        if pumps is not None
        else None
    )
    inp_file_dict["VALVES"] = (
        inp_file_valves(valves, curves, network.link_start_nodes, network.link_end_nodes)
        if valves is not None
        else None
    )
    inp_file_dict["EMITTERS"] = inp_file_emitters(junctions) if junctions is not None else None
    inp_file_dict["CURVES"] = inp_file_curves(curves)
    inp_file_dict["PATTERNS"] = inp_file_patterns(patterns)
    inp_file_dict["ENERGY"] = inp_file_energy(options, patterns, pumps, curves)
    inp_file_dict["STATUS"] = inp_file_status(valves, pumps)
    inp_file_dict["QUALITY"] = inp_file_quality(junctions, tanks, reservoirs)
    inp_file_dict["REACTIONS"] = inp_file_reactions(options)
    inp_file_dict["MIXING"] = inp_file_mixing(tanks) if tanks is not None else None
    inp_file_dict["OPTIONS"] = inp_file_options(options, temp_hydraulics_file)
    inp_file_dict["TIMES"] = inp_file_times(options)
    inp_file_dict["COORDINATES"] = (f"{name} {coord[0]} {coord[1]}" for name, coord in network.node_coordinates.items())
    inp_file_dict["VERTICES"] = (
        f"{name} {coord[0]} {coord[1]}" for name, vertices in network.link_middle_vertices.items() for coord in vertices
    )
    return inp_file_dict


def find_patterns(elements: Mapping[ModelLayer, Mapping], options: ModelOptions) -> dict[Pattern, str]:
    patterns: list[Pattern | None] = []

    first_pattern_name = 2

    if options.default_pattern:
        patterns.append(options.default_pattern)
        first_pattern_name = 1

    if options.energy_pattern:
        patterns.append(options.energy_pattern)

    for layer_dict in elements.values():
        for fieldname in layer_dict:
            try:
                parameter = Field(fieldname).type
            except ValueError:
                continue
            if parameter == SimpleFieldType.PATTERN:
                # layer_dict[fieldname] = [
                #     Pattern(p) if p is not None and Pattern(p) else None for p in layer_dict[fieldname]
                # ]
                patterns.extend(layer_dict[fieldname])

    counter = itertools.count(start=first_pattern_name)

    unique_patterns = list(dict.fromkeys(p for p in patterns if p is not None))

    return {pattern: str(next(counter)) for pattern in unique_patterns}


def find_curves(elements: Mapping[ModelLayer, Mapping]) -> dict[CurveType, dict[Curve, str]]:
    curves: dict[CurveType, set[Curve]] = {}

    for layer_dict in elements.values():
        for fieldname in layer_dict:
            try:
                parameter = Field(fieldname).type
            except ValueError:
                continue
            if isinstance(parameter, CurveType):
                # layer_dict[fieldname] = [Curve.factory(c) if c is not None else None for c in layer_dict[fieldname]]
                if parameter not in curves:
                    curves[parameter] = set()
                for curve in layer_dict[fieldname]:
                    if curve is not None:
                        curves[parameter].add(curve)

    return {
        curve_type: {curve: f"{curve_type.name}_{curve_name}" for curve_name, curve in enumerate(curves_set, start=1)}
        for curve_type, curves_set in curves.items()
        if curves_set
    }


def inp_file_junctions(junctions_dict: Mapping, patterns: Mapping[Pattern, str]) -> Iterable[str]:
    junction_list = []

    names = junctions_dict[Field.NAME]
    elevations = junctions_dict[Field.ELEVATION]
    base_demands = junctions_dict[Field.BASE_DEMAND] if Field.BASE_DEMAND in junctions_dict else itertools.repeat(None)

    demand_pattern = (
        (patterns[pat] if pat is not None else None for pat in junctions_dict[Field.DEMAND_PATTERN])
        if Field.DEMAND_PATTERN in junctions_dict
        else itertools.repeat(None)
    )

    for junction in zip(names, elevations, base_demands, demand_pattern):
        line = f"{junction[0]} {junction[1]}"
        if junction[2] is not None:
            line += f" {junction[2]}"
            if junction[3] is not None:
                line += f" {junction[3]}"

        junction_list.append(line)

    return junction_list


def inp_file_reservoirs(reservoirs_dict: Mapping, patterns: Mapping[Pattern, str]) -> Iterable[str]:
    head_patterns = (
        (patterns[pat] if pat is not None else "" for pat in reservoirs_dict[Field.HEAD_PATTERN])
        if Field.HEAD_PATTERN in reservoirs_dict
        else itertools.repeat("")
    )
    reservoir_data = zip(
        reservoirs_dict[Field.NAME],
        reservoirs_dict[Field.BASE_HEAD],
        head_patterns,
    )
    return (" ".join(str(p) for p in reservoir) for reservoir in reservoir_data)


def inp_file_tanks(tanks_dict: Mapping, curves: Mapping[CurveType, Mapping[Curve, str]]) -> Iterable[str]:
    vol_curves = curves.get(CurveType.VOLUME, {})

    vol_curve_field = (
        (vol_curves[curve] if curve is not None else "*" for curve in tanks_dict[Field.VOL_CURVE])
        if Field.VOL_CURVE in tanks_dict
        else itertools.repeat("*")
    )
    overflow_field = (
        ("YES" if overflow else "NO" if overflow is not None else "" for overflow in tanks_dict[Field.OVERFLOW])
        if Field.OVERFLOW in tanks_dict
        else itertools.repeat("")
    )
    tank_data = zip(
        tanks_dict[Field.NAME],
        tanks_dict[Field.ELEVATION],
        tanks_dict[Field.INIT_LEVEL],
        tanks_dict[Field.MIN_LEVEL],
        tanks_dict[Field.MAX_LEVEL],
        tanks_dict[Field.TANK_DIAMETER],
        tanks_dict[Field.MIN_VOL],
        vol_curve_field,
        overflow_field,
    )

    return (" ".join(str(p) for p in tank) for tank in tank_data)


def inp_file_pipes(
    pipes_dict: Mapping, link_start_nodes: Mapping[str, str], link_end_nodes: Mapping[str, str]
) -> Iterable[str]:
    minor_loss = (
        (ml if ml is not None else 0.0 for ml in pipes_dict[Field.MINOR_LOSS])
        if Field.MINOR_LOSS in pipes_dict
        else itertools.repeat(0.0)
    )

    check_valve = (
        (cv if cv is not None else False for cv in pipes_dict[Field.CHECK_VALVE])
        if Field.CHECK_VALVE in pipes_dict
        else itertools.repeat(False)
    )
    initial_status = (
        (status.upper() if status is not None else "OPEN" for status in pipes_dict[Field.INITIAL_STATUS])
        if Field.INITIAL_STATUS in pipes_dict
        else itertools.repeat("OPEN")
    )
    status = ("CV" if cv else init_status for cv, init_status in zip(check_valve, initial_status))

    start_nodes = (link_start_nodes[name] for name in pipes_dict[Field.NAME])
    end_nodes = (link_end_nodes[name] for name in pipes_dict[Field.NAME])

    pipe_data = zip(
        pipes_dict[Field.NAME],
        start_nodes,
        end_nodes,
        pipes_dict[Field.LENGTH],
        pipes_dict[Field.DIAMETER],
        pipes_dict[Field.ROUGHNESS],
        minor_loss,
        status,
    )

    return (" ".join(str(p) for p in pipe) for pipe in pipe_data)


def inp_file_pumps(
    pumps_dict: Mapping,
    patterns: Mapping[Pattern, str],
    curves: Mapping[CurveType, Mapping[Curve, str]],
    link_start_nodes: Mapping[str, str],
    link_end_nodes: Mapping[str, str],
) -> Iterable[str]:
    pump_curves = (
        (
            curves.get(CurveType.HEAD, {}).get(curve) if curve is not None else None
            for curve in pumps_dict[Field.PUMP_CURVE]
        )
        if Field.PUMP_CURVE in pumps_dict
        else itertools.repeat(None)
    )

    pump_param = (
        f"POWER {p[1]}" if p[0] == "POWER" else f"HEAD {p[2]}"
        for p in zip(
            pumps_dict[Field.PUMP_TYPE],
            pumps_dict.get(Field.POWER, itertools.repeat(None)),
            pump_curves,
        )
    )

    base_speeds = (
        (f"SPEED {speed}" if speed is not None else "" for speed in pumps_dict[Field.BASE_SPEED])
        if Field.BASE_SPEED in pumps_dict
        else itertools.repeat("")
    )
    speed_patterns = (
        (f"PATTERN {patterns[pat]}" if pat is not None else "" for pat in pumps_dict[Field.SPEED_PATTERN])
        if Field.SPEED_PATTERN in pumps_dict
        else itertools.repeat("")
    )

    start_nodes = (link_start_nodes[name] for name in pumps_dict[Field.NAME])
    end_nodes = (link_end_nodes[name] for name in pumps_dict[Field.NAME])

    pump_data = zip(
        pumps_dict[Field.NAME],
        start_nodes,
        end_nodes,
        pump_param,
        base_speeds,
        speed_patterns,
    )

    return (" ".join(str(p) for p in pump) for pump in pump_data)


def inp_file_valves(
    valves_dict: Mapping,
    curves: Mapping[CurveType, Mapping[Curve, str]],
    link_start_nodes: Mapping[str, str],
    link_end_nodes: Mapping[str, str],
) -> Iterable[str]:
    headloss_curves = (
        (
            curves.get(CurveType.HEADLOSS, {}).get(curve) if curve is not None else None
            for curve in valves_dict[Field.HEADLOSS_CURVE]
        )
        if Field.HEADLOSS_CURVE in valves_dict
        else itertools.repeat(None)
    )

    valve_setting = (
        v[1]
        if v[0] == ValveType.PRV.value
        else v[1]
        if v[0] == ValveType.PSV.value
        else v[1]
        if v[0] == ValveType.PBV.value
        else v[2]
        if v[0] == ValveType.FCV.value
        else v[3]
        if v[0] == ValveType.TCV.value
        else v[4]
        if v[0] == ValveType.GPV.value
        else "ERROR"
        for v in zip(
            valves_dict[Field.VALVE_TYPE],
            valves_dict.get(Field.PRESSURE_SETTING, itertools.repeat(None)),
            valves_dict.get(Field.FLOW_SETTING, itertools.repeat(None)),
            valves_dict.get(Field.THROTTLE_SETTING, itertools.repeat(None)),
            headloss_curves,
        )
    )
    minor_loss = (
        (ml if ml is not None else 0.0 for ml in valves_dict[Field.MINOR_LOSS])
        if Field.MINOR_LOSS in valves_dict
        else itertools.repeat(0.0)
    )

    start_nodes = (link_start_nodes[name] for name in valves_dict[Field.NAME])
    end_nodes = (link_end_nodes[name] for name in valves_dict[Field.NAME])

    valve_data = zip(
        valves_dict[Field.NAME],
        start_nodes,
        end_nodes,
        valves_dict[Field.DIAMETER],
        valves_dict[Field.VALVE_TYPE],
        valve_setting,
        minor_loss,
    )

    return (" ".join(str(p) for p in valve) for valve in valve_data)


def inp_file_emitters(junctions_dict: Mapping) -> Iterable[str]:
    emitter_data = []
    if junctions_dict is not None and Field.EMITTER_COEFFICIENT in junctions_dict:
        emitter_data = [
            (name, coeff)
            for name, coeff in zip(junctions_dict[Field.NAME], junctions_dict[Field.EMITTER_COEFFICIENT])
            if coeff is not None and coeff > 0.0
        ]

    return (f"{name} {coeff}" for name, coeff in emitter_data)


def inp_file_curves(curves: Mapping[CurveType, Mapping[Curve, str]]) -> Iterable[str]:
    curve_rows = []
    for curve_type, curves_of_type in curves.items():
        for curve, curve_name in curves_of_type.items():
            curve_rows.append(f";{curve_type.name}: {curve_name}")

            for point in list(curve):
                curve_rows.append(curve_name + " " + str(point[0]) + " " + str(point[1]))

    return curve_rows


def inp_file_patterns(patterns: Mapping[Pattern, str]) -> Iterable[str]:
    return (name + " " + pattern for pattern, name in patterns.items())


def inp_file_energy(
    options: ModelOptions,
    patterns: Mapping[Pattern, str],
    pumps_dict: Mapping | None,
    curves: Mapping[CurveType, Mapping[Curve, str]],
) -> Iterable[str] | None:
    lines = [
        f"GLOBAL PRICE {options.energy_price}",
        f"GLOBAL EFFIC {options.energy_pump_efficiency}",
        f"DEMAND CHARGE {options.energy_demand_charge}",
    ]
    if options.energy_pattern:
        lines += [f"GLOBAL PATTERN {patterns[options.energy_pattern]}"]

    if pumps_dict is not None:
        if Field.ENERGY_PATTERN in pumps_dict:
            for pump_name, energy_pattern in zip(pumps_dict[Field.NAME], pumps_dict[Field.ENERGY_PATTERN]):
                if energy_pattern is not None:
                    lines.append(f"PUMP {pump_name} PATTERN {patterns[energy_pattern]}")

        if Field.EFFICIENCY_CURVE in pumps_dict and CurveType.EFFICIENCY in curves:
            for pump_name, efficiency_curve in zip(pumps_dict[Field.NAME], pumps_dict[Field.EFFICIENCY_CURVE]):
                if efficiency_curve is not None:
                    curve_name = curves[CurveType.EFFICIENCY].get(efficiency_curve)
                    if curve_name:
                        lines.append(f"PUMP {pump_name} EFFIC {curve_name}")
        if Field.ENERGY_PRICE in pumps_dict:
            for pump_name, energy_price in zip(pumps_dict[Field.NAME], pumps_dict[Field.ENERGY_PRICE]):
                if energy_price is not None and energy_price != "":
                    lines.append(f"PUMP {pump_name} PRICE {energy_price}")
    return lines


def inp_file_status(valve_dict: Mapping | None, pump_dict: Mapping | None) -> Iterable[str]:
    status_lines = []
    if valve_dict is not None and Field.VALVE_STATUS in valve_dict:
        for valve_name, valve_status in zip(valve_dict[Field.NAME], valve_dict[Field.VALVE_STATUS]):
            if valve_status is not None:
                status_upper = valve_status.upper()
                if status_upper in ["OPEN", "CLOSED"]:
                    status_lines.append(f"{valve_name} {status_upper}")

    if pump_dict is not None and Field.INITIAL_STATUS in pump_dict:
        for pump_name, pump_status in zip(pump_dict[Field.NAME], pump_dict[Field.INITIAL_STATUS]):
            if pump_status is not None and pump_status != "":
                status_lines.append(f"{pump_name} {pump_status.upper()}")
    return status_lines


def inp_file_quality(
    junctions_dict: Mapping | None,
    tanks_dict: Mapping | None,
    reservoirs_dict: Mapping | None,
) -> Iterable[str]:
    quality_zips = [
        zip(d[Field.NAME], (q if q is not None else 0.0 for q in d[Field.INITIAL_QUALITY]))
        for d in [junctions_dict, tanks_dict, reservoirs_dict]
        if d is not None and Field.INITIAL_QUALITY in d
    ]
    return (f"{name} {quality}" for name, quality in itertools.chain(*quality_zips) if quality > 0.0)


def inp_file_reactions(options: ModelOptions) -> Iterable[str] | None:
    if options.quality_parameter is QualityParameter.NONE:
        return None
    return [
        f"ORDER BULK {options.bulk_reaction_order}",
        f"ORDER WALL {options.wall_reaction_order.value}",
        f"GLOBAL BULK {options.global_bulk_coefficient}",
        f"GLOBAL WALL {options.global_wall_coefficient}",
    ]


def inp_file_mixing(tanks_dict: Mapping) -> Iterable[str] | None:
    if Field.MIXING_MODEL not in tanks_dict or not any(tanks_dict[Field.MIXING_MODEL]):
        return None

    mixing_data = zip(
        tanks_dict[Field.NAME],
        (model if model is not None else False for model in tanks_dict[Field.MIXING_MODEL]),
        tanks_dict[Field.MIXING_FRACTION] if Field.MIXING_FRACTION in tanks_dict else itertools.repeat(None),
    )
    return (f"{name} {model} {fraction if model == '2COMP' else ''}" for name, model, fraction in mixing_data if model)


def inp_file_options(options: ModelOptions, temp_hydraulics_file: os.PathLike | str | None) -> Iterable[str]:
    trace_node = options.trace_node if options.quality_parameter is QualityParameter.TRACE else ""

    output = [
        f"UNITS {options.flow_unit.value}",
        f"HEADLOSS {options.headloss_formula.value}",
        f"DEMAND MODEL {options.demand_type.value}",
        f"MINIMUM PRESSURE {options.minimum_pressure}",
        f"REQUIRED PRESSURE {options.required_pressure}",
        f"PRESSURE EXPONENT {options.pressure_exponent}",
        f"DEMAND MULTIPLIER {options.demand_multiplier}",
        "PATTERN 1",
        f"EMITTER EXPONENT {options.emitter_exponent}",
        f"QUALITY {options.quality_parameter.value} {trace_node}",
        f"DIFFUSIVITY {options.relative_diffusivity}",
        f"TOLERANCE {options.quality_tolerance}",
    ]

    if temp_hydraulics_file:
        output.append(f"HYDRAULICS SAVE {Path(temp_hydraulics_file).resolve()}")

    return output


def inp_file_times(options: ModelOptions) -> Iterable[str]:
    return [
        f"DURATION {options.simulation_duration.total_seconds() / 3600}",
    ]


def inp_file_writer(file_path: os.PathLike | str, inp_file_dict: dict[str, Iterable[str] | None]) -> None:
    with Path(file_path).open("w", newline="") as file:
        for section, data in inp_file_dict.items():
            if not data:
                continue
            file.write(f"[{section}]\n")
            file.writelines(line + "\n" for line in data)
            file.write("\n")


if __name__ == "__main__":
    elements = {
        ModelLayer.JUNCTIONS: {
            "demand_pattern": [None, " 1 2 3"],
            "name": ["J1", "J2"],
            "elevation": [10.0, 20.0],
            "base_demand": [0.01, 0.02],
            "emitter_coefficient": [None, 0.1],
            "geometry": [None, None],
        },
        ModelLayer.RESERVOIRS: {
            "name": ["R1", "R2"],
            "base_head": [50.0, 1],
            "head_pattern": ["60 65 45", None],
            "initial_quality": [100.0, 200.0],
            "geometry": [None, None],
        },
        ModelLayer.TANKS: {
            "name": ["T1", "T2"],
            "elevation": [15.0, 25.0],
            "init_level": [5.0, 10.0],
            "min_level": [0.0, 2.0],
            "max_level": [10.0, 15.0],
            "tank_diameter": [10.0, 12.0],
            "min_vol": [0.0, 1.0],
            "vol_curve": [None, Curve("(0,0), (10,10), (15,15)")],
            "overflow": [True, False],
            "mixing_model": [None, "MIXED"],
            "mixing_fraction": [None, None],
            "geometry": [None, None],
        },
        ModelLayer.PIPES: {
            "name": ["P1", "P2", "P3"],
            "start_node_name": ["J1", "J2", "J2"],
            "end_node_name": ["J2", "R1", "R2"],
            "length": [1000.0, 1500.0, 1200.0],
            "diameter": [12.0, 14.0, 13.0],
            "roughness": [100.0, 110.0, 105.0],
            "initial_status": ["OPEN", "CLOSED", "OPEN"],
            "check_valve": [False, False, True],
            "geometry": [None, None, None],
        },
        ModelLayer.PUMPS: {
            "name": ["PU1", "PU2"],
            "start_node_name": ["J1", "J2"],
            "end_node_name": ["T1", "R1"],
            "pump_type": ["HEAD", "POWER"],
            "pump_curve": [Curve("(0,10), (10,8), (15,4)"), None],
            "power": [None, 5.0],
            "base_speed": [1500.0, None],
            "efficiency_curve": [None, Curve("(0,0), (1,2)")],
            "geometry": [None, None],
        },
        ModelLayer.VALVES: {
            "name": ["V1"],
            "start_node_name": ["T2"],
            "end_node_name": ["R2"],
            "diameter": [10.0],
            "valve_type": [ValveType.PRV.value],
            "pressure_setting": [30.0],
            "minor_loss": [0.0],
            "geometry": [None],
        },
    }

    # write_inp_file(elements, DEFAULT_OPTIONS, "output.inp", )
