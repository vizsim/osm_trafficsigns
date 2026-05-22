"""OSM data import -- replaces ``osm2pgsql -O flex`` + the Lua table definitions.

The original Lua config defines four osm2pgsql tables (``traffic_sign_node``,
``traffic_sign_way``, ``traffic_sign_zone``, ``highway``) and fills them in the
``process_node`` / ``process_way`` callbacks.

Here, a single :class:`pyosmium.SimpleHandler` does the same job, collecting
rows into plain lists which are then turned into GeoDataFrames. All geometries
are reprojected from WGS84 (EPSG:4326) to a local metric CRS so that distances
and azimuths in the processing steps are in metres/degrees -- the equivalent of
the ``projection = crs`` setting in the Lua table definitions.

STATUS: fully implemented. This is the import stage; the processing stages
(:mod:`tsp.nodes`, :mod:`tsp.ways`, :mod:`tsp.zones`, :mod:`tsp.merge`) are
where the spatial SQL still needs porting.
"""

from __future__ import annotations

import osmium
from shapely import wkb as shapely_wkb

from tsp.parse import parse_traffic_sign

# osm2pgsql/Lua default target CRS (UTM zone 33N, suitable for Berlin).
# Override per project area; the CLI exposes this as --crs.
DEFAULT_CRS = 25833

# highway values treated as "roads" (vs. other ways) -- carried over from the
# repeated IN (...) lists in the SQL files.
ROAD_HIGHWAY_VALUES = {
    "primary", "primary_link", "secondary", "secondary_link",
    "tertiary", "tertiary_link", "unclassified", "residential",
    "living_street", "pedestrian", "road",
}


class _TrafficSignHandler(osmium.SimpleHandler):
    """Collects traffic-sign nodes/ways and all highway ways from a pbf file.

    Mirrors the four tables from the Lua config. Rows are accumulated as dicts;
    geometries are stored as shapely objects in WGS84 and reprojected by the
    caller (:func:`read_osm`) in one vectorised step.
    """

    def __init__(self) -> None:
        super().__init__()
        # osmium factory that builds shapely geometries (WGS84)
        self._wkbfab = osmium.geom.WKBFactory()
        self.sign_nodes: list[dict] = []
        self.sign_ways: list[dict] = []   # traffic_sign on highway centerlines
        self.highways: list[dict] = []

    # -- nodes: Lua osm2pgsql.process_node ------------------------------------
    def node(self, n: osmium.osm.Node) -> None:
        ts = n.tags.get("traffic_sign")
        if ts is None:
            return
        parsed = parse_traffic_sign(ts, dict(n.tags))
        if parsed is None:
            return
        geom = shapely_wkb.loads(self._wkbfab.create_point(n), hex=True)
        self.sign_nodes.append({
            "osm_id": n.id,
            "osm_type": "N",
            "country_code": parsed["country_code"],
            "main_signs": parsed["main_signs"],
            "sign_list": parsed["sign_list"],
            # raw direction tag -- "forward"/"backward"/degrees resolved later
            "direction": n.tags.get("direction"),
            "highway": n.tags.get("highway"),
            "layer": _int_or_none(n.tags.get("layer")),
            "geom": geom,
        })

    # -- ways: Lua osm2pgsql.process_way --------------------------------------
    def way(self, w: osmium.osm.Way) -> None:
        if len(w.nodes) < 2:
            return
        try:
            geom = shapely_wkb.loads(self._wkbfab.create_linestring(w), hex=True)
        except RuntimeError:
            # incomplete way (missing node refs) -- skip, like osm2pgsql would
            return

        hw = w.tags.get("highway")
        ts = w.tags.get("traffic_sign")

        # traffic_sign on a highway centerline -> traffic_sign_way table
        if ts is not None and hw is not None:
            parsed = parse_traffic_sign(ts, dict(w.tags))
            if parsed is not None:
                self.sign_ways.append({
                    "osm_id": w.id,
                    "osm_type": "W",
                    "country_code": parsed["country_code"],
                    "main_signs": parsed["main_signs"],
                    "sign_list": parsed["sign_list"],
                    "zone_status": parsed["zone_status"],
                    "nested": parsed["nested"],
                    "highway": hw,
                    "oneway": w.tags.get("oneway"),
                    "oneway:bicycle": w.tags.get("oneway:bicycle"),
                    "layer": w.tags.get("layer"),
                    "geom": geom,
                })

        # every highway way -> highway table (skip closed area polygons)
        if hw is not None and not (w.is_closed() and w.tags.get("area") == "yes"):
            self.highways.append({
                "osm_id": w.id,
                "osm_type": "W",
                "highway": hw,
                "name": w.tags.get("name"),
                "oneway": w.tags.get("oneway"),
                "oneway:bicycle": w.tags.get("oneway:bicycle"),
                "traffic_sign": ts,
                "layer": _int_or_none(w.tags.get("layer")),
                "geom": geom,
            })


def read_osm(pbf_path: str, crs: int = DEFAULT_CRS):
    """Read *pbf_path* and return four GeoDataFrames in the target *crs*.

    Returns ``(traffic_sign_node, traffic_sign_way, traffic_sign_zone, highway)``.
    The way table is split into regular vs. zone here, mirroring the routing
    logic at the end of Lua ``process_traffic_sign`` (``zone_status`` -> which
    table(s) a way segment is written to).
    """
    import geopandas as gpd  # imported lazily so `parse` stays dependency-light

    handler = _TrafficSignHandler()
    handler.apply_file(pbf_path, locations=True)

    def _gdf(rows: list[dict]):
        gdf = gpd.GeoDataFrame(rows, geometry="geom", crs=4326)
        return gdf.to_crs(crs) if len(gdf) else gdf.set_crs(crs, allow_override=True)

    node_gdf = _gdf(handler.sign_nodes)
    highway_gdf = _gdf(handler.highways)

    # Split sign ways into regular / zone. Lua process_traffic_sign:
    #   zone_status "no"   -> traffic_sign_way only
    #   zone_status "only" -> traffic_sign_zone only
    #   zone_status "yes"  -> normally would split: zone parts to the zone
    #     layer, non-zone parts to the way layer. BUT a "yes" status usually
    #     reflects an OSM mapping mistake (`;`/`,` mixed up — e.g.
    #     `DE:260;DE:257-51,"gilt auch ..."` where the mapper meant the two
    #     main signs to share one post). Splitting drops the zone half of
    #     the way layer's representation, so we keep everything together in
    #     the way layer for "yes". This matches the user's intent that "both
    #     signs should render at the same post".
    way_rows, zone_rows = [], []
    from tsp.parse import (
        get_sign_list, get_main_signs, remove_zone_signs, remove_regular_signs,
    )
    for row in handler.sign_ways:
        status = row["zone_status"]
        if status == "no":
            way_rows.append(_way_row(row, row["nested"], get_sign_list, get_main_signs))
        elif status == "only":
            zone_rows.append(_way_row(row, row["nested"], get_sign_list, get_main_signs))
        else:   # "yes" — mixed; keep both halves together in the way layer
            way_rows.append(_way_row(row, row["nested"], get_sign_list, get_main_signs))

    way_gdf = _gdf(way_rows)
    zone_gdf = _gdf(zone_rows)
    return node_gdf, way_gdf, zone_gdf, highway_gdf


def _way_row(row, nested, get_sign_list, get_main_signs):
    """Build a traffic_sign_way/zone row from a parsed way and a filtered list."""
    return {
        "osm_id": row["osm_id"],
        "osm_type": row["osm_type"],
        "country_code": row["country_code"],
        "main_signs": get_main_signs(nested),
        "sign_list": get_sign_list(nested),
        "highway": row["highway"],
        "oneway": row["oneway"],
        "oneway:bicycle": row["oneway:bicycle"],
        "layer": row["layer"],
        "geom": row["geom"],
    }


def _int_or_none(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None
