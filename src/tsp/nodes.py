"""Port of ``sql/traffic_sign_node.sql`` -- direction & attributes for sign nodes.

Resolves the ``direction`` of standalone traffic-sign nodes (and adopts
``highway`` / ``layer`` from a nearby road where missing). Three steps, matching
the original SQL:

  1. Sign sits ON a highway vertex -> direction from the line geometry.
  2. Sign sits NEXT TO a highway   -> direction from the nearest road (<=20 m),
     then from any nearest way (<=10 m); also adopt highway/layer.
  3. Normalise all directions to integers in 0..360.

All neighbour queries use ``GeoDataFrame.sindex`` (an R-tree, the equivalent of
the PostGIS GiST index) so the cost stays near O(n log m) rather than O(n*m).
"""

from __future__ import annotations

import math

import geopandas as gpd
from shapely.geometry import Point

from tsp.osmread import ROAD_HIGHWAY_VALUES

# tolerance (metres) for deciding a node lies *on* a highway vertex
_ON_LINE_TOL = 0.5


def _azimuth_deg(p0: Point, p1: Point) -> float:
    """Bearing p0->p1 in degrees clockwise from north (== PostGIS ST_Azimuth)."""
    az = math.degrees(math.atan2(p1.x - p0.x, p1.y - p0.y))
    return (az + 360.0) % 360.0


def _is_missing(v) -> bool:
    """True if *v* is None or NaN (pandas turns None columns into NaN)."""
    if v is None:
        return True
    try:
        return math.isnan(v)
    except TypeError:
        return False


def _vertex_azimuth(line, vidx: int, backward: bool) -> float | None:
    """Direction of *line* at vertex index *vidx*.

    Forward: azimuth toward the next vertex (or from the previous one if *vidx*
    is the last point). Backward: the mirror case. See SQL step 1.
    """
    coords = list(line.coords)
    n = len(coords)
    if n < 2:
        return None
    pt = Point(coords[vidx])
    if not backward:
        if vidx == n - 1:
            return _azimuth_deg(Point(coords[vidx - 1]), pt)
        return _azimuth_deg(pt, Point(coords[vidx + 1]))
    else:
        if vidx == 0:
            return _azimuth_deg(pt, Point(coords[vidx + 1]))
        return _azimuth_deg(Point(coords[vidx - 1]), pt)


def _find_vertex_index(line, pt: Point, tol: float = _ON_LINE_TOL) -> int | None:
    """Return the index of the vertex of *line* coincident with *pt*, else None."""
    best_i, best_d = None, tol
    for i, c in enumerate(line.coords):
        d = math.hypot(c[0] - pt.x, c[1] - pt.y)
        if d <= best_d:
            best_i, best_d = i, d
    return best_i


def process_nodes(
    node_gdf: gpd.GeoDataFrame,
    highway_gdf: gpd.GeoDataFrame,
) -> gpd.GeoDataFrame:
    """Resolve direction + highway + layer for standalone traffic-sign nodes.

    Returns a copy of *node_gdf* with ``direction`` filled in as a normalised
    integer (0..360) wherever it could be derived.
    """
    nodes = node_gdf.copy()
    if len(nodes) == 0:
        nodes["direction"] = []
        return nodes

    # raw 'direction' tag is a string: "forward"/"backward"/number/None.
    # split into a numeric column and a forward/backward flag.
    numeric = []
    fb_flag = []  # None | 'forward' | 'backward'
    for v in nodes["direction"]:
        if v in ("forward", "backward"):
            numeric.append(None)
            fb_flag.append(v)
        elif v is None:
            numeric.append(None)
            fb_flag.append(None)
        else:
            try:
                numeric.append(int(float(v)))
            except (TypeError, ValueError):
                numeric.append(None)
            fb_flag.append(None)
    nodes["direction"] = numeric
    nodes["_fb"] = fb_flag

    hw_sindex = highway_gdf.sindex if len(highway_gdf) else None

    # --- Step 1: sign ON a highway vertex ------------------------------------
    for idx, node in nodes.iterrows():
        if not _is_missing(node["direction"]):
            continue
        if hw_sindex is None:
            continue
        pt = node["geom"]
        cand = hw_sindex.query(pt, predicate="dwithin", distance=_ON_LINE_TOL)
        for hpos in cand:
            line = highway_gdf.geometry.iloc[hpos]
            vidx = _find_vertex_index(line, pt)
            if vidx is None:
                continue
            backward = node["_fb"] == "backward"
            az = _vertex_azimuth(line, vidx, backward)
            if az is None:
                continue
            # forward / NULL: sign faces oncoming traffic -> add 180
            direction = az + (180.0 if not backward else 0.0)
            nodes.at[idx, "direction"] = int(direction)
            break

    # --- Step 2A: nearest ROAD within 20 m -----------------------------------
    roads = highway_gdf[highway_gdf["highway"].isin(ROAD_HIGHWAY_VALUES)]
    _orient_to_ways(nodes, roads, max_dist=20)

    # --- Step 2B: nearest ANY way within 10 m --------------------------------
    _orient_to_ways(nodes, highway_gdf, max_dist=10)

    # --- Step 3: normalise to integer 0..360 ---------------------------------
    def _norm(d):
        if d is None or (isinstance(d, float) and math.isnan(d)):
            return None
        return ((int(d) % 360) + 360) % 360

    nodes["direction"] = [_norm(d) for d in nodes["direction"]]
    nodes = nodes.drop(columns=["_fb"])
    return nodes


def _orient_to_ways(
    nodes: gpd.GeoDataFrame,
    ways: gpd.GeoDataFrame,
    max_dist: float,
) -> None:
    """In-place: for nodes still missing direction/highway/layer, adopt them
    from the nearest way within *max_dist* metres.

    direction = azimuth(node -> closest point on way) - 90, so the sign faces
    along the road. Mirrors SQL step 2 (DISTINCT ON = nearest match per node).
    """
    if len(ways) == 0:
        return
    way_sindex = ways.sindex

    for idx, node in nodes.iterrows():
        need_dir = _is_missing(node["direction"])
        need_hw = _is_missing(node["highway"])
        need_layer = _is_missing(node["layer"])
        if not (need_dir or need_hw or need_layer):
            continue

        pt = node["geom"]
        cand = way_sindex.query(pt, predicate="dwithin", distance=max_dist)
        if len(cand) == 0:
            continue

        best_pos, best_d = None, float("inf")
        for pos in cand:
            d = pt.distance(ways.geometry.iloc[pos])
            if d < best_d:
                best_pos, best_d = pos, d
        if best_pos is None:
            continue

        way = ways.iloc[best_pos]
        if need_dir:
            closest = way["geom"].interpolate(way["geom"].project(pt))
            angle = _azimuth_deg(pt, closest)
            nodes.at[idx, "direction"] = int(angle) - 90
        if need_hw:
            nodes.at[idx, "highway"] = way["highway"]
        if need_layer and not _is_missing(way["layer"]):
            nodes.at[idx, "layer"] = way["layer"]
