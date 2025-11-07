import pytest
from qgis.core import QgsFields, QgsVectorLayer

import gusnet.elements
from gusnet.interface import (
    NetworkModelError,
    Writer,
    check_network,
    options_from_wn,
)


@pytest.fixture
def wn():
    import wntr

    return wntr.network.WaterNetworkModel()


@pytest.fixture
def qgs_layer():
    return QgsVectorLayer("Point", "test_layer", "memory")


def test_writer_get_qgsfields(wn):
    writer = Writer(wn)
    fields = writer.get_qgsfields(gusnet.elements.ModelLayer.JUNCTIONS)
    assert isinstance(fields, QgsFields)


def test_writer_write(wn, qgs_layer):
    wn.add_junction("J1", base_demand=0.01, elevation=10)
    wn.add_junction("J2", base_demand=0.02, elevation=20)
    wn.add_pipe("P1", "J1", "J2", length=100, diameter=0.3, roughness=100)

    writer = Writer(wn)
    sink = qgs_layer.dataProvider()
    writer.write(gusnet.elements.ModelLayer.JUNCTIONS, sink)
    assert sink.featureCount() > 0


def test_writer_write_no_features(wn, qgs_layer):
    writer = Writer(wn)
    sink = qgs_layer.dataProvider()
    writer.write(gusnet.elements.ModelLayer.JUNCTIONS, sink)
    assert sink.featureCount() == 0


def test_check_network_empty_model(wn):
    with pytest.raises(NetworkModelError, match="The model is empty, no nodes or links found"):
        check_network(wn)


def test_check_network_no_junctions(wn):
    wn.add_tank("t1")
    wn.add_reservoir("r1")
    with pytest.raises(NetworkModelError, match="At least one junction is necessary"):
        check_network(wn)


def test_check_network_no_tanks_or_reservoirs(wn):
    wn.add_junction("j1")
    wn.add_junction("j2")
    wn.add_pipe("p1", "j1", "j2")
    with pytest.raises(NetworkModelError, match="At least one tank or reservoir is required"):
        check_network(wn)


def test_check_network_no_links(wn):
    wn.add_junction("j1")
    wn.add_junction("j2")
    wn.add_tank("t1")
    with pytest.raises(NetworkModelError, match=r"At least one link \(pipe, pump or valve\) is necessary"):
        check_network(wn)


def test_check_network_orphan_nodes(wn):
    wn.add_junction("j1")
    wn.add_junction("j2")
    wn.add_tank("t1")
    wn.add_pipe("p1", "j1", "j2")
    with pytest.raises(NetworkModelError, match="the following nodes are not connected to any links: t1"):
        check_network(wn)


def test_check_network_valid(wn):
    wn.add_junction("j1")
    wn.add_junction("j2")
    wn.add_tank("t1")
    wn.add_pipe("p1", "j1", "j2")
    wn.add_pipe("p2", "j2", "t1")
    try:
        check_network(wn)
    except NetworkModelError:
        pytest.fail("check_network raised NetworkModelError unexpectedly!")


def test_get_field_groups(wn):
    from gusnet.elements import DefaultOptions, FieldGroup

    assert gusnet.interface._get_field_groups(DefaultOptions()) == FieldGroup(0)

    wn.options.quality.parameter = "CHEMICAL"
    wn.options.report.energy = "YES"
    wn.options.hydraulic.demand_model = "PDD"

    options = options_from_wn(wn)

    field_groups = gusnet.interface._get_field_groups(options)

    assert field_groups == FieldGroup.PRESSURE_DEPENDENT_DEMAND | FieldGroup.ENERGY | FieldGroup.WATER_QUALITY_ANALYSIS
