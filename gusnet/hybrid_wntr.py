from __future__ import annotations

import itertools
from collections.abc import Iterable
from pathlib import Path
from typing import TYPE_CHECKING

from gusnet.elements import (
    CurveType,
    DefaultOptions,
    Field,
    ModelLayer,
    ModelOptions,
    Parameter,
    QualityParameter,
    ResultLayer,
    SimpleFieldType,
    ValveType,
)
from gusnet.interface import EpanetError, WntrModel
from gusnet.pattern_curve import Curve, Pattern
from gusnet.units import Converter

if TYPE_CHECKING:  # pragma: no cover
    import pandas as pd

    from gusnet.units import NumberType


class HybridWntrModel(WntrModel):
    _elements: dict[ModelLayer, pd.DataFrame]
    _options: ModelOptions = DefaultOptions()

    def __init__(self) -> None:
        self._converter = DummyConverter.from_options(self.options)
        self._elements = {}

    @property
    def options(self) -> ModelOptions:
        return self._options

    @options.setter
    def options(self, options: ModelOptions) -> None:
        self._options = options

    def set_elements(self, elements: dict[ModelLayer, pd.DataFrame]) -> None:
        self._elements = elements
        import pandas as pd

        nodes = [
            elements.get(ModelLayer.JUNCTIONS),
            elements.get(ModelLayer.RESERVOIRS),
            elements.get(ModelLayer.TANKS),
        ]
        links = [elements.get(ModelLayer.PIPES), elements.get(ModelLayer.PUMPS), elements.get(ModelLayer.VALVES)]

        node_geom_df = pd.concat([df[["name", "geometry"]] for df in nodes if df is not None])
        self._node_geometry = pd.Series(node_geom_df["geometry"].values, index=node_geom_df["name"])

        link_geom_df = pd.concat([df[["name", "geometry"]] for df in links if df is not None])
        self._link_geometry = pd.Series(link_geom_df["geometry"].values, index=link_geom_df["name"])

    def write_inp_file(self, file_path: str | Path) -> None:
        patterns = find_patterns(self._elements, self.options)
        curves = find_curves(self._elements)

        inp_file_dict: dict[str, Iterable[str] | None] = {}

        junction_df = self._elements.get(ModelLayer.JUNCTIONS)
        reservoir_df = self._elements.get(ModelLayer.RESERVOIRS)
        tank_df = self._elements.get(ModelLayer.TANKS)
        pipe_df = self._elements.get(ModelLayer.PIPES)
        pump_df = self._elements.get(ModelLayer.PUMPS)
        valve_df = self._elements.get(ModelLayer.VALVES)

        inp_file_dict["JUNCTIONS"] = inp_file_junctions(junction_df, patterns) if junction_df is not None else None
        inp_file_dict["RESERVOIRS"] = inp_file_reservoirs(reservoir_df, patterns) if reservoir_df is not None else None
        inp_file_dict["TANKS"] = inp_file_tanks(tank_df, curves) if tank_df is not None else None
        inp_file_dict["PIPES"] = inp_file_pipes(pipe_df) if pipe_df is not None else None
        inp_file_dict["PUMPS"] = inp_file_pumps(pump_df, patterns, curves) if pump_df is not None else None
        inp_file_dict["VALVES"] = inp_file_valves(valve_df, curves) if valve_df is not None else None
        inp_file_dict["EMITTERS"] = inp_file_emitters(junction_df) if junction_df is not None else None
        inp_file_dict["CURVES"] = inp_file_curves(curves)
        inp_file_dict["PATTERNS"] = inp_file_patterns(patterns)
        inp_file_dict["ENERGY"] = inp_file_energy(self.options, patterns, pump_df, curves)
        inp_file_dict["STATUS"] = inp_file_status(valve_df, pump_df)
        inp_file_dict["QUALITY"] = inp_file_quality(junction_df, tank_df, reservoir_df)
        inp_file_dict["REACTIONS"] = inp_file_reactions(self.options)
        inp_file_dict["MIXING"] = inp_file_mixing(tank_df) if tank_df is not None else None
        inp_file_dict["OPTIONS"] = inp_file_options(self.options)
        inp_file_dict["TIMES"] = inp_file_times(self.options)

        inp_file_writer(file_path, inp_file_dict)

    def run(self, output_file_prefix: str = "temp") -> None:
        import wntr

        inpfile = f"{output_file_prefix}.inp"
        rptfile = f"{output_file_prefix}.rpt"
        outfile = f"{output_file_prefix}.out"

        self.write_inp_file(inpfile)
        try:
            epanet = wntr.epanet.toolkit.ENepanet(version=2.2)
            epanet.ENopen(inpfile, rptfile, outfile)
            epanet.ENsolveH()
            epanet.ENsolveQ()
            epanet.ENreport()
            epanet.ENclose()
        except wntr.epanet.exceptions.EpanetException as e:
            raise EpanetError(e) from e

        result_reader = wntr.epanet.io.BinFile()

        results = result_reader.read(outfile, convert=False)

        self.set_results(results)

    def _get_pipe_lengths(self) -> pd.Series:
        import pandas as pd

        pipe_df = self._elements.get(ModelLayer.PIPES)

        if pipe_df is None:
            return pd.Series(dtype=float)
        return pd.Series(pipe_df[Field.LENGTH].values, index=pipe_df[Field.NAME])


def find_patterns(elements: dict[ModelLayer, pd.DataFrame], options: ModelOptions) -> dict[Pattern, str]:
    patterns: set[Pattern] = set()
    for df in elements.values():
        for fieldname in df.columns:
            try:
                parameter = Field(fieldname).type
            except ValueError:
                continue
            if parameter == SimpleFieldType.PATTERN:
                df[fieldname] = df[fieldname].map(Pattern.factory, na_action="ignore")
                df[fieldname].map(patterns.add, na_action="ignore")

    if options.energy_pattern:
        patterns.add(options.energy_pattern)

    return {pattern: str(pattern_name) for pattern_name, pattern in enumerate(patterns, start=2)}


def find_curves(elements: dict[ModelLayer, pd.DataFrame]) -> dict[CurveType, dict[Curve, str]]:
    curves: dict[CurveType, set[Curve]] = {}

    for df in elements.values():
        for fieldname in df.columns:
            try:
                parameter = Field(fieldname).type
            except ValueError:
                continue
            if isinstance(parameter, CurveType):
                df[fieldname] = df[fieldname].map(Curve.factory, na_action="ignore")
                curves[parameter] = set()
                for curve in df[fieldname].dropna():
                    curves[parameter].add(curve)

    return {
        curve_type: {curve: f"{curve_type.name}_{curve_name}" for curve_name, curve in enumerate(curves_set, start=1)}
        for curve_type, curves_set in curves.items()
        if curves_set
    }


def inp_file_junctions(junctions_df: pd.DataFrame, patterns: dict[Pattern, str]) -> Iterable[str]:
    import pandas as pd

    junction_list = []

    names = junctions_df[Field.NAME]
    elevations = junctions_df[Field.ELEVATION]
    base_demands = junctions_df[Field.BASE_DEMAND] if Field.BASE_DEMAND in junctions_df else itertools.repeat(None)
    demand_pattern = (
        junctions_df[Field.DEMAND_PATTERN].map(patterns, na_action="ignore")
        if Field.DEMAND_PATTERN in junctions_df
        else itertools.repeat(None)
    )

    for junction in zip(names, elevations, base_demands, demand_pattern):
        line = f"{junction[0]} {junction[1]}"
        if pd.notna(junction[2]):
            line += f" {junction[2]}"
            if pd.notna(junction[3]):
                line += f" {junction[3]}"

        junction_list.append(line)

    return junction_list


def inp_file_reservoirs(reservoirs_df: pd.DataFrame, patterns: dict[Pattern, str]) -> Iterable[str]:
    reservoir_data = zip(
        reservoirs_df[Field.NAME],
        reservoirs_df[Field.BASE_HEAD],
        reservoirs_df[Field.HEAD_PATTERN].map(patterns, na_action="ignore").fillna("")
        if Field.HEAD_PATTERN in reservoirs_df
        else itertools.repeat(""),
    )
    return (" ".join(str(p) for p in reservoir) for reservoir in reservoir_data)


def inp_file_tanks(tanks_df: pd.DataFrame, curves: dict[CurveType, dict[Curve, str]]) -> Iterable[str]:
    vol_curve_field = (
        tanks_df[Field.VOL_CURVE].map(curves.get(CurveType.VOLUME), na_action="ignore").fillna("*")
        if Field.VOL_CURVE in tanks_df.columns
        else itertools.repeat("*")
    )
    overflow_field = (
        tanks_df[Field.OVERFLOW].map(lambda x: "YES" if x else "NO", na_action="ignore").fillna("")
        if Field.OVERFLOW in tanks_df.columns
        else itertools.repeat("")
    )
    tank_data = zip(
        tanks_df[Field.NAME],
        tanks_df[Field.ELEVATION],
        tanks_df[Field.INIT_LEVEL],
        tanks_df[Field.MIN_LEVEL],
        tanks_df[Field.MAX_LEVEL],
        tanks_df[Field.TANK_DIAMETER],
        tanks_df[Field.MIN_VOL],
        vol_curve_field,
        overflow_field,
    )

    return (" ".join(str(p) for p in tank) for tank in tank_data)


def inp_file_pipes(pipes_df: pd.DataFrame) -> Iterable[str]:
    minor_loss = (
        pipes_df[Field.MINOR_LOSS].fillna(0.0) if Field.MINOR_LOSS in pipes_df.columns else itertools.repeat(0.0)
    )

    check_valve = (
        pipes_df[Field.CHECK_VALVE].fillna(False) if Field.CHECK_VALVE in pipes_df.columns else itertools.repeat(False)
    )
    initial_status = (
        pipes_df[Field.INITIAL_STATUS].fillna("OPEN").str.upper()
        if Field.INITIAL_STATUS in pipes_df.columns
        else itertools.repeat("OPEN")
    )
    status = ("CV" if cv else initial_status for cv, initial_status in zip(check_valve, initial_status))

    pipe_data = zip(
        pipes_df[Field.NAME],
        pipes_df["start_node_name"],
        pipes_df["end_node_name"],
        pipes_df[Field.LENGTH],
        pipes_df[Field.DIAMETER],
        pipes_df[Field.ROUGHNESS],
        minor_loss,
        status,
    )

    return (" ".join(str(p) for p in pipe) for pipe in pipe_data)


def inp_file_pumps(
    pumps_df: pd.DataFrame, patterns: dict[Pattern, str], curves: dict[CurveType, dict[Curve, str]]
) -> Iterable[str]:
    pump_param = (
        f"POWER {p[1]}" if p[0] == "POWER" else f"HEAD {p[2]}"
        for p in zip(
            pumps_df[Field.PUMP_TYPE],
            pumps_df.get(Field.POWER, itertools.repeat(None)),
            pumps_df[Field.PUMP_CURVE].map(curves.get(CurveType.HEAD), na_action="ignore")
            if Field.PUMP_CURVE in pumps_df.columns
            else itertools.repeat(None),
        )
    )

    base_speeds = (
        pumps_df[Field.BASE_SPEED].map(lambda x: f"SPEED {x}", na_action="ignore").fillna("")
        if Field.BASE_SPEED in pumps_df.columns
        else itertools.repeat("")
    )
    speed_patterns = (
        pumps_df[Field.SPEED_PATTERN]
        .map(patterns, na_action="ignore")
        .map(lambda x: f"PATTERN {x}", na_action="ignore")
        .fillna("")
        if Field.SPEED_PATTERN in pumps_df.columns
        else itertools.repeat("")
    )

    pump_data = zip(
        pumps_df[Field.NAME],
        pumps_df["start_node_name"],
        pumps_df["end_node_name"],
        pump_param,
        base_speeds,
        speed_patterns,
    )

    return (" ".join(str(p) for p in pump) for pump in pump_data)


def inp_file_valves(valves_df: pd.DataFrame, curves: dict[CurveType, dict[Curve, str]]) -> Iterable[str]:
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
            valves_df[Field.VALVE_TYPE],
            valves_df.get(Field.PRESSURE_SETTING, itertools.repeat(None)),
            valves_df.get(Field.FLOW_SETTING, itertools.repeat(None)),
            valves_df.get(Field.THROTTLE_SETTING, itertools.repeat(None)),
            valves_df[Field.HEADLOSS_CURVE].map(curves.get(CurveType.HEADLOSS, {}), na_action="ignore")
            if Field.HEADLOSS_CURVE in valves_df.columns
            else itertools.repeat(None),
        )
    )
    valve_data = zip(
        valves_df[Field.NAME],
        valves_df["start_node_name"],
        valves_df["end_node_name"],
        valves_df[Field.DIAMETER],
        valves_df[Field.VALVE_TYPE],
        valve_setting,
        valves_df[Field.MINOR_LOSS].fillna(0.0) if Field.MINOR_LOSS in valves_df.columns else itertools.repeat(0.0),
    )

    return (" ".join(str(p) for p in valve) for valve in valve_data)


def inp_file_emitters(junctions_df: pd.DataFrame) -> Iterable[str]:
    if junctions_df is not None and Field.EMITTER_COEFFICIENT in junctions_df.columns:
        emitter_mask = junctions_df[Field.EMITTER_COEFFICIENT] > 0.0
        emitter_data = zip(
            junctions_df[Field.NAME][emitter_mask], junctions_df[Field.EMITTER_COEFFICIENT][emitter_mask]
        )

    return (f"{name} {coeff}" for name, coeff in emitter_data)


def inp_file_curves(curves: dict[CurveType, dict[Curve, str]]) -> Iterable[str]:
    curve_rows = []
    for curve_type, curves_of_type in curves.items():
        for curve, curve_name in curves_of_type.items():
            curve_rows.append(f";{curve_type.name}: {curve_name}")

            for point in list(curve):
                curve_rows.append(curve_name + " " + str(point[0]) + " " + str(point[1]))

    return curve_rows


def inp_file_patterns(patterns: dict[Pattern, str]) -> Iterable[str]:
    return (name + " " + pattern for pattern, name in patterns.items())


def inp_file_energy(
    options: ModelOptions,
    patterns: dict[Pattern, str],
    pumps_df: pd.DataFrame | None,
    curves: dict[CurveType, dict[Curve, str]],
) -> Iterable[str] | None:
    lines = [
        f"GLOBAL PRICE {options.energy_price}",
        f"GLOBAL EFFICIENCY {options.energy_pump_efficiency}",
        f"DEMAND CHARGE {options.energy_demand_charge}",
    ]
    if options.energy_pattern:
        lines += [f"GLOBAL PATTERN {patterns[options.energy_pattern]}"]

    if pumps_df is not None:
        if Field.ENERGY_PATTERN in pumps_df.columns:
            for pump_name, energy_pattern in zip(
                pumps_df[Field.NAME],
                pumps_df[Field.ENERGY_PATTERN].map(patterns, na_action="ignore").fillna(""),
            ):
                if energy_pattern:
                    lines.append(f"PUMP {pump_name} PATTERN {energy_pattern}")

        if Field.EFFICIENCY_CURVE in pumps_df.columns and CurveType.EFFICIENCY in curves:
            for pump_name, efficiency_curve in zip(
                pumps_df[Field.NAME],
                pumps_df[Field.EFFICIENCY_CURVE].map(curves[CurveType.EFFICIENCY], na_action="ignore").fillna(""),
            ):
                if efficiency_curve:
                    lines.append(f"PUMP {pump_name} EFFIC {efficiency_curve}")
        if Field.ENERGY_PRICE in pumps_df.columns:
            for pump_name, energy_price in zip(
                pumps_df[Field.NAME],
                pumps_df[Field.ENERGY_PRICE].fillna(""),
            ):
                if energy_price:
                    lines.append(f"PUMP {pump_name} PRICE {energy_price}")
    return lines


def inp_file_status(valve_df: pd.DataFrame | None, pump_df: pd.DataFrame | None) -> Iterable[str]:
    status_lines = []
    if valve_df is not None and Field.VALVE_STATUS in valve_df.columns:
        for valve_name, valve_status in zip(
            valve_df[Field.NAME],
            valve_df[Field.VALVE_STATUS].str.upper().fillna(""),
        ):
            if valve_status in ["OPEN", "CLOSED"]:
                status_lines.append(f"{valve_name} {valve_status}")

    if pump_df is not None and Field.INITIAL_STATUS in pump_df.columns:
        for pump_name, pump_status in zip(
            pump_df[Field.NAME],
            pump_df[Field.INITIAL_STATUS].str.upper().fillna(""),
        ):
            if pump_status:
                status_lines.append(f"{pump_name} {pump_status}")
    return status_lines


def inp_file_quality(
    junctions_df: pd.DataFrame | None,
    tanks_df: pd.DataFrame | None,
    reservoirs_df: pd.DataFrame | None,
) -> Iterable[str]:
    quality_zips = [
        zip(df[Field.NAME], df[Field.INITIAL_QUALITY].fillna(0.0))
        for df in [junctions_df, tanks_df, reservoirs_df]
        if df is not None and Field.INITIAL_QUALITY in df.columns
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


def inp_file_mixing(tanks_df: pd.DataFrame) -> Iterable[str] | None:
    if Field.MIXING_MODEL not in tanks_df.columns or not tanks_df[Field.MIXING_MODEL].any():
        return None

    mixing_data = zip(
        tanks_df[Field.NAME],
        tanks_df[Field.MIXING_MODEL].fillna(False),
        tanks_df[Field.MIXING_FRACTION] if Field.MIXING_FRACTION in tanks_df.columns else itertools.repeat(None),
    )
    return (f"{name} {model} {fraction if model == '2COMP' else ''}" for name, model, fraction in mixing_data if model)


def inp_file_options(options: ModelOptions) -> Iterable[str]:
    trace_node = options.trace_node if options.quality_parameter is QualityParameter.TRACE else ""
    return [
        f"UNITS {options.flow_unit.value}",
        f"HEADLOSS {options.headloss_formula.value}",
        f"DEMAND MODEL {options.demand_type.value}",
        f"MINIMUM PRESSURE {options.minimum_pressure}",
        f"REQUIRED PRESSURE {options.required_pressure}",
        f"PRESSURE EXPONENT {options.pressure_exponent}",
        f"DEMAND MULTIPLIER {options.demand_multiplier}",
        f"EMITTER EXPONENT {options.emitter_exponent}",
        f"QUALITY {options.quality_parameter.value} {trace_node}",
        f"DIFFUSIVITY {options.relative_diffusivity}",
        f"TOLERANCE {options.quality_tolerance}",
    ]


def inp_file_times(options: ModelOptions) -> Iterable[str]:
    return [
        f"DURATION {options.simulation_duration}",
    ]


def inp_file_writer(file_path: str | Path, inp_file_dict: dict[str, Iterable[str] | None]) -> None:
    with Path(file_path).open("w", newline="") as file:
        for section, data in inp_file_dict.items():
            if not data:
                continue
            file.write(f"[{section}]\n")
            file.writelines(line + "\n" for line in data)
            file.write("\n")


class DummyConverter(Converter):
    def to_si(self, value: NumberType, parameter: Parameter) -> NumberType:  # noqa: ARG002
        return value

    def from_si(self, value: NumberType, parameter: Parameter) -> NumberType:  # noqa: ARG002
        return value


if __name__ == "__main__":
    import pandas as pd

    model = HybridWntrModel()
    model.set_elements(
        {
            ModelLayer.JUNCTIONS: pd.DataFrame(
                {
                    "demand_pattern": [None, " 1 2 3"],
                    "name": ["J1", "J2"],
                    "elevation": [10.0, 20.0],
                    "base_demand": [0.01, 0.02],
                    "emitter_coefficient": [None, 0.1],
                    "geometry": [None, None],
                }
            ),
            ModelLayer.RESERVOIRS: pd.DataFrame(
                {
                    "name": ["R1", "R2"],
                    "base_head": [50.0, 1],
                    "head_pattern": ["60 65 45", None],
                    "initial_quality": [100.0, 200.0],
                    "geometry": [None, None],
                }
            ),
            ModelLayer.TANKS: pd.DataFrame(
                {
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
                }
            ),
            ModelLayer.PIPES: pd.DataFrame(
                {
                    "name": ["P1", "P2", "P3"],
                    "start_node_name": ["J1", "J2", "J2"],
                    "end_node_name": ["J2", "R1", "R2"],
                    "length": [1000.0, 1500.0, 1200.0],
                    "diameter": [12.0, 14.0, 13.0],
                    "roughness": [100.0, 110.0, 105.0],
                    "initial_status": ["OPEN", "CLOSED", "OPEN"],
                    "check_valve": [False, False, True],
                    "geometry": [None, None, None],
                }
            ),
            ModelLayer.PUMPS: pd.DataFrame(
                {
                    "name": ["PU1", "PU2"],
                    "start_node_name": ["J1", "J2"],
                    "end_node_name": ["T1", "R1"],
                    "pump_type": ["HEAD", "POWER"],
                    "pump_curve": [Curve("(0,10), (10,8), (15,4)"), None],
                    "power": [None, 5.0],
                    "base_speed": [1500.0, None],
                    "efficiency_curve": [None, Curve("(0,0), (1,2)")],
                    "geometry": [None, None],
                }
            ),
        }
    )
    model.write_inp_file("output.inp")

    model.run()

    results = model.get_results()

    print(results[ResultLayer.NODES])
    print(results[ResultLayer.LINKS])
