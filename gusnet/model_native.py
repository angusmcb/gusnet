from __future__ import annotations

import contextlib
import logging
import os
import tempfile
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING

from gusnet.elements import (
    Field,
    FieldGroup,
    FlowUnit,
    ModelLayer,
    ModelOptions,
    QualityParameter,
    ResultLayer,
)
from gusnet.epanet_wrapper import run_analysis
from gusnet.inpfile_reader import read_inp_file
from gusnet.inpfile_writer import write_inp_file
from gusnet.network import Network
from gusnet.output_file_reader import read_output_file
from gusnet.profiler import profile
from gusnet.wntr_wrapper import WntrWrapper

if TYPE_CHECKING:  # pragma: no cover
    with contextlib.suppress(ImportError):
        import wntr
    from typing import Self

logger = logging.getLogger(__name__)


@dataclass
class HybridWntrModel:
    network: Network
    options: ModelOptions
    elements: Mapping[ModelLayer, Mapping[str, Iterable]]
    """Contains the properties for each element (pipe, junction etc...) as a dict of lists/iterables"""

    @classmethod
    def from_inp_file(cls, file_path: os.PathLike | str) -> Self:
        elements, network, options = read_inp_file(file_path)
        return cls(network=network, options=options, elements=elements)

    @classmethod
    def from_wntr(
        cls,
        wn: wntr.network.WaterNetworkModel,
        flow_unit: FlowUnit | None,
        simulation_results: wntr.sim.SimulationResults | None = None,
    ) -> Self:
        wntr_wrapper = WntrWrapper(wn)
        options = wntr_wrapper.options_from_wn()
        elements = wntr_wrapper.get_elements(flow_unit)
        network = wntr_wrapper.get_network()
        model = cls(network=network, options=options, elements=elements)
        if simulation_results:
            wntr_wrapper.set_results(simulation_results)
            model._processed_results = wntr_wrapper.get_results(flow_unit)
        return model

    def write_inp_file(self, file_path: os.PathLike | str) -> None:
        write_inp_file(self.elements, self.options, self.network, file_path)

    def run(self, report_file: os.PathLike | str) -> None:
        with (
            tempfile.NamedTemporaryFile(mode="w+t", suffix=".inp") as input_file,
            tempfile.NamedTemporaryFile(mode="w+b", suffix=".bin") as output_file,
        ):
            self.write_inp_file(input_file.name)

            with profile("Run EPANET simulation"):
                run_analysis(input_file.name, report_file, output_file.name)

            with profile("Process BIN file results"):
                self._processed_results = read_output_file(output_file.name)

    def get_results(self) -> Mapping[ResultLayer, Mapping]:
        if self._processed_results is None:
            msg = "No results available. Have you run the simulation?"
            raise RuntimeError(msg)

        return self._processed_results

    def elements_to_wntr(self, wn: wntr.network.WaterNetworkModel) -> None:
        """Writes elements to a wntr model, without writing the options"""
        wntr_wrapper = WntrWrapper(wn)
        wntr_wrapper.options = self.options
        wntr_wrapper.set_elements(self.elements, self.network)

    def suggested_fields(self, layer: ModelLayer | ResultLayer | None = None) -> list[Field]:
        field_groups = FieldGroup.BASE

        if self.options.quality_parameter is not QualityParameter.NONE:
            field_groups = field_groups | FieldGroup.WATER_QUALITY_ANALYSIS

        if self.options.energy_report:
            field_groups = field_groups | FieldGroup.ENERGY

        if layer:
            return [field for field in layer.wq_fields() if field.field_group & field_groups]
        else:
            return [field for field in Field if field.field_group & field_groups]
