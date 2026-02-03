from qgis.core import QgsGeometry, QgsPoint, QgsPointXY

from gusnet.spatial_index2 import SpatialIndex


def test_spatial_index_add_nodes():
    index = SpatialIndex()
    geometries = [[1, 1], [2, 2], [3, 3]]
    names = ["node1", "node2", "node3"]
    index.add_nodes(geometries, names)
    # Trigger index initialization
    index.snap_links([QgsGeometry.fromPolyline([QgsPoint(1, 1), QgsPoint(2, 2)])])
    assert index._index.num_items == 3


def test_spatial_index_snap_link():
    index = SpatialIndex()
    points = [[1, 1], [2, 2]]
    node_names = ["node1", "node2"]
    index.add_nodes(points, node_names)
    links = [QgsGeometry.fromPolyline([QgsPoint(1, 1), QgsPoint(2, 2)])]
    results = index.snap_links(links)
    assert results[0][0] == "node1"
    assert results[1][0] == "node2"


def test_spatial_index_snap_link_nearby():
    index = SpatialIndex()
    points = [[1, 1], [2, 2]]
    node_names = ["node1", "node2"]
    index.add_nodes(points, node_names)
    geometry = QgsGeometry.fromPolyline([QgsPoint(1.01, 1.01), QgsPoint(1.92, 1.92)])
    links = [geometry]

    results = index.snap_links(links)
    start_node = results[0][0]
    end_node = results[1][0]
    assert start_node == "node1"
    assert end_node == "node2"
    assert geometry.asPolyline() == [QgsPointXY(1, 1), QgsPointXY(2, 2)]


def test_spatial_index_snap_link_far_apart():
    index = SpatialIndex()
    points = [[1, 1], [2, 2]]
    node_names = ["node1", "node2"]
    index.add_nodes(points, node_names)
    links = [QgsGeometry.fromPolyline([QgsPoint(10, 10), QgsPoint(20, 20)])]

    results = index.snap_links(links)
    # snap_links doesn't raise errors - it returns None for unmatched nodes
    start_node = results[0][0]
    end_node = results[1][0]
    # Both endpoints are too far from any node
    assert start_node is None
    assert end_node is None


def test_spatial_index_snap_links():
    index = SpatialIndex()
    points = [[1, 1], [2, 2]]
    node_names = ["node1", "node2"]
    index.add_nodes(points, node_names)
    links = [
        QgsGeometry.fromPolyline([QgsPoint(1, 1), QgsPoint(2, 2)]),
        QgsGeometry.fromPolyline([QgsPoint(1.01, 1.01), QgsPoint(1.92, 1.92)]),
    ]

    results = index.snap_links(links)
    assert len(results[0]) == 2
    for start_node, end_node in zip(*results):
        assert start_node == "node1"
        assert end_node == "node2"


def test_spatial_index_snap_tolerance_short_link():
    """Test that a short link won't snap to a node that's too far away relative to link length."""
    index = SpatialIndex()
    # Default snap_tolerance is 0.1 (10% of link length)
    points = [[0, 0], [100, 0]]
    node_names = ["node1", "node2"]
    index.add_nodes(points, node_names)

    # Create a short link (length = 1.0) with endpoints 0.15 units away from nodes
    # Snap tolerance = 0.1 * 1.0 = 0.1, so 0.15 is too far (beyond sqrt(0.15^2) > 0.1)
    # Actually the tolerance is squared, so we need distance > 0.1 * length = 0.1
    # Let's use 0.5 to be clearly outside tolerance
    links = [QgsGeometry.fromPolyline([QgsPoint(0.5, 0), QgsPoint(1.5, 0)])]
    results = index.snap_links(links)

    # Both endpoints should be None (too far to snap)
    assert results[0][0] is None
    assert results[1][0] is None


def test_spatial_index_snap_tolerance_long_link():
    """Test that a long link can snap to nodes at the same absolute distance."""
    index = SpatialIndex()
    points = [[0, 0], [100, 0]]
    node_names = ["node1", "node2"]
    index.add_nodes(points, node_names)

    # Create a long link (length ≈ 99.6) with endpoints 0.2 units away from nodes
    # Snap tolerance = 0.1 * 99.6 ≈ 9.96, so 0.2 is well within tolerance
    links = [QgsGeometry.fromPolyline([QgsPoint(0.2, 0), QgsPoint(99.8, 0)])]

    results = index.snap_links(links)

    # Both endpoints should snap successfully
    assert results[0][0] == "node1"
    assert results[1][0] == "node2"


def test_spatial_index_snap_tolerance_one_end_too_far():
    """Test that only one endpoint snaps if the other is too far."""
    index = SpatialIndex()
    points = [[0, 0], [10, 0]]
    node_names = ["node1", "node2"]
    index.add_nodes(points, node_names)

    links = [QgsGeometry.fromPolyline([QgsPoint(0.05, 0), QgsPoint(12, 0)])]

    results = index.snap_links(links)

    # Start should snap to node1, end should not snap to any node
    assert results[0][0] == "node1"
    assert results[1][0] is None


def test_spatial_index_snap_with_intermediate_vertices():
    """Test snapping works correctly with links that have intermediate vertices."""
    index = SpatialIndex()
    points = [[0, 0], [10, 0]]
    node_names = ["node1", "node2"]
    index.add_nodes(points, node_names)

    # Create a link with intermediate vertices (zigzag pattern)
    # Total length is longer due to zigzag, so snap tolerance is higher
    geom = QgsGeometry.fromPolyline(
        [
            QgsPoint(0.1, 0),  # Near node1
            QgsPoint(3, 2),  # Intermediate
            QgsPoint(5, -1),  # Intermediate
            QgsPoint(7, 2),  # Intermediate
            QgsPoint(9.9, 0),  # Near node2
        ]
    )
    links = [geom]
    results = index.snap_links(links)

    # Both endpoints should snap
    assert results[0][0] == "node1"
    assert results[1][0] == "node2"

    # Check that intermediate vertices are preserved
    snapped_polyline = geom.asPolyline()
    assert len(snapped_polyline) == 5
    # First and last should be snapped to nodes
    assert snapped_polyline[0] == QgsPointXY(0, 0)
    assert snapped_polyline[-1] == QgsPointXY(10, 0)
    # Intermediate vertices should be unchanged
    assert snapped_polyline[1] == QgsPointXY(3, 2)
    assert snapped_polyline[2] == QgsPointXY(5, -1)
    assert snapped_polyline[3] == QgsPointXY(7, 2)
