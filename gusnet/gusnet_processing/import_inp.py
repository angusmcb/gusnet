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

import dataclasses
import warnings
from pathlib import Path
from typing import TYPE_CHECKING, Any

from qgis.core import (
    QgsProcessingContext,
    QgsProcessingException,
    QgsProcessingFeedback,
    QgsProcessingParameterCrs,
    QgsProcessingParameterEnum,
    QgsProcessingParameterFeatureSink,
    QgsProcessingParameterFile,
)
from qgis.PyQt.QtGui import QIcon

from gusnet.elements import FlowUnit, ModelLayer, ModelOptions
from gusnet.gusnet_processing.common import CommonProcessingBase, profile
from gusnet.i18n import tr
from gusnet.interface import Writer, options_from_wn, options_to_wn
from gusnet.settings import SettingKey
from gusnet.units import SpecificUnitNames, UnitNames

if TYPE_CHECKING:  # pragma: no cover
    import wntr


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

        self.addParameter(
            QgsProcessingParameterEnum(
                self.UNITS,
                tr("Units to to convert to (leave blank to use .inp file units)"),
                options=[fu.friendly_name for fu in FlowUnit],
                optional=True,
            )
        )

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
        feedback: QgsProcessingFeedback,
    ) -> dict[str, str]:
        with profile(tr("Verifying Dependencies"), 10, feedback):
            self._check_wntr()

        with profile(tr("Loading INP File"), 40, feedback):
            input_file = self.parameterAsFile(parameters, self.INPUT, context)
            wn = self._load_inp(input_file)

        options = options_from_wn(wn)

        options = self._set_flow_unit(parameters, context, options)

        options_to_wn(options, wn)

        self._describe_model(wn, feedback)

        feedback.pushInfo(
            tr("Will output with the following units: {flow_unit}").format(flow_unit=options.flow_unit.friendly_name)
        )

        self._options_to_save = options

        self._settings = {SettingKey.MODEL_LAYERS: {}}

        with profile(tr("Creating Outputs"), 80, feedback):
            network_writer = Writer(wn)

            # this is just to give a little user output
            # extra_analysis_type_names = [
            #     str(atype.name)
            #     for atype in [FieldGroup.ENERGY, FieldGroup.WATER_QUALITY_ANALYSIS, FieldGroup.PRESSURE_DEPENDENT_DEMAND]  # noqa: E501
            #     if network_model.field_groups is not None and atype in network_model.field_groups
            # ]
            # if len(extra_analysis_type_names):
            #     feedback.pushInfo("Will include columns for analysis types: " + ", ".join(extra_analysis_type_names))
            group_name = tr("Model Layers ({filename})").format(filename=Path(input_file).stem)
            units = SpecificUnitNames.from_options(options)
            outputs = self._write_to_sinks(parameters, context, network_writer, group_name, units)

        return outputs

    def _load_inp(self, input_file: str) -> wntr.network.WaterNetworkModel:
        import wntr

        try:
            wn: wntr.network.WaterNetworkModel = wntr.network.read_inpfile(input_file)
        except FileNotFoundError as e:
            msg = tr(".inp file does not exist ({input_file})").format(input_file=input_file)
            raise QgsProcessingException(msg) from e
        except wntr.epanet.exceptions.EpanetException as e:
            msg = tr("error reading .inp file: {e}").format(e=e)
            raise QgsProcessingException(msg) from e

        return wn

    def _set_flow_unit(
        self, parameters: dict[str, Any], context: QgsProcessingContext, options: ModelOptions
    ) -> ModelOptions:
        if parameters.get(self.UNITS) is not None:
            unit_enum_int = self.parameterAsEnum(parameters, self.UNITS, context)
            flow_unit = list(FlowUnit)[unit_enum_int]
            options = dataclasses.replace(options, flow_unit=flow_unit)

        return options

    def _write_to_sinks(
        self,
        parameters: dict[str, Any],
        context: QgsProcessingContext,
        network_writer: Writer,
        group_name: str,
        units: UnitNames | None,
    ) -> dict[str, str]:
        crs = self.parameterAsCrs(parameters, self.CRS, context)

        # for shapefile writing
        warnings.filterwarnings("ignore", "Field", RuntimeWarning)
        warnings.filterwarnings("ignore", "Normalized/laundered field name:", RuntimeWarning)

        outputs: dict[str, str] = {}
        layers: dict[ModelLayer, str] = {}
        for layer in ModelLayer:
            fields = network_writer.get_qgsfields(layer)
            (sink, outputs[layer.name]) = self.parameterAsSink(
                parameters, layer.name, context, fields, layer.qgs_wkb_type, crs
            )
            layers[layer] = outputs[layer.name]
            network_writer.write(layer, sink)

        self._setup_postprocessing(context, layers, group_name, False, unit_names=units)

        return outputs
