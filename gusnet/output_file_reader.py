from __future__ import annotations

import array
import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from struct import Struct, unpack
from types import MappingProxyType
from typing import NamedTuple

from gusnet.elements import Field, ResultLayer

MAGIC_NUMBER = 516114521
EXPECTED_VERSION = 200

LINK_PIPE_TYPES = (0, 1)


def read_output_file(file_path: Path | str) -> Mapping[ResultLayer, Mapping]:
    output_file = OutputFile(file_path)

    switched_nodes = {
        param: [
            getattr(output_file.timestep_node_results[time], param) for time in range(output_file.num_reporting_periods)
        ]
        for param in [Field.DEMAND, Field.HEAD, Field.PRESSURE, Field.QUALITY]
    }
    switched_links = {
        param: [
            getattr(output_file.timestep_link_results[time], param) for time in range(output_file.num_reporting_periods)
        ]
        for param in [Field.FLOWRATE, Field.VELOCITY, Field.HEADLOSS, Field.QUALITY, Field.REACTION_RATE]
    }

    if output_file.num_reporting_periods == 1:
        node_results = {param: value[0] for param, value in switched_nodes.items()}
        link_results = {param: value[0] for param, value in switched_links.items()}

        link_results[Field.UNIT_HEADLOSS] = [
            node_headloss if link_type in LINK_PIPE_TYPES else None
            for link_type, node_headloss in zip(output_file.link_types, link_results[Field.HEADLOSS])
        ]
        link_results[Field.HEADLOSS] = [
            node_headloss * link_length / 1000 if link_type in LINK_PIPE_TYPES else node_headloss
            for link_type, node_headloss, link_length in zip(
                output_file.link_types, link_results[Field.HEADLOSS], output_file.link_length
            )
        ]

    else:
        node_results = {
            param: [
                [timesteps[time][node_index] for time in range(output_file.num_reporting_periods)]
                for node_index in range(output_file.num_nodes)
            ]
            for param, timesteps in switched_nodes.items()
        }

        link_results = {
            param: [
                [timesteps[time][link_index] for time in range(output_file.num_reporting_periods)]
                for link_index in range(output_file.num_links)
            ]
            for param, timesteps in switched_links.items()
        }

        link_results[Field.UNIT_HEADLOSS] = [
            node_headloss if link_type in LINK_PIPE_TYPES else None
            for link_type, node_headloss in zip(output_file.link_types, link_results[Field.HEADLOSS])
        ]
        link_results[Field.HEADLOSS] = [
            [node_headloss * link_length / 1000 for node_headloss in node_headloss_list]
            if link_type in LINK_PIPE_TYPES
            else node_headloss_list
            for link_type, node_headloss_list, link_length in zip(
                output_file.link_types, link_results[Field.HEADLOSS], output_file.link_length
            )
        ]

    node_results[Field.NAME] = output_file.node_names
    link_results[Field.NAME] = output_file.link_names

    return MappingProxyType(
        {
            ResultLayer.NODES: MappingProxyType(node_results),
            ResultLayer.LINKS: MappingProxyType(link_results),
        }
    )


class PumpEnergyUsage(NamedTuple):
    pump_index: int
    utilisation: float
    avg_efficiency: float
    avg_power_flow: float
    avg_power: float
    peak_power: float
    avg_cost_day: float


class NodeResults(NamedTuple):
    demand: array.array[float]
    head: array.array[float]
    pressure: array.array[float]
    quality: array.array[float]


class LinkResults(NamedTuple):
    flowrate: array.array[float]
    velocity: array.array[float]
    headloss: array.array[float]
    quality: array.array[float]
    status: array.array[float]
    setting: array.array[float]
    reaction_rate: array.array[float]
    friction_factor: array.array[float]


@dataclass(init=False)
class OutputFile:
    version: int
    num_nodes: int
    num_tanks: int
    num_links: int
    num_pumps: int
    num_valves: int
    quality_type: int
    trace_node_index: int
    flow_units: int
    pressure_units: int
    statistics_type: int
    report_start_time: int
    report_time_step: int
    simulation_duration: int
    title: str
    input_file: str
    report_file: str
    chemical_name: str
    chemical_units: str
    node_names: list[str]
    link_names: list[str]
    head_nodes: array.array[int]
    tail_nodes: array.array[int]
    link_types: array.array[int]
    tank_index: array.array[int]
    tank_surface_area: array.array[float]
    elevation: array.array[float]
    link_length: array.array[float]
    link_diameter: array.array[float]
    pump_energies: list[PumpEnergyUsage]
    demand_charge: float
    timestep_link_results: list[LinkResults]
    timestep_node_results: list[NodeResults]
    avg_bulk_reaction_rate: float
    avg_wall_reaction_rate: float
    avg_tank_reaction_rate: float
    avg_source_inflow_rate: float
    num_reporting_periods: int
    warning_flags: int

    def __init__(self, bin_file: Path | str) -> None:
        with Path(bin_file).open("rb") as f:
            prelude_struct = Struct("<15i80s80s80s260s260s32s32s")
            prelude_data = prelude_struct.unpack(f.read(prelude_struct.size))
            (
                magic_number,
                self.version,
                self.num_nodes,
                self.num_tanks,
                self.num_links,
                self.num_pumps,
                self.num_valves,
                self.quality_type,
                self.trace_node_index,
                self.flow_units,
                self.pressure_units,
                self.statistics_type,
                self.report_start_time,
                self.report_time_step,
                self.simulation_duration,
                title1,
                title2,
                title3,
                self.input_file,
                self.report_file,
                self.chemical_name,
                self.chemical_units,
            ) = prelude_data

            if magic_number != MAGIC_NUMBER:
                raise MagicNumberError

            self.title = (
                title1.decode("utf-8").rstrip("\x00")
                + title2.decode("utf-8").rstrip("\x00")
                + title3.decode("utf-8").rstrip("\x00")
            )

            name_struct = Struct("<32s")
            name_size = name_struct.size

            self.node_names = [
                name_struct.unpack(f.read(name_size))[0].rstrip(b"\x00").decode("utf-8") for _ in range(self.num_nodes)
            ]
            self.link_names = [
                name_struct.unpack(f.read(name_size))[0].rstrip(b"\x00").decode("utf-8") for _ in range(self.num_links)
            ]

            self.head_nodes = array.array("i", f.read(4 * self.num_links))
            self.tail_nodes = array.array("i", f.read(4 * self.num_links))
            self.link_types = array.array("i", f.read(4 * self.num_links))
            self.tank_index = array.array("i", f.read(4 * self.num_tanks))
            self.tank_surface_area = array.array("f", f.read(4 * self.num_tanks))
            self.elevation = array.array("f", f.read(4 * self.num_nodes))
            self.link_length = array.array("f", f.read(4 * self.num_links))
            self.link_diameter = array.array("f", f.read(4 * self.num_links))

            energy_struct = Struct("<i6f")
            self.pump_energies = [
                PumpEnergyUsage._make(energy_struct.unpack(f.read(energy_struct.size))) for _ in range(self.num_pumps)
            ]

            (self.demand_charge,) = unpack("<f", f.read(4))

            position_of_time_series_data = f.tell()

            epilog_struct = Struct("<4f3i")

            f.seek(-epilog_struct.size, os.SEEK_END)

            epilog_data = epilog_struct.unpack(f.read(epilog_struct.size))
            (
                self.avg_bulk_reaction_rate,
                self.avg_wall_reaction_rate,
                self.avg_tank_reaction_rate,
                self.avg_source_inflow_rate,
                self.num_reporting_periods,
                self.warning_flags,
                magic_number,
            ) = epilog_data

            if magic_number != MAGIC_NUMBER:
                raise MagicNumberError

            f.seek(position_of_time_series_data, os.SEEK_SET)

            self.timestep_node_results = []
            self.timestep_link_results = []

            for _ in range(self.num_reporting_periods):
                self.timestep_node_results.append(
                    NodeResults._make(
                        array.array("f", f.read(4 * self.num_nodes)) for _ in range(len(NodeResults._fields))
                    )
                )
                self.timestep_link_results.append(
                    LinkResults._make(
                        array.array("f", f.read(4 * self.num_links)) for _ in range(len(LinkResults._fields))
                    )
                )


class BinFileError(ValueError):
    """Custom exception for BinFile errors."""

    pass


class MagicNumberError(BinFileError):
    """Custom exception for invalid magic number in BinFile."""

    def __init__(self, message: str = "Invalid magic number in BinFile.") -> None:
        super().__init__(message)
        self.message = message


if __name__ == "__main__":
    OutputFile("temp.bin")
