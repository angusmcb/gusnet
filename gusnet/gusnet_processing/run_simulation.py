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

import logging
import time
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any

from qgis.core import (
    QgsApplication,
    QgsCoordinateReferenceSystem,
    QgsProcessingContext,
    QgsProcessingException,
    QgsProcessingFeedback,
    QgsProcessingLayerPostProcessorInterface,
    QgsProcessingParameterDefinition,
    QgsProcessingParameterEnum,
    QgsProcessingParameterFeatureSink,
    QgsProcessingParameterFeatureSource,
    QgsProcessingParameterFileDestination,
    QgsProcessingParameterNumber,
    QgsProcessingParameterString,
    QgsProcessingUtils,
    QgsProject,
)
from qgis.PyQt.QtCore import QCoreApplication, QThread
from qgis.PyQt.QtGui import QIcon

import gusnet
from gusnet.elements import (
    DefaultOptions,
    DemandType,
    FlowUnit,
    HeadlossFormula,
    MassUnit,
    ModelLayer,
    ModelOptions,
    QualityParameter,
    ResultLayer,
    WallReactionOrder,
)
from gusnet.gusnet_processing.common import CommonProcessingBase, profile
from gusnet.i18n import tr
from gusnet.interface import (
    NetworkModelError,
    Writer,
    check_network,
    describe_network,
    describe_pipes,
    options_from_wn,
    options_to_wn,
)
from gusnet.pattern_curve import Pattern
from gusnet.settings import ProjectSettings, SettingKey
from gusnet.style import style
from gusnet.units import SpecificUnitNames

if TYPE_CHECKING:
    import wntr


class _ModelCreatorAlgorithm(CommonProcessingBase):
    UNITS = "UNITS"
    DURATION = "DURATION"
    HEADLOSS_FORMULA = "HEADLOSS_FORMULA"
    OUTPUT_INP = "OUTPUT_INP"
    DEMAND_TYPE = "DEMAND_TYPE"
    DEMAND_MULTIPLIER = "DEMAND_MULTIPLIER"
    EMITTER_EXPONENT = "EMITTER_EXPONENT"
    MINIMUM_PRESSURE = "MINIMUM_PRESSURE"
    REQUIRED_PRESSURE = "REQUIRED_PRESSURE"
    PRESSURE_EXPONENT = "PRESSURE_EXPONENT"
    ENERGY_PRICE = "ENERGY_PRICE"
    ENERGY_PATTERN = "ENERGY_PATTERN"
    ENERGY_PUMP_EFFICIENCY = "ENERGY_PUMP_EFFICIENCY"
    ENERGY_DEMAND_CHARGE = "ENERGY_DEMAND_CHARGE"
    QUALITY_PARAMETER = "QUALITY_PARAMETER"
    MASS_UNIT = "MASS_UNIT"
    RELATIVE_DIFFUSIVITY = "RELATIVE_DIFFUSIVITY"
    TRACE_NODE = "TRACE_NODE"
    QUALITY_TOLERANCE = "QUALITY_TOLERANCE"
    BULK_REACTION_ORDER = "BULK_REACTION_ORDER"
    WALL_REACTION_ORDER = "WALL_REACTION_ORDER"
    GLOBAL_BULK_COEFFICIENT = "GLOBAL_BULK_COEFFICIENT"
    GLOBAL_WALL_COEFFICIENT = "GLOBAL_WALL_COEFFICIENT"
    LIMITING_CONCENTRATION = "LIMITING_CONCENTRATION"
    WALL_COEFFICIENT_CORRELATION = "WALL_COEFFICIENT_CORRELATION"

    def initAlgorithm(self, config=None):  # noqa N802
        self.init_input_parameters()
        self.init_output_parameters()

    def options_to_param_values(self, options: ModelOptions) -> dict[str, Any]:
        """Convert ModelOptions to parameter values for the algorithm."""
        param_values: dict[str, Any] = {}

        param_values[self.UNITS] = list(FlowUnit).index(options.flow_unit)
        param_values[self.HEADLOSS_FORMULA] = list(HeadlossFormula).index(options.headloss_formula)
        param_values[self.DURATION] = options.simulation_duration
        param_values[self.DEMAND_TYPE] = list(DemandType).index(options.demand_type)
        param_values[self.DEMAND_MULTIPLIER] = options.demand_multiplier
        param_values[self.EMITTER_EXPONENT] = options.emitter_exponent
        param_values[self.MINIMUM_PRESSURE] = options.minimum_pressure
        param_values[self.REQUIRED_PRESSURE] = options.required_pressure
        param_values[self.PRESSURE_EXPONENT] = options.pressure_exponent
        param_values[self.ENERGY_PRICE] = options.energy_price
        param_values[self.ENERGY_PATTERN] = str(options.energy_pattern)
        param_values[self.ENERGY_PUMP_EFFICIENCY] = options.energy_pump_efficiency
        param_values[self.ENERGY_DEMAND_CHARGE] = options.energy_demand_charge
        param_values[self.QUALITY_PARAMETER] = list(QualityParameter).index(options.quality_parameter)
        param_values[self.MASS_UNIT] = list(MassUnit).index(options.mass_unit)
        param_values[self.RELATIVE_DIFFUSIVITY] = options.relative_diffusivity
        param_values[self.TRACE_NODE] = options.trace_node
        param_values[self.QUALITY_TOLERANCE] = options.quality_tolerance
        param_values[self.BULK_REACTION_ORDER] = options.bulk_reaction_order
        param_values[self.WALL_REACTION_ORDER] = list(WallReactionOrder).index(options.wall_reaction_order)
        param_values[self.GLOBAL_BULK_COEFFICIENT] = options.global_bulk_coefficient
        param_values[self.GLOBAL_WALL_COEFFICIENT] = options.global_wall_coefficient
        param_values[self.LIMITING_CONCENTRATION] = options.limiting_concentration
        param_values[self.WALL_COEFFICIENT_CORRELATION] = options.wall_coefficient_correlation

        return param_values

    def get_default_input_layers(self) -> dict[str, str]:
        project_settings = ProjectSettings(QgsProject.instance())
        saved_layers = project_settings.get(SettingKey.MODEL_LAYERS, {})
        input_layers = {
            layer_type.name: saved_layers.get(layer_type.name)
            for layer_type in ModelLayer
            if QgsProject.instance().mapLayer(saved_layers.get(layer_type.name))
        }
        return input_layers

    def init_input_parameters(self):
        project_settings = ProjectSettings(QgsProject.instance())

        default_values = self.options_to_param_values(DefaultOptions())
        saved_values = self.options_to_param_values(project_settings.load_options())

        default_layers = project_settings.get(SettingKey.MODEL_LAYERS, {})
        for lyr in ModelLayer:
            param = QgsProcessingParameterFeatureSource(
                lyr.name,
                lyr.friendly_name,
                types=lyr.acceptable_processing_vectors,
                optional=lyr is not ModelLayer.JUNCTIONS,
            )
            savedlyr = default_layers.get(lyr.name)
            if savedlyr and param.checkValueIsAcceptable(savedlyr) and QgsProject.instance().mapLayer(savedlyr):
                param.setGuiDefaultValueOverride(savedlyr)

            self.addParameter(param)

        param = QgsProcessingParameterEnum(self.UNITS, tr("Units"), options=[fu.friendly_name for fu in FlowUnit])
        self.addParameter(param)

        param = QgsProcessingParameterEnum(
            self.HEADLOSS_FORMULA, tr("Headloss Formula"), options=[f.friendly_name for f in HeadlossFormula]
        )
        self.addParameter(param)

        param = QgsProcessingParameterNumber(
            self.DURATION, tr("Simulation duration in hours (or 0 for single period)"), minValue=0
        )
        self.addParameter(param)

        param = QgsProcessingParameterEnum(
            self.DEMAND_TYPE, tr("Demand Type"), options=[option.friendly_name for option in DemandType]
        )
        self.addParameter(param)

        param = QgsProcessingParameterNumber(
            self.DEMAND_MULTIPLIER, tr("Demand Multiplier"), QgsProcessingParameterNumber.Double
        )
        param.setMetadata({"widget_wrapper": {"decimals": 2}})
        param.setFlags(param.flags() | QgsProcessingParameterDefinition.FlagAdvanced)
        self.addParameter(param)

        param = QgsProcessingParameterNumber(
            self.EMITTER_EXPONENT, tr("Emitter exponent"), QgsProcessingParameterNumber.Double, minValue=0
        )
        param.setMetadata({"widget_wrapper": {"decimals": 2}})
        param.setFlags(param.flags() | QgsProcessingParameterDefinition.FlagAdvanced)
        self.addParameter(param)

        param = QgsProcessingParameterNumber(
            self.MINIMUM_PRESSURE, tr("Minimum pressure"), QgsProcessingParameterNumber.Double, minValue=0
        )
        param.setMetadata({"widget_wrapper": {"decimals": 1}})
        param.setFlags(param.flags() | QgsProcessingParameterDefinition.FlagAdvanced)
        self.addParameter(param)

        param = QgsProcessingParameterNumber(
            self.REQUIRED_PRESSURE, tr("Required pressure"), QgsProcessingParameterNumber.Double, minValue=0.1
        )
        param.setMetadata({"widget_wrapper": {"decimals": 1}})
        param.setFlags(param.flags() | QgsProcessingParameterDefinition.FlagAdvanced)
        self.addParameter(param)

        param = QgsProcessingParameterNumber(self.PRESSURE_EXPONENT, tr("Pressure exponent"), minValue=0)
        param.setFlags(param.flags() | QgsProcessingParameterDefinition.FlagAdvanced)
        self.addParameter(param)

        param = QgsProcessingParameterNumber(
            self.ENERGY_PRICE, tr("Energy price (per kWh)"), QgsProcessingParameterNumber.Double, minValue=0
        )
        param.setMetadata({"widget_wrapper": {"decimals": 3}})
        param.setFlags(param.flags() | QgsProcessingParameterDefinition.FlagAdvanced)
        self.addParameter(param)

        # Optional: allow empty / unset energy price pattern
        param = QgsProcessingParameterString(self.ENERGY_PATTERN, tr("Energy price pattern"), optional=True)
        param.setFlags(param.flags() | QgsProcessingParameterDefinition.FlagAdvanced)
        self.addParameter(param)

        param = QgsProcessingParameterNumber(
            self.ENERGY_PUMP_EFFICIENCY, tr("Pump efficiency (%)"), minValue=0, maxValue=100
        )
        param.setFlags(param.flags() | QgsProcessingParameterDefinition.FlagAdvanced)
        self.addParameter(param)

        param = QgsProcessingParameterNumber(self.ENERGY_DEMAND_CHARGE, tr("Energy demand charge"), minValue=0)
        param.setFlags(param.flags() | QgsProcessingParameterDefinition.FlagAdvanced)
        self.addParameter(param)

        param = QgsProcessingParameterEnum(
            self.QUALITY_PARAMETER, tr("Quality analysis"), options=[qp.friendly_name for qp in QualityParameter]
        )
        param.setFlags(param.flags() | QgsProcessingParameterDefinition.FlagAdvanced)
        self.addParameter(param)

        param = QgsProcessingParameterEnum(
            self.MASS_UNIT, tr("Mass unit"), options=[mu.friendly_name for mu in MassUnit]
        )
        param.setFlags(param.flags() | QgsProcessingParameterDefinition.FlagAdvanced)
        self.addParameter(param)

        param = QgsProcessingParameterNumber(self.RELATIVE_DIFFUSIVITY, tr("Relative diffusivity"), minValue=0)
        param.setFlags(param.flags() | QgsProcessingParameterDefinition.FlagAdvanced)
        self.addParameter(param)

        # Optional: trace node may be left unset
        param = QgsProcessingParameterString(self.TRACE_NODE, tr("Trace node name"), optional=True)
        param.setFlags(param.flags() | QgsProcessingParameterDefinition.FlagAdvanced)
        self.addParameter(param)

        param = QgsProcessingParameterNumber(self.QUALITY_TOLERANCE, tr("Quality tolerance"), minValue=0)
        param.setFlags(param.flags() | QgsProcessingParameterDefinition.FlagAdvanced)
        self.addParameter(param)

        param = QgsProcessingParameterNumber(self.BULK_REACTION_ORDER, tr("Bulk reaction order"), minValue=0)
        param.setFlags(param.flags() | QgsProcessingParameterDefinition.FlagAdvanced)
        self.addParameter(param)

        param = QgsProcessingParameterEnum(
            self.WALL_REACTION_ORDER, tr("Wall reaction order"), options=[wr.friendly_name for wr in WallReactionOrder]
        )
        param.setFlags(param.flags() | QgsProcessingParameterDefinition.FlagAdvanced)
        self.addParameter(param)

        param = QgsProcessingParameterNumber(self.GLOBAL_BULK_COEFFICIENT, tr("Global bulk coefficient"), minValue=0)
        param.setFlags(param.flags() | QgsProcessingParameterDefinition.FlagAdvanced)
        self.addParameter(param)

        param = QgsProcessingParameterNumber(self.GLOBAL_WALL_COEFFICIENT, tr("Global wall coefficient"), minValue=0)
        param.setFlags(param.flags() | QgsProcessingParameterDefinition.FlagAdvanced)
        self.addParameter(param)

        param = QgsProcessingParameterNumber(self.LIMITING_CONCENTRATION, tr("Limiting concentration"), minValue=0)
        param.setFlags(param.flags() | QgsProcessingParameterDefinition.FlagAdvanced)
        self.addParameter(param)

        param = QgsProcessingParameterNumber(
            self.WALL_COEFFICIENT_CORRELATION, tr("Wall coefficient correlation"), minValue=0
        )
        param.setFlags(param.flags() | QgsProcessingParameterDefinition.FlagAdvanced)
        self.addParameter(param)

        for param_def in self.parameterDefinitions():
            param_name = param_def.name()
            if param_name in default_values:
                param_def.setDefaultValue(default_values[param_name])
                param_def.setGuiDefaultValueOverride(saved_values[param_name])

    def init_output_parameters(self):
        pass

    def init_output_files_parameters(self):
        self.addParameter(
            QgsProcessingParameterFeatureSink(ResultLayer.NODES.results_name, tr("Simulation Results - Nodes"))
        )
        self.addParameter(
            QgsProcessingParameterFeatureSink(ResultLayer.LINKS.results_name, tr("Simulation Results - Links"))
        )

    def init_export_inp_parameter(self):
        self.addParameter(
            QgsProcessingParameterFileDestination(self.OUTPUT_INP, tr("Output .inp file"), fileFilter="*.inp")
        )

    def _get_crs(self, parameters: dict[str, Any], context: QgsProcessingContext) -> QgsCoordinateReferenceSystem:
        junction_source = self.parameterAsSource(parameters, ModelLayer.JUNCTIONS.name, context)
        return junction_source.sourceCrs()

    def _get_model_options(self, parameters: dict[str, Any], context: QgsProcessingContext) -> ModelOptions:
        """
        Get the model options from the parameters.
        """

        # Numeric/simple parameters
        duration = self.parameterAsDouble(parameters, self.DURATION, context)
        demand_multiplier = self.parameterAsDouble(parameters, self.DEMAND_MULTIPLIER, context)
        emitter_exponent = self.parameterAsDouble(parameters, self.EMITTER_EXPONENT, context)
        minimum_pressure = self.parameterAsDouble(parameters, self.MINIMUM_PRESSURE, context)
        required_pressure = self.parameterAsDouble(parameters, self.REQUIRED_PRESSURE, context)
        pressure_exponent = self.parameterAsDouble(parameters, self.PRESSURE_EXPONENT, context)

        energy_price = self.parameterAsDouble(parameters, self.ENERGY_PRICE, context)
        energy_pump_efficiency = self.parameterAsDouble(parameters, self.ENERGY_PUMP_EFFICIENCY, context)
        energy_demand_charge = self.parameterAsDouble(parameters, self.ENERGY_DEMAND_CHARGE, context)

        relative_diffusivity = self.parameterAsDouble(parameters, self.RELATIVE_DIFFUSIVITY, context)

        quality_tolerance = self.parameterAsDouble(parameters, self.QUALITY_TOLERANCE, context)

        bulk_reaction_order = self.parameterAsDouble(parameters, self.BULK_REACTION_ORDER, context)

        global_bulk_coefficient = self.parameterAsDouble(parameters, self.GLOBAL_BULK_COEFFICIENT, context)
        global_wall_coefficient = self.parameterAsDouble(parameters, self.GLOBAL_WALL_COEFFICIENT, context)
        limiting_concentration = self.parameterAsDouble(parameters, self.LIMITING_CONCENTRATION, context)
        wall_coefficient_correlation = self.parameterAsDouble(parameters, self.WALL_COEFFICIENT_CORRELATION, context)

        trace_node = self.parameterAsString(parameters, self.TRACE_NODE, context) or ""

        try:
            energy_pattern = Pattern(self.parameterAsString(parameters, self.ENERGY_PATTERN, context))
        except ValueError as e:
            raise QgsProcessingException(e) from e

        # Enum parameters

        flow_unit = list(FlowUnit)[self.parameterAsEnum(parameters, self.UNITS, context)]
        headloss = list(HeadlossFormula)[self.parameterAsEnum(parameters, self.HEADLOSS_FORMULA, context)]
        demand_type = list(DemandType)[self.parameterAsEnum(parameters, self.DEMAND_TYPE, context)]
        quality_parameter = list(QualityParameter)[self.parameterAsEnum(parameters, self.QUALITY_PARAMETER, context)]
        mass_unit = list(MassUnit)[self.parameterAsEnum(parameters, self.MASS_UNIT, context)]
        wall_reaction_order = list(WallReactionOrder)[
            self.parameterAsEnum(parameters, self.WALL_REACTION_ORDER, context)
        ]

        return ModelOptions(
            flow_unit=flow_unit,
            headloss_formula=headloss,
            simulation_duration=duration,
            demand_multiplier=demand_multiplier,
            emitter_exponent=emitter_exponent,
            demand_type=demand_type,
            minimum_pressure=minimum_pressure,
            required_pressure=required_pressure,
            pressure_exponent=pressure_exponent,
            energy_report=True,
            energy_price=energy_price,
            energy_pattern=energy_pattern,
            energy_pump_efficiency=energy_pump_efficiency,
            energy_demand_charge=energy_demand_charge,
            quality_parameter=quality_parameter,
            mass_unit=mass_unit,
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

    def _get_wn(
        self, parameters: dict[str, Any], context: QgsProcessingContext, feedback: QgsProcessingFeedback
    ) -> wntr.network.WaterNetworkModel:
        sources = {lyr.name: self.parameterAsSource(parameters, lyr.name, context) for lyr in ModelLayer}

        crs = self._get_crs(parameters, context)

        model_options = self._get_model_options(parameters, context)

        flow_unit_string = model_options.flow_unit.name
        headloss_string = model_options.headloss_formula.value

        try:
            with logger_to_feedback("gusnet", feedback), logger_to_feedback("wntr", feedback):
                wn = gusnet.from_qgis(sources, flow_unit_string, headloss_string, project=context.project(), crs=crs)
            check_network(wn)
        except NetworkModelError as e:
            raise QgsProcessingException(tr("Error preparing model: {exception}").format(exception=e)) from None

        try:
            options_to_wn(model_options, wn)
        except ValueError as e:
            raise QgsProcessingException(e) from e

        return wn

    def _run_simulation(
        self, feedback: QgsProcessingFeedback, wn: wntr.network.WaterNetworkModel
    ) -> wntr.sim.SimulationResults:
        """
        Run the simulation on the given WaterNetworkModel.
        """

        import wntr

        temp_folder = Path(QgsProcessingUtils.tempFolder()) / "wntr"
        sim = wntr.sim.EpanetSimulator(wn)
        try:
            with logger_to_feedback("wntr", feedback):
                sim_results = sim.run_sim(file_prefix=str(temp_folder))
        except wntr.epanet.exceptions.EpanetException as e:
            raise QgsProcessingException(tr("Epanet error: {exception}").format(exception=e)) from e

        return sim_results

    def _describe_model(self, wn: wntr.network.WaterNetworkModel, feedback: QgsProcessingFeedback) -> None:
        if hasattr(feedback, "pushFormattedMessage"):  # QGIS > 3.32
            feedback.pushFormattedMessage(*describe_network(wn))
            feedback.pushFormattedMessage(*describe_pipes(wn))
        else:
            feedback.pushInfo(describe_network(wn)[1])
            feedback.pushInfo(describe_pipes(wn)[1])

    def prepareAlgorithm(  # noqa: N802
        self, parameters: dict[str, Any], context: QgsProcessingContext, feedback: QgsProcessingFeedback
    ) -> None:
        if QThread.currentThread() == QCoreApplication.instance().thread():
            project_settings = ProjectSettings()

            layers = {
                lyr.name: input_layer.id()
                for lyr in ModelLayer
                if (input_layer := self.parameterAsVectorLayer(parameters, lyr.name, context))
            }
            project_settings.set(SettingKey.MODEL_LAYERS, layers)

            project_settings.save_options(self._get_model_options(parameters, context))

        return super().prepareAlgorithm(parameters, context, feedback)

    def write_output_result_layers(
        self,
        parameters: dict[str, Any],
        context: QgsProcessingContext,
        feedback: QgsProcessingFeedback,
        wn: wntr.network.WaterNetworkModel,
        sim_results: wntr.sim.SimulationResults,
    ) -> dict[str, str]:
        outputs: dict[str, str] = {}

        with logger_to_feedback("wntr", feedback), logger_to_feedback("gusnet", feedback):
            result_writer = Writer(wn, sim_results)  # type: ignore

        crs = self._get_crs(parameters, context)

        group_name = tr("Simulation Results ({finish_time})").format(finish_time=time.strftime("%X"))

        options = options_from_wn(wn)

        style_theme = "extended" if options.simulation_duration else None
        unit_names = SpecificUnitNames.from_options(options)

        for layer_type in ResultLayer:
            fields = result_writer.get_qgsfields(layer_type)

            (sink, layer_id) = self.parameterAsSink(
                parameters, layer_type.results_name, context, fields, layer_type.qgs_wkb_type, crs
            )

            result_writer.write(layer_type, sink)

            outputs[layer_type.results_name] = layer_id

            if not context.willLoadLayerOnCompletion(layer_id):
                continue

            post_processor = LayerPostProcessor(layer_type, style_theme, unit_names)

            layer_details = context.layerToLoadOnCompletionDetails(layer_id)
            layer_details.setPostProcessor(post_processor)
            layer_details.groupName = group_name
            layer_details.layerSortKey = 1 if layer_type is ResultLayer.LINKS else 2

            self.post_processors[layer_id] = post_processor

        return outputs

    def write_inp_file(
        self,
        parameters: dict[str, Any],
        context: QgsProcessingContext,
        feedback: QgsProcessingFeedback,
        wn: wntr.network.WaterNetworkModel,
    ) -> dict[str, str]:
        import wntr

        inp_file = self.parameterAsFile(parameters, self.OUTPUT_INP, context)

        wntr.network.write_inpfile(wn, inp_file)

        feedback.pushInfo(tr(".inp file written to: {file_path}").format(file_path=inp_file))

        return {self.OUTPUT_INP: inp_file}


class RunSimulation(_ModelCreatorAlgorithm):
    def createInstance(self):  # noqa N802
        return RunSimulation()

    def name(self):
        return "run"

    def displayName(self):  # noqa N802
        return tr("Run Simulation")

    def shortHelpString(self):  # noqa N802
        return tr("""
This will take all of the model layers (junctions, tanks, reservoirs, pipes, valves, pumps), \
combine them with the chosen options, and run a simulation on WNTR.
The output files are a layer of 'nodes' (junctions, tanks, reservoirs) and \
'links' (pipes, valves, pumps).
Optionally, you can also output an EPANET '.inp' file which can be run / viewed \
in other software.
            """)

    def icon(self):
        return QIcon("gusnet:run.svg")

    def init_output_parameters(self):
        self.init_output_files_parameters()

    @profile(tr("Run Simulation"))
    def processAlgorithm(  # noqa N802
        self,
        parameters: dict[str, Any],
        context: QgsProcessingContext,
        feedback: QgsProcessingFeedback,
    ) -> dict:
        with profile(tr("Verifying Dependencies"), 10, feedback):
            self._check_wntr()

        with profile(tr("Preparing Model"), 30, feedback):
            wn = self._get_wn(parameters, context, feedback)

            self._describe_model(wn, feedback)

        with profile(tr("Running Simulation"), 50, feedback):
            sim_results = self._run_simulation(feedback, wn)

        with profile(tr("Creating Outputs"), 80, feedback):
            outputs = self.write_output_result_layers(parameters, context, feedback, wn, sim_results)

        return outputs


class ExportInpFile(_ModelCreatorAlgorithm):
    def createInstance(self):  # noqa N802
        return ExportInpFile()

    def name(self):
        return "export"

    def displayName(self):  # noqa N802
        return tr("Export Inp File")

    def shortHelpString(self):  # noqa N802
        return tr("""
This will take all of the model layers (junctions, tanks, reservoirs, pipes, valves, pumps), \
combine them with the chosen options, and run a simulation on WNTR.
The output files are a layer of 'nodes' (junctions, tanks, reservoirs) and \
'links' (pipes, valves, pumps).
Optionally, you can also output an EPANET '.inp' file which can be run / viewed \
in other software.
            """)

    def icon(self):
        return QgsApplication.getThemeIcon("mActionFileSave.svg")

    def init_output_parameters(self):
        self.init_export_inp_parameter()

    @profile(tr("Export Inp File"))
    def processAlgorithm(  # noqa N802
        self,
        parameters: dict[str, Any],
        context: QgsProcessingContext,
        feedback: QgsProcessingFeedback,
    ) -> dict:
        with profile(tr("Verifying Dependencies"), 10, feedback):
            self._check_wntr()

        with profile(tr("Preparing Model"), 30, feedback):
            wn = self._get_wn(parameters, context, feedback)

            self._describe_model(wn, feedback)

        with profile(tr("Creating Outputs"), 80, feedback):
            outputs = self.write_inp_file(parameters, context, feedback, wn)

        return outputs


class LayerPostProcessor(QgsProcessingLayerPostProcessorInterface):
    def __init__(self, layer_type: ResultLayer, style_theme: str | None, unit_names: SpecificUnitNames):
        super().__init__()
        self.layer_type = layer_type
        self.style_theme = style_theme
        self.unit_names = unit_names

    def postProcessLayer(self, layer, context, feedback):  # noqa N802 ARG002
        style(layer, self.layer_type, self.style_theme, self.unit_names)


@contextmanager
def logger_to_feedback(logger_name: str, feedback: QgsProcessingFeedback):
    """
    Context manager to redirect logging messages to QgsProcessingFeedback.
    """

    class FeedbackHandler(logging.Handler):
        def emit(self, record):
            feedback.pushWarning(record.getMessage())

    logger = logging.getLogger(logger_name)
    logger.propagate = False
    logging_handler = FeedbackHandler()
    logging_handler.setLevel("INFO")
    logger.addHandler(logging_handler)

    try:
        yield
    finally:
        logger.propagate = True
        logger.removeHandler(logging_handler)
