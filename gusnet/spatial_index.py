from __future__ import annotations

from collections.abc import Iterable

from qgis.core import (
    QgsAbstractFeatureIterator,
    QgsFeature,
    QgsFeatureIterator,
    QgsFeatureRequest,
    QgsGeometry,
    QgsLineString,
    QgsPointXY,
    QgsSpatialIndex,
)

from gusnet.i18n import tr


class SpatialIndex:
    snap_tolerance = 0.1

    def __init__(self) -> None:
        self._node_spatial_index = QgsSpatialIndex()
        self._nodelist: list[tuple[QgsPointXY, str]] = []
        self._node_names: tuple[str, ...] = ()
        self._node_coordinates: tuple[tuple[float, float], ...] = ()

    def add_node(self, geometry: QgsGeometry, element_name: str) -> None:
        "Add a node to the spatial index."

        point = geometry.asPoint()
        feature_id = len(self._nodelist)
        self._nodelist.append((point, element_name))
        self._node_spatial_index.addFeature(feature_id, geometry.boundingBox())

    def add_nodes(self, names: Iterable[str], geometries: Iterable[tuple[float, float]]) -> None:
        """Add nodes from pandas series to the spatial index."""

        # for i, (x, y) in enumerate(geometries, start=len(self._node_coordinates)):
        #     self._node_spatial_index.addFeature(i, QgsRectangle(x, y, x, y))

        #     next_index = 0

        # features = []

        # for i, geometry in enumerate(geometries, start=len(self._node_coordinates)):
        #     f = QgsFeature(i)
        #     f.setGeometry(QgsGeometry.fromWkt(f"POINT ({geometry[0]} {geometry[1]})"))
        #     features.append(f)

        # # Add all features at once
        # vl = QgsVectorLayer("Point", "temp", "memory")
        # vl.dataProvider().addFeatures(features)
        # self._node_spatial_index = QgsSpatialIndex(vl)

        fi = FeatureIterator(QgsFeatureRequest())
        fi.set_geometries([QgsGeometry.fromWkt(f"POINT ({x} {y})") for x, y in geometries])
        qfi = QgsFeatureIterator(fi)
        self._node_spatial_index = QgsSpatialIndex(qfi)

        self._node_names += tuple(names)
        self._node_coordinates += tuple(geometries)

    def snap_links(self, geometries: Iterable[QgsGeometry]) -> tuple[tuple, ...]:
        """Snap the start and end points of links to the nearest nodes in the spatial index.

        Returns:
            tuple: (snapped_geometries, start_node_names, end_node_names) as separate lists.
        """

        results = [self.snap_link_2(data) for data in geometries]
        return tuple(zip(*results))

    def snap_link(self, geometry: QgsGeometry, link_name: str = "") -> tuple[QgsGeometry, str, str]:
        """Snap the start and end points of a link to the nearest node in the spatial index.

        Returns:
            tuple: A tuple containing the snapped geometry, start node name, and end node name."""

        vertices = geometry.asPolyline()

        start_point = vertices.pop(0)
        end_point = vertices.pop()
        original_length = geometry.length()

        new_start_point, start_node_name = self._snapper(start_point, original_length, link_name)
        new_end_point, end_node_name = self._snapper(end_point, original_length, link_name)

        snapped_geometry = QgsGeometry.fromPolylineXY([new_start_point, *vertices, new_end_point])

        return snapped_geometry, start_node_name, end_node_name

    def snap_link_2(self, geometry: QgsGeometry) -> tuple[str | None, str | None]:
        linestring = geometry.constGet()
        if not (isinstance(linestring, QgsLineString)):
            return None, None

        start_point = (linestring.xAt(0), linestring.yAt(0))
        end_point = (linestring.xAt(-1), linestring.yAt(-1))

        max_length = geometry.length() * self.snap_tolerance

        new_start_point, start_node_name = self._snapper2(start_point, max_length)
        new_end_point, end_node_name = self._snapper2(end_point, max_length)

        if new_start_point:
            linestring.setXAt(0, new_start_point[0])
            linestring.setYAt(0, new_start_point[1])
        if new_end_point:
            linestring.setXAt(-1, new_end_point[0])
            linestring.setYAt(-1, new_end_point[1])

        return start_node_name, end_node_name

    def _snapper(self, line_vertex_point: QgsPointXY, original_length: float, link_name: str) -> tuple[QgsPointXY, str]:
        nearest = self._node_spatial_index.nearestNeighbor(line_vertex_point)
        matched_node_point, matched_node_name = self._nodelist[nearest[0]]

        snap_distance = matched_node_point.distance(line_vertex_point)
        if snap_distance > original_length * self.snap_tolerance:
            raise SnapTooFarError(link_name, matched_node_name)

        return matched_node_point, matched_node_name

    def _snapper2(
        self, point: tuple[float, float], max_snap_length: float
    ) -> tuple[tuple[float, float], str] | tuple[None, None]:
        nearest = self._node_spatial_index.nearestNeighbor(QgsPointXY(point[0], point[1]), 1, max_snap_length)
        if not nearest:
            return None, None
        nearest_point = self._node_coordinates[nearest[0]]

        distance = ((nearest_point[0] - point[0]) ** 2 + (nearest_point[1] - point[1]) ** 2) ** 0.5

        if distance > max_snap_length:
            return None, None

        return self._node_coordinates[nearest[0]], self._node_names[nearest[0]]


class FeatureIterator(QgsAbstractFeatureIterator):
    def close(self):
        pass

    def rewind(self):
        pass

    def fetchFeature(self, f: QgsFeature):  # noqa: N802
        try:
            idx, geom = next(self._geometry_iter)
            f.setId(idx)
            f.setGeometry(geom)
        except StopIteration:
            return False
        return True

    def set_geometries(self, geometries: Iterable[QgsGeometry]):
        self._geometries = geometries
        self._geometry_iter = enumerate(geometries)


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
