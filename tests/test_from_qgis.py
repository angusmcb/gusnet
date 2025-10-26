from __future__ import annotations

import re
import types
from typing import Any

import pytest
from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsFeature,
    QgsGeometry,
    QgsPointXY,
    QgsProject,
    QgsVectorLayer,
    edit,
)

import gusnet


def layer(
    layer_type: str, fields: list[tuple[str, type | str]] | None = None, crs: str | None = None
) -> QgsVectorLayer:
    if not fields:
        fields = []

    field_string = "&".join([f"field={name}:{type_to_string(the_type)}" for name, the_type in fields])
    crs_string = f"crs={crs}" if crs else "crs=None"
    return QgsVectorLayer(f"{layer_type}?{crs_string}&{field_string}", "", "memory")


def type_to_string(the_type: type | Any) -> str:
    if type(the_type) not in [type, types.GenericAlias]:
        if isinstance(the_type, list):
            if len(the_type) == 0 or type(the_type[0]) is str:
                the_type = list[str]
            elif type(the_type[0]) is float:
                the_type = list[float]
            elif type(the_type[0]) is int:
                the_type = list[int]
            elif type(the_type[0]) is bool:
                the_type = list[bool]
        else:
            the_type = type(the_type)

    if the_type is str:
        return "string"
    if the_type is float:
        return "double"
    if the_type is int:
        return "integer"
    if the_type is bool:
        return "boolean"
    if the_type == list[str]:
        return "string[]"
    if the_type == list[int]:
        return "integer[]"
    if the_type == list[float]:
        return "double[]"
    if the_type == list[bool]:
        return "boolean[]"

    if the_type is type(None):
        return "string"

    msg = f"Unsupported type: {the_type}"
    raise ValueError(msg)


def add_point(layer: QgsVectorLayer, point: tuple[float, float], fields: list | None = None):
    if not fields:
        fields = []
    feature = QgsFeature()
    feature.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(*point)))
    feature.setAttributes(fields)
    layer.dataProvider().addFeature(feature)
    layer.updateExtents()


def add_line(layer: QgsVectorLayer, points: list[tuple[float, float]], fields: list | None = None):
    if not fields:
        fields = []
    feature = QgsFeature()
    feature.setGeometry(QgsGeometry.fromPolylineXY([QgsPointXY(x, y) for x, y in points]))
    feature.setAttributes(fields)
    layer.dataProvider().addFeature(feature)
    layer.updateExtents()


def delete_all_features(layer: QgsVectorLayer):
    with edit(layer):
        layer.deleteFeatures(layer.allFeatureIds())


@pytest.fixture
def simple_layers() -> dict[str, QgsVectorLayer]:
    junction_layer = layer("point", [("name", str), ("elevation", float), ("base_demand", float)])
    add_point(junction_layer, (1, 1), ["J1", 0.0, 1])
    tank_layer = layer(
        "point",
        [
            ("name", str),
            ("elevation", float),
            ("min_level", float),
            ("max_level", float),
            ("init_level", float),
            ("tank_diameter", float),
        ],
    )
    add_point(tank_layer, (4, 5), ["T1", 1.0, 0, 1, 0.1, 5.0])
    pipe_layer = layer("linestring", [("name", str), ("roughness", float), ("diameter", float)])
    add_line(pipe_layer, [(1, 1), (4, 5)], ["P1", 100, 10])
    return {"JUNCTIONS": junction_layer, "PIPES": pipe_layer, "TANKS": tank_layer}


@pytest.fixture
def all_layers() -> dict[str, QgsVectorLayer]:
    junction_layer = layer("Point", [("elevation", float)])
    add_point(junction_layer, (1, 1), [0])
    add_point(junction_layer, (2, 2), [1.0])

    tank_layer = layer(
        "point",
        [
            ("elevation", float),
            ("min_level", float),
            ("max_level", float),
            ("init_level", float),
            ("tank_diameter", float),
        ],
    )
    add_point(tank_layer, (3, 3), [0, 0, 1, 0.5, 5.0])

    reservoir_layer = layer("Point", [("base_head", float)])
    add_point(reservoir_layer, (4, 4), [5.0])

    pipe_layer = layer("LineString", [("diameter", float), ("roughness", float)])
    add_line(pipe_layer, [(1, 1), (4, 4)], [0.1, 100])

    pump_layer = layer("LineString", [("pump_type", str), ("power", float), ("pump_curve", str)])
    add_line(pump_layer, [(2, 2), (3, 3)], ["power", 10])
    add_line(pump_layer, [(2, 2), (3, 3)], ["head", None, "(0,0), (1, 1)"])

    valve_layer = layer(
        "LineString", [("diameter", float), ("valve_type", str), ("pressure_setting", float), ("headloss_curve", str)]
    )
    add_line(valve_layer, [(1, 1), (2, 2)], [1, "PRV", 1.0])
    add_line(valve_layer, [(2, 2), (3, 3)], [1, "GPV", None, "[(0,0), (1, 1)]"])

    return {
        "JUNCTIONS": junction_layer,
        "TANKS": tank_layer,
        "RESERVOIRS": reservoir_layer,
        "PIPES": pipe_layer,
        "PUMPS": pump_layer,
        "VALVES": valve_layer,
    }


def test_simple_layers(simple_layers):
    import wntr

    wn = gusnet.from_qgis(simple_layers, "LPS", "H-W")

    assert isinstance(wn, wntr.network.WaterNetworkModel)
    assert "J1" in wn.junction_name_list


def test_broken_layername(simple_layers):
    simple_layers["wrongname"] = simple_layers["JUNCTIONS"]

    with pytest.raises(ValueError, match="'wrongname' is not a valid layer type."):
        gusnet.from_qgis(simple_layers, "LPS", "H-W")


def test_minimum_attributes(all_layers):
    import wntr

    wn = gusnet.from_qgis(all_layers, "LPS", "H-W")

    assert isinstance(wn, wntr.network.WaterNetworkModel)
    assert "1" in wn.junction_name_list
    assert "2" in wn.junction_name_list
    assert "4" in wn.tank_name_list
    assert "3" in wn.reservoir_name_list
    assert "1" in wn.pipe_name_list
    assert "2" in wn.pump_name_list
    assert "3" in wn.pump_name_list
    assert "4" in wn.valve_name_list
    assert "5" in wn.valve_name_list


@pytest.mark.parametrize(
    ("layer_name", "field"),
    [
        ("JUNCTIONS", "elevation"),
        ("TANKS", "elevation"),
        ("TANKS", "min_level"),
        ("TANKS", "max_level"),
        ("TANKS", "init_level"),
        ("TANKS", "tank_diameter"),
        ("RESERVOIRS", "base_head"),
        ("PIPES", "diameter"),
        ("PIPES", "roughness"),
        ("PUMPS", "pump_type"),
        ("PUMPS", "power"),
        ("PUMPS", "pump_curve"),
        ("VALVES", "valve_type"),
        ("VALVES", "pressure_setting"),
        ("VALVES", "headloss_curve"),
        ("VALVES", "diameter"),
    ],
)
def test_check_all_minimum_attributes_required(all_layers, layer_name, field):
    all_layers[layer_name].dataProvider().deleteAttributes([all_layers[layer_name].fields().indexFromName(field)])
    all_layers[layer_name].updateFields()

    with pytest.raises(gusnet.interface.GenericRequiredFieldError):
        gusnet.from_qgis(all_layers, "LPS", "H-W")


def test_no_pipes(all_layers):
    import wntr

    del all_layers["PIPES"]

    wn = gusnet.from_qgis(all_layers, "LPS", "H-W")

    assert isinstance(wn, wntr.network.WaterNetworkModel)


def test_no_links(simple_layers):
    delete_all_features(simple_layers["PIPES"])

    with pytest.raises(gusnet.interface.NetworkModelError, match="There are no links in the model"):
        gusnet.from_qgis(simple_layers, "LPS", "H-W")


def test_no_nodes(simple_layers):
    delete_all_features(simple_layers["JUNCTIONS"])
    delete_all_features(simple_layers["TANKS"])

    with pytest.raises(gusnet.interface.NetworkModelError, match="There are no nodes in the model"):
        gusnet.from_qgis(simple_layers, "LPS", "H-W")


def test_wntr_error(simple_layers):
    name_with_spaces = "this name has spaces"
    add_line(simple_layers["PIPES"], [(1, 1), (4, 5)], [name_with_spaces, 100, 5])

    with pytest.raises(gusnet.interface.WntrError, match="name must be"):
        gusnet.from_qgis(simple_layers, "LPS", "H-W")


def test_unmeasurable_pipe(qgis_new_project):
    junction_layer = layer("point", [("name", str), ("elevation", float)], "EPSG:4326")
    add_point(junction_layer, (1, 1), ["J1", 1])
    add_point(junction_layer, (9000, 9000), ["J2", 1])
    pipe_layer = layer("linestring", [("name", str), ("diameter", float), ("roughness", float)], "EPSG:4326")
    add_line(pipe_layer, [(1, 1), (9000, 9000)], ["P1", 1, 100])
    layers = {"JUNCTIONS": junction_layer, "PIPES": pipe_layer}

    class ProjectMock:
        def ellipsoid():
            return "EPSG:7030"

        def transformContext():  # noqa: N802
            return QgsProject.instance().transformContext()

    with pytest.raises(gusnet.interface.PipeMeasuringError, match="cannot calculate length of"):
        gusnet.from_qgis(layers, "LPS", "H-W", project=ProjectMock)


@pytest.mark.parametrize("headloss", ["H-W", "D-W", "C-M"])
def test_from_qgis_headloss(simple_layers, headloss):
    wn = gusnet.from_qgis(simple_layers, "LPS", headloss=headloss)

    assert "J1" in wn.junction_name_list
    assert "T1" in wn.tank_name_list
    assert "P1" in wn.pipe_name_list
    assert wn.options.hydraulic.headloss == headloss


@pytest.mark.parametrize(
    ("headloss", "unit", "expected_roughness"),
    [
        ("H-W", "LPS", 100),
        ("D-W", "LPS", 0.1),
        ("C-M", "LPS", 100),
        ("H-W", "GPM", 100),
        ("D-W", "GPM", 0.030480000000000004),
        ("C-M", "GPM", 100),
    ],
)
@pytest.mark.filterwarnings("ignore: QgsField constructor is deprecated")
def test_roughness_conversion(simple_layers, headloss, unit, expected_roughness):
    import wntr

    if wntr.__version__ == "1.2.0" and headloss == "D-W":
        pytest.skip("Problem with headloss conversion in older wntr versions")

    wn = gusnet.from_qgis(simple_layers, unit, headloss=headloss)
    assert isinstance(wn, wntr.network.WaterNetworkModel)
    assert wn.get_link("P1").roughness == expected_roughness


@pytest.mark.filterwarnings("ignore: QgsField constructor is deprecated")
@pytest.mark.filterwarnings("ignore:Changing the headloss formula")
@pytest.mark.parametrize(
    ("headloss", "unit", "expected_roughness"),
    [
        ("H-W", "LPS", 100),
        ("D-W", "LPS", 0.1),
        ("C-M", "LPS", 100),
        ("H-W", "GPM", 100),
        ("D-W", "GPM", 0.030480000000000004),
        ("C-M", "GPM", 100),
    ],
)
@pytest.mark.filterwarnings("ignore: QgsField constructor is deprecated")
def test_roughness_conversion_with_wn_options(simple_layers, headloss, unit, expected_roughness):
    import wntr

    if wntr.__version__ == "1.2.0" and headloss == "D-W":
        pytest.skip("Problem with headloss conversion in older wntr versions")

    wn = wntr.network.WaterNetworkModel()
    wn.options.hydraulic.headloss = headloss

    wn = gusnet.from_qgis(simple_layers, unit, wn=wn)
    assert isinstance(wn, wntr.network.WaterNetworkModel)
    assert wn.get_link("P1").roughness == expected_roughness


def test_from_qgis_invalid_headloss(simple_layers):
    with pytest.raises(ValueError, match="headloss must be set if wn is not set: possible values are: H-W, D-W, C-M"):
        gusnet.from_qgis(simple_layers, "LPS", headloss=None)


def test_from_qgis_invalid_headloss_with_wn(simple_layers):
    import wntr

    wn = wntr.network.WaterNetworkModel()
    with pytest.raises(
        ValueError,
        match="Cannot set headloss when wn is set. Set the headloss in the wn.options.hydraulic.headloss instead",
    ):
        gusnet.from_qgis(simple_layers, "LPS", headloss="INVALID", wn=wn)


def test_duplicate_names():
    junction_layer = layer("point", [("name", str), ("elevation", float)])
    add_point(junction_layer, (1, 1), ["J1", 0])
    add_point(junction_layer, (2, 2), ["J1", 0])  # Conflict: same name as the first junction
    add_point(junction_layer, (3, 3), ["J1", 0])
    add_point(junction_layer, (3, 3), ["J2", 0])
    add_point(junction_layer, (3, 3), ["J2", 0])

    pipe_layer = layer("LineString", [("name", str), ("diameter", float), ("roughness", float)])
    add_line(pipe_layer, [(1, 1), (2, 2)], ["P1", 1, 1])
    add_line(pipe_layer, [(2, 2), (3, 3)], ["P1", 1, 1])  # Conflict: same name as the first pipe

    layers = {"JUNCTIONS": junction_layer, "PIPES": pipe_layer}

    with pytest.raises(gusnet.interface.NetworkModelError, match="Duplicate names found: J1, J2"):
        gusnet.from_qgis(layers, "LPS", "H-W")


def test_name_generation_with_conflicts():
    junctions = layer("point", [("name", str), ("elevation", float)])
    add_point(junctions, (1, 1), ["", 1])
    add_point(junctions, (2, 2), ["1", 1])
    add_point(junctions, (3, 3), ["", 1])

    tanks = layer(
        "point",
        [
            ("name", str),
            ("elevation", float),
            ("min_level", float),
            ("max_level", float),
            ("init_level", float),
            ("tank_diameter", float),
        ],
    )
    add_point(tanks, (5, 1), ["xx", 1, 1, 1, 1, 1])
    add_point(tanks, (6, 2), ["0", 1, 1, 1, 1, 1])
    add_point(tanks, (7, 3), [None, 1, 1, 1, 1, 1])

    reservoirs = layer("point", [("base_head", float)])
    add_point(reservoirs, (8, 1), [1])
    add_point(reservoirs, (9, 2), [1])

    pipes = layer("linestring", [("name", str), ("roughness", float), ("diameter", float)])
    add_line(pipes, [(1, 1), (2, 2)], ["1", 1, 1])
    add_line(pipes, [(2, 2), (3, 3)], ["", 1, 1])  # Conflict: same name as the first pipe

    layers = {"JUNCTIONS": junctions, "TANKS": tanks, "RESERVOIRS": reservoirs, "PIPES": pipes}

    wn = gusnet.from_qgis(layers, "LPS", "H-W")

    assert len(wn.junction_name_list) == 3
    assert len(wn.pipe_name_list) == 2
    assert wn.node_name_list == ["2", "1", "3", "4", "5", "xx", "0", "6"]
    assert wn.link_name_list == ["1", "2"]


@pytest.mark.parametrize(
    ("unit", "expected_demand"),
    {("GPM", 6.30901964e-05), ("LPS", 0.001), ("lps", 0.001), ("CFS", 0.0283168466)},
)
def test_unit_conversion_demand(simple_layers, unit, expected_demand):
    wn = gusnet.from_qgis(simple_layers, unit, "H-W")
    assert wn.get_node("J1").base_demand == expected_demand


def test_bad_units(simple_layers):
    with pytest.raises(
        ValueError,
        match="'NON-EXISTANT' is not a known set of units. Possible units are: LPS, LPM, MLD, CMH, CMD, CFS, GPM, MGD, IMGD, AFD",  # noqa: E501
    ):
        gusnet.from_qgis(simple_layers, units="Non-existant", headloss="H-W")


def test_length_measurement_utm(simple_layers):
    for layer in simple_layers.values():
        layer.setCrs(QgsCoordinateReferenceSystem("EPSG:32600"))

    wn = gusnet.from_qgis(simple_layers, "LPS", "H-W")

    pipe = wn.get_link("P1")
    assert pipe.length == 5.0


def test_custom_attributes():
    # Create layers directly
    junction_layer = layer(
        "point",
        [
            ("name", str),
            ("base_demand", float),
            ("custom_str", str),
            ("custom_int", int),
            ("custom_float", float),
            ("custom_bool", bool),
            ("elevation", float),
        ],
    )
    add_point(junction_layer, (1, 1), ["J1", 1, "xx", 2, 2.5, True, 1.0])
    add_point(junction_layer, (2, 2), ["J2", 2, "yy", 1000000000, 7.2, False, 1.0])

    pipe_layer = layer("linestring", [("name", str), ("roughness", float), ("diameter", float)])
    add_line(pipe_layer, [(1, 1), (2, 2)], ["P1", 100, 5])

    layers = {"JUNCTIONS": junction_layer, "PIPES": pipe_layer}

    wn = gusnet.from_qgis(layers, "LPS", "H-W")

    assert wn.get_node("J1").custom_str == "xx"
    assert wn.get_node("J1").custom_int == 2
    assert wn.get_node("J1").custom_float == 2.5
    assert wn.get_node("J1").custom_bool is True

    assert wn.get_node("J2").custom_str == "yy"
    assert wn.get_node("J2").custom_int == 1000000000
    assert wn.get_node("J2").custom_float == 7.2
    assert wn.get_node("J2").custom_bool is False


@pytest.fixture
def layers_that_snap():
    junction_layer = layer("point", [("name", str), ("elevation", float)])
    add_point(junction_layer, (0, 0), ["J1", 0.0])
    add_point(junction_layer, (3000, 4000), ["J2", 100.0])
    pipe_layer = layer("linestring", [("name", str), ("roughness", float), ("diameter", float)])
    add_line(pipe_layer, [(1, 1), (2800, 3800)], ["P1", 100, 10])
    return {"JUNCTIONS": junction_layer, "PIPES": pipe_layer}


def test_snap_nodes(layers_that_snap):
    wn = gusnet.from_qgis(layers_that_snap, "LPS", "H-W")

    assert "P1" in wn.pipe_name_list
    assert wn.get_link("P1").start_node_name == "J1"
    assert wn.get_link("P1").end_node_name == "J2"


@pytest.fixture
def mixed_crs_layers():
    junction_layer = layer("point", [("name", str), ("elevation", float)], "EPSG:4326")
    add_point(junction_layer, (-83, 38), ["J1", 0.0])
    tank_layer = layer(
        "point",
        [
            ("name", str),
            ("elevation", float),
            ("min_level", float),
            ("max_level", float),
            ("init_level", float),
            ("tank_diameter", float),
        ],
        "EPSG:32616",
    )
    add_point(tank_layer, (844219, 4230929), ["T1", 100.0, 0, 1, 0.5, 1.0])
    pipe_layer = layer("linestring", [("name", str), ("diameter", float), ("roughness", float)], "EPSG:3089")
    add_line(pipe_layer, [(5713511, 3899366), (5691228, 3957214)], ["P1", 1, 100])
    return {"JUNCTIONS": junction_layer, "PIPES": pipe_layer, "TANKS": tank_layer}


def test_snap_nodes_mixed_crs(mixed_crs_layers):
    wn = gusnet.from_qgis(mixed_crs_layers, "LPS", "H-W")

    assert "P1" in wn.pipe_name_list
    assert wn.get_link("P1").start_node_name == "J1"
    assert wn.get_link("P1").end_node_name == "T1"


@pytest.mark.parametrize("crs", ["EPSG:32616", "EPSG:3089"])
def test_snap_nodes_mixed_crs_with_crs_specified(mixed_crs_layers, crs):
    wn = gusnet.from_qgis(mixed_crs_layers, "LPS", "H-W", crs=crs)
    assert wn.get_link("P1").length == pytest.approx(18900, 0.01)


def test_snap_nodes_mixed_crs_length(mixed_crs_layers):
    wn = gusnet.from_qgis(mixed_crs_layers, "LPS", "H-W")
    assert wn.get_link("P1").length == pytest.approx(19569, 0.01)


def test_snap_length(layers_that_snap):
    wn = gusnet.from_qgis(layers_that_snap, "LPS", "H-W")
    assert wn.get_link("P1").length == 5000


def test_too_far_to_snap():
    junction_layer = layer("point", [("name", str), ("elevation", float)])
    add_point(junction_layer, (1, 1), ["J1", 1])
    add_point(junction_layer, (1000, 1000), ["J2", 1])
    pipe_layer = layer("linestring", [("name", str), ("diameter", float), ("roughness", float)])
    add_line(pipe_layer, [(1, 1), (900, 900)], ["P1", 100, 100])
    layers = {"JUNCTIONS": junction_layer, "PIPES": pipe_layer}

    with pytest.raises(gusnet.interface.NetworkModelError, match="too far away to snap to"):
        gusnet.from_qgis(layers, "LPS", "H-W")


def test_measure_no_crs(simple_layers):
    wn = gusnet.from_qgis(simple_layers, "LPS", "H-W")

    assert wn.get_link("P1").length == 5.0


def test_measure_utm(simple_layers):
    # 32636 is a utm crs
    wn = gusnet.from_qgis(simple_layers, "LPS", "H-W", crs="EPSG:32636")

    assert wn.get_link("P1").length == 5.0


def test_measure_feet(simple_layers):
    # 3089 is a feet crs
    wn = gusnet.from_qgis(simple_layers, "LPS", "H-W", crs="EPSG:3089")

    assert wn.get_link("P1").length == pytest.approx(5.0 / 3.2808, 0.01)


def test_prioritise_length_attribute(simple_layers, caplog):
    pipe_layer = layer("linestring", [("name", str), ("diameter", float), ("roughness", float), ("length", float)])
    add_line(pipe_layer, [(1, 1), (4, 5)], ["P1", 1, 1])
    add_line(pipe_layer, [(1, 1), (4, 5)], ["P2", 1, 1, 100])
    simple_layers["PIPES"] = pipe_layer

    wn = gusnet.from_qgis(simple_layers, "LPS", "H-W")

    warn_message = (
        "1 pipe(s) have very different attribute length vs measured length. First five are: P2 (5 metres vs 100 metres)"
    )
    assert warn_message in caplog.messages

    assert wn.get_link("P1").length == 5
    assert wn.get_link("P2").length == 100


@pytest.mark.parametrize(
    ("bool_attr", "expected_result"),
    [
        (1, True),
        (0, False),
        (True, True),
        (False, False),
        ("True", True),
        ("False", False),
        ("1", True),
        ("0", False),
        (1.0, True),
        (0.0, False),
        ("1.0", True),
        ("0.0", False),
        (None, False),
    ],
)
def test_boolean_attributes(bool_attr, expected_result):
    if bool_attr in ["True", "False"]:
        pytest.skip("String True/False Boolean attributes are not supported in WNTR yet")

    junction_layer = layer("point", [("name", str), ("elevation", float)])
    add_point(junction_layer, (1, 1), ["J1", 1])
    tank_layer = layer(
        "point",
        [
            ("name", str),
            ("elevation", float),
            ("min_level", float),
            ("max_level", float),
            ("init_level", float),
            ("tank_diameter", float),
            ("overflow", bool_attr),
        ],
    )
    add_point(tank_layer, (4, 5), ["T1", 1.0, 0, 1, 0.5, 5, bool_attr])
    pipe_layer = layer(
        "linestring", [("name", str), ("diameter", float), ("roughness", float), ("check_valve", bool_attr)]
    )
    add_line(pipe_layer, [(1, 1), (4, 5)], ["P1", 1, 1, bool_attr])

    layers = {"JUNCTIONS": junction_layer, "TANKS": tank_layer, "PIPES": pipe_layer}

    wn = gusnet.from_qgis(layers, "LPS", "H-W")

    assert wn.get_link("P1").check_valve is expected_result
    assert wn.get_node("T1").overflow is expected_result


@pytest.mark.parametrize(
    ("float_attr", "expected_result", "field_type"),
    [
        (1, 1.0, int),
        (0, 0.0, int),
        ("1", 1.0, str),
        ("0", 0.0, str),
        (1.1, 1.1, float),
        (0.0, 0.0, float),
        ("1.1", 1.1, str),
        ("0.0", 0.0, str),
    ],
)
def test_float_attributes(float_attr, expected_result, field_type):
    if float_attr in ["True", "False"]:
        pytest.skip("String True/False Boolean attributes are not supported in WNTR yet")

    junction_layer = layer("point", [("name", str), ("elevation", field_type), ("pressure_exponent", field_type)])
    add_point(junction_layer, (1, 1), ["J1", float_attr, float_attr])
    # additionally check that 'elevation' can accept mixed types
    tank_layer = layer(
        "point",
        [
            ("name", str),
            ("tank_diameter", float),
            ("elevation", float),
            ("min_level", float),
            ("max_level", float),
            ("init_level", float),
        ],
    )
    add_point(tank_layer, (4, 5), ["T1", float_attr, 865.0, float_attr, float_attr, float_attr])
    pipe_layer = layer("linestring", [("name", str), ("length", field_type), ("diameter", float), ("roughness", float)])
    add_line(pipe_layer, [(1, 1), (4, 5)], ["P1", float_attr, 100.0, 100.0])

    layers = {"JUNCTIONS": junction_layer, "TANKS": tank_layer, "PIPES": pipe_layer}

    wn = gusnet.from_qgis(layers, "lps", "H-W")
    assert wn.get_node("J1").elevation == expected_result
    assert wn.get_node("J1").pressure_exponent == expected_result
    assert wn.get_node("T1").diameter == expected_result
    assert wn.get_node("T1").elevation == 865.0
    assert wn.get_link("P1").length == expected_result


@pytest.mark.parametrize(
    ("float_attr", "attr_type"), [("not_a_float", str), (["not", "a", "float"], list[str]), ([1], list[int])]
)
def test_float_error(simple_layers, float_attr, attr_type):
    pipe_layer = layer("linestring", [("name", str), ("diameter", attr_type), ("roughness", float)])
    add_line(pipe_layer, [(1, 1), (4, 5)], ["P1", float_attr, 1.0])

    simple_layers["PIPES"] = pipe_layer

    with pytest.raises(gusnet.interface.NetworkModelError, match="Problem in column diameter: "):
        gusnet.from_qgis(simple_layers, "LPS", "H-W")


@pytest.fixture
def pattern():
    return "1 0 2.5 -3"


@pytest.fixture
def expected_pattern():
    return [1, 0, 2.5, -3]


@pytest.fixture
def demand_pattern_layers(pattern, simple_layers):
    junctions = layer(
        "point", [("name", str), ("elevation", float), ("base_demand", float), ("demand_pattern", pattern)]
    )
    add_point(junctions, (1, 1), ["J1", 1, 1, pattern])

    simple_layers["JUNCTIONS"] = junctions

    return simple_layers


@pytest.fixture
def head_pattern_layers(pattern, simple_layers):
    reservoir_layer = layer("point", [("name", str), ("base_head", float), ("head_pattern", pattern)])
    add_point(reservoir_layer, (5, 5), ["R1", 1.0, pattern])
    simple_layers["RESERVOIRS"] = reservoir_layer
    return simple_layers


@pytest.fixture
def pump_energy_pattern_layers(pattern, simple_layers):
    pump_layer = layer("linestring", [("name", str), ("pump_type", str), ("power", float), ("energy_pattern", pattern)])
    add_line(pump_layer, [(1, 1), (4, 5)], ["PUMP1", "POWER", 10, pattern])

    simple_layers["PUMPS"] = pump_layer

    return simple_layers


def test_demand_pattern(demand_pattern_layers, expected_pattern):
    wn = gusnet.from_qgis(demand_pattern_layers, "LPS", "H-W")

    assert wn.get_node("J1").demand_timeseries_list[0].pattern_name == "2"
    assert list(wn.patterns["2"].multipliers) == expected_pattern


def test_head_pattern(head_pattern_layers, expected_pattern):
    wn = gusnet.from_qgis(head_pattern_layers, "LPS", "H-W")

    assert wn.get_node("R1").head_pattern_name == "2"
    assert list(wn.patterns["2"].multipliers) == expected_pattern


def test_energy_pattern(pump_energy_pattern_layers, expected_pattern):
    wn = gusnet.from_qgis(pump_energy_pattern_layers, "LPS", "H-W")

    assert wn.get_link("PUMP1").energy_pattern == "2"
    assert list(wn.patterns["2"].multipliers) == expected_pattern


def test_speed_pattern(simple_layers):
    pump_layer = layer("linestring", [("name", str), ("pump_type", str), ("power", float), ("speed_pattern", str)])
    add_line(pump_layer, [(1, 1), (4, 5)], ["PUMP1", "POWER", 10, "5 4 3 2 1 1"])
    simple_layers["PUMPS"] = pump_layer

    wn = gusnet.from_qgis(simple_layers, "LPS", "H-W")

    assert wn.get_link("PUMP1").speed_pattern_name == "2"
    assert list(wn.patterns["2"].multipliers) == [5.0, 4.0, 3.0, 2.0, 1.0, 1.0]


def test_lots_of_patterns():
    junction_layer = layer(
        "point", [("name", str), ("elevation", float), ("base_demand", float), ("demand_pattern", str)]
    )
    add_point(junction_layer, (1, 1), ["J1", 1, 1, "1 0 2.5"])
    add_point(junction_layer, (2, 2), ["J2", 1, 1, "1 0 2.5"])
    add_point(junction_layer, (3, 3), ["J3", 1, 1, "1 0 3.0"])
    add_point(junction_layer, (3, 3), ["J4", 1, 1, ""])

    reservoir_layer = layer("point", [("name", str), ("base_head", float), ("head_pattern", str)])
    add_point(reservoir_layer, (4, 5), ["R1", 1, "2 0 200.5"])
    add_point(reservoir_layer, (5, 6), ["R2", 1])

    pump_layer = layer("linestring", [("name", str), ("pump_type", str), ("power", float), ("speed_pattern", str)])
    add_line(pump_layer, [(1, 1), (4, 5)], ["P1", "POWER", 10, "5 4 3 2 1 1"])
    pattern_layers = {"JUNCTIONS": junction_layer, "PUMPS": pump_layer, "RESERVOIRS": reservoir_layer}
    wn = gusnet.from_qgis(pattern_layers, "LPS", "H-W")

    assert wn.get_node("J1").demand_timeseries_list[0].pattern_name == "2"
    assert wn.get_node("J2").demand_timeseries_list[0].pattern_name == "2"
    assert wn.get_node("J3").demand_timeseries_list[0].pattern_name == "3"
    assert wn.get_node("R1").head_pattern_name == "4"
    assert wn.get_node("R2").head_pattern_name is None
    assert wn.get_link("P1").speed_pattern_name == "5"


@pytest.mark.parametrize(
    ("pattern", "expected_value"),
    [
        ("1 0 2.5", [1.0, 0.0, 2.5]),
        ("1 0 2.5 -3", [1.0, 0.0, 2.5, -3]),
        ("1", [1.0]),
        ("0", [0.0]),
        ("1 0 2.5 -3 4 5 5 5 0 7.8", [1.0, 0.0, 2.5, -3, 4, 5, 5, 5, 0, 7.8]),
        ("   2    ", [2.0]),
    ],
)
def test_pattern_string_values(expected_value, demand_pattern_layers):
    wn = gusnet.from_qgis(demand_pattern_layers, "LPS", "H-W")

    assert wn.get_node("J1").demand_timeseries_list[0].pattern_name == "2"
    assert list(wn.patterns["2"].multipliers) == expected_value


@pytest.mark.parametrize(
    "pattern", ["1 0 2,5", "1 0 xx", 1.0, 2, 0, True, False, [""], ["  "], ["1", "not_a_number", "3"], ["1", ""]]
)
def test_bad_pattern(pattern, demand_pattern_layers):
    with pytest.raises(gusnet.interface.PatternError, match=re.escape(str(pattern))):
        gusnet.from_qgis(demand_pattern_layers, "LPS", "H-W")


@pytest.mark.parametrize("pattern", ["", "  ", []])
def test_empty_pattern(pattern, demand_pattern_layers):
    wn = gusnet.from_qgis(demand_pattern_layers, "LPS", "H-W")

    assert len(wn.patterns) == 0
    assert wn.get_node("J1").demand_timeseries_list[0].pattern_name == "1"
    assert wn.get_node("J1").demand_timeseries_list[0].pattern is None


@pytest.mark.parametrize("pattern", ["", "  ", []])
def test_empty_head_pattern(pattern, head_pattern_layers):
    wn = gusnet.from_qgis(head_pattern_layers, "LPS", "H-W")

    assert len(wn.patterns) == 0
    assert wn.get_node("R1").head_pattern_name is None
    assert wn.get_node("R1").head_timeseries.pattern is None


@pytest.mark.parametrize("pattern", [[1.0, 0.0, 2.0], ["1.0", "0.0", "2.0"], [1, 0, 2]])
def test_pattern_list_types(demand_pattern_layers):
    wn = gusnet.from_qgis(demand_pattern_layers, "LPS", "H-W")

    assert wn.get_node("J1").demand_timeseries_list[0].pattern_name == "2"
    assert list(wn.patterns["2"].multipliers) == [1, 0, 2.0]


@pytest.mark.parametrize("pattern", [[1.0, 0.0, 2.0], [1.0, 0.0, 2.1], [1.0], [0.0], [2.2]])
def test_pattern_list_values(pattern, demand_pattern_layers):
    wn = gusnet.from_qgis(demand_pattern_layers, "LPS", "H-W")

    assert wn.get_node("J1").demand_timeseries_list[0].pattern_name == "2"
    assert list(wn.patterns["2"].multipliers) == pattern


@pytest.mark.parametrize("pattern", [[1, 0, -1, 100]])
def test_two_list_pattern(pattern, demand_pattern_layers):
    add_point(demand_pattern_layers["JUNCTIONS"], (1, 2), ["J2", 1, 1, pattern])

    wn = gusnet.from_qgis(demand_pattern_layers, "LPS", "H-W")

    assert wn.get_node("J1").demand_timeseries_list[0].pattern_name == "2"
    assert wn.get_node("J2").demand_timeseries_list[0].pattern_name == "2"
    assert list(wn.patterns["2"].multipliers) == pattern


def test_pattern_plus_empty(demand_pattern_layers, expected_pattern):
    add_point(demand_pattern_layers["JUNCTIONS"], (1, 2), ["J2", 1, 1])

    wn = gusnet.from_qgis(demand_pattern_layers, "LPS", "H-W")

    assert len(wn.patterns) == 1
    assert wn.get_node("J1").demand_timeseries_list[0].pattern_name == "2"
    assert wn.get_node("J2").demand_timeseries_list[0].pattern_name == "1"
    assert wn.get_node("J2").demand_timeseries_list[0].pattern is None
    assert list(wn.patterns["2"].multipliers) == expected_pattern


@pytest.fixture
def curve_string():
    return "[(0.0, 200.5),(20.0,50)]"


@pytest.fixture
def pump_head_curve_layers(simple_layers, curve_string):
    pump_layer = layer("linestring", [("name", str), ("pump_type", str), ("pump_curve", curve_string)])
    add_line(pump_layer, [(1, 1), (4, 5)], ["PUMP1", "HEAD", curve_string])
    simple_layers["PUMPS"] = pump_layer
    return simple_layers


@pytest.fixture
def tank_vol_curve_layers(simple_layers, curve_string):
    tank_layer = layer(
        "point",
        [
            ("name", str),
            ("elevation", float),
            ("tank_diameter", float),
            ("max_level", float),
            ("min_level", float),
            ("init_level", float),
            ("vol_curve", curve_string),
        ],
    )
    add_point(tank_layer, (4, 5), ["T1", 1, 20, 1, 1, 1, curve_string])
    simple_layers["TANKS"] = tank_layer
    return simple_layers


@pytest.fixture
def valve_headloss_curve_layers(simple_layers, curve_string):
    valve_layer = layer(
        "linestring", [("name", str), ("valve_type", str), ("diameter", float), ("headloss_curve", curve_string)]
    )
    add_line(valve_layer, [(1, 1), (4, 5)], ["V1", "GPV", 1, curve_string])
    simple_layers["VALVES"] = valve_layer
    return simple_layers


@pytest.fixture
def pump_efficiency_curve_layers(simple_layers, curve_string):
    pump_layer = layer(
        "linestring", [("name", str), ("pump_type", str), ("power", float), ("efficiency", curve_string)]
    )
    add_line(pump_layer, [(1, 1), (4, 5)], ["PUMP1", "POWER", 10, curve_string])
    simple_layers["PUMPS"] = pump_layer
    return simple_layers


@pytest.mark.parametrize(
    "curve_string",
    [
        "[(0.0, 200.5),(20.0,50)]",
        "(0.0, 200.5),(20.0,50)",
        "[[0.0, 200.5],[20.0,50]]",
        "(0.0, 200.5),[20.0,50]",
        "(0.0, 200.5)    ,(20.0,50)  ",
        "(0., 200.5),(20.0,50)",
        "('0.0', 200.5), (20.0,50)",
    ],
)
class TestCurveNoConversion:
    def test_head_curve(self, pump_head_curve_layers):
        wn = gusnet.from_qgis(pump_head_curve_layers, "LPS", "H-W")

        assert wn.get_link("PUMP1").pump_curve_name == "1"
        assert wn.curves["1"].points == [(0.0, 200.5), (0.02, 50.0)]

    def test_volume_curve(self, tank_vol_curve_layers):
        wn = gusnet.from_qgis(tank_vol_curve_layers, "LPS", "H-W")

        assert wn.get_node("T1").vol_curve_name == "1"
        assert wn.curves["1"].points == [(0.0, 200.5), (20.0, 50)]

    def test_valve_headloss_curve(self, valve_headloss_curve_layers):
        wn = gusnet.from_qgis(valve_headloss_curve_layers, "LPS", "H-W")

        assert wn.get_link("V1").headloss_curve_name == "1"
        assert wn.curves["1"].points == [(0.0, 200.5), (0.02, 50.0)]

    @pytest.mark.skip("Efficiency curve bug in wntr")
    def test_pump_efficiency_curve(self, pump_efficiency_curve_layers):
        wn = gusnet.from_qgis(pump_efficiency_curve_layers, "LPS", "H-W")

        assert wn.get_link("PUMP1").efficiencey.multipliers == "1"


class TestCurveMetricConversion:
    def test_head_curve(self, pump_head_curve_layers):
        wn = gusnet.from_qgis(pump_head_curve_layers, "LPS", "H-W")

        assert wn.get_link("PUMP1").pump_curve_name == "1"
        assert wn.curves["1"].points == [(0.0, 200.5), (0.02, 50)]

    def test_volume_curve(self, tank_vol_curve_layers):
        wn = gusnet.from_qgis(tank_vol_curve_layers, "LPS", "H-W")

        assert wn.get_node("T1").vol_curve_name == "1"
        assert wn.curves["1"].points == [(0.0, 200.5), (20.0, 50.0)]

    def test_valve_headloss_curve(self, valve_headloss_curve_layers):
        wn = gusnet.from_qgis(valve_headloss_curve_layers, "LPS", "H-W")

        assert wn.get_link("V1").headloss_curve_name == "1"
        assert wn.curves["1"].points == [(0.0, 200.5), (0.02, 50.0)]


class TestCurveImperialConversion:
    def test_head_curve(self, pump_head_curve_layers):
        wn = gusnet.from_qgis(pump_head_curve_layers, "GPM", "H-W")

        assert wn.get_link("PUMP1").pump_curve_name == "1"
        assert wn.curves["1"].points == [(0.0, 61.1124), (0.0012618039280000001, 15.24)]

    def test_volume_curve(self, tank_vol_curve_layers):
        wn = gusnet.from_qgis(tank_vol_curve_layers, "GPM", "H-W")

        assert wn.get_node("T1").vol_curve_name == "1"
        assert wn.curves["1"].points == [(0.0, 5.677527741696001), (6.096, 1.4158423296000002)]

    def test_valve_headloss_curve(self, valve_headloss_curve_layers):
        wn = gusnet.from_qgis(valve_headloss_curve_layers, "GPM", "H-W")

        assert wn.get_link("V1").headloss_curve_name == "1"
        assert wn.curves["1"].points == [(0.0, 61.1124), (0.0012618039280000001, 15.24)]


@pytest.mark.parametrize(
    "curve_string",
    [
        "[]",
        "[(0.0,100),(10.0,1000)],(20,10000.0)",
        "[xx]",
        "[(1,2),(20,2,3)]",
        '[(1.0,"x"),(20.0,3)]',
        "[1, 10, 20]",
        "[1,2] [2, 3]",
        "(1,2) (20, 2)",
        "assert False",
        "dict()",
        "list()",
        1,
        1.0,
        0.0,
        True,
        False,
    ],
)
class TestCurveError:
    def test_tank_volume(self, tank_vol_curve_layers, curve_string):
        with pytest.raises(gusnet.interface.CurveError, match=re.escape(str(curve_string))):
            gusnet.from_qgis(tank_vol_curve_layers, "LPS", "H-W")

    def test_pump_head(self, pump_head_curve_layers, curve_string):
        with pytest.raises(gusnet.interface.CurveError, match=re.escape(str(curve_string))):
            gusnet.from_qgis(pump_head_curve_layers, "LPS", "H-W")

    def test_valve_headloss_curve(self, valve_headloss_curve_layers, curve_string):
        with pytest.raises(gusnet.interface.CurveError, match=re.escape(str(curve_string))):
            gusnet.from_qgis(valve_headloss_curve_layers, "LPS", "H-W")


@pytest.mark.parametrize("curve_string", [None, "", "  "])
class TestCurveEmpty:
    def test_tank_volume(self, tank_vol_curve_layers):
        wn = gusnet.from_qgis(tank_vol_curve_layers, "LPS", "H-W")

        assert wn.nodes["T1"].vol_curve_name is None

    def test_pump_head(self, pump_head_curve_layers):
        with pytest.raises(gusnet.interface.PumpCurveMissingError):
            gusnet.from_qgis(pump_head_curve_layers, "LPS", "H-W")

    def test_valve_headloss_curve(self, valve_headloss_curve_layers):
        with pytest.raises(gusnet.interface.ValveSettingError):
            gusnet.from_qgis(valve_headloss_curve_layers, "LPS", "H-W")


def test_null_geometry_point(simple_layers):
    layer = simple_layers["JUNCTIONS"]

    with edit(layer):
        feature = QgsFeature()
        feature.setAttributes(["JX", 1])
        layer.dataProvider().addFeature(feature)
        feature = QgsFeature()
        feature.setAttributes(["JXX", 1])
        layer.dataProvider().addFeature(feature)

    with pytest.raises(gusnet.interface.NullGeometryError, match=r"2 feature\(s\) in Junctions with no geometry"):
        gusnet.from_qgis(simple_layers, "LPS", "H-W")


def test_null_geometry_link(simple_layers):
    layer = simple_layers["PIPES"]

    with edit(layer):
        feature = QgsFeature()
        feature.setAttributes(["PX", 100, 100])
        layer.dataProvider().addFeature(feature)

    with pytest.raises(gusnet.interface.NullGeometryError, match=r"1 feature\(s\) in Pipes with no geometry"):
        gusnet.from_qgis(simple_layers, "LPS", "H-W")


@pytest.mark.parametrize(
    ("initial_status", "expected_status"),
    [("OPEN", "Open"), ("Open", "Open"), ("CLOSED", "Closed"), ("Closed", "Closed"), (None, "Open")],
)
def test_initial_status_pump(simple_layers, initial_status, expected_status):
    pump_layer = layer("linestring", [("name", str), ("pump_type", str), ("power", float), ("initial_status", str)])
    add_line(pump_layer, [(1, 1), (4, 5)], ["PUMP1", "POWER", 10, initial_status])
    simple_layers["PUMPS"] = pump_layer

    wn = gusnet.from_qgis(simple_layers, "LPS", "H-W")

    assert wn.get_link("PUMP1").initial_status.name == expected_status


@pytest.mark.parametrize(
    ("initial_status", "expected_status"), [("OPEN", "Open"), ("CLOSED", "Closed"), (None, "Open")]
)
def test_initial_status_pipe(simple_layers, initial_status, expected_status):
    pipe_layer = layer(
        "linestring", [("name", str), ("diameter", float), ("roughness", float), ("initial_status", str)]
    )
    add_line(pipe_layer, [(1, 1), (4, 5)], ["P1", 1, 1, initial_status])
    simple_layers["PIPES"] = pipe_layer

    wn = gusnet.from_qgis(simple_layers, "LPS", "H-W")

    assert wn.get_link("P1").initial_status.name == expected_status


@pytest.mark.parametrize(
    ("initial_status", "expected_status"),
    [("OPEN", "Open"), ("CLOSED", "Closed"), ("ACTIVE", "Active"), (None, "Active")],
)
def test_initial_status_valve(initial_status, expected_status):
    import wntr

    junction_layer = layer("point", [("name", str), ("elevation", float)])
    add_point(junction_layer, (1, 1), ["J1", 1])
    add_point(junction_layer, (4, 5), ["J2", 1])

    valve_layer = layer(
        "linestring",
        [("name", str), ("diameter", float), ("valve_type", str), ("pressure_setting", float), ("initial_status", str)],
    )
    add_line(valve_layer, [(1, 1), (4, 5)], ["V1", 1, "PRV", 1, initial_status])

    layers = {"JUNCTIONS": junction_layer, "VALVES": valve_layer}

    wn = gusnet.from_qgis(layers, "LPS", "H-W")
    assert wn.get_link("V1").initial_status == wntr.network.base.LinkStatus[expected_status]


def test_inital_status_string_error(simple_layers):
    initial_status = "NOT_A_STATUS"

    valve_layer = layer(
        "linestring",
        [
            ("name", str),
            ("diameter", float),
            ("valve_type", str),
            ("pressure_setting", float),
            ("initial_status", initial_status),
        ],
    )
    add_line(valve_layer, [(1, 1), (4, 5)], ["V1", 1, "PRV", 1, initial_status])
    simple_layers["VALVES"] = valve_layer

    with pytest.raises(gusnet.interface.WntrError, match=initial_status):
        gusnet.from_qgis(simple_layers, "LPS", "H-W")


@pytest.mark.parametrize("initial_status", [1.0, True, False])
def test_inital_status_type_error(simple_layers, initial_status):
    valve_layer = layer(
        "linestring",
        [
            ("name", str),
            ("diameter", float),
            ("valve_type", str),
            ("pressure_setting", float),
            ("initial_status", initial_status),
        ],
    )
    add_line(valve_layer, [(1, 1), (4, 5)], ["V1", 1, "PRV", 1, initial_status])
    simple_layers["VALVES"] = valve_layer

    with pytest.raises(gusnet.interface.WntrError, match="initial_status"):
        gusnet.from_qgis(simple_layers, "LPS", "H-W")


@pytest.fixture
def valve_type():
    return "PRV"


@pytest.fixture
def initial_setting():
    return 100.0


@pytest.fixture
def valve_layers(valve_type, initial_setting):
    junction_layer = layer("point", [("name", str), ("elevation", float)])
    add_point(junction_layer, (1, 1), ["J1", 100])
    add_point(junction_layer, (4, 5), ["J2", 0])

    valve_layer = layer(
        "linestring",
        [
            ("name", str),
            ("valve_type", valve_type),
            ("pressure_setting", initial_setting),
            ("flow_setting", initial_setting),
            ("throttle_setting", initial_setting),
            ("diameter", float),
        ],
    )
    add_line(valve_layer, [(1, 1), (4, 5)], ["V1", valve_type, initial_setting, initial_setting, initial_setting, 10])

    return {"JUNCTIONS": junction_layer, "VALVES": valve_layer}


@pytest.mark.parametrize("valve_type", ["PRV", "PSV", "PBV", "prv"])
def test_pressure_valve_initial_setting_conversion_valves(valve_layers):
    wn = gusnet.from_qgis(valve_layers, "cfs", "H-W")

    assert wn.get_link("V1").initial_setting == pytest.approx(70.3438726)


@pytest.mark.parametrize("valve_type", ["FCV"])
def test_flow_valve_initial_setting_conversion_valves(valve_layers):
    wn = gusnet.from_qgis(valve_layers, "lps", "H-W")

    assert wn.get_link("V1").initial_setting == 0.1


@pytest.mark.parametrize("valve_type", ["tcv"])
def test_tcv_valve_initial_setting(valve_layers):
    wn = gusnet.from_qgis(valve_layers, "cfs", "H-W")

    assert wn.get_link("V1").initial_setting == 100


@pytest.mark.parametrize("valve_type", ["fcv", "prv", "tcv"])
@pytest.mark.parametrize("initial_setting", [None])
def test_valve_no_initial_setting(valve_layers):
    with pytest.raises(gusnet.interface.ValveSettingError):
        gusnet.from_qgis(valve_layers, "cfs", "H-W")


@pytest.mark.parametrize("valve_type", ["FCV", "PRV", "PSV", "PBV", "TCV", "GPV"])
@pytest.mark.parametrize("initial_setting", ["string_type"])
def test_pressure_valve_initial_setting_conversion_valves_bad_values(valve_layers):
    with pytest.raises(gusnet.interface.NetworkModelError, match="pressure_setting"):
        gusnet.from_qgis(valve_layers, "cfs", "H-W")


@pytest.mark.parametrize("valve_type", [None])
def test_valve_type_not_specified(valve_layers):
    with pytest.raises(gusnet.interface.RequiredFieldError, match="valve_type"):
        gusnet.from_qgis(valve_layers, "LPS", "H-W")


@pytest.mark.parametrize("valve_type", ["not_a_valve_type"])
def test_valve_type_wrong_type(valve_layers):
    with pytest.raises(gusnet.interface.ValveTypeError, match="valve_type"):
        gusnet.from_qgis(valve_layers, "LPS", "H-W")


@pytest.mark.parametrize("valve_type", [0, 1, 1.0, True, False])
def test_valve_type_is_number(valve_layers):
    with pytest.raises(gusnet.interface.ValveTypeError, match="valve_type"):
        gusnet.from_qgis(valve_layers, "LPS", "H-W")


def test_pump_with_no_pump_type(simple_layers):
    pump_layer = layer("linestring", [("name", str)])
    add_line(pump_layer, [(1, 1), (4, 5)], ["PUMP1"])
    simple_layers.update({"PUMPS": pump_layer})
    with pytest.raises(gusnet.interface.NetworkModelError, match="pump_type"):
        gusnet.from_qgis(simple_layers, "LPS", "H-W")


@pytest.mark.parametrize("pump_type", ["not_a_type", None, 1, 1.2])
def test_pump_with_wrong_pump_type(simple_layers, pump_type):
    pump_layer = layer("linestring", [("name", str), ("pump_type", pump_type)])
    add_line(pump_layer, [(1, 1), (4, 5)], ["PUMP1", pump_type])
    simple_layers.update({"PUMPS": pump_layer})
    with pytest.raises(gusnet.interface.NetworkModelError, match="pump_type"):
        gusnet.from_qgis(simple_layers, "LPS", "H-W")


def test_power_pump(simple_layers):
    pump_layer = layer("linestring", [("name", str), ("pump_type", str), ("power", float)])
    add_line(pump_layer, [(1, 1), (4, 5)], ["PUMP1", "POWER", 10.1])
    simple_layers.update({"PUMPS": pump_layer})

    wn = gusnet.from_qgis(simple_layers, "LPS", "H-W")

    assert wn.get_link("PUMP1").pump_type == "POWER"
    assert wn.get_link("PUMP1").power == 10100.0


def test_head_pump(simple_layers):
    pump_layer = layer("linestring", [("name", str), ("pump_type", str), ("pump_curve", str)])
    add_line(pump_layer, [(1, 1), (4, 5)], ["PUMP1", "HEAD", "[(0.0, 200.5),(1.0,50)]"])
    simple_layers.update({"PUMPS": pump_layer})

    wn = gusnet.from_qgis(simple_layers, "LPS", "H-W")

    assert wn.get_link("PUMP1").pump_type == "HEAD"
    assert wn.get_link("PUMP1").get_pump_curve().points == [(0.0, 200.5), (0.001, 50)]


def test_head_pump_empty_curve(simple_layers):
    pump_layer = layer("linestring", [("name", str), ("pump_type", str), ("pump_curve", str)])
    add_line(pump_layer, [(1, 1), (4, 5)], ["PUMP1", "HEAD", ""])
    simple_layers.update({"PUMPS": pump_layer})

    with pytest.raises(gusnet.interface.PumpCurveMissingError):
        gusnet.from_qgis(simple_layers, "LPS", "H-W")


def test_head_pump_no_curve(simple_layers):
    pump_layer = layer("linestring", [("name", str), ("pump_type", str)])
    add_line(pump_layer, [(1, 1), (4, 5)], ["PUMP1", "HEAD"])
    simple_layers.update({"PUMPS": pump_layer})

    with pytest.raises(gusnet.interface.PumpCurveMissingError):
        gusnet.from_qgis(simple_layers, "LPS", "H-W")


def test_head_pump_conversion(simple_layers):
    pump_layer = layer("linestring", [("name", str), ("pump_type", str), ("pump_curve", str)])
    add_line(pump_layer, [(1, 1), (4, 5)], ["PUMP1", "HEAD", "[(0.0, 10),(1000.0,50)]"])
    simple_layers.update({"PUMPS": pump_layer})

    wn = gusnet.from_qgis(simple_layers, "GPM", "H-W")

    assert wn.get_link("PUMP1").pump_type == "HEAD"
    assert wn.get_link("PUMP1").get_pump_curve().points == [(0.0, 3.048), (0.0630901964, 15.24)]


def test_pump_mixed_types(simple_layers):
    pump_layer = layer("linestring", [("name", str), ("pump_type", str), ("power", float), ("pump_curve", str)])

    add_line(pump_layer, [(1, 1), (4, 5)], ["PUMP1", "POWER", 10.1, None])
    add_line(pump_layer, [(1, 1), (4, 5)], ["PUMP2", "HEAD", None, "[(0.0, 200.5),(1.0,50)]"])
    simple_layers.update({"PUMPS": pump_layer})

    wn = gusnet.from_qgis(simple_layers, "LPS", "H-W")

    assert wn.get_link("PUMP1").pump_type == "POWER"
    assert wn.get_link("PUMP2").pump_type == "HEAD"

    assert wn.get_link("PUMP1").power == 10100.0
    assert wn.get_link("PUMP2").get_pump_curve().points == [(0.0, 200.5), (0.001, 50.0)]


def test_power_pump_with_no_power(simple_layers):
    pump_layer = layer("linestring", [("name", str), ("pump_type", str)])
    add_line(pump_layer, [(1, 1), (4, 5)], ["PUMP1", "POWER"])
    simple_layers.update({"PUMPS": pump_layer})

    with pytest.raises(gusnet.interface.PumpPowerError):
        gusnet.from_qgis(simple_layers, "LPS", "H-W")


def test_power_pump_with_one_missing_power(simple_layers):
    pump_layer = layer("linestring", [("name", str), ("pump_type", str), ("power", float)])
    add_line(pump_layer, [(1, 1), (4, 5)], ["PUMP1", "POWER", 1])
    add_line(pump_layer, [(1, 1), (4, 5)], ["PUMP2", "POWER"])
    simple_layers.update({"PUMPS": pump_layer})

    with pytest.raises(gusnet.interface.PumpPowerError):
        gusnet.from_qgis(simple_layers, "LPS", "H-W")


@pytest.mark.parametrize("power", ["not_a_number"])
def test_power_pump_with_wrong_power_type(simple_layers, power):
    pump_layer = layer("linestring", [("name", str), ("pump_type", str), ("power", power)])
    add_line(pump_layer, [(1, 1), (4, 5)], ["PUMP1", "POWER", power])
    simple_layers.update({"PUMPS": pump_layer})

    with pytest.raises(gusnet.interface.NetworkModelError, match=str(power)):
        gusnet.from_qgis(simple_layers, "LPS", "H-W")


@pytest.mark.parametrize("power", [0, 0.0, -1])
def test_power_pump_with_wrong_power_value(simple_layers, power):
    pump_layer = layer("linestring", [("name", str), ("pump_type", str), ("power", power)])
    add_line(pump_layer, [(1, 1), (4, 5)], ["PUMP1", "POWER", power])
    simple_layers.update({"PUMPS": pump_layer})

    with pytest.raises(gusnet.interface.PumpPowerError):
        gusnet.from_qgis(simple_layers, "LPS", "H-W")
