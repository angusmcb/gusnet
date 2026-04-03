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
import datetime
import logging
import time
import uuid
from collections.abc import Generator, Mapping
from contextlib import contextmanager
from enum import Enum
from pathlib import Path
from types import MappingProxyType
from typing import Any, cast, get_type_hints

from qgis.core import (
    QgsApplication,
    QgsCoordinateReferenceSystem,
    QgsProcessingContext,
    QgsProcessingException,
    QgsProcessingFeatureSource,
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

from gusnet.elements import (
    DEFAULT_OPTIONS,
    DemandType,
    EnumWithName,
    FlowUnit,
    HeadlossFormula,
    MassUnit,
    Model,
    ModelLayer,
    ModelOptions,
    OptionsFieldMetadata,
    QualityParameter,
    ResultLayer,
    WallReactionOrder,
)
from gusnet.epanet_wrapper import EpanetWrapperError, run_analysis
from gusnet.feature_reader import ReadFeatureError, read
from gusnet.feature_writer import get_qgs_fields_from_options, write
from gusnet.gusnet_processing.common import CommonProcessingBase
from gusnet.i18n import tr
from gusnet.inpfile_writer import write_inp_file
from gusnet.network import Network
from gusnet.output_file_reader import BinFileError, read_output_file
from gusnet.pattern_curve import Pattern
from gusnet.profiler import profile
from gusnet.settings import ProjectSettings, SettingKey
from gusnet.statistics import ModelStatistics
from gusnet.style import style
from gusnet.units import SpecificUnitNames
from gusnet.verify_model import VerificationError, verify_model


class _ModelCreatorAlgorithm(CommonProcessingBase):
    UNITS = "UNITS"
    DURATION = "DURATION"
    HEADLOSS_FORMULA = "HEADLOSS_FORMULA"
    OUTPUT_INP = "OUTPUT_INP"
    DEMAND_TYPE = "DEMAND_TYPE"
    DEMAND_MULTIPLIER = "DEMAND_MULTIPLIER"
    DEFAULT_PATTERN = "DEFAULT_PATTERN"
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
        self.init_model_layer_parameters()
        self.init_settings_parameters()
        self.init_output_parameters()

    def options_to_param_values(self, options: ModelOptions) -> Mapping[str, Any]:
        """Convert ModelOptions to parameter values for the algorithm."""

        in_dict = dataclasses.asdict(options)
        out_dict: dict[str, Any] = {}
        for data_field in dataclasses.fields(options):
            field_value = in_dict[data_field.name]
            out_value: Any = None

            if isinstance(field_value, Enum):
                out_value = list(type(field_value)).index(field_value)
            elif isinstance(field_value, datetime.timedelta):
                out_value = field_value.total_seconds() / 3600
            elif isinstance(field_value, Pattern):
                out_value = str(field_value)
            else:
                out_value = field_value

            out_dict[data_field.name.upper()] = out_value

        return MappingProxyType(out_dict)

        param_values: dict[str, Any] = {}

        param_values[self.UNITS] = list(FlowUnit).index(options.flow_units)
        param_values[self.HEADLOSS_FORMULA] = list(HeadlossFormula).index(options.headloss_formula)
        param_values[self.DURATION] = options.simulation_duration.total_seconds() / 3600  # hours
        param_values[self.DEMAND_TYPE] = list(DemandType).index(options.demand_model)
        param_values[self.DEMAND_MULTIPLIER] = options.demand_multiplier
        param_values[self.DEFAULT_PATTERN] = str(options.default_pattern)
        param_values[self.EMITTER_EXPONENT] = options.emitter_exponent
        param_values[self.MINIMUM_PRESSURE] = options.minimum_pressure
        param_values[self.REQUIRED_PRESSURE] = options.required_pressure
        param_values[self.PRESSURE_EXPONENT] = options.pressure_exponent
        param_values[self.ENERGY_PRICE] = options.energy_price
        param_values[self.ENERGY_PATTERN] = str(options.energy_price_pattern)
        param_values[self.ENERGY_PUMP_EFFICIENCY] = options.energy_pump_efficiency
        param_values[self.ENERGY_DEMAND_CHARGE] = options.energy_demand_charge
        param_values[self.QUALITY_PARAMETER] = list(QualityParameter).index(options.quality_parameter)
        param_values[self.MASS_UNIT] = list(MassUnit).index(options.mass_units)
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
        project = QgsProject.instance()
        if not project:
            return {}

        saved_layers = ProjectSettings(project).get(SettingKey.MODEL_LAYERS, {})
        input_layers = {
            str(layer_type): saved_layers.get(layer_type.name)
            for layer_type in ModelLayer
            if project.mapLayer(saved_layers.get(layer_type))
        }

        return input_layers

    def init_model_layer_parameters(self) -> None:
        project_settings = ProjectSettings(QgsProject.instance())
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

        # self.add_param_enum(self.UNITS, tr("Units"), FlowUnit, advanced=False)

        # self.add_param_enum(self.HEADLOSS_FORMULA, tr("Headloss Formula"), HeadlossFormula, advanced=False)

        # self.add_param_float(self.DURATION, tr("Simulation duration in hours (or 0 for single period)"), 2, 0, False)

        # self.add_param_enum(self.DEMAND_TYPE, tr("Demand type"), DemandType, advanced=False)

        # self.add_param_float(self.DEMAND_MULTIPLIER, tr("Demand Multiplier"), 2, None, advanced=True)

        # param = QgsProcessingParameterString(self.DEFAULT_PATTERN, tr("Default Demand Pattern"), optional=True)
        # param.setFlags(param.flags() | QgsProcessingParameterDefinition.FlagAdvanced)
        # self.addParameter(param)

        # self.add_param_float(self.EMITTER_EXPONENT, tr("Emitter exponent"), 2, None, True)

        # self.add_param_float(self.MINIMUM_PRESSURE, tr("Minimum pressure"), 1, 0, True)

        # self.add_param_float(self.REQUIRED_PRESSURE, tr("Required pressure"), 1, 0.1, True)

        # self.add_param_float(self.PRESSURE_EXPONENT, tr("Pressure exponent"), 2, 0, True)

        # self.add_param_float(self.ENERGY_PRICE, tr("Energy price (per kWh)"), 3, 0, True)

        # # Optional: allow empty / unset energy price pattern
        # param = QgsProcessingParameterString(self.ENERGY_PATTERN, tr("Energy price pattern"), optional=True)
        # param.setFlags(param.flags() | QgsProcessingParameterDefinition.FlagAdvanced)
        # self.addParameter(param)

        # self.add_param_float(self.ENERGY_PUMP_EFFICIENCY, tr("Pump efficiency (%)"), 1, 0, True)

        # self.add_param_float(self.ENERGY_DEMAND_CHARGE, tr("Energy demand charge"), 2, 0, True)

        # self.add_param_enum(self.QUALITY_PARAMETER, tr("Quality analysis"), QualityParameter, advanced=True)

        # self.add_param_enum(self.MASS_UNIT, tr("Mass unit"), MassUnit, advanced=True)

        # param = QgsProcessingParameterNumber(self.RELATIVE_DIFFUSIVITY, tr("Relative diffusivity"), minValue=0)
        # param.setFlags(param.flags() | QgsProcessingParameterDefinition.FlagAdvanced)
        # self.addParameter(param)

        # # Optional: trace node may be left unset
        # param = QgsProcessingParameterString(self.TRACE_NODE, tr("Trace node name"), optional=True)
        # param.setFlags(param.flags() | QgsProcessingParameterDefinition.FlagAdvanced)
        # self.addParameter(param)

        # param = QgsProcessingParameterNumber(self.QUALITY_TOLERANCE, tr("Quality tolerance"), minValue=0)
        # param.setFlags(param.flags() | QgsProcessingParameterDefinition.FlagAdvanced)
        # self.addParameter(param)

        # param = QgsProcessingParameterNumber(self.BULK_REACTION_ORDER, tr("Bulk reaction order"), minValue=0)
        # param.setFlags(param.flags() | QgsProcessingParameterDefinition.FlagAdvanced)
        # self.addParameter(param)

        # self.add_param_enum(self.WALL_REACTION_ORDER, tr("Wall reaction order"), WallReactionOrder, advanced=True)

        # param = QgsProcessingParameterNumber(self.GLOBAL_BULK_COEFFICIENT, tr("Global bulk coefficient"))
        # param.setFlags(param.flags() | QgsProcessingParameterDefinition.FlagAdvanced)
        # self.addParameter(param)

        # param = QgsProcessingParameterNumber(self.GLOBAL_WALL_COEFFICIENT, tr("Global wall coefficient"))
        # param.setFlags(param.flags() | QgsProcessingParameterDefinition.FlagAdvanced)
        # self.addParameter(param)

        # param = QgsProcessingParameterNumber(self.LIMITING_CONCENTRATION, tr("Limiting concentration"), minValue=0)
        # param.setFlags(param.flags() | QgsProcessingParameterDefinition.FlagAdvanced)
        # self.addParameter(param)

        # param = QgsProcessingParameterNumber(
        #     self.WALL_COEFFICIENT_CORRELATION, tr("Wall coefficient correlation"), minValue=0
        # )
        # param.setFlags(param.flags() | QgsProcessingParameterDefinition.FlagAdvanced)
        # self.addParameter(param)

        # for param_def in self.parameterDefinitions():
        #     param_name = param_def.name()
        #     if param_name in default_values:
        #         param_def.setDefaultValue(default_values[param_name])
        #         param_def.setGuiDefaultValueOverride(saved_values[param_name])

    def init_settings_parameters(self) -> None:
        data_types = get_type_hints(ModelOptions)
        default_values = self.options_to_param_values(DEFAULT_OPTIONS)
        saved_values = self.options_to_param_values(ProjectSettings(QgsProject.instance()).load_options())

        for data_field in dataclasses.fields(ModelOptions):
            field_name = data_field.name.upper()
            field_type = data_types[data_field.name]
            metadata = cast(OptionsFieldMetadata, data_field.metadata)

            param: QgsProcessingParameterDefinition | None = None

            if issubclass(field_type, EnumWithName):
                param = QgsProcessingParameterEnum(field_name, options=[e.friendly_name for e in field_type])

            elif field_type is float or field_type is int or field_type is datetime.timedelta:
                param_type = (
                    QgsProcessingParameterNumber.Integer if field_type is int else QgsProcessingParameterNumber.Double
                )
                num_param = QgsProcessingParameterNumber(field_name, type=param_type)

                if metadata.get("decimals") is not None:
                    num_param.setMetadata({"widget_wrapper": {"decimals": metadata["decimals"]}})

                if metadata.get("minimum") is not None:
                    num_param.setMinimum(metadata["minimum"])

                if metadata.get("maximum") is not None:
                    num_param.setMaximum(metadata["maximum"])

                param = num_param

            elif field_type is Pattern or field_type is str:
                param = QgsProcessingParameterString(field_name, optional=True)

            else:
                msg = f"Unsupported field type for settings parameter: {field_type}"
                raise TypeError(msg)

            param.setDescription(metadata.get("description", field_name.replace("_", " ").title()))

            if metadata.get("advanced", False):
                param.setFlags(param.flags() | QgsProcessingParameterDefinition.FlagAdvanced)

            param.setDefaultValue(default_values[field_name])
            param.setGuiDefaultValueOverride(saved_values[field_name])

            self.addParameter(param)

    def add_param_enum(self, name: str, description: str, enum_type: type[EnumWithName], advanced: bool) -> None:  # noqa: FBT001
        param = QgsProcessingParameterEnum(name, description, options=[e.friendly_name for e in enum_type])
        if advanced:
            param.setFlags(param.flags() | QgsProcessingParameterDefinition.FlagAdvanced)

        self.addParameter(param)

    def add_param_float(
        self,
        name: str,
        description: str,
        decimals: int,
        min_value: float | None,
        advanced: bool,  # noqa: FBT001
    ) -> None:
        param = QgsProcessingParameterNumber(name, description, QgsProcessingParameterNumber.Double)
        if min_value is not None:
            param.setMinimum(min_value)
        if decimals is not None:
            param.setMetadata({"widget_wrapper": {"decimals": decimals}})
        if advanced:
            param.setFlags(param.flags() | QgsProcessingParameterDefinition.FlagAdvanced)
        self.addParameter(param)

    def init_output_parameters(self):
        pass

    def init_output_files_parameters(self):
        self.addParameter(
            QgsProcessingParameterFeatureSink(ResultLayer.NODES.results_name, tr("Simulation Results - Nodes"))
        )
        self.addParameter(
            QgsProcessingParameterFeatureSink(ResultLayer.LINKS.results_name, tr("Simulation Results - Links"))
        )

    def _get_crs(self, parameters: dict[str, Any], context: QgsProcessingContext) -> QgsCoordinateReferenceSystem:
        junction_source = self.parameterAsSource(parameters, ModelLayer.JUNCTIONS, context)
        junction_source = cast(QgsProcessingFeatureSource, junction_source)
        return junction_source.sourceCrs()

    def _get_model_options(self, parameters: dict[str, Any], context: QgsProcessingContext) -> ModelOptions:
        """
        Get the model options from the parameters.
        """

        data_types = get_type_hints(ModelOptions)

        options_dict: dict[str, Any] = {}
        value: Any

        for data_field in dataclasses.fields(ModelOptions):
            field_name = data_field.name.upper()
            field_type = data_types[data_field.name]

            try:
                if field_type is float:
                    value = self.parameterAsDouble(parameters, field_name, context)
                elif field_type is int:
                    value = self.parameterAsInt(parameters, field_name, context)
                elif field_type is datetime.timedelta:
                    value = datetime.timedelta(hours=self.parameterAsDouble(parameters, field_name, context))
                elif issubclass(field_type, EnumWithName):
                    value = list(field_type)[self.parameterAsEnum(parameters, field_name, context)]
                elif field_type is Pattern:
                    value = Pattern(self.parameterAsString(parameters, field_name, context))
                elif field_type is str:
                    value = self.parameterAsString(parameters, field_name, context)
                else:
                    msg = f"Unsupported field type for settings parameter: {field_type}"
                    raise TypeError(msg)

                options_dict[data_field.name] = value

            except ValueError as e:
                msg = f"Invalid value for parameter {field_name}: {e}"
                raise QgsProcessingException(msg) from e

        return ModelOptions(**options_dict)

    def _get_model(
        self, parameters: dict[str, Any], context: QgsProcessingContext
    ) -> tuple[ModelOptions, Network, Mapping]:
        sources = {
            lyr: source for lyr in ModelLayer if (source := self.parameterAsSource(parameters, lyr.name, context))
        }

        crs = self._get_crs(parameters, context)

        model_options = self._get_model_options(parameters, context)

        ellipsoid = context.ellipsoid()
        transform_context = context.transformContext()

        with profile(tr("Reading features")):
            try:
                elements, network = read(sources, crs, transform_context, ellipsoid, model_options.flow_units)
            except ReadFeatureError as e:
                raise QgsProcessingException(tr("Error reading features: {exception}").format(exception=e)) from e

        with profile(tr("Verifying model")):
            try:
                verify_model(elements, network)
            except VerificationError as e:
                raise QgsProcessingException(tr("Error verifying model: {exception}").format(exception=e)) from e

        return model_options, network, elements

    # def _describe_model(self, model: HybridWntrModel, feedback: QgsProcessingFeedback) -> None:
    #     if hasattr(feedback, "pushFormattedMessage"):  # QGIS > 3.32
    #         feedback.pushFormattedMessage(*model.describe_network())
    #         feedback.pushFormattedMessage(*model.describe_pipes())
    #     else:
    #         feedback.pushInfo(model.describe_network()[1])
    #         feedback.pushInfo(model.describe_pipes()[1])

    def prepareAlgorithm(  # noqa: N802
        self, parameters: dict[str, Any], context: QgsProcessingContext, feedback: QgsProcessingFeedback | None
    ) -> bool:
        app = QCoreApplication.instance()
        if app and QThread.currentThread() == app.thread():
            project_settings = ProjectSettings()

            layers = {
                str(lyr): input_layer.id()
                for lyr in ModelLayer
                if (input_layer := self.parameterAsVectorLayer(parameters, str(lyr), context))
            }
            project_settings.set(SettingKey.MODEL_LAYERS, layers)

            project_settings.save_options(self._get_model_options(parameters, context))

        return super().prepareAlgorithm(parameters, context, feedback)

    def write_output_result_layers(
        self,
        parameters: dict[str, Any],
        context: QgsProcessingContext,
        options: ModelOptions,
        network: Network,
        attributes: Mapping[ResultLayer, Mapping],
    ) -> dict[str, str]:
        outputs: dict[str, str] = {}

        crs = self._get_crs(parameters, context)

        group_name = tr("Simulation Results ({finish_time})").format(finish_time=time.strftime("%X"))

        style_theme = "extended" if options.simulation_duration else None
        unit_names = SpecificUnitNames.from_options(options)

        for layer_type in ResultLayer:
            fields = get_qgs_fields_from_options(options, layer_type)

            attribute_df = attributes[layer_type]

            (sink, layer_id) = self.parameterAsSink(
                parameters, layer_type.results_name, context, fields, layer_type.wkb_type, crs
            )

            if not sink:
                continue

            geometries = network.node_geometries if layer_type.is_node else network.link_geometries

            write(sink, fields, attribute_df, geometries)

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
combine them with the chosen options, and run a simulation using EPANET. \
The results will be loaded as new layers in QGIS, and a summary of the model \
The output files are a layer of 'nodes' (junctions, tanks, reservoirs) and \
'links' (pipes, valves, pumps).
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
        feedback: QgsProcessingFeedback | None,
    ) -> dict:
        if not feedback:
            feedback = QgsProcessingFeedback()

        with profile(tr("Verifying Dependencies"), 10, feedback):
            self._check_can_execute()

        with logger_to_feedback("gusnet", feedback):
            with profile(tr("Preparing Model"), 30, feedback):
                model_options, network, elements = self._get_model(parameters, context)

            feedback.pushInfo(str(ModelStatistics.from_model(Model(network, model_options, elements))))

            temp_file_dir = Path(QgsProcessingUtils.tempFolder(context)) / f"gusnet_run_{uuid.uuid4().hex}"
            temp_file_dir.mkdir(parents=True, exist_ok=True)
            feedback.pushDebugInfo(tr("Using temporary folder: {folder}").format(folder=temp_file_dir))
            input_file = temp_file_dir / "run_input.inp"
            report_file = temp_file_dir / "run_report.rpt"
            output_file = temp_file_dir / "run_output.bin"
            hydraulics_temp_file = temp_file_dir / "run_hydraulics.tmp"

            with profile(tr("Writing EPANET input file"), 40, feedback):
                write_inp_file(elements, model_options, network, input_file, hydraulics_temp_file)

            with profile(tr("Run EPANET simulation"), 50, feedback):
                try:
                    run_analysis(input_file, report_file, output_file)
                except EpanetWrapperError as e:
                    raise QgsProcessingException(e) from e

            with profile(tr("Process results output file"), 60, feedback):
                try:
                    result_attributes = read_output_file(output_file)
                except BinFileError as e:
                    raise QgsProcessingException(e) from e

            with profile(tr("Creating output layers"), 80, feedback):
                outputs = self.write_output_result_layers(
                    parameters, context, model_options, network, result_attributes
                )

        return outputs


class ProcessingParameterInpFileDestination(QgsProcessingParameterFileDestination):
    def defaultFileExtension(self):  # noqa: N802
        return "inp"


class ExportInpFile(_ModelCreatorAlgorithm):
    def createInstance(self):  # noqa N802
        return ExportInpFile()

    def name(self):
        return "export"

    def displayName(self):  # noqa N802
        return tr("Export Inp File")

    def shortHelpString(self):  # noqa N802
        return tr(
            "This will take all of the model layers (junctions, tanks, reservoirs, pipes, valves, pumps),"
            "combine them with the chosen options, and produce an EPANET '.inp' file which can be run / viewed "
            "in other software."
        )

    def icon(self):
        return QgsApplication.getThemeIcon("mActionFileSave.svg")

    def init_output_parameters(self):
        self.addParameter(
            ProcessingParameterInpFileDestination(self.OUTPUT_INP, tr("Output .inp file"), fileFilter="*.inp")
        )

    @profile(tr("Export Inp File"))
    def processAlgorithm(  # noqa N802
        self,
        parameters: dict[str, Any],
        context: QgsProcessingContext,
        feedback: QgsProcessingFeedback | None,
    ) -> dict:
        with logger_to_feedback("gusnet", feedback):
            with profile(tr("Preparing Model"), 30, feedback):
                model_options, network, elements = self._get_model(parameters, context)
                # self._describe_model(model, feedback)

            with profile(tr("Creating Outputs"), 80, feedback):
                inp_file_path = self.parameterAsFile(parameters, self.OUTPUT_INP, context)

                write_inp_file(elements, model_options, network, inp_file_path)

        return {self.OUTPUT_INP: inp_file_path}


class LayerPostProcessor(QgsProcessingLayerPostProcessorInterface):
    def __init__(self, layer_type: ResultLayer, style_theme: str | None, unit_names: SpecificUnitNames):
        super().__init__()
        self.layer_type = layer_type
        self.style_theme = style_theme
        self.unit_names = unit_names

    def postProcessLayer(self, layer, context, feedback):  # noqa N802 ARG002
        style(layer, self.layer_type, self.style_theme, self.unit_names)


@contextmanager
def logger_to_feedback(logger_name: str, feedback: QgsProcessingFeedback | None) -> Generator[None, None, None]:
    """
    Context manager to redirect logging messages to QgsProcessingFeedback.
    """

    if not feedback:
        feedback = QgsProcessingFeedback()

    class FeedbackHandler(logging.Handler):
        def emit(self, record):
            if record.levelno >= logging.WARNING:
                feedback.pushWarning(record.getMessage())
            elif record.levelno >= logging.INFO:
                feedback.pushInfo(record.getMessage())
            else:
                feedback.pushDebugInfo(record.getMessage())

    logger = logging.getLogger(logger_name)
    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    logging_handler = FeedbackHandler()
    logger.addHandler(logging_handler)

    try:
        yield
    finally:
        logger.propagate = True
        logger.removeHandler(logging_handler)
