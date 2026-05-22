"""Port of ``sql/traffic_sign_zone.sql`` -- one sign node per zone entrance.

Zone signs (Tempo-30-Zone etc.) are not repeated at every junction; a single
node is placed where the zone is entered. Four steps:

  1. Merge zone segments with identical sign IDs.
  2. Find zone-entrance vertices: points where a zone road meets a non-zone
     road (counting segment-ends per coordinate, like ways.py).
  3. Buffer the entrance points (8 m).
  4. Place the sign node where the buffer circle crosses the zone segment;
     direction faces into the zone.
"""

from __future__ import annotations

import geopandas as gpd
import shapely
from shapely.geometry import Point
from shapely.ops import unary_union

from tsp.nodes import _azimuth_deg
from tsp.osmread import ROAD_HIGHWAY_VALUES
from tsp.parse import ZONE_IDS
from tsp.ways import _explode_lines, _safe_linemerge, _segments, _snap_key

_BUFFER_R = 8


def process_zones(
    zone_gdf: gpd.GeoDataFrame,
    highway_gdf: gpd.GeoDataFrame,
) -> gpd.GeoDataFrame:
    """Derive one traffic-sign node per zone entrance.

    Returns a GeoDataFrame equivalent to the SQL table ``traffic_sign_nodes_zone``
    with columns: osm_id, country_code, sign_list, main_signs, direction,
    highway, layer, geom.
    """
    cols = ["osm_id", "country_code", "sign_list", "main_signs",
            "direction", "highway", "layer"]
    crs = zone_gdf.crs
    empty = gpd.GeoDataFrame(
        {c: [] for c in cols},
        geometry=gpd.GeoSeries([], crs=crs), crs=crs).rename_geometry("geom")
    if len(zone_gdf) == 0:
        return empty

    # --- Step 1: merge zone segments by identical sign IDs -------------------
    # keep only zone-signed segments (sign_list contains a zone id)
    def _is_zone_row(sign_list):
        return any(zid in (sign_list or "") for zid in ZONE_IDS)

    zoned = zone_gdf[zone_gdf["sign_list"].apply(_is_zone_row)]
    if len(zoned) == 0:
        return empty

    merge_keys = ["osm_type", "osm_id", "country_code", "sign_list",
                  "main_signs", "highway", "layer"]
    merged_rows = []
    for keys, grp in zoned.groupby(merge_keys, dropna=False):
        geom = _safe_linemerge(unary_union(list(grp["geom"])))
        for part in _explode_lines(geom):
            row = dict(zip(merge_keys, keys))
            row["geom"] = part
            merged_rows.append(row)
    segments = gpd.GeoDataFrame(merged_rows, geometry="geom", crs=crs)

    # restrict to road-class zone segments (SQL only considers roads)
    segments = segments[segments["highway"].isin(ROAD_HIGHWAY_VALUES)]
    if len(segments) == 0:
        return empty

    # --- Step 2: find zone-entrance vertices ---------------------------------
    # Pick the road-class highways that intersect any zone segment, via the
    # sindex per segment — avoids the global `unary_union` over many segments
    # (which can be hundreds of MB of MultiLineString for big extracts).
    road_mask = highway_gdf["highway"].isin(ROAD_HIGHWAY_VALUES)
    road_highways = highway_gdf[road_mask]
    if len(road_highways) == 0:
        return empty
    hw_sindex = road_highways.sindex
    relevant_idx: set[int] = set()
    for geom in segments["geom"]:
        relevant_idx.update(hw_sindex.query(geom, predicate="intersects"))
    if not relevant_idx:
        return empty
    relevant = road_highways.iloc[sorted(relevant_idx)]

    # per snapped coord: total road ends, and ends NOT carrying the zone sign
    total: dict = {}
    connected: dict = {}      # road ends without the zone sign
    rep: dict = {}
    # which sign_list(s) live at each coordinate (for entrance attribution)
    coord_signs: dict = {}

    # Pass over relevant highways via parallel zip — ~10× faster than iterrows()
    # on geopandas frames.
    for geom, ts in zip(relevant["geom"].values, relevant["traffic_sign"].values):
        if isinstance(ts, float):  # pandas NaN
            ts = None
        carries_zone = ts is not None and any(zid in ts for zid in ZONE_IDS)
        for a, b in _segments(geom):
            for c in (a, b):
                k = _snap_key(c[0], c[1])
                total[k] = total.get(k, 0) + 1
                if k not in rep:
                    rep[k] = c
                if not carries_zone:
                    connected[k] = connected.get(k, 0) + 1

    # which zone sign_list passes through each coordinate
    for geom, sign_list in zip(segments["geom"].values, segments["sign_list"].values):
        for c in geom.coords:
            coord_signs.setdefault(_snap_key(c[0], c[1]), set()).add(sign_list)

    entrances = []  # (coord, sign_list)
    for k, t in total.items():
        conn = connected.get(k, 0)
        # entrance: a zone road meets a non-zone road
        if t > conn and conn > 0 and k in coord_signs:
            for sl in coord_signs[k]:
                entrances.append((rep[k], sl))
    if not entrances:
        return empty

    # --- Steps 3+4: buffer entrance, place node on the circle ----------------
    # Group segments by sign_list as plain dicts (was: pd.Series via iterrows
    # — slow + verbose access via s[...]).
    seg_by_sign: dict = {}
    for geom, osm_id, country, sign_list, main_signs, highway, layer in zip(
        segments["geom"].values,
        segments["osm_id"].values,
        segments["country_code"].values,
        segments["sign_list"].values,
        segments["main_signs"].values,
        segments["highway"].values,
        segments["layer"].values,
    ):
        seg_by_sign.setdefault(sign_list, []).append({
            "geom": geom,
            "osm_id": osm_id,
            "country_code": country,
            "sign_list": sign_list,
            "main_signs": main_signs,
            "highway": highway,
            "layer": layer,
        })

    rows = []
    for coord, sign_list in entrances:
        entrance_pt = Point(coord)
        circle = entrance_pt.buffer(_BUFFER_R).exterior
        for s in seg_by_sign.get(sign_list, []):
            inter = circle.intersection(s["geom"])
            if inter.is_empty:
                continue
            for part in shapely.get_parts(inter):
                if part.geom_type != "Point":
                    continue
                # direction: from the node toward the entrance (into the zone)
                direction = int(_azimuth_deg(part, entrance_pt))
                rows.append({
                    "osm_id": s["osm_id"],
                    "country_code": s["country_code"],
                    "sign_list": s["sign_list"],
                    "main_signs": s["main_signs"],
                    "direction": direction,
                    "highway": s["highway"],
                    "layer": s["layer"],
                    "geom": part,
                })

    if not rows:
        return empty
    return gpd.GeoDataFrame(rows, geometry="geom", crs=crs)
