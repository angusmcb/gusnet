from __future__ import annotations

import math
from collections.abc import Iterable
from types import MappingProxyType
from typing import cast

from qgis.core import QgsGeometry, QgsPoint, QgsPointXY

from gusnet.spatial_index import SpatialIndex


class Network:
    """Stores the network/geometry aspects of a model- geometries and linkages

    Always add all node geometries before link geometries.

    Do not write/edit directly the exposed properties - use the provided methods."""

    def __init__(self) -> None:
        self._node_coordinates: dict[str, tuple[float, float]] = {}
        self._node_geometries: dict[str, QgsGeometry] = {}
        self._link_geometries: dict[str, QgsGeometry] = {}
        self._link_middle_vertices: dict[str, list[tuple[float, float]]] = {}
        self._link_start_nodes: dict[str, str] = {}
        self._link_end_nodes: dict[str, str] = {}

        self.node_coordinates = MappingProxyType(self._node_coordinates)
        self.node_geometries = MappingProxyType(self._node_geometries)
        self.link_geometries = MappingProxyType(self._link_geometries)
        self.link_middle_vertices = MappingProxyType(self._link_middle_vertices)
        self.link_start_nodes = MappingProxyType(self._link_start_nodes)
        self.link_end_nodes = MappingProxyType(self._link_end_nodes)

        self._spatial_index: SpatialIndex | None = None

    def add_node_geometries(self, names: Iterable[str], geometries: Iterable[QgsGeometry]) -> None:
        coordinates = (_point_geometry_to_tuple(geom) for geom in geometries)

        self._add_nodes(names, coordinates, geometries)

    def add_link_geometries(self, names: Iterable[str], geometries: Iterable[QgsGeometry]) -> None:
        spatial_index = self._get_spatial_index()

        start_node, end_node = spatial_index.snap_links(geometries)
        middle_vertices = (_line_geometry_to_vertices(geom) for geom in geometries)

        self._add_links(names, middle_vertices, start_node, end_node, geometries)

    def add_nodes_from_points(self, names: Iterable[str], points: Iterable[tuple[float, float]]) -> None:
        geometries = (create_point_geometry(point) for point in points)

        self._add_nodes(names, points, geometries)

    def add_links_from_nodes_and_vertices(
        self,
        names: Iterable[str],
        start_nodes: Iterable[str],
        end_nodes: Iterable[str],
        vertices: Iterable[list[tuple[float, float]]],
    ) -> None:
        """Using start node, end node and middle vertices create geometries"""

        node_coord_dict = self.node_coordinates

        try:
            part_iterator = zip(start_nodes, end_nodes, vertices, strict=True)
        except TypeError:  # python 3.9
            part_iterator = zip(start_nodes, end_nodes, vertices)

        geometries = [
            _create_line_geometry(node_coord_dict[start], node_coord_dict[end], middle_vertices)
            if start and end
            else QgsGeometry()
            for start, end, middle_vertices in part_iterator
        ]

        self._add_links(names, vertices, start_nodes, end_nodes, geometries)

    def _add_nodes(
        self, names: Iterable[str], coordinates: Iterable[tuple[float, float]], geometeries: Iterable[QgsGeometry]
    ) -> None:
        try:
            self._node_coordinates.update(zip(names, coordinates, strict=True))
            self._node_geometries.update(zip(names, geometeries, strict=True))
        except TypeError:  # python 3.9
            self._node_coordinates.update(zip(names, coordinates))
            self._node_geometries.update(zip(names, geometeries))
        self._spatial_index = None

    def _add_links(
        self,
        names: Iterable[str],
        middle_vertices: Iterable[list[tuple[float, float]]],
        start_node: Iterable[str],
        end_node: Iterable[str],
        geometries: Iterable[QgsGeometry],
    ) -> None:
        try:
            self._link_start_nodes.update(zip(names, start_node, strict=True))
            self._link_end_nodes.update(zip(names, end_node, strict=True))
            self._link_middle_vertices.update(zip(names, middle_vertices, strict=True))
            self._link_geometries.update(zip(names, geometries, strict=True))
        except TypeError:  # python 3.9
            self._link_start_nodes.update(zip(names, start_node))
            self._link_end_nodes.update(zip(names, end_node))
            self._link_middle_vertices.update(zip(names, middle_vertices))
            self._link_geometries.update(zip(names, geometries))

    def _get_spatial_index(self) -> SpatialIndex:
        if not self._spatial_index:
            self._spatial_index = SpatialIndex()
            self._spatial_index.add_nodes(
                *zip(*(point for point in self._node_coordinates.items() if point[1] != (math.nan, math.nan)))
            )

        return self._spatial_index


def _point_geometry_to_tuple(geometry: QgsGeometry) -> tuple[float, float]:
    try:
        point = geometry.constGet()
        point = cast(QgsPoint, point)
        return (point.x(), point.y())
    except (AttributeError, TypeError, ValueError):
        return (math.nan, math.nan)


def create_point_geometry(coord: tuple[float, float]) -> QgsGeometry:
    return QgsGeometry.fromWkt(f"POINT ({coord[0]} {coord[1]})")


def _line_geometry_to_vertices(geometry: QgsGeometry) -> list[tuple[float, float]]:
    try:
        return [(v.x(), v.y()) for v in geometry.asPolyline()[1:-1]]
    except (TypeError, ValueError):
        return []


def _create_line_geometry(
    start: tuple[float, float], end: tuple[float, float], middle_vertices: Iterable[tuple[float, float]]
) -> QgsGeometry:
    points = [QgsPointXY(p[0], p[1]) for p in [start, *middle_vertices, end]]
    return QgsGeometry.fromPolylineXY(points)
