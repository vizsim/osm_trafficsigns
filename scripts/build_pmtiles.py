"""Convert a traffic-signs GeoParquet into PMTiles via tippecanoe.

Reads ``output/<name>.parquet`` (any EPSG), reprojects to EPSG:4326, writes a
GeoJSON sidecar, then invokes ``tippecanoe`` (https://github.com/felt/tippecanoe)
to produce ``viz/data/<name>.pmtiles`` for serving in MapLibre.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import geopandas as gpd

from tsp.signlist import collapse_shared_family, normalize_code, parse_sign_list

# How many additional stack positions to materialize as feature properties.
# 3 means we get stack_1, stack_2, stack_3 in addition to the primary —
# enough to cover the typical 1 + 3 supplementary plates on German signs.
STACK_DEPTH = 3

REPO_ROOT = Path(__file__).resolve().parent.parent
PARQUET_DIR = REPO_ROOT / "output"
PMTILES_DIR = REPO_ROOT / "viz" / "data"
LAYER_NAME = "traffic_signs"
MIN_ZOOM = 8
MAX_ZOOM = 16


def parquet_to_geojson(parquet_path: Path, geojson_path: Path) -> int:
    gdf = gpd.read_parquet(parquet_path).to_crs(4326)
    # Parse sign_list ONCE into ordered items, then derive both icon_code
    # (the primary) and stack_N_code/stack_N_text (the additional items
    # rendered below the primary at zoom ≥ ICON_MIN_ZOOM).
    parsed = gdf["sign_list"].map(parse_sign_list)
    main_signs_code = gdf["main_signs"].map(normalize_code)

    def _primary(items):
        for kind, value in items:
            if kind == "code":
                return value
        return None

    # Fall back from sign_list's primary to a normalised main_signs code, then
    # empty string. The raw main_signs is NOT a fallback: it can contain free
    # text (e.g. "Rad- und Gehwegschäden") which would then get baked into
    # icon_code and trigger MapLibre image-fetches against URLs containing
    # those text strings.
    gdf["icon_code"] = (
        parsed.map(_primary)
        .fillna(main_signs_code)
        .fillna("")
    )

    # Shared-family collapse: codes like `262-3.5` get routed to the family
    # base `262.svg` with the variant number ("3,5") rendered as an overlay
    # text layer on top of the icon. See signlist.SHARED_FAMILY_BASES.
    collapsed = gdf["icon_code"].map(collapse_shared_family)
    gdf["icon_code"] = collapsed.map(lambda t: t[0])
    gdf["overlay_text"] = collapsed.map(lambda t: t[1])

    def _slot(items, idx, want_kind):
        # idx is 1-based here (slot 1 = items[1], because items[0] is the
        # primary already exposed via icon_code).
        if idx < len(items) and items[idx][0] == want_kind:
            return items[idx][1]
        return ""

    for i in range(1, STACK_DEPTH + 1):
        gdf[f"stack_{i}_code"] = parsed.map(lambda items, i=i: _slot(items, i, "code"))
        gdf[f"stack_{i}_text"] = parsed.map(lambda items, i=i: _slot(items, i, "text"))

    geojson_path.parent.mkdir(parents=True, exist_ok=True)
    gdf.to_file(geojson_path, driver="GeoJSON")
    return len(gdf)


def run_tippecanoe(geojson_path: Path, pmtiles_path: Path) -> None:
    pmtiles_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "tippecanoe",
        "-o", str(pmtiles_path),
        f"--layer={LAYER_NAME}",
        f"--minimum-zoom={MIN_ZOOM}",
        f"--maximum-zoom={MAX_ZOOM}",
        # Keep every point at every zoom: -r1 disables the default 1/2.5
        # drop-per-zoom-level decimation, and the two `--no-*-limit` flags
        # stop tippecanoe from shedding features when tiles get fat.
        "--drop-rate=1",
        "--no-feature-limit",
        "--no-tile-size-limit",
        "--force",
        str(geojson_path),
    ]
    print("$", " ".join(cmd))
    subprocess.run(cmd, check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "names", nargs="*",
        default=[
            "brandenburg_signs",
            "sachsen_signs",
            "mecklenburg_vorpommern_signs",
            "sachsen_anhalt_signs",
            "thueringen_signs",
        ],
        help="Parquet basenames in output/ to convert (default: the five viz states).",
    )
    args = parser.parse_args()

    for name in args.names:
        parquet = PARQUET_DIR / f"{name}.parquet"
        if not parquet.exists():
            print(f"!! {parquet} not found", file=sys.stderr)
            return 1
        geojson = PMTILES_DIR / f"{name}.geojson"
        pmtiles = PMTILES_DIR / f"{name}.pmtiles"
        n = parquet_to_geojson(parquet, geojson)
        print(f"[{name}] {n} features -> {geojson}")
        run_tippecanoe(geojson, pmtiles)
        # GeoJSON is intermediate; remove after pmtiles is built.
        geojson.unlink()
        print(f"[{name}] wrote {pmtiles}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
