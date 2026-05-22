"""Port of ``sql/traffic_sign_way.sql`` -- regular signs from centerline tags.

Turns ``traffic_sign`` tags carried on highway centerlines into individual sign
nodes, placed (and repeated) at the relevant junctions. Four steps:

  1. Merge way segments with identical sign attributes.
  2. Detect junctions by counting how many highway segment-ends meet at a point,
     and buffer them.
  3. Subtract the junction buffers from the merged sign-ways -> the segments
     *between* junctions.
  4. Place a sign node at each free segment end, direction along the segment;
     adopt osm_id/layer from the nearest highway.

Junction detection is the performance-critical part. Instead of geometric
overlay it counts coordinates: every highway segment endpoint is rounded to a
fixed grid and tallied with ``numpy.unique`` -- O(n) instead of O(n*m).
"""

from __future__ import annotations

import math

import geopandas as gpd
import numpy as np
import shapely
from shapely.geometry import Point
from shapely.ops import linemerge, unary_union

from tsp.nodes import _azimuth_deg, _is_missing
from tsp.osmread import ROAD_HIGHWAY_VALUES

# coordinate rounding tolerance (metres) for treating vertices as identical
_SNAP = 0.01
# junction buffer radius and minimum road-segment length (from the SQL)
_BUFFER_R = 8
_MIN_ROAD_LEN = 10
# cycling-related sign IDs treated specially on contraflow oneways
_BICYCLE_IDS = ("244.1",)

_GROUP_KEYS = ["country_code", "main_signs", "sign_list", "highway",
               "oneway", "oneway:bicycle"]


def _snap_key(x: float, y: float) -> tuple[int, int]:
    """Round a coordinate to the snap grid -> hashable key."""
    return (round(x / _SNAP), round(y / _SNAP))


def _segments(line) -> list[tuple[tuple, tuple]]:
    """Yield consecutive coordinate pairs (segments) of a LineString."""
    cs = list(line.coords)
    return [(cs[i], cs[i + 1]) for i in range(len(cs) - 1)]


def process_ways(
    way_gdf: gpd.GeoDataFrame,
    highway_gdf: gpd.GeoDataFrame,
) -> gpd.GeoDataFrame:
    """Derive regular traffic-sign nodes from highway-centerline sign tags.

    Returns a GeoDataFrame equivalent to the SQL table ``traffic_sign_nodes_way``
    with columns: geom, osm_id, country_code, sign_list, main_signs, highway,
    direction, layer.
    """
    empty = gpd.GeoDataFrame(
        {c: [] for c in ["osm_id", "country_code", "sign_list", "main_signs",
                         "highway", "direction", "layer"]},
        geometry=gpd.GeoSeries([], crs=way_gdf.crs), crs=way_gdf.crs,
    ).rename_geometry("geom")
    if len(way_gdf) == 0:
        return empty

    crs = way_gdf.crs

    # --- Step 1: merge ways with identical sign attributes -------------------
    merged_rows = []
    for keys, grp in way_gdf.groupby(_GROUP_KEYS, dropna=False):
        geom = _safe_linemerge(unary_union(list(grp["geom"])))
        hw = dict(zip(_GROUP_KEYS, keys))["highway"]
        hw_type = "road" if hw in ROAD_HIGHWAY_VALUES else "way"
        for part in _explode_lines(geom):
            row = dict(zip(_GROUP_KEYS, keys))
            row["highway_type"] = hw_type
            row["geom"] = part
            merged_rows.append(row)
    merged = gpd.GeoDataFrame(merged_rows, geometry="geom", crs=crs)

    # --- Step 2: detect junctions, build buffers -----------------------------
    buffers = _junction_buffers(way_gdf, highway_gdf, crs)

    # --- Step 3: subtract junction buffers from merged sign-ways -------------
    if len(buffers):
        buf_union = unary_union(list(buffers["geom"]))
    else:
        buf_union = None

    # Iterate via parallel zip over the columns we need — avoids per-row
    # Series materialisation (`iterrows()` is ~10× slower on geopandas).
    # We use zip() rather than itertuples() because one of the group keys
    # ("oneway:bicycle") isn't a valid Python identifier.
    group_arrays = [merged[k].values for k in _GROUP_KEYS]
    seg_rows = []
    for geom, hw_type, *group_vals in zip(
        merged["geom"].values,
        merged["highway_type"].values,
        *group_arrays,
    ):
        if buf_union is not None:
            geom = geom.difference(buf_union)
        for part in _explode_lines(geom):
            if part.is_empty or part.length == 0:
                continue
            if hw_type == "road" and part.length <= _MIN_ROAD_LEN:
                continue
            seg_rows.append({
                **dict(zip(_GROUP_KEYS, group_vals)),
                "geom": part,
            })
    if not seg_rows:
        return empty
    segments = gpd.GeoDataFrame(seg_rows, geometry="geom", crs=crs)

    # --- Step 4: place sign nodes at free segment ends -----------------------
    nodes = _place_endpoint_nodes(segments, highway_gdf, crs)
    return nodes


def _safe_linemerge(geom):
    """linemerge() only accepts Multi* / collections; pass LineStrings through."""
    if geom.geom_type == "LineString":
        return geom
    return linemerge(geom)


def _explode_lines(geom):
    """Return a flat list of LineStrings from a (Multi)LineString / collection."""
    if geom is None or geom.is_empty:
        return []
    if geom.geom_type == "LineString":
        return [geom]
    return [g for g in shapely.get_parts(geom) if g.geom_type == "LineString"]


def _junction_buffers(way_gdf, highway_gdf, crs) -> gpd.GeoDataFrame:
    """Detect junctions and return a GeoDataFrame of 8 m buffer polygons.

    A point is a junction when 3+ road segment-ends meet (road-road), or when
    a sign-way meets a road there (way-road). Counting is done by tallying
    rounded coordinates of every highway segment endpoint.
    """
    # Only highways that intersect a sign-way matter. Use the highway sindex
    # to find candidates *per sign-way* — that's both cheaper than a global
    # `unary_union(all sign ways)` (which builds a huge MultiLineString) and
    # avoids `highway_gdf.intersects(global_union)` (which still has to do
    # the full predicate against that huge MultiLineString per highway).
    if len(highway_gdf) == 0 or len(way_gdf) == 0:
        return gpd.GeoDataFrame({"geom": []}, geometry="geom", crs=crs)
    hw_sindex = highway_gdf.sindex
    relevant_idx: set[int] = set()
    for geom in way_gdf["geom"]:
        relevant_idx.update(hw_sindex.query(geom, predicate="intersects"))
    if not relevant_idx:
        return gpd.GeoDataFrame({"geom": []}, geometry="geom", crs=crs)
    relevant = highway_gdf.iloc[sorted(relevant_idx)]

    # per snapped coordinate: total ends, road ends, sign-road ends
    # Per snapped coordinate: total segment-ends, road-only segment-ends, and
    # a representative `(x, y)` so we can recover an actual point per key.
    # Built in a SINGLE pass over relevant highways — the previous version
    # iterated `relevant` twice (once for counts, once for representatives).
    # Iterating via the geometry/highway Series directly is also noticeably
    # faster than `iterrows()` (no per-row Series materialisation).
    total: dict = {}
    road: dict = {}
    rep: dict = {}
    for geom, hw_type in zip(relevant.geometry.values, relevant["highway"].values):
        is_road = hw_type in ROAD_HIGHWAY_VALUES
        for a, b in _segments(geom):
            for c in (a, b):
                k = _snap_key(c[0], c[1])
                total[k] = total.get(k, 0) + 1
                if is_road:
                    road[k] = road.get(k, 0) + 1
                if k not in rep:
                    rep[k] = c

    # mark coords that lie on a sign-way (for the way-road junction rule)
    sign_way_keys: set = set()
    for geom in way_gdf["geom"].values:
        for c in geom.coords:
            sign_way_keys.add(_snap_key(c[0], c[1]))

    junction_pts = []
    for k, t in total.items():
        r = road.get(k, 0)
        if r >= 3:
            junction_pts.append(rep[k])               # road-road junction
        elif 0 < r < 3 and t > r and k in sign_way_keys:
            junction_pts.append(rep[k])               # way-road junction

    if not junction_pts:
        return gpd.GeoDataFrame({"geom": []},
                                geometry="geom", crs=crs)
    bufs = [Point(p).buffer(_BUFFER_R) for p in junction_pts]
    return gpd.GeoDataFrame({"geom": bufs}, geometry="geom", crs=crs)


def _place_endpoint_nodes(segments, highway_gdf, crs) -> gpd.GeoDataFrame:
    """Place sign nodes at segment ends not shared with another segment."""
    # Pull the columns we need as numpy arrays once — iterating these in
    # parallel via zip() is ~10× faster than `iterrows()` on geopandas.
    geom_arr = segments["geom"].values
    oneway_arr = segments["oneway"].values
    oneway_bike_arr = segments["oneway:bicycle"].values
    sign_list_arr = segments["sign_list"].values
    main_signs_arr = segments["main_signs"].values
    highway_arr = segments["highway"].values
    country_arr = segments["country_code"].values

    # Tally all segment endpoints (single pass) to find "free" (unshared) ends.
    end_count: dict = {}
    for geom in geom_arr:
        cs = list(geom.coords)
        for c in (cs[0], cs[-1]):
            k = _snap_key(c[0], c[1])
            end_count[k] = end_count.get(k, 0) + 1

    rows = []
    for geom, oneway, oneway_bike, sign_list, main_signs, highway, country in zip(
        geom_arr, oneway_arr, oneway_bike_arr, sign_list_arr,
        main_signs_arr, highway_arr, country_arr,
    ):
        cs = list(geom.coords)
        if len(cs) < 2:
            continue
        sl = sign_list or ""
        has_bike_sign = any(b in sl for b in _BICYCLE_IDS)

        # start point: skip on oneway=-1 (unless contraflow bike exception)
        start_ok = (oneway is None or oneway != "-1") or \
                   (oneway_bike == "no" and has_bike_sign)
        # end point: skip on oneway=yes (unless contraflow bike exception)
        end_ok = (oneway is None or oneway != "yes") or \
                 (oneway_bike == "no" and has_bike_sign)

        candidates = []
        if start_ok:
            direction = _azimuth_deg(Point(cs[1]), Point(cs[0]))
            candidates.append((cs[0], direction))
        if end_ok:
            direction = _azimuth_deg(Point(cs[-2]), Point(cs[-1]))
            candidates.append((cs[-1], direction))

        for coord, direction in candidates:
            if end_count.get(_snap_key(coord[0], coord[1]), 0) != 1:
                continue
            rows.append({
                "geom": Point(coord),
                "osm_id": 999,
                "country_code": country,
                "sign_list": sign_list,
                "main_signs": main_signs,
                "highway": highway,
                "direction": int(direction),
                "layer": None,
            })

    nodes = gpd.GeoDataFrame(rows, geometry="geom", crs=crs) if rows else \
        gpd.GeoDataFrame(
            {c: [] for c in ["osm_id", "country_code", "sign_list",
                             "main_signs", "highway", "direction", "layer"]},
            geometry=gpd.GeoSeries([], crs=crs), crs=crs).rename_geometry("geom")

    # adopt osm_id + layer from the nearest highway line
    if len(nodes) and len(highway_gdf):
        hw_sindex = highway_gdf.sindex
        hw_geoms = highway_gdf.geometry.values
        hw_osm_ids = highway_gdf["osm_id"].values
        hw_layers = highway_gdf["layer"].values
        # Bulk-assign at the end (per-row `.at` writes are slow).
        new_osm_ids = nodes["osm_id"].tolist()
        new_layers = nodes["layer"].tolist()
        for i, pt in enumerate(nodes["geom"].values):
            cand = hw_sindex.query(pt, predicate="dwithin", distance=0.1)
            best_pos, best_d = None, float("inf")
            for pos in cand:
                d = pt.distance(hw_geoms[pos])
                if d < best_d:
                    best_pos, best_d = pos, d
            if best_pos is not None:
                new_osm_ids[i] = hw_osm_ids[best_pos]
                new_layers[i] = hw_layers[best_pos]
        nodes["osm_id"] = new_osm_ids
        nodes["layer"] = new_layers
    return nodes
