import pytest
from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsProject,
    QgsVectorLayer,
)
from qgis.PyQt import QtWidgets

import gusnet
from gusnet.elements import FlowUnit, HeadlossFormula
from gusnet.plugin import (
    DurationSettingMenu,
    LoadExampleAction,
    LoadInpAction,
    LoadTemplateToGeopackageAction,
    LoadTemplateToMemoryAction,
    Plugin,
    RunAction,
    SettingMenu,
)
from gusnet.settings import ProjectSettings, SettingKey


@pytest.fixture
def loaded_plugin():
    plugin = Plugin()
    plugin.TESTING = True
    plugin.initGui()
    yield plugin
    plugin.unload()


def test_class_factory(qgis_iface):
    plugin_class = gusnet.classFactory(qgis_iface)
    assert isinstance(plugin_class, Plugin)


def test_plugin_load_unload():
    plugin = Plugin()
    plugin.TESTING = True
    plugin.initGui()
    plugin.unload()


def test_processing_provider_registered(qgis_app, loaded_plugin):
    assert qgis_app.processingRegistry().providerById("gusnet")


def test_create_template_layers(qgis_new_project):
    action = LoadTemplateToMemoryAction()
    action.trigger()
    action.task.waitForFinished()
    assert len(QgsProject.instance().mapLayers()) == 6


def list_layers_in_geopackage(geopackage_path):
    layers = QgsVectorLayer(geopackage_path, "geopackage_layers", "ogr")

    assert layers.isValid()

    layer_names = []
    for layer in layers.dataProvider().subLayers():
        layer_name = layer.split("!!::!!")[1]
        layer_names.append(layer_name)

    return layer_names


def test_create_template_geopackage(mocker, tmp_path):
    geopackage_path = str(tmp_path / "template.gpkg")
    mocker.patch("gusnet.plugin.QFileDialog.getSaveFileName", return_value=(geopackage_path, ""))

    action = LoadTemplateToGeopackageAction()
    action.trigger()
    action.task.waitForFinished()

    assert (tmp_path / "template.gpkg").exists()

    layers = ["junctions", "pipes", "pumps", "reservoirs", "tanks", "valves"]
    layers_in_geopackage = list_layers_in_geopackage(str(tmp_path / "template.gpkg"))
    for layer in layers:
        assert layer in layers_in_geopackage


def patch_dialogs(mocker, file, crs):
    mocker.patch("gusnet.plugin.QFileDialog", autospec=True).getOpenFileName.return_value = (file, "")

    qpsd = mocker.patch("gusnet.plugin.QgsProjectionSelectionDialog", autospec=True)
    qpsd.return_value.exec.return_value = bool(crs)
    qpsd.return_value.crs.return_value = QgsCoordinateReferenceSystem(crs)


@pytest.mark.skipif(
    not hasattr(QtWidgets.QMessageBox, "Close"), reason="QMessageBox.Close in pytest-qgis will error in qt6"
)
@pytest.mark.qgis_show_map(timeout=3, zoom_to_common_extent=True)
def test_load_inp_file_visual_check(qgis_iface, mocker, qgis_new_project, clean_message_bar):
    patch_dialogs(mocker, gusnet.examples["KY10"], "EPSG:32629")

    action = LoadInpAction()
    action.trigger()
    action.task.waitForFinished()

    assert len(QgsProject.instance().mapLayers()) == 6


def test_load_inp_file(qgis_iface, mocker, qgis_new_project, clean_message_bar):
    patch_dialogs(mocker, gusnet.examples["KY10"], "EPSG:32629")

    action = LoadInpAction()
    action.trigger()
    action.task.waitForFinished()

    assert len(QgsProject.instance().mapLayers()) == 6

    assert qgis_iface.messageBar().currentItem().text() == "Loaded .inp file"


def test_load_inp_file_bad_inp(qgis_iface, mocker, bad_inp, qgis_new_project, clean_message_bar):
    patch_dialogs(mocker, bad_inp, "EPSG:4326")

    action = LoadInpAction()
    action.trigger()
    action.task.waitForFinished()

    assert (
        qgis_iface.messageBar().currentItem().text()
        == "error reading .inp file: (Error 201) syntax error (%s), at line 330:\n   [FOO]"
    )

    assert len(QgsProject.instance().mapLayers()) == 0


def test_load_inp_file_no_file_selected(mocker, qgis_new_project):
    patch_dialogs(mocker, "", "EPSG:4326")

    action = LoadInpAction()
    action.trigger()

    assert len(QgsProject.instance().mapLayers()) == 0


def test_load_inp_file_no_crs_selected(mocker, qgis_new_project):
    patch_dialogs(mocker, gusnet.examples["KY10"], "")

    action = LoadInpAction()
    action.trigger()

    assert len(QgsProject.instance().mapLayers()) == 0


def test_load_example(qgis_new_project):
    action = LoadExampleAction()
    action.trigger()
    action.task.waitForFinished()

    assert len(QgsProject.instance().mapLayers()) == 7


def test_run(qgis_new_project):
    action = LoadExampleAction()
    action.trigger()
    action.task.waitForFinished()

    action = RunAction()
    action.trigger()
    action.task.waitForFinished()

    assert len(QgsProject.instance().mapLayers()) == 9


@pytest.mark.parametrize("formula", list(HeadlossFormula))
def test_setting_menu_headloss_formula_updates_setting(formula):
    """Test that selecting a headloss formula in SettingMenu updates the project setting."""
    menu = SettingMenu(
        title="Headloss Formula",
        parent=None,
        setting=SettingKey.HEADLOSS_FORMULA,
    )

    action = menu.actions[formula]
    action.trigger()
    assert ProjectSettings().get(SettingKey.HEADLOSS_FORMULA) == formula


@pytest.mark.parametrize("unit", list(FlowUnit))
def test_setting_menu_flow_units_updates_setting(unit):
    """Test that selecting a flow unit in SettingMenu updates the project setting."""
    menu = SettingMenu(
        title="Units",
        parent=None,
        setting=SettingKey.FLOW_UNITS,
    )
    action = menu.actions[unit]
    action.trigger()
    assert ProjectSettings().get(SettingKey.FLOW_UNITS) == unit


def test_setting_menu_checkmarks_reflect_setting(qgis_iface):
    """Test that the checked action matches the current setting."""
    menu = SettingMenu(
        title="Headloss Formula",
        parent=None,
        setting=SettingKey.HEADLOSS_FORMULA,
    )
    # Set to each value and check update_checked
    for formula in HeadlossFormula:
        ProjectSettings().set(SettingKey.HEADLOSS_FORMULA, formula)
        menu.update_checked()
        for f, action in menu.actions.items():
            if f == formula:
                assert action.isChecked()
            else:
                assert not action.isChecked()


def test_duration_setting_menu_triggers_and_checkmarks(qgis_iface):
    """Test DurationSettingMenu triggers and checkmarks."""
    menu = DurationSettingMenu(title="Duration")
    # Test single period
    menu.actions[0].trigger()
    assert ProjectSettings().get(SettingKey.SIMULATION_DURATION) == 0
    # Test several hours
    for hour in [1, 5, 10, 24]:
        menu.actions[hour].trigger()
        assert ProjectSettings().get(SettingKey.SIMULATION_DURATION) == hour
        menu.update_checked()
        for h, action in menu.actions.items():
            if h == hour:
                assert action.isChecked()
            else:
                assert not action.isChecked()
    # Test dynamic addition for a duration not in actions
    ProjectSettings().set(SettingKey.SIMULATION_DURATION, 42)
    menu.update_checked()
    assert menu.actions[42].isChecked()
