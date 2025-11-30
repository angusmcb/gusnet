from __future__ import annotations

import csv
import functools
import itertools
from pathlib import Path
from typing import TYPE_CHECKING

from gusnet.elements import (
    CurveType,
    DefaultOptions,
    DemandType,
    Field,
    ModelLayer,
    ModelOptions,
    Parameter,
    QualityParameter,
    SimpleFieldType,
)
from gusnet.interface import EpanetError, WntrModel
from gusnet.pattern_curve import Curve, Pattern
from gusnet.units import Converter

if TYPE_CHECKING:  # pragma: no cover
    import pandas as pd

    from gusnet.units import NumberType


class HybridWntrModel(WntrModel):
    _elements: dict[ModelLayer, pd.DataFrame] | None = None
    _options: ModelOptions = DefaultOptions()
    _junctions: pd.DataFrame | None = None
    _reservoirs: pd.DataFrame | None = None
    _tanks: pd.DataFrame | None = None
    _pipes: pd.DataFrame | None = None
    _pumps: pd.DataFrame | None = None
    _valves: pd.DataFrame | None = None
    _patterns: dict[str, Pattern]
    _curves: dict[str, Curve]

    def __init__(self) -> None:
        # self.options = DefaultOptions()
        self._converter = DummyConverter.from_options(self.options)
        self._patterns = {}
        self._curves = {}
        self._next_pattern_name = functools.partial(next, map(str, itertools.count(2)))
        self._next_curve_name = functools.partial(next, map(str, itertools.count(1)))
        self._existing_patterns: dict[Pattern, str] = {}

    @property
    def options(self) -> ModelOptions:
        return self._options

    @options.setter
    def options(self, options: ModelOptions) -> None:
        self._options = options

    def set_elements(self, elements: dict[ModelLayer, pd.DataFrame]) -> None:
        import pandas as pd

        for df in elements.values():
            for fieldname in df.columns:
                try:
                    parameter = Field(fieldname).type
                except ValueError:
                    continue
                if isinstance(parameter, CurveType):
                    df[fieldname] = df[fieldname].map(
                        functools.partial(self.add_curve, curve_type=parameter), na_action="ignore"
                    )

                if parameter == SimpleFieldType.PATTERN:
                    df[fieldname] = df[fieldname].map(self.add_pattern, na_action="ignore")

        self._junctions = elements.get(ModelLayer.JUNCTIONS)
        self._reservoirs = elements.get(ModelLayer.RESERVOIRS)
        self._tanks = elements.get(ModelLayer.TANKS)
        self._pipes = elements.get(ModelLayer.PIPES)
        self._pumps = elements.get(ModelLayer.PUMPS)
        self._valves = elements.get(ModelLayer.VALVES)

        node_geom = [
            df[["name", "geometry"]] for df in [self._junctions, self._reservoirs, self._tanks] if df is not None
        ]
        node_geom_df = pd.concat(node_geom)
        self._node_geometry = pd.Series(node_geom_df["geometry"].values, index=node_geom_df["name"])
        link_geom = [df[["name", "geometry"]] for df in [self._pipes, self._pumps, self._valves] if df is not None]
        link_geom_df = pd.concat(link_geom)
        self._link_geometry = pd.Series(link_geom_df["geometry"].values, index=link_geom_df["name"])

    def _add_finalised_pattern(self, name: str, pattern: Pattern) -> None:
        self._patterns[name] = pattern

    def add_curve(self, curve: str, curve_type: CurveType) -> str | None:  # noqa: ARG002
        if not isinstance(curve, Curve):
            curve = Curve(curve)

        if not curve:
            return None

        name = self._next_curve_name()

        self._curves[name] = curve
        return name

    def write_inp_file(self, file_path: str | Path) -> None:
        import pandas as pd

        inp_file_dict = self.get_inp_file_dict()

        with Path(file_path).open("w", newline="") as file:
            for section, data in inp_file_dict.items():
                file.write(f"[{section}]\n")
                if isinstance(data, (pd.DataFrame, pd.Series)):
                    # quote none means errors will be thrown rather than adding quotes
                    data.to_csv(file, sep=" ", header=False, index=False, quoting=csv.QUOTE_NONE)
                else:
                    file.writelines(line + "\n" for line in data)
                file.write("\n")

    def get_inp_file_dict(self) -> dict[str, pd.DataFrame]:
        import pandas as pd

        inp_file_dict: dict[str, pd.DataFrame] = {}

        if self._junctions is not None:
            junction_list = []

            names = self._junctions[Field.NAME]
            elevations = self._junctions[Field.ELEVATION]
            base_demands = self._junctions.get(Field.BASE_DEMAND, itertools.repeat(None))
            demand_pattern = self._junctions.get(Field.DEMAND_PATTERN, itertools.repeat(None))

            for junction in zip(names, elevations, base_demands, demand_pattern):
                line = f"{junction[0]} {junction[1]}"
                if pd.notna(junction[2]):
                    line += f" {junction[2]}"
                    if pd.notna(junction[3]):
                        line += f" {junction[3]}"

                junction_list.append(line)

            inp_file_dict["JUNCTIONS"] = junction_list

        if self._reservoirs is not None:
            inp_file_dict["RESERVOIRS"] = subset(self._reservoirs, [Field.NAME, Field.BASE_HEAD, Field.HEAD_PATTERN])

        if self._tanks is not None:
            vol_curve_field = (
                self._tanks[Field.VOL_CURVE].fillna("*")
                if Field.VOL_CURVE in self._tanks.columns
                else itertools.repeat("*")
            )
            overflow_field = (
                self._tanks[Field.OVERFLOW].map(lambda x: "YES" if x else "NO", na_action="ignore").fillna("")
                if Field.OVERFLOW in self._tanks.columns
                else itertools.repeat("")
            )
            tank_data = zip(
                self._tanks[Field.NAME],
                self._tanks[Field.ELEVATION],
                self._tanks[Field.INIT_LEVEL],
                self._tanks[Field.MIN_LEVEL],
                self._tanks[Field.MAX_LEVEL],
                self._tanks[Field.TANK_DIAMETER],
                self._tanks[Field.MIN_VOL],
                vol_curve_field,
                overflow_field,
            )

            inp_file_dict["TANKS"] = (" ".join(str(p) for p in tank) for tank in tank_data)

        if self._pipes is not None:
            minor_loss = (
                self._pipes[Field.MINOR_LOSS].fillna(0.0)
                if Field.MINOR_LOSS in self._pipes.columns
                else itertools.repeat(0.0)
            )

            check_valve = (
                self._pipes[Field.CHECK_VALVE].fillna(False)
                if Field.CHECK_VALVE in self._pipes.columns
                else itertools.repeat(False)
            )
            initial_status = (
                self._pipes[Field.INITIAL_STATUS].fillna("OPEN").str.upper()
                if Field.INITIAL_STATUS in self._pipes.columns
                else itertools.repeat("OPEN")
            )
            status = ("CV" if cv else initial_status for cv, initial_status in zip(check_valve, initial_status))

            pipe_data = zip(
                self._pipes[Field.NAME],
                self._pipes["start_node_name"],
                self._pipes["end_node_name"],
                self._pipes[Field.LENGTH],
                self._pipes[Field.DIAMETER],
                self._pipes[Field.ROUGHNESS],
                minor_loss,
                status,
            )

            inp_file_dict["PIPES"] = (" ".join(str(p) for p in pipe) for pipe in pipe_data)

        if self._pumps is not None:
            powers = (
                self._pumps[Field.POWER].map(lambda x: f"POWER {x}", na_action="ignore").fillna("")
                if Field.POWER in self._pumps.columns
                else itertools.repeat("")
            )
            curves = (
                self._pumps[Field.PUMP_CURVE].map(lambda x: f"HEAD {x}", na_action="ignore").fillna("")
                if Field.PUMP_CURVE in self._pumps.columns
                else itertools.repeat("")
            )
            base_speeds = (
                self._pumps[Field.BASE_SPEED].map(lambda x: f"SPEED {x}", na_action="ignore").fillna("")
                if Field.BASE_SPEED in self._pumps.columns
                else itertools.repeat("")
            )
            speed_patterns = (
                self._pumps[Field.SPEED_PATTERN].map(lambda x: f"PATTERN {x}", na_action="ignore").fillna("")
                if Field.SPEED_PATTERN in self._pumps.columns
                else itertools.repeat("")
            )

            pump_data = zip(
                self._pumps[Field.NAME],
                self._pumps["start_node_name"],
                self._pumps["end_node_name"],
                powers,
                curves,
                base_speeds,
                speed_patterns,
            )

            inp_file_dict["PUMPS"] = (" ".join(str(p) for p in pump) for pump in pump_data)

        if self._valves is not None:
            self._valves["valve_setting"] = 0.0

            inp_file_dict["VALVES"] = subset(
                self._valves,
                [
                    Field.NAME,
                    "start_node_name",
                    "end_node_name",
                    Field.DIAMETER,
                    Field.VALVE_TYPE,
                    "valve_setting",
                    Field.MINOR_LOSS,
                ],
            )

        if self._junctions is not None and Field.EMITTER_COEFFICIENT in self._junctions.columns:
            emitter_mask = self._junctions[Field.EMITTER_COEFFICIENT] > 0.0
            emitter_data = zip(
                self._junctions[Field.NAME][emitter_mask], self._junctions[Field.EMITTER_COEFFICIENT][emitter_mask]
            )

            inp_file_dict["EMITTERS"] = (f"{name} {coeff}" for name, coeff in emitter_data)

        if self._curves:
            curve_rows = []
            for curve_name, curve in self._curves.items():
                curve_points = list(curve)

                for point in curve_points:
                    curve_rows.append(curve_name + " " + str(point[0]) + " " + str(point[1]))

            inp_file_dict["CURVES"] = curve_rows

        if self._patterns:
            inp_file_dict["PATTERNS"] = (name + " " + pattern for name, pattern in self._patterns.items())

        quality_zips = [
            zip(df[Field.NAME], df[Field.INITIAL_QUALITY].fillna(0.0))
            for df in [self._junctions, self._tanks, self._reservoirs]
            if df is not None and Field.INITIAL_QUALITY in df.columns
        ]
        inp_file_dict["QUALITY"] = (
            f"{name} {quality}" for name, quality in itertools.chain(*quality_zips) if quality > 0.0
        )

        if self.options.quality_parameter is not QualityParameter.NONE:
            reaction_rows = [
                f"ORDER BULK {self.options.bulk_reaction_order}",
                f"ORDER WALL {self.options.wall_reaction_order.value}",
                f"GLOBAL BULK {self.options.global_bulk_coefficient}",
                f"GLOBAL WALL {self.options.global_wall_coefficient}",
            ]
            inp_file_dict["REACTIONS"] = reaction_rows

        if (
            self._tanks is not None
            and Field.MIXING_MODEL in self._tanks.columns
            and self._tanks[Field.MIXING_MODEL].any()
        ):
            mixing_data = zip(
                self._tanks[Field.NAME],
                self._tanks[Field.MIXING_MODEL].fillna(False),
                self._tanks[Field.MIXING_FRACTION],
            )
            inp_file_dict["MIXING"] = (
                f"{name} {model} {fraction if model == '2COMP' else ''}"
                for name, model, fraction in mixing_data
                if model
            )

        options_rows = [
            f"UNITS {self.options.flow_unit.value}",
            f"HEADLOSS {self.options.headloss_formula.value}",
            f"DEMAND MULTIPLIER {self.options.demand_multiplier}",
            f"EMITTER EXPONENT {self.options.emitter_exponent}",
        ]
        if self.options.demand_type == DemandType.PRESSURE_DEPENDENT:
            options_rows.extend(
                [
                    "DEMAND MODEL PDA",
                    f"MINIMUM PRESSURE {self.options.minimum_pressure}",
                    f"REQUIRED PRESSURE {self.options.required_pressure}",
                    f"PRESSURE EXPONENT {self.options.pressure_exponent}",
                ]
            )
        if self.options.quality_parameter is not QualityParameter.NONE:
            options_rows.extend(
                [
                    f"QUALITY {self.options.quality_parameter.value}",
                    f"DIFFUSIVITY {self.options.relative_diffusivity}",
                ]
            )

        inp_file_dict["OPTIONS"] = options_rows

        if self.options.simulation_duration > 0:
            time_rows = [
                f"DURATION {self.options.simulation_duration}",
            ]
            inp_file_dict["TIMES"] = time_rows

        return inp_file_dict

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

        if self._pipes is None:
            raise ValueError
        return pd.Series(self._pipes[Field.LENGTH].values, index=self._pipes[Field.NAME])


def subset(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    """Return a subset of the dataframe where the column matches one of the values."""
    existing_columns = set(df.columns.tolist())
    return df[[c for c in columns if c in existing_columns]]


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
                    "vol_curve": ["", "(0,0), (10,10), (15,15)"],
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
                    "pump_curve": ["(0,10), (10,8), (15,4)", None],
                    "power": [None, 5.0],
                    "efficiency_curve": [None, None],
                    "base_speed": [1500.0, None],
                    "geometry": [None, None],
                }
            ),
        }
    )
    model.write_inp_file("output.inp")

    model.run()

    print(model.get_results())
