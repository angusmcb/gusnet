import pytest
from qgis.core import QgsGeometry, QgsPoint, QgsPointXY

from gusnet.spatial_index import SnapTooFarError, SpatialIndex


def test_spatial_index_add_node():
    index = SpatialIndex()
    geometry = QgsGeometry(QgsPoint(1, 1))
    index.add_node(geometry, "node1")
    assert len(index._nodelist) == 1


def test_spatial_index_snap_link():
    index = SpatialIndex()
    geometry = QgsGeometry.fromPolyline([QgsPoint(1, 1), QgsPoint(2, 2)])
    index.add_node(QgsGeometry(QgsPoint(1, 1)), "node1")
    index.add_node(QgsGeometry(QgsPoint(2, 2)), "node2")
    snapped_geometry, start_node, end_node = index.snap_link(geometry)
    assert start_node == "node1"
    assert end_node == "node2"


def test_spatial_index_snap_link_nearby():
    index = SpatialIndex()
    index.add_node(QgsGeometry(QgsPoint(1, 1)), "node1")
    index.add_node(QgsGeometry(QgsPoint(2, 2)), "node2")
    geometry = QgsGeometry.fromPolyline([QgsPoint(1.01, 1.01), QgsPoint(1.92, 1.92)])
    snapped_geometry, start_node, end_node = index.snap_link(geometry)
    assert start_node == "node1"
    assert end_node == "node2"
    assert snapped_geometry.asPolyline() == [QgsPointXY(1, 1), QgsPointXY(2, 2)]


def test_spatial_index_snap_link_far_apart():
    index = SpatialIndex()
    index.add_node(QgsGeometry(QgsPoint(1, 1)), "node1")
    index.add_node(QgsGeometry(QgsPoint(2, 2)), "node2")
    geometry = QgsGeometry.fromPolyline([QgsPoint(10, 10), QgsPoint(20, 20)])
    with pytest.raises(SnapTooFarError, match="node2"):
        index.snap_link(geometry)


# def test_spatial_index_snap_link_multi_part():
#     index = SpatialIndex()
#     index.add_node(QgsGeometry(QgsPoint(1, 1)), "node1")
#     index.add_node(QgsGeometry(QgsPoint(2, 2)), "node2")
#     geometry = QgsGeometry.fromMultiPolylineXY(
#         [[QgsPointXY(1, 1), QgsPointXY(2, 2)], [QgsPointXY(3, 3), QgsPointXY(4, 4)]]
#     )
#     with pytest.raises(SnapError, match="All links must be single part lines"):
#         index.snap_link(geometry)


# def test_spatial_index_snap_link_invalid_geometry():
#     index = SpatialIndex()
#     index.add_node(QgsGeometry(QgsPoint(1, 1)), "node1")
#     index.add_node(QgsGeometry(QgsPoint(2, 2)), "node2")
#     geometry = QgsGeometry()  # Invalid geometry
#     with pytest.raises(SnapError, match="All links must have valid geometry"):
#         index.snap_link(geometry)


def test_spatial_index_add_nodes():
    index = SpatialIndex()
    geometries = [
        QgsGeometry(QgsPoint(1, 1)),
        QgsGeometry(QgsPoint(2, 2)),
        QgsGeometry(QgsPoint(3, 3)),
    ]
    names = ["node1", "node2", "node3"]
    index.add_nodes(geometries, names)
    assert len(index._nodelist) == 3
    assert index._nodelist[0][1] == "node1"
    assert index._nodelist[1][1] == "node2"
    assert index._nodelist[2][1] == "node3"


def test_spatial_index_snap_links():
    index = SpatialIndex()
    index.add_node(QgsGeometry(QgsPoint(1, 1)), "node1")
    index.add_node(QgsGeometry(QgsPoint(2, 2)), "node2")
    links = [
        QgsGeometry.fromPolyline([QgsPoint(1, 1), QgsPoint(2, 2)]),
        QgsGeometry.fromPolyline([QgsPoint(1.01, 1.01), QgsPoint(1.92, 1.92)]),
    ]
    names = ["link1", "link2"]
    results = index.snap_links(links, names)
    assert len(results) == 2
    for snapped_geometry, start_node, end_node in results:  # noqa: B007
        assert start_node == "node1"
        assert end_node == "node2"
