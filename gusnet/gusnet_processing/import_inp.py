"""
***************************************************************************
*                                                                         *
*   This program is free software; you can redistribute it and/or modify  *
*   it under the terms of the GNU General Public License as published by  *
*   the Free Software Foundation; either version 2 of the License, or     *
*   (at your option) any later version.                                   *
*                                                                         *
***************************************************************************
"""

from __future__ import annotations

import warnings
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from qgis.core import (
    QgsProcessingContext,
    QgsProcessingException,
    QgsProcessingFeedback,
    QgsProcessingParameterCrs,
    QgsProcessingParameterFeatureSink,
    QgsProcessingParameterFile,
)
from qgis.PyQt.QtGui import QIcon

from gusnet.elements import ModelLayer, ModelOptions
from gusnet.feature_writer import get_qgs_fields_from_options, write
from gusnet.gusnet_processing.common import CommonProcessingBase
from gusnet.i18n import tr
from gusnet.inpfile_reader import InpFileReadError, read_inp_file
from gusnet.network import Network
from gusnet.profiler import profile
from gusnet.settings import SettingKey
from gusnet.units import SpecificUnitNames, UnitNames


class ImportInp(CommonProcessingBase):
    INPUT = "INPUT"
    CRS = "CRS"
    UNITS = "UNITS"

    def createInstance(self):  # noqa N802
        return ImportInp()

    def name(self):
        return "import_inp"

    def displayName(self):  # noqa N802
        return tr("Import from Epanet INP file")

    def shortHelpString(self):  # noqa N802
        return tr("""
            Import all junctions, tanks, reservoirs, pipes, pumps and valves from an EPANET inp file.
            This will also save selected options from the .inp file.
            All units will be converted into the unit set selected. If not selected, it will default \
            to the unit set in the .inp file.
            """)

    def icon(self):
        return QIcon(":images/themes/default/mActionFileOpen.svg")

    def initAlgorithm(self, config=None):  # noqa N802
        self.addParameter(
            QgsProcessingParameterFile(
                self.INPUT,
                tr("Epanet Input File (.inp)"),
                behavior=QgsProcessingParameterFile.File,
                extension="inp",
            )
        )

        param = QgsProcessingParameterCrs(self.CRS, tr("Coordinate Reference System (CRS)"))
        param.setGuiDefaultValueOverride("ProjectCrs")
        self.addParameter(param)

        # self.addParameter(
        #     QgsProcessingParameterEnum(
        #         self.UNITS,
        #         tr("Units to to convert to (leave blank to use .inp file units)"),
        #         options=[fu.friendly_name for fu in FlowUnit],
        #         optional=True,
        #     )
        # )

        for layer in ModelLayer:
            self.addParameter(QgsProcessingParameterFeatureSink(layer.name, layer.friendly_name))

    def preprocessParameters(self, parameters):  # noqa N802
        if not Path(parameters[self.INPUT]).is_file():
            example_file = Path(__file__).parent.parent / "resources" / "examples" / parameters[self.INPUT]
            if example_file.is_file():
                parameters[self.INPUT] = str(example_file)

        return parameters

    @profile(tr("Import from Epanet INP file"))
    def processAlgorithm(  # noqa N802
        self,
        parameters: dict[str, Any],
        context: QgsProcessingContext,
        feedback: QgsProcessingFeedback | None,
    ) -> dict[str, str]:
        if not feedback:
            feedback = QgsProcessingFeedback()

        with profile(tr("Loading INP File"), 30, feedback):
            input_file = self.parameterAsFile(parameters, self.INPUT, context)

            try:
                attribute_tables, network, options = read_inp_file(input_file)
            except InpFileReadError as e:
                raise QgsProcessingException(e) from e

            # options = self._set_flow_unit(parameters, context, options)

            # self._describe_model(model.wn, feedback)

            feedback.pushInfo(
                tr("Will output with the following units: {flow_unit}").format(
                    flow_unit=options.flow_unit.friendly_name
                )
            )

        self._options_to_save = options
        self._settings = {SettingKey.MODEL_LAYERS: {}}

        with profile(tr("Creating Outputs"), 80, feedback):
            group_name = tr("Model Layers ({filename})").format(filename=Path(input_file).stem)
            units = SpecificUnitNames.from_options(options)
            outputs = self._write_to_sinks(parameters, context, attribute_tables, network, options, group_name, units)

        return outputs

    # def _set_flow_unit(
    #     self, parameters: dict[str, Any], context: QgsProcessingContext, options: ModelOptions
    # ) -> ModelOptions:
    #     if parameters.get(self.UNITS) is not None:
    #         unit_enum_int = self.parameterAsEnum(parameters, self.UNITS, context)
    #         flow_unit = list(FlowUnit)[unit_enum_int]
    #         options = dataclasses.replace(options, flow_unit=flow_unit)

    #     return options

    def _write_to_sinks(
        self,
        parameters: dict[str, Any],
        context: QgsProcessingContext,
        attribute_tables: Mapping[ModelLayer, Mapping[str, list[Any]]],
        network: Network,
        options: ModelOptions,
        group_name: str,
        units: UnitNames | None,
    ) -> dict[str, str]:
        crs = self.parameterAsCrs(parameters, self.CRS, context)

        # for shapefile writing
        warnings.filterwarnings("ignore", "Field", RuntimeWarning)
        warnings.filterwarnings("ignore", "Normalized/laundered field name:", RuntimeWarning)

        outputs: dict[str, str] = {}
        for layer in ModelLayer:
            attribute_table = attribute_tables.get(layer)

            fields = get_qgs_fields_from_options(options, layer)

            (sink, outputs[layer]) = self.parameterAsSink(parameters, layer, context, fields, layer.wkb_type, crs)

            geometries = network.node_geometries if layer.is_node else network.link_geometries

            if sink and attribute_table is not None:
                write(sink, fields, attribute_table, geometries)

        self._setup_postprocessing(context, outputs, group_name, False, unit_names=units)

        return outputs
