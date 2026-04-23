import pytest
from qgis.core import QgsCoordinateReferenceSystem, QgsExpressionContextUtils, QgsGeometry, QgsProject, QgsVectorLayer

from gusnet.plugin import DurationSettingMenu, LoadTemplateToMemoryAction, Plugin, RunAction


@pytest.fixture
def loaded_plugin():
    plugin = Plugin()
    plugin.TESTING = True
    plugin.initGui()
    yield plugin
    plugin.unload()


def point(x: float, y: float) -> QgsGeometry:
    return QgsGeometry.fromWkt(f"POINT({x} {y})")


def line(*points: tuple[float, float]) -> QgsGeometry:
    points_str = ", ".join(f"{x} {y}" for x, y in points)
    return QgsGeometry.fromWkt(f"LINESTRING({points_str})")


def layer_to_dict(layer: QgsVectorLayer) -> list[dict]:
    fnames = [field.name() for field in layer.fields()]
    return [dict(zip(fnames, f.attributes())) for f in layer.getFeatures()]


def layer_to_dict_by_name(layer: QgsVectorLayer) -> dict[str, dict]:
    fnames = [field.name() for field in layer.fields()]
    return {f["name"]: dict(zip(fnames, f.attributes())) for f in layer.getFeatures()}


@pytest.mark.qgis_show_map(timeout=3, zoom_to_common_extent=True)
def test_end_to_end(loaded_plugin, qgis_bot, qgis_new_project, qgis_processing, french_locale) -> None:
    project = QgsProject.instance()
    assert isinstance(project, QgsProject)
    project.setCrs(QgsCoordinateReferenceSystem("EPSG:2056"))

    action = LoadTemplateToMemoryAction()
    action.trigger()
    action.task.waitForFinished()

    j = project.mapLayersByName("Nœuds de jonction")[0]
    r = project.mapLayersByName("Réservoirs")[0]
    t = project.mapLayersByName("Cuves")[0]
    p = project.mapLayersByName("Canalisations")[0]
    v = project.mapLayersByName("Vannes")[0]
    pumps = project.mapLayersByName("Pompes")[0]

    add = qgis_bot.create_feature_with_attribute_dialog

    ## Group 1
    add(r, point(0, 0), {"name": "Reservoir1", "base_head": 10, "head_pattern": "1 2 3 4 5 6"})
    add(j, point(0, 1), {"name": "Junction1", "elevation": 5, "base_demand": 2, "demand_pattern": "1 2 3 2 1 0"})
    add(p, line((0, 0), (0, 1)), {"name": "Pipe1", "length": 567, "diameter": 222, "roughness": 123})

    ## Group 2
    add(r, point(1, 0), {"name": "Reservoir2"})
    add(j, point(2, 1), {"name": "Junction2", "base_demand": 100})
    add(p, line((1, 0), (2, 0), (2, 1)), {"name": "PipeWithBend"})

    # Group 3
    add(t, point(5, 2), {"name": "Tank1"})
    add(j, point(7, 4), {"base_demand": 66.6})
    add(j, point(9, 2), {"name": "JunctionWithoutPattern", "base_demand": 3})
    add(p, line((5, 2), (7, 4)), {"name": "Pipe2"})
    add(v, line((7, 4), (9, 2)), {})
    add(pumps, line((7, 4), (9, 2)), {})

    # confirm single period results

    run_action = RunAction()
    run_action.trigger()
    run_action.task.waitForFinished()

    # assert [l.name() for l in project.mapLayers().values()] == None

    node_out_layer = project.mapLayersByName("Résultats de simulation - Nœuds")[0]
    link_out_layer = project.mapLayersByName("Résultats de simulation - Liens")[0]

    nodes_out = layer_to_dict_by_name(node_out_layer)
    links_out = layer_to_dict_by_name(link_out_layer)

    assert nodes_out["Junction1"]["demand"] == 2.0
    assert nodes_out["Reservoir1"]["head"] == 10.0
    assert nodes_out["1"]["demand"] == pytest.approx(66.6)

    assert links_out["Pipe1"]["flowrate"] == 2.0
    assert links_out["Pipe1"]["velocity"] == pytest.approx(0.052, abs=0.001)
    assert links_out["Pipe1"]["headloss"] == pytest.approx(0.012489, abs=0.01)
    assert links_out["Pipe1"]["unit_headloss"] == pytest.approx(0.012489 / 567 * 1000, abs=0.00001)

    assert links_out["PipeWithBend"]["headloss"] == pytest.approx(4.40616748046875, abs=0.01)
    assert links_out["PipeWithBend"]["unit_headloss"] == pytest.approx(4.40616748046875 / 2 * 1000, abs=0.00001)

    ## confirm extended period results

    project.removeMapLayers([node_out_layer.id(), link_out_layer.id()])

    durations_menu = DurationSettingMenu()
    durations_menu.actions[6].trigger()

    QgsExpressionContextUtils.setProjectVariable(project, "gusnet_demand_multiplier", "1.1")
    QgsExpressionContextUtils.setProjectVariable(project, "gusnet_default_pattern", " 2.0 1 ")

    run_action = RunAction()
    run_action.trigger()
    run_action.task.waitForFinished()

    node_out_layer = project.mapLayersByName("Résultats de simulation - Nœuds")[0]
    link_out_layer = project.mapLayersByName("Résultats de simulation - Liens")[0]

    nodes_out = layer_to_dict_by_name(node_out_layer)
    links_out = layer_to_dict_by_name(link_out_layer)

    # check demand pattern was applied correctly
    assert nodes_out["Junction1"]["demand"] == pytest.approx([2.2, 4.4, 6.6, 4.4, 2.2, 0.0, 2.2], abs=0.00001)
    assert nodes_out["JunctionWithoutPattern"]["demand"] == pytest.approx(
        [6.6, 3.3, 6.6, 3.3, 6.6, 3.3, 6.6], abs=0.00001
    )
    # check head pattern was applied correctly
    assert nodes_out["Reservoir1"]["head"] == pytest.approx([10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 10.0], abs=0.0001)
    assert nodes_out["Reservoir1"]["pressure"] == pytest.approx([0.0, 10.0, 20.0, 30.0, 40.0, 50.0, 0.0], abs=0.0001)
    assert nodes_out["Reservoir1"]["demand"] == pytest.approx([-2.2, -4.4, -6.6, -4.4, -2.2, 0.0, -2.2], abs=0.0001)
