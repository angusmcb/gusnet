"""Benchmark test comparing spatial_index.py and spatial_index2.py"""

import timeit

import numpy as np
import pandas as pd
from qgis.core import QgsGeometry, QgsPointXY


def test_spatial_index_benchmark_comparison(qgis_app):
    """Compare performance between QgsSpatialIndex and NearestNeighborIndex implementations."""
    from gusnet.spatial_index import SpatialIndex as SpatialIndexOld
    from gusnet.spatial_index2 import SpatialIndex as SpatialIndexNew

    print("\n" + "=" * 80)
    print("SPATIAL INDEX BENCHMARK COMPARISON")
    print("=" * 80)
    print("\nComparing:")
    print("  - spatial_index.py (QgsSpatialIndex)")
    print("  - spatial_index2.py (NearestNeighborIndex)")
    print("=" * 80)

    # Test with different dataset sizes
    sizes = [100, 1_000, 5_000]

    for n_nodes in sizes:
        print(f"\n{'=' * 80}")
        print(f"Dataset size: {n_nodes:,} nodes, {n_nodes // 2:,} links")
        print(f"{'=' * 80}")

        # Generate random nodes
        np.random.seed(42)
        node_coords = np.random.rand(n_nodes, 2) * 10000  # 10km x 10km area

        # Create node geometries and names
        # For OLD implementation: QgsGeometry objects
        node_geometries_old = [QgsGeometry.fromPointXY(QgsPointXY(x, y)) for x, y in node_coords]
        # For NEW implementation: [[x, y], ...] lists
        node_geometries_new = [[float(x), float(y)] for x, y in node_coords]

        node_names = [f"N{i}" for i in range(n_nodes)]
        node_geoms_old_series = pd.Series(node_geometries_old)
        node_geoms_new_series = node_geometries_new
        node_names_series = pd.Series(node_names)

        # Generate random links connecting random nodes
        n_links = n_nodes // 2
        link_geometries = []
        link_names = []
        for i in range(n_links):
            # Random start and end nodes (with small offset to avoid exact matches)
            start_idx = np.random.randint(0, n_nodes)
            end_idx = np.random.randint(0, n_nodes)
            if start_idx == end_idx:
                end_idx = (end_idx + 1) % n_nodes

            # Add small random offsets (1-5 meters) to test snapping
            start_x, start_y = node_coords[start_idx]
            end_x, end_y = node_coords[end_idx]
            start_x += np.random.uniform(-5, 5)
            start_y += np.random.uniform(-5, 5)
            end_x += np.random.uniform(-5, 5)
            end_y += np.random.uniform(-5, 5)

            # Add a middle point for more realistic link geometry
            mid_x = (start_x + end_x) / 2 + np.random.uniform(-10, 10)
            mid_y = (start_y + end_y) / 2 + np.random.uniform(-10, 10)

            link_geom = QgsGeometry.fromPolylineXY(
                [QgsPointXY(start_x, start_y), QgsPointXY(mid_x, mid_y), QgsPointXY(end_x, end_y)]
            )
            link_geometries.append(link_geom)
            link_names.append(f"L{i}")

        link_geoms_series = pd.Series(link_geometries)
        link_names_series = pd.Series(link_names)

        # Benchmark OLD implementation (QgsSpatialIndex)
        print("\n--- QgsSpatialIndex (spatial_index.py) ---")

        def test_old(
            node_geoms=node_geoms_old_series,
            node_names=node_names_series,
            link_geoms=link_geoms_series,
            link_names=link_names_series,
        ):
            index_old = SpatialIndexOld()
            index_old.snap_tolerance = 1.0  # Increase tolerance for benchmark
            index_old.add_nodes(node_geoms, node_names)
            results = index_old.snap_links(link_geoms, link_names)
            return results

        time_old = timeit.timeit(test_old, number=5) / 5
        geoms_old, starts_old, ends_old = test_old()
        print(f"Total time:     {time_old * 1000:.2f} ms")
        print("  add_nodes:    (included in total)")
        print("  snap_links:   (included in total)")
        print(f"Links snapped:  {len(geoms_old)}")

        # Benchmark NEW implementation (NearestNeighborIndex)
        print("\n--- NearestNeighborIndex (spatial_index2.py) ---")

        def test_new(
            node_geoms=node_geoms_new_series,
            node_names=node_names_series,
            link_geoms=link_geoms_series,
        ):
            index_new = SpatialIndexNew()
            index_new.snap_tolerance = 1.0  # Increase tolerance for benchmark
            index_new.add_nodes(node_geoms, node_names)
            results = index_new.snap_links(link_geoms)
            return results

        time_new = timeit.timeit(test_new, number=5) / 5
        geoms_new, starts_new, ends_new = test_new()
        print(f"Total time:     {time_new * 1000:.2f} ms")
        print("  add_nodes:    (included in total)")
        print("  snap_links:   (included in total)")
        print(f"Links snapped:  {len(geoms_new)}")

        # Compare results
        speedup = time_old / time_new
        print(f"\n{'=' * 80}")
        if speedup > 1:
            print(f"✓ SPEEDUP: {speedup:.2f}x faster with NearestNeighborIndex")
        else:
            print(f"⚠ SLOWER: {1 / speedup:.2f}x slower with NearestNeighborIndex")
        print(f"{'=' * 80}")

        # Verify results match
        mismatches = 0
        for i in range(len(geoms_old)):
            if starts_old[i] != starts_new[i] or ends_old[i] != ends_new[i]:
                mismatches += 1
                if mismatches <= 3:  # Only print first 3 mismatches
                    print(
                        f"WARNING: Mismatch at link {i}: "
                        f"OLD({starts_old[i]},{ends_old[i]}) vs NEW({starts_new[i]},{ends_new[i]})"
                    )

        if mismatches == 0:
            print("✓ Results match perfectly between implementations")
        else:
            print(f"⚠ Found {mismatches} mismatches out of {len(geoms_old)} links")

        # Memory usage estimate
        print("\nMemory estimate:")
        print("  Old (QgsSpatialIndex): Unknown (C++ implementation)")
        print(
            f"  New (NearestNeighborIndex): ~{n_nodes * 2 * 8 / 1024:.1f} KB (coords) + "
            f"{n_nodes * 8 / 1024:.1f} KB (ids)"
        )

    print(f"\n{'=' * 80}")
    print("Benchmark complete!")
    print(f"{'=' * 80}")
