from __future__ import annotations

import functools
import logging
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any, ClassVar

from qgis.core import (
    QgsApplication,
    QgsProcessingAlgorithm,
    QgsProcessingContext,
    QgsProcessingException,
    QgsProcessingFeedback,
    QgsProcessingLayerPostProcessorInterface,
    QgsVectorLayer,
)
from qgis.PyQt.QtCore import QCoreApplication, QThread

from gusnet.elements import ModelLayer, ModelOptions, ResultLayer
from gusnet.i18n import tr
from gusnet.settings import ProjectSettings, SettingKey
from gusnet.style import style
from gusnet.units import SpecificUnitNames

if TYPE_CHECKING:  # pragma: no cover
    import wntr
LOGGER = logging.getLogger("gusnet")

SHOW_TIMING = False


class CommonProcessingBase(QgsProcessingAlgorithm):
    post_processors: ClassVar[dict[str, QgsProcessingLayerPostProcessorInterface]] = {}
    _options_to_save: ModelOptions | None = None
    _settings: dict[SettingKey, Any] | None = None

    def helpUrl(self) -> str:  # noqa: N802
        return "https://www.gusnet.org"

    def postProcessAlgorithm(self, context, feedback):  # noqa: N802
        if QThread.currentThread() == QCoreApplication.instance().thread():
            project_settings = ProjectSettings()

            if self._options_to_save:
                project_settings.save_options(self._options_to_save)

            if self._settings:
                for setting_key, setting_value in self._settings.items():
                    project_settings.set(setting_key, setting_value)

        return super().postProcessAlgorithm(context, feedback)

    def canExecute(self):  # noqa: N802
        try:
            import wntr  # noqa: F401
        except ImportError:
            msg = tr("WNTR cannot be loaded. Please wait a minute then try again, or consult our help site.")
            return False, msg

        return True, ""

    def _check_wntr(self) -> None:
        can_execute, message = self.canExecute()
        if not can_execute:
            raise QgsProcessingException(message)

    def _describe_model(self, wn: wntr.network.model.WaterNetworkModel, feedback: QgsProcessingFeedback) -> None:
        feedback.pushInfo(tr("WNTR model created. Model contains:"))
        feedback.pushInfo(str(wn.describe(level=0)))

    def _setup_postprocessing(self, context: QgsProcessingContext, outputs: dict, group_name: str, *args, **kwargs):
        output_order = [
            ModelLayer.JUNCTIONS,
            ModelLayer.PIPES,
            ModelLayer.PUMPS,
            ModelLayer.VALVES,
            ModelLayer.RESERVOIRS,
            ModelLayer.TANKS,
        ]

        for layer_type, lyr_id in outputs.items():
            if not context.willLoadLayerOnCompletion(lyr_id):
                continue

            self.post_processors[lyr_id] = ModelLayerPostProcessor(layer_type, *args, **kwargs)

            layer_details = context.layerToLoadOnCompletionDetails(lyr_id)
            layer_details.setPostProcessor(self.post_processors[lyr_id])
            layer_details.groupName = group_name
            layer_details.layerSortKey = output_order.index(layer_type)


class ModelLayerPostProcessor(QgsProcessingLayerPostProcessorInterface):
    def __init__(
        self,
        layer_type: ModelLayer | ResultLayer,
        make_editable: bool = False,  # noqa: FBT001, FBT002
        unit_names: SpecificUnitNames | None = None,
    ):
        super().__init__()
        self.layer_type = layer_type
        self.make_editable = make_editable
        self.unit_names = unit_names

    def postProcessLayer(self, layer: QgsVectorLayer, context, feedback) -> None:  # noqa N802 ARG002
        style(layer, self.layer_type, None, self.unit_names)

        project_settings = ProjectSettings()
        wntr_layers = project_settings.get(SettingKey.MODEL_LAYERS, {})
        wntr_layers[self.layer_type.name] = layer.id()
        project_settings.set(SettingKey.MODEL_LAYERS, wntr_layers)

        if self.make_editable:
            layer.startEditing()


PROFILER_GROUP_NAME = "Gusnet"


@contextmanager
def profile(name: str, percentage: int | None = None, feedback: QgsProcessingFeedback | None = None):
    """
    Context manager to profile a block of code in processing.
    """

    if feedback and feedback.isCanceled():
        raise QgsProcessingException(tr("Execution of script cancelled by user"))

    if feedback:
        feedback.setProgressText(name)
        # this is to ensure that feedback goes to min 5% straight away rather than waiting at 100
        feedback.setProgress(feedback.progress() + 5)

    qgs_profiler = QgsApplication.profiler()
    qgs_profiler.start(name, PROFILER_GROUP_NAME)

    try:
        yield functools.partial(profile, feedback=feedback)

        if feedback and percentage:
            feedback.setProgress(percentage)
    finally:
        qgs_profiler.end(PROFILER_GROUP_NAME)
