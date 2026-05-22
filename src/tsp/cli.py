"""Command-line entrypoint -- replaces ``data_preparation_traffic_sign.sh``.

The original shell script: optionally downloads a pbf, optionally extracts a
bounding box with ``osmium extract``, imports into PostGIS, runs the SQL, done.

This port keeps the same shape but writes a GeoParquet file instead of filling
a database. The optional bounding-box extract is done in-process with
pyosmium (no external ``osmium`` binary required).

Usage
-----
    uv run tsp --input osm/berlin-latest.osm.pbf \\
               --bbox 13.3924,52.4543,13.4859,52.5009 \\
               --output output/traffic_signs.parquet

    # already-extracted file, no clipping:
    uv run tsp --input osm/extract_neukoelln.osm.pbf --output output/signs.parquet
"""

from __future__ import annotations

import argparse
import sys
import time

from tsp.osmread import DEFAULT_CRS


def _log(msg: str) -> None:
    print(f"{time.strftime('%Y-%m-%d %H:%M:%S')}  [INFO] {msg}", flush=True)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="tsp",
        description="Extract traffic sign locations & directions from OSM data.",
    )
    p.add_argument("--input", "-i", required=True,
                   help="Path to an .osm.pbf file.")
    p.add_argument("--output", "-o", default="output/traffic_signs.parquet",
                   help="Output GeoParquet path (default: output/traffic_signs.parquet).")
    p.add_argument("--bbox", "-b", default=None,
                   help="Optional bounding box 'minlon,minlat,maxlon,maxlat' "
                        "to clip the input before processing.")
    p.add_argument("--crs", type=int, default=DEFAULT_CRS,
                   help=f"Target metric CRS / EPSG code (default: {DEFAULT_CRS}).")
    p.add_argument("--keep-intermediate", action="store_true",
                   help="Also write the node/way/zone layers as separate "
                        "GeoParquet files (useful for debugging, like the "
                        "intermediate PostGIS tables).")
    return p


def run(args: argparse.Namespace) -> int:
    """Pipeline orchestration -- mirrors the order of the shell script."""
    from tsp.osmread import read_osm
    from tsp.nodes import process_nodes
    from tsp.ways import process_ways
    from tsp.zones import process_zones
    from tsp.merge import merge_signs

    input_path = args.input

    # --- optional bbox extract (replaces `osmium extract -b ...`) ------------
    if args.bbox:
        _log("Creating OSM data extract...")
        input_path = _extract_bbox(args.input, args.bbox)

    # --- import (replaces osm2pgsql + Lua) -----------------------------------
    _log("Importing OSM data...")
    node_gdf, way_gdf, zone_gdf, highway_gdf = read_osm(input_path, crs=args.crs)
    _log(f"  - {len(node_gdf)} sign nodes, {len(way_gdf)} sign ways, "
         f"{len(zone_gdf)} zone ways, {len(highway_gdf)} highways")

    # --- processing (replaces the 4 SQL files) -------------------------------
    _log("Processing OSM traffic sign data...")
    _log("  - traffic sign nodes...")
    node_signs = process_nodes(node_gdf, highway_gdf)
    _log("  - traffic sign ways...")
    way_signs = process_ways(way_gdf, highway_gdf)
    _log("  - traffic sign zones...")
    zone_signs = process_zones(zone_gdf, highway_gdf)
    _log("  - merge data...")
    result = merge_signs(node_signs, way_signs, zone_signs)

    # --- output --------------------------------------------------------------
    from pathlib import Path
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    _log(f"Writing GeoParquet -> {out_path}")
    result.to_parquet(out_path)

    if args.keep_intermediate:
        node_signs.to_parquet(out_path.with_name("traffic_sign_node.parquet"))
        way_signs.to_parquet(out_path.with_name("traffic_sign_nodes_way.parquet"))
        zone_signs.to_parquet(out_path.with_name("traffic_sign_nodes_zone.parquet"))

    _log("Script completed.")
    return 0


def _extract_bbox(pbf_path: str, bbox: str) -> str:
    """Clip *pbf_path* to *bbox* using pyosmium, return the new file path.

    Equivalent to ``osmium extract -b minlon,minlat,maxlon,maxlat``. A way is
    kept if any of its nodes falls inside the box; ``ForwardReferenceWriter``
    with ``back_references=True`` then pulls in the referenced nodes so the
    output is geometrically complete.
    """
    import os
    import osmium

    minlon, minlat, maxlon, maxlat = (float(x) for x in bbox.split(","))
    out_path = os.path.join(
        os.path.dirname(pbf_path) or ".",
        "extract_" + os.path.basename(pbf_path),
    )

    # node IDs inside the bbox -> used to decide which ways to keep
    inside: set[int] = set()
    for obj in osmium.FileProcessor(pbf_path).with_locations():
        if isinstance(obj, osmium.osm.Node):
            loc = obj.location
            if loc.valid() and minlon <= loc.lon <= maxlon \
                    and minlat <= loc.lat <= maxlat:
                inside.add(obj.id)

    writer = osmium.ForwardReferenceWriter(
        out_path, pbf_path, overwrite=True, back_references=True,
    )
    for obj in osmium.FileProcessor(pbf_path):
        if isinstance(obj, osmium.osm.Node):
            if obj.id in inside:
                writer.add(obj)
        elif isinstance(obj, osmium.osm.Way):
            if any(n.ref in inside for n in obj.nodes):
                writer.add(obj)
    writer.close()
    return out_path


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return run(args)
    except NotImplementedError as e:
        print(f"[NOT IMPLEMENTED] {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
