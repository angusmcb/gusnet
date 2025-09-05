from __future__ import annotations

import contextlib
import importlib
import math
import sys
import typing
from pathlib import Path

from qgis.core import (
    Qgis,
    QgsApplication,
    QgsCoordinateReferenceSystem,
    QgsLayerTreeLayer,
    QgsLayerTreeNode,
    QgsProcessingAlgorithm,
    QgsProcessingAlgRunnerTask,
    QgsProcessingContext,
    QgsProcessingFeedback,
    QgsProcessingOutputLayerDefinition,
    QgsProject,
    QgsRasterLayer,
    QgsSettings,
    QgsTask,
)
from qgis.gui import QgisInterface, QgsLayerTreeViewIndicator, QgsProjectionSelectionDialog
from qgis.PyQt.QtCore import QCoreApplication, QLocale, QObject, QSettings, QTranslator, pyqtSlot

# from qgis.processing import execAlgorithmDialog for qgis 3.40 onwards
from qgis.PyQt.QtGui import QIcon, QPainter
from qgis.PyQt.QtWidgets import (
    QAction,
    QActionGroup,
    QFileDialog,
    QMenu,
    QPushButton,
    QToolButton,
    QWidget,
)
from qgis.utils import iface

import gusnet
import gusnet.expressions
from gusnet.dependencies import WntrInstaller
from gusnet.elements import DemandType, FlowUnit, HeadlossFormula, ModelLayer, ResultLayer
from gusnet.gusnet_processing.empty_model import TemplateLayers
from gusnet.gusnet_processing.import_inp import ImportInp
from gusnet.gusnet_processing.provider import Provider
from gusnet.gusnet_processing.run_simulation import RunSimulation
from gusnet.i18n import tr
from gusnet.settings import ProjectSettings, SettingKey

MESSAGE_CATEGORY = "Gusnet"

VERSION_SETTING = "gusnet/version"

LOGO_ICON = QIcon("gusnet:logo.svg")

iface = typing.cast(QgisInterface, iface)


class Plugin:
    TESTING = False

    def __init__(self) -> None:
        self.object = QWidget()
        self.task_manager = QgsApplication.taskManager()

        self.init_translation()

        self.menu = tr("Gusnet")

    def init_translation(self):
        lang_code = QSettings().value("locale/userLocale", "en")
        qgis_locale = QLocale(lang_code)
        locale_path = str(Path(__file__).parent / "resources" / "i18n")
        translator = QTranslator(self.object)
        translator.load(qgis_locale, "", "", locale_path)
        QCoreApplication.installTranslator(translator)

    def initProcessing(self):  # noqa N802
        self.provider = Provider()
        QgsApplication.processingRegistry().addProvider(self.provider)

    def initGui(self) -> None:  # noqa N802
        """Create the menu entries and toolbar icons inside the QGIS GUI."""

        self.initProcessing()

        self.setup_actions()

        self.setup_menu()

        self.setup_toolbar()

        self._indicator_registry = IndicatorRegistry()

        self._append_console_statements()

        self.warm_up_wntr()

    def unload(self) -> None:
        """Removes the plugin menu item and icon from QGIS GUI."""

        self.cleanup_menu()
        self.cleanup_toolbar()
        self.cleanup_actions()

        QgsApplication.processingRegistry().removeProvider(self.provider)

        self._indicator_registry.destroy()

        self.object.deleteLater()

    def setup_actions(self) -> None:
        self.run_action = RunAction()
        self.load_template_memory_action = LoadTemplateToMemoryAction()
        self.load_template_geopackage_action = LoadTemplateToGeopackageAction()
        self.load_inp_action = LoadInpAction()
        self.load_example_action = LoadExampleAction()
        self.open_settings_action = OpenSettingsAction()

    def cleanup_actions(self) -> None:
        self.run_action.deleteLater()
        self.load_template_memory_action.deleteLater()
        self.load_template_geopackage_action.deleteLater()
        self.load_inp_action.deleteLater()
        self.load_example_action.deleteLater()
        self.open_settings_action.deleteLater()

    def setup_menu(self) -> None:
        """Setup the plugin menu in the QGIS GUI."""
        iface.addPluginToMenu(self.menu, self.run_action)
        iface.addPluginToMenu(self.menu, self.load_template_memory_action)
        iface.addPluginToMenu(self.menu, self.load_template_geopackage_action)
        iface.addPluginToMenu(self.menu, self.load_inp_action)
        iface.addPluginToMenu(self.menu, self.load_example_action)
        try:
            our_menu_action = next(action for action in iface.pluginMenu().actions() if action.text() == self.menu)
            our_menu_action.setIcon(LOGO_ICON)
        except StopIteration:
            pass

    def cleanup_menu(self) -> None:
        iface.removePluginMenu(self.menu, self.run_action)
        iface.removePluginMenu(self.menu, self.load_template_memory_action)
        iface.removePluginMenu(self.menu, self.load_template_geopackage_action)
        iface.removePluginMenu(self.menu, self.load_inp_action)
        iface.removePluginMenu(self.menu, self.load_example_action)

    def setup_toolbar(self) -> None:
        template_menu = QMenu(self.object)
        template_menu.addAction(self.load_template_memory_action)
        template_menu.addAction(self.load_template_geopackage_action)

        template_button = QToolButton(self.object)
        template_button.setMenu(template_menu)
        template_button.setDefaultAction(self.load_template_memory_action)
        template_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)

        run_menu = QMenu(self.object)
        run_menu.addAction(self.run_action)
        run_menu.addAction(self.open_settings_action)
        run_menu.addMenu(SettingMenu(tr("Headloss Formula"), run_menu, SettingKey.HEADLOSS_FORMULA))
        run_menu.addMenu(SettingMenu(tr("Units"), run_menu, SettingKey.FLOW_UNITS))
        run_menu.addMenu(DurationSettingMenu(tr("Duration (hours)"), run_menu))
        run_menu.addMenu(SettingMenu(tr("Demand Type"), run_menu, SettingKey.DEMAND_TYPE))

        run_button = QToolButton(self.object)
        run_button.setMenu(run_menu)
        run_button.setDefaultAction(self.run_action)
        run_button.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)

        self.template_button = iface.addToolBarWidget(template_button)
        iface.addToolBarIcon(self.load_inp_action)
        self.run_button = iface.addToolBarWidget(run_button)

    def cleanup_toolbar(self) -> None:
        iface.removeToolBarIcon(self.template_button)
        iface.removeToolBarIcon(self.load_inp_action)
        iface.removeToolBarIcon(self.run_button)

    def warm_up_wntr(self) -> None:
        """wntr is slow to load so start warming it up now !"""
        task: QgsTask = QgsTask.fromFunction(
            "Set up wntr",
            import_wntr,
            flags=QgsTask.Hidden | QgsTask.Silent,
        )
        task.taskCompleted.connect(self.show_welcome_message)
        task.taskTerminated.connect(self.install_wntr)

        self.task_manager.addTask(task)

        if self.TESTING:
            assert task.waitForFinished()  # noqa: S101

    def install_wntr(self) -> None:
        task: QgsTask = QgsTask.fromFunction(
            tr("Installing WNTR"),
            lambda _: WntrInstaller.install_wntr(),
            flags=QgsTask.Silent,
        )
        task.taskCompleted.connect(self.show_welcome_message)
        task.taskTerminated.connect(
            lambda: iface.messageBar().pushMessage(
                tr("Failed to install WNTR. Please check your internet connection."), level=Qgis.MessageLevel.Critical
            )
        )

        self.task_manager.addTask(task)

        if self.TESTING:
            assert task.waitForFinished()  # noqa: S101

    def show_welcome_message(self):
        old_version = QgsSettings().value(VERSION_SETTING, None)
        QgsSettings().setValue(VERSION_SETTING, gusnet.__version__)

        if old_version == gusnet.__version__:
            return

        title = tr("Gusnet upgraded successfully") if old_version else tr("Gusnet installed successfully")
        text = tr("Load an example to try me out")

        message_item = iface.messageBar().createMessage(title, text)

        example_button = QPushButton(tr("Load Example"))
        example_button.clicked.connect(self.load_example_action.trigger)
        example_button.clicked.connect(message_item.dismiss)

        message_item.layout().addWidget(example_button)

        iface.messageBar().pushItem(message_item)

    def _append_console_statements(self) -> None:
        """Append the console statements to the QGIS console."""

        with contextlib.suppress(ModuleNotFoundError, AttributeError):
            import console

            console.console_sci._init_statements.extend(["import gusnet", "import wntr"])  # noqa: SLF001


class ProcessingRunnerAction(QAction):
    success_message: str = ""

    def __init__(self, algorithm: QgsProcessingAlgorithm) -> None:
        super().__init__()

        self.algorithm = algorithm
        self.setText(algorithm.displayName())
        self.setIcon(IconWithLogo(algorithm.icon()))
        self.triggered.connect(self.run)

    def run(self) -> None:
        self.feedback = ProcessingFeedbackWithLogging()

        self.context = QgsProcessingContext()
        self.context.setProject(QgsProject.instance())
        self.context.setFeedback(self.feedback)

        self.algorithm = self.algorithm.create()

        try:
            parameters = self.get_parameters()
        except CantGetParametersException:
            return

        ok, msg = self.algorithm.checkParameterValues(parameters, self.context)

        if not ok:
            self.display_error(msg)
            return

        if not self.isEnabled():
            return
        self.setEnabled(False)

        self.task = QgsProcessingAlgRunnerTask(self.algorithm, parameters, self.context, self.feedback)
        self.task.executed.connect(self.on_executed)

        QgsApplication.taskManager().addTask(self.task)

    def get_parameters(self) -> dict:
        """Return the parameters for the algorithm."""
        return {}

    def on_executed(self, successful, results):
        if successful:
            self.on_executed_successfully(results)
        else:
            self.on_executed_with_error()

        self.setEnabled(True)

    def on_executed_successfully(self, results):
        import processing

        processing.handleAlgorithmResults(self.algorithm, self.context, self.feedback, results)

        self.show_success_message()

    def on_executed_with_error(self):
        self.display_error(self.feedback.errors[0], self.feedback.textLog())

        QgsApplication.messageLog().logMessage(
            self.feedback.errors[0] + "\n" + self.feedback.textLog(),
            MESSAGE_CATEGORY,
            Qgis.MessageLevel.Critical,
        )

    def display_error(self, error_text: str, show_more: str | None = None) -> None:
        params = {"title": tr("Error"), "text": error_text, "level": Qgis.MessageLevel.Critical, "duration": 0}
        if show_more:
            params["showMore"] = show_more
        iface.messageBar().pushMessage(**params)

    def show_success_message(self):
        """Show the success message in the message bar."""
        if self.success_message:
            level = Qgis.MessageLevel.Warning if self.feedback.warnings else Qgis.MessageLevel.Success
            title = tr("Analysed with Warnings") if self.feedback.warnings else tr("Success")
            iface.messageBar().pushMessage(
                title=title,
                text=self.success_message,
                showMore=self.feedback.textLog(),
                level=level,
                duration=0,
            )


class CantGetParametersException(BaseException):
    pass


class TemporaryOutputLayerDefinition(QgsProcessingOutputLayerDefinition):
    def __init__(self):
        super().__init__("TEMPORARY_OUTPUT", QgsProject.instance())


class GeopackageOutputLayerDefinition(QgsProcessingOutputLayerDefinition):
    def __init__(self, path: str, name: str):
        super().__init__(f"ogr:dbname='{path}' table='{name}' (geom)", QgsProject.instance())


class RunAction(ProcessingRunnerAction):
    def __init__(self):
        super().__init__(RunSimulation())
        self.setToolTip(tr("Run the simulation with the current settings."))

    def get_parameters(self) -> dict:
        project_settings = ProjectSettings()

        saved_layers = project_settings.get(SettingKey.MODEL_LAYERS, {})
        input_layers = {
            layer_type.name: saved_layers.get(layer_type.name)
            for layer_type in ModelLayer
            if QgsProject.instance().mapLayer(saved_layers.get(layer_type.name))
        }

        if not len(input_layers):
            self.display_error("Set the layers that will be part of the model before running it.")
            raise CantGetParametersException

        result_layers = {layer.results_name: TemporaryOutputLayerDefinition() for layer in ResultLayer}

        flow_units = project_settings.get(SettingKey.FLOW_UNITS, FlowUnit.LPS)
        flow_unit_id = list(FlowUnit).index(flow_units)

        headloss_formula = project_settings.get(SettingKey.HEADLOSS_FORMULA, HeadlossFormula.HAZEN_WILLIAMS)
        headloss_formula_id = list(HeadlossFormula).index(headloss_formula)

        demand_type = project_settings.get(SettingKey.DEMAND_TYPE, DemandType.FIXED)
        demand_type_id = list(DemandType).index(demand_type)

        duration = project_settings.get(SettingKey.SIMULATION_DURATION, 0)

        self.set_success_message(flow_units, headloss_formula)

        return {
            RunSimulation.UNITS: flow_unit_id,
            RunSimulation.HEADLOSS_FORMULA: headloss_formula_id,
            RunSimulation.DURATION: duration,
            RunSimulation.DEMAND_TYPE: demand_type_id,
            **result_layers,
            **input_layers,
        }

    def set_success_message(self, units: FlowUnit, headloss_formula: HeadlossFormula) -> None:
        """Set the success message for this action."""
        self.success_message = tr("Analysed using units '{units}' and headloss formula '{headloss_formula}'").format(
            units=units.friendly_name,
            headloss_formula=headloss_formula.friendly_name,
        )


class LoadTemplateToMemoryAction(ProcessingRunnerAction):
    def __init__(self):
        super().__init__(TemplateLayers())
        self.setText(tr("Create Template Memory Layers"))

    def get_parameters(self) -> dict:
        layer_dict = {layer.value: TemporaryOutputLayerDefinition() for layer in ModelLayer}
        return {TemplateLayers.CRS: QgsProject.instance().crs(), **layer_dict}


class LoadTemplateToGeopackageAction(ProcessingRunnerAction):
    def __init__(self):
        super().__init__(TemplateLayers())
        self.setText(tr("Create Template Geopackage"))
        self.setIcon(IconWithLogo(QgsApplication.getThemeIcon("mGeoPackage.svg")))

    def get_parameters(self) -> dict:
        geopackage_path, _ = QFileDialog.getSaveFileName(
            iface.mainWindow(),
            tr("Save Geopackage"),
            QSettings().value("UI/lastProjectDir"),
            tr("Geopackage") + " (*.gpkg)",
        )
        if not geopackage_path:
            raise CantGetParametersException

        layer_dict = {
            layer.value: GeopackageOutputLayerDefinition(geopackage_path, layer.value.lower()) for layer in ModelLayer
        }
        return {TemplateLayers.CRS: None, **layer_dict}


class LoadInpAction(ProcessingRunnerAction):
    def __init__(self):
        super().__init__(ImportInp())
        self.success_message = tr("Loaded .inp file")

    def get_parameters(self) -> dict:
        filepath = self.get_filepath()

        crs = self.get_crs()

        layer_dict = {layer.value: TemporaryOutputLayerDefinition() for layer in ModelLayer}

        return {ImportInp.INPUT: filepath, ImportInp.CRS: crs, **layer_dict}

    def get_filepath(self) -> str:
        """Get the file path from the user."""
        filepath, _ = QFileDialog.getOpenFileName(
            None, tr("Choose Input File"), QSettings().value("UI/lastProjectDir"), tr("EPANET INP File") + " (*.inp)"
        )
        if not filepath:
            raise CantGetParametersException
        return str(filepath)

    def get_crs(self) -> QgsCoordinateReferenceSystem:
        """Get the CRS from the user."""
        crs_selector = QgsProjectionSelectionDialog(iface.mainWindow())
        crs_selector.setCrs(QgsProject.instance().crs())
        crs_selector.showNoCrsForLayerMessage()
        if not crs_selector.exec():
            raise CantGetParametersException
        return crs_selector.crs()


class LoadExampleAction(LoadInpAction):
    def __init__(self):
        super().__init__()
        self.setText(tr("Load Example"))
        self.setIcon(QIcon())
        self.setToolTip(tr("Load an example network"))
        self.success_message = tr("Example loaded with Open Street Map background")

    def get_crs(self) -> QgsCoordinateReferenceSystem:
        return QgsCoordinateReferenceSystem("EPSG:3089")

    def get_filepath(self) -> str:
        return gusnet.examples["KY10"]

    def set_transform_context(self) -> None:
        transform_context = QgsProject.instance().transformContext()
        transform_string = (
            "+proj=pipeline +step +inv +proj=webmerc +lat_0=0 +lon_0=0 +x_0=0 +y_0=0 +ellps=WGS84 +step +inv"
            " +proj=hgridshift +grids=us_noaa_kyhpgn.tif +step"
            " +proj=lcc +lat_0=36.3333333333333 +lon_0=-85.75 +lat_1=37.0833333333333 +lat_2=38.6666666666667"
            " +x_0=1500000 +y_0=999999.9998984 +ellps=GRS80 +step"
            " +proj=unitconvert +xy_in=m +xy_out=us-ft"
        )
        transform_context.addCoordinateOperation(
            QgsCoordinateReferenceSystem("EPSG:3857"), self.get_crs(), transform_string, False
        )
        QgsProject.instance().setTransformContext(transform_context)

    def load_osm(self) -> None:
        root = QgsProject.instance().layerTreeRoot()
        tms = "type=xyz&url=https://tile.openstreetmap.org/{z}/{x}/{y}.png&zmax=19&zmin=0"
        title = tr("OpenStreetMap")
        layer = QgsRasterLayer(tms, title, "wms")
        layer.setOpacity(0.5)
        QgsProject.instance().addMapLayer(layer, False)
        root.insertChildNode(len(root.children()), QgsLayerTreeLayer(layer))

    def on_executed_successfully(self, results) -> None:
        self.set_transform_context()
        self.load_osm()
        super().on_executed_successfully(results)


class ProcessingFeedbackWithLogging(QgsProcessingFeedback):
    def __init__(self, logFeedback: bool = True):  # noqa
        self.errors: list[str] = []
        self.warnings: list[str] = []
        super().__init__(logFeedback)

    def reportError(self, error: str | None, fatalError: bool = False):  # noqa N802
        if error:
            self.errors.append(error)

        super().reportError(error, fatalError)

    def pushWarning(self, warning: str | None):  # noqa N802
        if warning:
            self.warnings.append(warning)

        super().pushWarning(warning)


class OpenSettingsAction(QAction):
    def __init__(self):
        super().__init__(tr("Change layers..."))
        self.setToolTip(tr("Open the settings dialog to change the model layers."))

        self.triggered.connect(self.open_settings)

    def open_settings(self):
        import processing

        processing.execAlgorithmDialog("wntr:run")  # type: ignore


def import_wntr(_: QgsTask):
    """Pre-import wntr to speed up loading"""

    if "wntr" in sys.modules:
        import wntr

        importlib.reload(wntr)

    import wntr  # type: ignore

    if not Path(wntr.__file__).exists():
        msg = "File missing - probably due to plugin upgrade"
        raise ImportError(msg)


class IconWithLogo(QIcon):
    _logo_pixmap = LOGO_ICON.pixmap(128, 128)

    def __init__(self, icon: QIcon):
        result_pixmap = icon.pixmap(256, 256)
        painter = QPainter(result_pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        painter.drawPixmap(128, 128, 128, 128, self._logo_pixmap)
        painter.end()

        super().__init__(result_pixmap)


class IndicatorRegistry(QObject):
    """Registry for layer tree indicators"""

    def __init__(self) -> None:
        super().__init__()

        self._layer_ids: dict[ModelLayer, str] = {}
        self._indicators = {layer: ModelLayerIndicator(self, layer) for layer in ModelLayer}

        root = QgsProject.instance().layerTreeRoot()
        root.addedChildren.connect(self.layer_tree_layer_added)
        root.willRemoveChildren.connect(self.layer_tree_layer_will_be_removed)

        QgsProject.instance().customVariablesChanged.connect(self.update_layer_ids)

        self.update_layer_ids()

    def destroy(self) -> None:
        """Self destruct mechanism"""
        for layer_type in ModelLayer:
            old_id = self._layer_ids.get(layer_type)
            if not old_id:
                continue

            layer_tree_layer = QgsProject.instance().layerTreeRoot().findLayer(old_id)

            if layer_tree_layer:
                indicator = self._indicators[layer_type]
                iface.layerTreeView().removeIndicator(layer_tree_layer, indicator)

        self.deleteLater()

    @pyqtSlot(QgsLayerTreeNode, int, int)
    def layer_tree_layer_added(
        self,
        layer_tree: QgsLayerTreeNode,
        indexFrom: int,  # noqa: N803
        indexTo: int,  # noqa: N803
    ) -> None:
        """Receive layer tree layers added and attach indicator to them if indicator exists."""

        layer_tree_nodes = layer_tree.children()[indexFrom : indexTo + 1]

        for layer_tree_node in layer_tree_nodes:
            try:
                layer_id = layer_tree_node.layerId()
            except AttributeError:  # Not a layer node
                continue

            if layer_id not in self._layer_ids.values():
                continue

            model_layer = next(key for key, value in self._layer_ids.items() if value == layer_id)

            indicator = self._indicators[model_layer]

            iface.layerTreeView().addIndicator(layer_tree_node, indicator)

    @pyqtSlot(QgsLayerTreeNode, int, int)
    def layer_tree_layer_will_be_removed(
        self,
        layer_tree: QgsLayerTreeNode,
        indexFrom: int,  # noqa: N803
        indexTo: int,  # noqa: N803
    ) -> None:
        """Receive layer tree layers added and attach indicator to them if indicator exists."""

        layer_tree_view = iface.layerTreeView()
        layer_tree_nodes = layer_tree.children()[indexFrom : indexTo + 1]

        for layer_tree_node in layer_tree_nodes:
            for indicator in layer_tree_view.indicators(layer_tree_node):
                if isinstance(indicator, ModelLayerIndicator):
                    layer_tree_view.removeIndicator(layer_tree_node, indicator)

    @pyqtSlot()
    def update_layer_ids(self) -> None:
        """Update the layer ids in the registry based on project settings."""
        new_layer_ids: dict[ModelLayer, str] = {}
        for layer, layer_id in ProjectSettings().get(SettingKey.MODEL_LAYERS, {}).items():
            try:
                new_layer_ids[ModelLayer[layer]] = layer_id
            except KeyError:
                continue

        if new_layer_ids == self._layer_ids:
            return

        for layer_type in ModelLayer:
            old_id = self._layer_ids.get(layer_type)
            new_id = new_layer_ids.get(layer_type)

            if old_id == new_id:
                continue

            indicator = self._indicators[layer_type]
            root = QgsProject.instance().layerTreeRoot()

            if old_id:
                layer_tree_layer = root.findLayer(old_id)
                if layer_tree_layer:
                    iface.layerTreeView().removeIndicator(layer_tree_layer, indicator)

            if new_id:
                layer_tree_layer = root.findLayer(new_id)
                if layer_tree_layer:
                    iface.layerTreeView().addIndicator(layer_tree_layer, indicator)

        self._layer_ids = new_layer_ids


class ModelLayerIndicator(QgsLayerTreeViewIndicator):
    def __init__(self, parent: QObject, layer_type: ModelLayer):
        super().__init__(parent)

        self.setIcon(LOGO_ICON)
        self.setToolTip(layer_type.friendly_name)


class SettingMenu(QMenu):
    def __init__(self, title: str | None = None, parent: QWidget | None = None, setting: SettingKey | None = None):
        super().__init__(title, parent)

        self.action_group = QActionGroup(self)
        self.action_group.triggered.connect(lambda action: ProjectSettings().set(setting, action.data()))  # type: ignore
        self.actions = {}  # type: ignore
        self.setting_key = setting

        self.setup_actions()

        self.aboutToShow.connect(self.update_checked)

    def setup_actions(self):
        for option in self.setting_key.expected_type:
            self.setup_action(option, option.friendly_name)

    def setup_action(self, option, option_name: str):
        action = QAction(option_name, self.action_group, checkable=True)
        action.setData(option)
        self.actions[option] = action
        self.addAction(action)

    def update_checked(self):
        current_setting = ProjectSettings().get(self.setting_key, next(iter(self.setting_key.expected_type)))
        self.actions[current_setting].setChecked(True)


class DurationSettingMenu(SettingMenu):
    def __init__(self, title=None, parent=None):
        super().__init__(title, parent, SettingKey.SIMULATION_DURATION)

    def setup_actions(self):
        self.setup_action(0, tr("Single period simulation"))

        for hour in range(1, 25):
            self.setup_action(hour, tr("%n hour(s)", "", hour))

    def update_checked(self):
        current_duration = math.floor(ProjectSettings().get(SettingKey.SIMULATION_DURATION, 0))

        if current_duration not in self.actions:
            self.setup_action(current_duration, tr("%n hour(s)", "", current_duration))

        self.actions[current_duration].setChecked(True)
