from __future__ import annotations

from typing import TYPE_CHECKING

from qgis.core import QgsGeometry, QgsPointXY, QgsSpatialIndex

from gusnet.i18n import tr

if TYPE_CHECKING:  # pragma: no cover
    import pandas as pd


class SpatialIndex:
    snap_tolerance = 0.1

    def __init__(self) -> None:
        self._node_spatial_index = QgsSpatialIndex()
        self._nodelist: list[tuple[QgsPointXY, str]] = []

    def add_node(self, geometry: QgsGeometry, element_name: str) -> None:
        "Add a node to the spatial index."

        point = geometry.asPoint()
        feature_id = len(self._nodelist)
        self._nodelist.append((point, element_name))
        self._node_spatial_index.addFeature(feature_id, geometry.boundingBox())

    def add_nodes(self, geometries: pd.Series, names: pd.Series) -> None:
        """Add nodes from pandas series to the spatial index."""

        for geometry, element_name in zip(geometries, names):
            self.add_node(geometry, element_name)

    def snap_links(self, geometries: pd.Series, names: pd.Series) -> list[tuple[QgsGeometry, str, str]]:
        """Snap the start and end points of links to the nearest nodes in the spatial index.

        Returns:
            list: A list of tuples containing the snapped geometry, start node name, and end node name.
        """
        return [self.snap_link(*data) for data in zip(geometries, names)]

    def snap_link(self, geometry: QgsGeometry, link_name: str = "") -> tuple[QgsGeometry, str, str]:
        """Snap the start and end points of a link to the nearest node in the spatial index.

        Returns:
            tuple: A tuple containing the snapped geometry, start node name, and end node name."""
        try:
            vertices = geometry.asPolyline()
        except TypeError:
            msg = tr("All links must be single part lines")
            raise SnapError(msg) from None
        except ValueError:
            msg = tr("All links must have valid geometry")
            raise SnapError(msg) from None

        start_point = vertices.pop(0)
        end_point = vertices.pop()
        original_length = geometry.length()

        new_start_point, start_node_name = self._snapper(start_point, original_length, link_name)
        new_end_point, end_node_name = self._snapper(end_point, original_length, link_name)

        if start_node_name == end_node_name:
            raise SnapSameNodeError(link_name, start_node_name)

        snapped_geometry = QgsGeometry.fromPolylineXY([new_start_point, *vertices, new_end_point])

        return snapped_geometry, start_node_name, end_node_name

    def _snapper(self, line_vertex_point: QgsPointXY, original_length: float, link_name: str) -> tuple[QgsPointXY, str]:
        nearest = self._node_spatial_index.nearestNeighbor(line_vertex_point)
        matched_node_point, matched_node_name = self._nodelist[nearest[0]]

        snap_distance = matched_node_point.distance(line_vertex_point)
        if snap_distance > original_length * self.snap_tolerance:
            raise SnapTooFarError(link_name, matched_node_name)

        return matched_node_point, matched_node_name


class SnapError(Exception):
    """Custom exception for snapping errors in the spatial index."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class SnapTooFarError(SnapError):
    """Custom exception for snapping errors when the node is too far away."""

    def __init__(self, link_name: str, closest_node: str) -> None:
        message = tr("For the link '{link_name}', the closest node ({node_name}) is too far away to snap to.").format(
            link_name=link_name, node_name=closest_node
        )
        super().__init__(message)


class SnapSameNodeError(SnapError):
    """Custom exception for snapping errors when the start and end nodes are the same."""

    def __init__(self, link_name: str, node_name: str) -> None:
        message = tr("The link '{link_name}' connects to the same node on both ends ({node_name}).").format(
            link_name=link_name, node_name=node_name
        )
        super().__init__(message)
