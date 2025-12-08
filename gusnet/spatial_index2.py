from __future__ import annotations

from collections.abc import Sequence
from typing import cast

import numpy as np
import numpy.typing as npt


class NearestNeighborIndex:
    """Fast vectorized nearest neighbor search using NumPy brute-force approach.

    Uses float64 for coordinates, providing sub-millimeter precision even with
    large coordinate values (e.g., projected coordinate systems).
    """

    def __init__(self, points: npt.ArrayLike, ids: Sequence[str] | None = None) -> None:
        """
        Create an index from a set of points.

        Args:
            points: Nx2 array of coordinates [[x1, y1], [x2, y2], ...]
            ids: Optional list/array of string IDs for each point (default: integer indices)
        """
        self.dtype = np.float64

        points = np.asarray(points, dtype=self.dtype)
        if points.ndim != 2 or points.shape[1] != 2:
            msg = "points must be Nx2 array"
            raise ValueError(msg)

        self.num_items = len(points)

        # Choose index dtype based on number of items
        self.index_dtype = np.uint16 if self.num_items < 65536 else np.uint32

        # Store points as Nx2 array
        self.coords = points

        # Store IDs - either provided strings or integer indices
        if ids is not None:
            ids_array = np.asarray(ids, dtype=object)
            if len(ids_array) != self.num_items:
                msg = f"ids length ({len(ids_array)}) must match points length ({self.num_items})"
                raise ValueError(msg)
            self.ids: npt.NDArray[np.object_] = ids_array
            self.has_string_ids = True
        else:
            self.ids = np.arange(self.num_items, dtype=self.index_dtype)  # type: ignore[assignment]
            self.has_string_ids = False

        # Internal integer indices for lookups
        self._indices = np.arange(self.num_items, dtype=self.index_dtype)

    def nearest(self, qx: float, qy: float, max_distance: float | None = None) -> tuple:
        """
        Find the nearest point using brute-force vectorized NumPy operations.

        Args:
            qx, qy: Query point coordinates
            max_distance: Optional maximum search distance (None = unlimited)

        Returns:
            tuple of (id, distance, x, y) or (None, None, None, None) if not found
            id is a string if IDs were provided during initialization, otherwise an integer
        """
        # Direct computation for single query (more efficient than batching)
        dx = self.coords[:, 0] - qx
        dy = self.coords[:, 1] - qy
        dist_sq = dx * dx + dy * dy

        min_idx = int(np.argmin(dist_sq))
        min_dist_sq = dist_sq[min_idx]

        # Check distance constraint if specified
        if max_distance is not None and min_dist_sq > max_distance**2:
            return (None, None, None, None)

        # Get the ID, distance, and coordinates
        result_id = self.ids[min_idx]
        dist = float(np.sqrt(min_dist_sq))
        result_id_converted = result_id if self.has_string_ids else int(result_id)
        x, y = float(self.coords[min_idx, 0]), float(self.coords[min_idx, 1])
        return (result_id_converted, dist, x, y)

    def nearest_batch(
        self,
        query_points: npt.ArrayLike,
        max_distance_sq: npt.ArrayLike,
    ) -> tuple[npt.NDArray[np.object_], npt.NDArray[np.float64]]:
        """
        Find the single nearest neighbor for multiple query points at once.
        Uses fully vectorized implementation for efficiency.

        Args:
            query_points: Nx2 array of query coordinates [[x1, y1], [x2, y2], ...]
            max_distance_sq: Array of maximum SQUARED search distances (length must match query_points)

        Returns:
            tuple of (ids, coords) where:
                ids: array of IDs (strings if provided, otherwise integers). None for not found.
                coords: Nx2 float64 array of matched coordinates, [nan, nan] for not found
        """
        query_points = np.asarray(query_points, dtype=self.dtype)
        if query_points.ndim != 2 or query_points.shape[1] != 2:
            msg = "query_points must be Nx2 array"
            raise ValueError(msg)

        n_queries = len(query_points)

        # Memory threshold: use vectorized approach if result matrix < ~100MB
        # (n_queries * n_points * 8 bytes for float64)
        memory_threshold = 100_000_000  # 100 MB
        matrix_size = n_queries * self.num_items * 8

        if matrix_size < memory_threshold:
            # Fully vectorized approach for small-to-medium cases
            # Compute squared distances directly without intermediate diff array
            # Broadcasting: (n_queries, 1) - (1, n_points) = (n_queries, n_points)
            dx = query_points[:, 0:1] - self.coords[:, 0]
            dy = query_points[:, 1:2] - self.coords[:, 1]
            dist_sq = dx * dx + dy * dy

            # Find minimum index for each query
            min_indices = np.argmin(dist_sq, axis=1)

            # Get minimum squared distances
            min_dist_sq = dist_sq[np.arange(n_queries), min_indices]

            # Apply distance constraint (compare squared distances)
            valid_mask = min_dist_sq <= max_distance_sq

            # Map to user IDs vectorized
            result_ids = np.empty(n_queries, dtype=object)
            result_ids[valid_mask] = self.ids[min_indices[valid_mask]]
            result_ids[~valid_mask] = None

            # Convert to Python int if using integer indices
            if not self.has_string_ids:
                result_ids[valid_mask] = np.vectorize(int)(result_ids[valid_mask])

            # Return coordinates
            result_coords = np.full((n_queries, 2), np.nan, dtype=np.float64)
            result_coords[valid_mask] = self.coords[min_indices[valid_mask]]
            return result_ids, result_coords
        else:
            # Loop-based approach for large cases to avoid excessive memory
            result_ids = np.empty(n_queries, dtype=object)
            result_coords = np.full((n_queries, 2), np.nan, dtype=np.float64)

            for i in range(n_queries):
                qx, qy = query_points[i]
                dist_sq = (self.coords[:, 0] - qx) ** 2 + (self.coords[:, 1] - qy) ** 2
                min_idx = np.argmin(dist_sq)
                min_dist_sq = dist_sq[min_idx]

                if min_dist_sq > max_distance_sq[i]:
                    result_ids[i] = None
                else:
                    idx = int(min_idx)
                    result_ids[i] = self.ids[idx] if self.has_string_ids else int(self.ids[idx])
                    result_coords[i] = self.coords[idx]

            return result_ids, result_coords


class SpatialIndex:
    """Drop-in replacement for gusnet.spatial_index.SpatialIndex using NearestNeighborIndex.

    Compatible with the original SpatialIndex API but uses NumPy-based nearest neighbor
    search instead of QgsSpatialIndex for improved performance.
    """

    snap_tolerance = 0.1

    def __init__(self) -> None:
        self._index: NearestNeighborIndex | None = None
        self._points: list[Sequence] = []
        self._point_names: list[Sequence[str]] = []

    def add_nodes(self, geometries, names) -> None:
        """Add nodes from pandas series to the spatial index.

        Args:
            geometries: Series of QgsGeometry objects
            names: Series of node names/IDs
        """

        self._points.append(geometries)

        self._point_names.append(names)

        self._index = None

    def _init_index(self):
        self._index = NearestNeighborIndex(np.concatenate(self._points), np.concatenate(self._point_names))

    def snap_links(self, geometries) -> tuple[list, npt.NDArray[np.object_], npt.NDArray[np.object_]]:
        """Snap the start and end points of links to the nearest nodes in the spatial index.

        Vectorized implementation that batches all endpoint queries together for efficiency.
        Does not raise SnapTooFarError - invalid snaps return None for unmatched nodes.

        Args:
            geometries: Series of QgsGeometry objects (polylines)
            names: Series of link names/IDs

        Returns:
            tuple: (snapped_geometries, start_node_names, end_node_names) where geometries is a list
                   and node names are NumPy object arrays.
        """
        from qgis.core import QgsGeometry, QgsPointXY

        if not self._index:
            self._init_index()

        self._index = cast(NearestNeighborIndex, self._index)

        # Extract all start and end points and metadata
        start_points = []
        end_points = []
        middle_vertices = []

        for geom in geometries:
            vertices = geom.asPolyline()
            start = vertices[0]
            end = vertices[-1]
            middle = vertices[1:-1]

            start_points.append([start.x(), start.y()])
            end_points.append([end.x(), end.y()])
            middle_vertices.append(middle)

        # Convert to numpy arrays for vectorized operations
        start_points_array = np.array(start_points, dtype=np.float64)
        end_points_array = np.array(end_points, dtype=np.float64)

        # Calculate max distances squared directly from endpoint differences
        dx = end_points_array[:, 0] - start_points_array[:, 0]
        dy = end_points_array[:, 1] - start_points_array[:, 1]
        max_distances_sq = (dx * dx + dy * dy) * ((self.snap_tolerance) ** 2)

        # Single batch query for all endpoints with coordinates
        start_node_names, start_coords = self._index.nearest_batch(start_points_array, max_distances_sq)
        end_node_names, end_coords = self._index.nearest_batch(end_points_array, max_distances_sq)

        # Build result arrays
        snapped_geoms = []

        for start_coord, end_coord, start_pt, end_pt, middle_verts in zip(
            start_coords, end_coords, start_points, end_points, middle_vertices
        ):
            # Get snapped coordinates (use matched coords if valid, otherwise use original)
            if not np.isnan(start_coord[0]):
                new_start = QgsPointXY(float(start_coord[0]), float(start_coord[1]))
            else:
                new_start = QgsPointXY(start_pt[0], start_pt[1])

            if not np.isnan(end_coord[0]):
                new_end = QgsPointXY(float(end_coord[0]), float(end_coord[1]))
            else:
                new_end = QgsPointXY(end_pt[0], end_pt[1])

            # Reconstruct geometry
            snapped_geometry = QgsGeometry.fromPolylineXY([new_start, *middle_verts, new_end])
            snapped_geoms.append(snapped_geometry)

        return snapped_geoms, start_node_names, end_node_names
