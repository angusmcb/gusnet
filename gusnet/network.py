from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from functools import lru_cache
from types import MappingProxyType

from qgis.core import QgsGeometry

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

        self._node_elevations: dict[str, float] = {}
        self._spatial_index: SpatialIndex | None = None

    def add_node_geometries(
        self, names: Iterable[str], geometries: Iterable[QgsGeometry], elevations: Iterable[float] | None
    ) -> None:
        coordinates = (_point_geometry_to_tuple(geom) for geom in geometries)

        if elevations:
            for geometry, elevation in zip(geometries, elevations):
                if elevation is not None:
                    geometry.get().addZValue(elevation)  # type: ignore[union-attr]

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
            _create_line_geometry(node_coord_dict[start], node_coord_dict[end], tuple(middle_vertices))
            if start and end
            else QgsGeometry()
            for start, end, middle_vertices in part_iterator
        ]

        self._add_links(names, vertices, start_nodes, end_nodes, geometries)

    def add_elevations(self, node_elevations: Mapping[str, float]):
        for node_name, node_geom in self._node_geometries.items():
            try:
                node_elevation = node_elevations[node_name]
            except KeyError:
                continue
            node_point = node_geom.get()
            node_point.addZValue(node_elevation)

        for link_name, link_geom in self._link_geometries.items():
            try:
                start_z = node_elevations[self._link_start_nodes[link_name]]
                end_z = node_elevations[self._link_end_nodes[link_name]]
            except KeyError:
                continue
            line_string = link_geom.get()
            line_string.addZValue(start_z)
            line_string.setZAt(-1, end_z)

            total_length = line_string.length()
            gradient = (end_z - start_z) / total_length

            for vertex_id in range(1, line_string.vertexCount() - 1):
                incremental_length = link_geom.distanceToVertex(vertex_id)
                interpolated_z = incremental_length * gradient + start_z
                line_string.setZAt(vertex_id, interpolated_z)

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


@lru_cache(maxsize=10000)
def _point_geometry_to_tuple(geometry: QgsGeometry) -> tuple[float, float]:
    try:
        point = geometry.constGet()
        return (point.x(), point.y())  # type: ignore[union-attr]
    except (AttributeError, TypeError, ValueError):
        return (math.nan, math.nan)


@lru_cache(maxsize=10000)
def _line_geometry_to_vertices(geometry: QgsGeometry) -> list[tuple[float, float]]:
    try:
        if geometry.constGet().vertexCount() < 3:  # type: ignore[union-attr]
            return []
        return [(v.x(), v.y()) for v in geometry.asPolyline()[1:-1]]
    except (TypeError, ValueError):
        return []


@lru_cache(maxsize=10000)
def create_point_geometry(coord: tuple[float, float]) -> QgsGeometry:
    return QgsGeometry.fromWkt(f"POINT ({coord[0]} {coord[1]})")


@lru_cache(maxsize=10000)
def _create_line_geometry(
    start: tuple[float, float], end: tuple[float, float], middle_vertices: tuple[tuple[float, float], ...]
) -> QgsGeometry:
    points = [start, *middle_vertices, end]
    return QgsGeometry.fromWkt(f"LINESTRING ({', '.join(f'{p[0]} {p[1]}' for p in points)})")
