import math

from gusnet.network import Network


def test_add_z():
    n = Network()
    n.add_nodes_from_points(["1", "2"], [(0, 0), (1, 1)])
    n.add_links_from_nodes_and_vertices(["l1"], ["1"], ["2"], [[]])

    n.add_elevations({"1": 10, "2": 20})

    assert n.node_geometries["1"].constGet().z() == 10
    assert n.node_geometries["2"].constGet().z() == 20

    assert n.link_geometries["l1"].constGet().zAt(0) == 10
    assert n.link_geometries["l1"].constGet().zAt(1) == 20


def test_add_z_with_middle_vertices():
    n = Network()
    n.add_nodes_from_points(["1", "2"], [(0, 0), (1, 1)])
    n.add_links_from_nodes_and_vertices(["l1"], ["1"], ["2"], [[(0, 1)]])

    n.add_elevations({"1": 10, "2": 20})

    assert n.node_geometries["1"].constGet().z() == 10
    assert n.node_geometries["2"].constGet().z() == 20

    assert n.link_geometries["l1"].constGet().zAt(0) == 10
    assert n.link_geometries["l1"].constGet().zAt(2) == 20

    assert n.link_geometries["l1"].constGet().zAt(1) == 15


def test_add_z_with_missing_values():
    n = Network()
    n.add_nodes_from_points(["1", "2", "3"], [(0, 0), (1, 1), (2, 2)])
    n.add_links_from_nodes_and_vertices(["l1", "l2"], ["1", "2"], ["2", "3"], [[(0, 1)], []])

    n.add_elevations({"1": 10, "2": 20})

    assert n.node_geometries["1"].constGet().z() == 10
    assert n.node_geometries["2"].constGet().z() == 20
    assert math.isnan(n.node_geometries["3"].constGet().z())

    assert n.link_geometries["l1"].constGet().zAt(0) == 10
    assert n.link_geometries["l1"].constGet().zAt(2) == 20

    assert n.link_geometries["l1"].constGet().zAt(1) == 15

    assert math.isnan(n.link_geometries["l2"].constGet().zAt(0))


# def test_add_m_with_middle_vertices():
#     n = Network()
#     n.add_nodes_from_points(["1", "2"], [(0, 0), (1, 1)])
#     n.add_links_from_nodes_and_vertices(["l1"], ["1"], ["2"], [[(0, 1)]])

#     n.add_measure({"1": 10, "2": 20})

#     assert n.node_geometries["1"].constGet().m() == 10
#     assert n.node_geometries["2"].constGet().m() == 20

#     assert n.link_geometries["l1"].constGet().mAt(0) == 10
#     assert n.link_geometries["l1"].constGet().mAt(2) == 20

#     assert n.link_geometries["l1"].constGet().mAt(1) == 15
