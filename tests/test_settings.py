import pytest
from qgis.core import QgsExpressionContextUtils, QgsProject

from gusnet.elements import FlowUnit, HeadlossFormula
from gusnet.settings import ProjectSettings, SettingKey


def write(var, value=None):
    QgsExpressionContextUtils.setProjectVariable(QgsProject.instance(), "gusnet_" + var, value)


def read(var):
    return QgsExpressionContextUtils.projectScope(QgsProject.instance()).variable("gusnet_" + var)


def test_read():
    QgsProject.instance().clear()
    ProjectSettings().set(SettingKey.FLOW_UNITS, FlowUnit.LPS)
    written_value = read("flow_unit")
    assert written_value == "LPS"


def test_write():
    QgsProject.instance().clear()
    write("model_layers", '{"key": "value"}')
    read_value = ProjectSettings().get(SettingKey.MODEL_LAYERS)

    assert read_value == {"key": "value"}


def test_get_default_value():
    QgsProject.instance().clear()
    project_settings = ProjectSettings()
    default_value = "default"
    result = project_settings.get(SettingKey.FLOW_UNITS, default=default_value)
    assert result == default_value


def test_set_value():
    project_settings = ProjectSettings(project=QgsProject.instance())
    project_settings.set(SettingKey.FLOW_UNITS, FlowUnit.LPS)
    result = read("flow_unit")
    assert result == "LPS"


def test_set_and_get_value():
    project_settings = ProjectSettings(project=QgsProject.instance())
    project_settings.set(SettingKey.FLOW_UNITS, FlowUnit.CFS)
    result = project_settings.get(SettingKey.FLOW_UNITS)
    assert result == FlowUnit.CFS


def test_set_invalid_type():
    project_settings = ProjectSettings(project=QgsProject.instance())
    with pytest.raises(TypeError):
        project_settings.set(SettingKey.FLOW_UNITS, 123)


def test_get_invalid_enum_value():
    QgsProject.instance().clear()
    project_settings = ProjectSettings()
    result = project_settings.get(SettingKey.FLOW_UNITS, default="default")
    assert result == "default"


def test_set_and_get_dict():
    project_settings = ProjectSettings(project=QgsProject.instance())
    test_dict = {"key": "value"}
    project_settings.set(SettingKey.MODEL_LAYERS, test_dict)
    result = project_settings.get(SettingKey.MODEL_LAYERS)
    assert result == test_dict


def test_set_and_get_headloss_formula():
    project_settings = ProjectSettings(project=QgsProject.instance())
    headloss_formula = HeadlossFormula.HAZEN_WILLIAMS
    project_settings.set(SettingKey.HEADLOSS_FORMULA, headloss_formula)
    result = project_settings.get(SettingKey.HEADLOSS_FORMULA)
    assert result == headloss_formula


def test_set_and_get_duration():
    project_settings = ProjectSettings(project=QgsProject.instance())
    duration = 3600  # Duration in seconds
    project_settings.set(SettingKey.SIMULATION_DURATION, duration)
    result = project_settings.get(SettingKey.SIMULATION_DURATION)
    assert result == duration


def test_malformed_value_for_headloss_formula():
    project_settings = ProjectSettings(project=QgsProject.instance())
    write("headloss_formula", "malformed_value")
    default_value = HeadlossFormula.HAZEN_WILLIAMS
    result = project_settings.get(SettingKey.HEADLOSS_FORMULA, default=default_value)
    assert result == default_value


def test_malformed_value_for_duration():
    project_settings = ProjectSettings(project=QgsProject.instance())
    write("simulation_duration", "not_a_number")
    default_value = 3600  # Default duration in seconds
    result = project_settings.get(SettingKey.SIMULATION_DURATION, default=default_value)
    assert result == default_value


@pytest.mark.parametrize("value", [None, "[", "[1,2]", "assert False", "string", "1 + 2", 123])
def test_malformed_value_for_model_layers(value):
    project_settings = ProjectSettings()
    write("model_layers", value)
    default_value = "DEFAULT"
    result = project_settings.get(SettingKey.MODEL_LAYERS, default=default_value)
    assert result == default_value


@pytest.fixture
def tmp_qgs(tmp_path, qgis_new_project):
    qgs_path = str(tmp_path / "test_project.qgs")
    QgsProject.instance().setFileName(qgs_path)
    return qgs_path


@pytest.mark.parametrize(
    ("setting", "value"),
    [
        (SettingKey.FLOW_UNITS, FlowUnit.LPS),
        (SettingKey.FLOW_UNITS, FlowUnit.GPM),
        (SettingKey.HEADLOSS_FORMULA, HeadlossFormula.HAZEN_WILLIAMS),
        (SettingKey.SIMULATION_DURATION, 3600),
        (SettingKey.MODEL_LAYERS, {"key": "value"}),
    ],
)
def test_project_settings_save_reload(tmp_qgs, setting, value):
    ProjectSettings().set(setting, value)
    QgsProject.instance().write()
    QgsProject.instance().read(tmp_qgs)

    result = ProjectSettings().get(setting)
    assert result == value
