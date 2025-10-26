import pytest
from qgis.core import NULL, QgsCoordinateReferenceSystem, QgsProject, QgsVectorLayer

import gusnet


@pytest.fixture
def wn():
    import wntr

    wn = wntr.network.WaterNetworkModel()
    wn.add_junction("J1", base_demand=0.01, elevation=10, coordinates=(1, 1))
    wn.add_junction("J2", base_demand=0.02, elevation=20, coordinates=(2, 2))
    wn.add_reservoir("R1", base_head=10, coordinates=(0, 0))
    wn.add_pipe("P1", "J1", "J2", length=100, diameter=0.3, roughness=100)
    wn.add_pipe("P2", "J2", "R1", length=150, diameter=400, roughness=100)
    return wn


@pytest.fixture
def eps(wn):
    wn.options.time.duration = 3600


@pytest.fixture
def results(wn):
    import wntr

    sim = wntr.sim.EpanetSimulator(wn)
    return sim.run_sim()


def check_values(layer: QgsVectorLayer, field_name: str, expected_values: list):
    """
    Helper function to check if the values in a specific field of a layer's features match the expected values.

    :param layer: QgsVectorLayer to check.
    :param field_name: Name of the field to validate.
    :param expected_values: List of expected values.
    :raises AssertionError: If the field values do not match the expected values.
    """
    assert layer.isValid(), "Layer is not valid."
    assert layer.fields()[field_name], f"Field '{field_name}' does not exist in the layer."

    actual_values = [feature[field_name] for feature in layer.getFeatures()]

    error_message = f"Field '{field_name}' values do not match. Expected: {expected_values}, Actual: {actual_values}"

    for actual, expected in zip(actual_values, expected_values):
        if isinstance(expected, (list, float, int)):
            assert actual == pytest.approx(expected), error_message
        else:
            assert actual == expected, error_message


def test_basic_wn(qgis_new_project, wn):
    layers = gusnet.to_qgis(wn)
    assert isinstance(layers, dict)
    assert isinstance(layers["JUNCTIONS"], QgsVectorLayer)
    assert isinstance(layers["PIPES"], QgsVectorLayer)
    assert len(QgsProject.instance().mapLayers()) == 6
    check_values(layers["JUNCTIONS"], "name", ["J1", "J2"])


def test_empty_wn(qgis_new_project):
    import wntr

    wn = wntr.network.WaterNetworkModel()
    layers = gusnet.to_qgis(wn)
    assert isinstance(layers, dict)
    assert isinstance(layers["JUNCTIONS"], QgsVectorLayer)
    assert len(QgsProject.instance().mapLayers()) == 6
    assert layers["JUNCTIONS"].featureCount() == 0


def test_demand_conversion(wn):
    layers = gusnet.to_qgis(wn, units="LPS")

    check_values(layers["JUNCTIONS"], "base_demand", [10, 20])


def test_results(qgis_new_project, wn, results):
    layers = gusnet.to_qgis(wn, results=results, units="LPS")
    assert len(QgsProject.instance().mapLayers()) == 2
    check_values(layers["NODES"], "demand", [10.0, 20.0, -30.0])
    check_values(layers["LINKS"], "flowrate", [-10.0, -30.0])


def test_eps_results(qgis_new_project, wn, eps, results):
    layers = gusnet.to_qgis(wn, results=results, units="LPS")
    assert len(QgsProject.instance().mapLayers()) == 2
    check_values(layers["NODES"], "demand", [[10.0, 10.0], [20.0, 20.0], [-30.0, -30.0]])
    check_values(layers["LINKS"], "flowrate", [[-10.0, -10.0], [-30.0, -30.0]])


def test_custom_attr_str(wn):
    wn.nodes["J1"].custom_str = "Custom String"
    layers = gusnet.to_qgis(wn)

    check_values(layers["JUNCTIONS"], "custom_str", ["Custom String", NULL])


def test_custom_attr_int(wn):
    wn.nodes["J2"].custom_int = 42
    layers = gusnet.to_qgis(wn)

    check_values(layers["JUNCTIONS"], "custom_int", [NULL, 42])

    field = layers["JUNCTIONS"].fields().field("custom_int")
    assert field.typeName().lower() in ("integer", "int")


def test_custom_attr_float(wn):
    wn.nodes["J1"].custom_float = 3.14
    layers = gusnet.to_qgis(wn)

    check_values(layers["JUNCTIONS"], "custom_float", [3.14, NULL])


def test_custom_attr_bool(wn):
    wn.links["P1"].custom_bool = True
    layers = gusnet.to_qgis(wn)

    check_values(layers["PIPES"], "custom_bool", [True, NULL])


def test_valid_crs_string(wn):
    crs = "EPSG:3857"
    layers = gusnet.to_qgis(wn, crs=crs)

    assert layers["JUNCTIONS"].crs().authid() == crs


def test_valid_crs_object(wn):
    crs = QgsCoordinateReferenceSystem("EPSG:3857")
    layers = gusnet.to_qgis(wn, crs=crs)
    assert isinstance(layers, dict)
    assert "JUNCTIONS" in layers
    assert layers["JUNCTIONS"].crs().authid() == crs.authid()


def test_invalid_crs_string(wn):
    crs = "INVALID_CRS"
    with pytest.raises(ValueError, match=f"CRS {crs} is not valid."):
        gusnet.to_qgis(wn, crs=crs)


def test_invalid_crs_object(wn):
    crs = QgsCoordinateReferenceSystem("INVALID_CRS")
    with pytest.raises(ValueError, match="is not valid."):
        gusnet.to_qgis(wn, crs=crs)


def test_default_crs(wn):
    layers = gusnet.to_qgis(wn)
    assert isinstance(layers, dict)
    assert "JUNCTIONS" in layers
    assert layers["JUNCTIONS"].crs().isValid() is False


def test_no_crs(wn):
    layers = gusnet.to_qgis(wn, crs=None)
    assert isinstance(layers, dict)
    assert "JUNCTIONS" in layers
    assert layers["JUNCTIONS"].crs().isValid() is False


def test_demand_pattern(wn):
    wn.add_pattern("P1", [0.5, 1.0, 1.5])
    wn.add_junction("J3", base_demand=0.01, demand_pattern="P1")

    layers = gusnet.to_qgis(wn)

    check_values(layers["JUNCTIONS"], "demand_pattern", [NULL, NULL, "0.5 1.0 1.5"])


def test_head_pattern(wn):
    wn.add_pattern("H1", [10, 20, 30])
    wn.add_reservoir("R2", base_head=10, head_pattern="H1")
    layers = gusnet.to_qgis(wn)

    check_values(layers["RESERVOIRS"], "head_pattern", [NULL, "10.0 20.0 30.0"])


def test_vol_curve(wn):
    wn.add_curve("C1", "VOLUME", [(0, 0), (10, 10), (20, 20)])
    wn.add_tank("T1", vol_curve="C1")
    layers = gusnet.to_qgis(wn)

    check_values(
        layers["TANKS"],
        "vol_curve",
        ["[(0.0, 0.0), (32.808398950131235, 353.14666721488584), (65.61679790026247, 706.2933344297717)]"],
    )


def test_pump_curve(wn):
    wn.add_curve("C1", "HEAD", [(0, 0), (10, 10), (20, 20)])
    wn.add_pump("PUMP1", "J1", "J2", pump_type="head", pump_parameter="C1")
    layers = gusnet.to_qgis(wn, units="LPS")

    check_values(layers["PUMPS"], "pump_curve", ["[(0.0, 0.0), (10000.0, 10.0), (20000.0, 20.0)]"])


def test_speed_pattern(wn):
    wn.add_pattern("S1", [0.5, 1.0, 1.5])
    wn.add_pump("PUMP1", "J1", "J2", pattern="S1")
    layers = gusnet.to_qgis(wn)

    check_values(layers["PUMPS"], "speed_pattern", ["0.5 1.0 1.5"])


def test_energy_pattern(wn):
    wn.add_pattern("E1", [0.5, 1.0, 1.5])
    wn.add_pump("PUMP1", "J1", "J2")
    wn.links["PUMP1"].energy_pattern = "E1"

    layers = gusnet.to_qgis(wn)

    check_values(layers["PUMPS"], "energy_pattern", ["0.5 1.0 1.5"])


def test_efficiency_curve(wn):
    wn.add_curve("C1", "EFFICIENCY", [(0, 0), (10, 0.5), (20, 1)])
    wn.add_pump("PUMP1", "J1", "J2")

    try:  # wntr <= 1.3
        wn.links["PUMP1"].efficiency = wn.curves["C1"]

        layers = gusnet.to_qgis(wn, units="LPS")  # check efficiency doesn't crash the export

    except AttributeError:
        wn.links["PUMP1"].efficiency_curve_name = "C1"

        layers = gusnet.to_qgis(wn, units="LPS")

        check_values(layers["PUMPS"], "efficiency_curve", ["[(0.0, 0), (10000.0, 0.5), (20000.0, 1)]"])


def test_valve_active(wn):
    wn.add_valve("v1", "J1", "J2")
    layers = gusnet.to_qgis(wn)

    check_values(layers["VALVES"], "valve_status", ["Active"])


@pytest.mark.parametrize("valve_type", ["PRV", "PSV", "PBV"])
def test_p_valve_setting(wn, valve_type):
    wn.add_valve("v1", "J1", "J2", valve_type=valve_type, initial_setting=10)

    layers = gusnet.to_qgis(wn)

    check_values(layers["VALVES"], "pressure_setting", [14.21588])


def test_flow_valve_setting(wn):
    wn.add_valve("v1", "J1", "J2", valve_type="FCV", initial_setting=10)

    layers = gusnet.to_qgis(wn, units="CMH")

    check_values(layers["VALVES"], "flow_setting", [10.0 * 3600])


def test_gpv_curve(wn):
    wn.add_curve("C1", "HEADLOSS", [(0, 0), (10, 10), (20, 20)])
    wn.add_valve("v1", "J1", "J2", valve_type="GPV", initial_setting="C1")

    layers = gusnet.to_qgis(wn, units="lps")

    check_values(layers["VALVES"], "headloss_curve", ["[(0.0, 0.0), (10000.0, 10.0), (20000.0, 20.0)]"])


def test_tcv_setting(wn):
    wn.add_valve("v1", "J1", "J2", valve_type="TCV", initial_setting=10)

    layers = gusnet.to_qgis(wn)

    check_values(layers["VALVES"], "throttle_setting", [10.0])


def test_unit_warning(wn, caplog):
    gusnet.to_qgis(wn)

    expected_warning = "No units specified. Will use the value from wn: Gallons per Minute"
    assert expected_warning in caplog.messages
