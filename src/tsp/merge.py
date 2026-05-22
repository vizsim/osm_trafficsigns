"""Port of ``sql/merge.sql`` -- combine the three node sources into one layer.

Concatenates the standalone sign nodes, the way-derived nodes and the
zone-entrance nodes. Way/zone nodes are dropped when an equivalent standalone
node already exists nearby (a mapper already placed it explicitly).
"""

from __future__ import annotations

import math

import geopandas as gpd
import pandas as pd

#: dedup parameters from merge.sql
DEDUP_DISTANCE_M = 8
DEDUP_DIRECTION_TOLERANCE_DEG = 45

#: final column order (== SQL `traffic_signs` table)
OUTPUT_COLUMNS = [
    "geom", "country_code", "sign_list", "main_signs",
    "direction", "osm_id", "highway", "source",
]


def _angle_diff(a, b) -> float:
    """Smallest absolute difference between two angles, on a 0..360 circle."""
    d = abs(float(a) - float(b)) % 360
    return min(d, 360 - d)


def merge_signs(
    node_gdf: gpd.GeoDataFrame,
    way_nodes_gdf: gpd.GeoDataFrame,
    zone_nodes_gdf: gpd.GeoDataFrame,
) -> gpd.GeoDataFrame:
    """Merge node/way/zone sign layers into the final ``traffic_signs`` layer."""
    crs = node_gdf.crs

    def _prep(gdf, source):
        g = gdf.copy()
        g["source"] = source
        keep = [c for c in OUTPUT_COLUMNS if c in g.columns]
        return g[keep]

    node_part = _prep(node_gdf, "node")
    way_part = _prep(way_nodes_gdf, "way")
    zone_part = _prep(zone_nodes_gdf, "zone")

    # dedup way/zone rows against the explicitly mapped standalone nodes
    node_sindex = node_gdf.sindex if len(node_gdf) else None

    def _is_duplicate(row) -> bool:
        """True if a standalone node within 8 m has the same main_signs and a
        direction within +/-45 deg."""
        if node_sindex is None:
            return False
        pt = row["geom"]
        cand = node_sindex.query(pt, predicate="dwithin",
                                 distance=DEDUP_DISTANCE_M)
        for pos in cand:
            other = node_gdf.iloc[pos]
            if other["main_signs"] != row["main_signs"]:
                continue
            d_row, d_other = row["direction"], other["direction"]
            if d_row is None or d_other is None:
                continue
            try:
                if math.isnan(d_row) or math.isnan(d_other):
                    continue
            except TypeError:
                pass
            if _angle_diff(d_row, d_other) <= DEDUP_DIRECTION_TOLERANCE_DEG:
                return True
        return False

    def _filter(part):
        if node_sindex is None or len(part) == 0:
            return part
        mask = ~part.apply(_is_duplicate, axis=1)
        return part[mask]

    way_part = _filter(way_part)
    zone_part = _filter(zone_part)

    merged = pd.concat([node_part, way_part, zone_part], ignore_index=True)
    result = gpd.GeoDataFrame(merged, geometry="geom", crs=crs)
    # ensure stable column order
    for c in OUTPUT_COLUMNS:
        if c not in result.columns:
            result[c] = None
    return result[OUTPUT_COLUMNS]
