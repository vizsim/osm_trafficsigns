# OSM traffic sign processing — Python port

Pure-Python reimplementation of
[SupaplexOSM/traffic_sign_processing](https://github.com/SupaplexOSM/traffic_sign_processing),
plus a MapLibre web viewer and a QGIS style.

The pipeline extracts traffic-sign **locations** and **directions** from an
`.osm.pbf` file. Where the original used a Lua config + `osm2pgsql` +
PostGIS/PL-pgSQL, this port uses **pyosmium** for reading, **GeoPandas/Shapely**
for spatial processing, and writes a **GeoParquet** file.

## Workflow at a glance

```text
osm/*.osm.pbf
        │
        │  uv run tsp           (src/tsp/, the pipeline)
        ▼
output/<name>.parquet  ──────────────────────► QGIS  (uses output/<name>.qml)
        │                                            (SVG markers, see scripts/build_qml.py)
        │
        │  scripts/extract_sign_colors.py
        ├──► viz/data/sign_colors.json
        └──► viz/SIGN_CLASSIFICATION.md (auto-doc)
        │
        │  scripts/build_pmtiles.py  (uses sign_normalize.py)
        ▼
viz/data/<name>.pmtiles  ──────────────────────► viz/ (MapLibre, see viz/README.md)
```

Three layers of output: a **GeoParquet** for analysis & QGIS, a **PMTiles** for
the web viewer, and a colour-classification **JSON** that drives the web view's
dot colours and fallback labels.

## Setup

```bash
uv sync --extra dev          # create the venv and install everything
uv run pytest                # 13 tests: parsing + full pipeline
```

External tools needed for the viewer track:

- **`tippecanoe`** (only for `scripts/build_pmtiles.py`) — apt-installable on
  Ubuntu/Debian, or build from <https://github.com/felt/tippecanoe>.

## Run the pipeline

```bash
uv run tsp --input osm/bremen-latest.osm.pbf \
           --output output/bremen_signs.parquet
```

| Flag | Meaning |
| --- | --- |
| `--input, -i` | path to an `.osm.pbf` file |
| `--output, -o` | output GeoParquet path (default `output/traffic_signs.parquet`) |
| `--bbox, -b` | optional `minlon,minlat,maxlon,maxlat` clip |
| `--crs` | target metric EPSG code (default 25833, UTM 33N / Berlin) |
| `--keep-intermediate` | also write the node/way/zone layers as separate parquets next to the main output |

The output GeoParquet has the same columns as the original `traffic_signs`
table: `geom, country_code, sign_list, main_signs, direction, osm_id,
highway, source`.

### Pre-filtering large extracts with osmium (optional but recommended)

For anything bigger than a small region, pre-filter the PBF down to just the
features the pipeline reads — `traffic_sign` nodes/ways plus the highway
network they relate to. This typically shrinks the file by ~75 % and the
pipeline runtime by a similar factor:

```bash
osmium tags-filter osm/berlin-latest.osm.pbf \
    nw/traffic_sign \
    w/highway \
    --overwrite -o osm/berlin-filtered.osm.pbf

uv run tsp -i osm/berlin-filtered.osm.pbf -o output/berlin_signs.parquet
```

Berlin (94 MB → 25 MB; pipeline 5-10× faster). Requires `osmium` on `$PATH`
(`apt install osmium-tool`).

## Web viewer (MapLibre + PMTiles)

See [viz/README.md](viz/README.md). tl;dr from the repo root:

```bash
uv run python scripts/extract_sign_colors.py  # build the colour-classification JSON + docs
uv run python scripts/build_pmtiles.py        # bremen_signs.parquet → viz/data/bremen_signs.pmtiles
python3 -m http.server 8000 --directory viz   # open http://localhost:8000/
```

The SVG library (`viz/symbols/<country>/`) is committed in the repo — no
separate fetch step needed. Most SVGs are from
[SupaplexOSM](https://github.com/SupaplexOSM/traffic_sign_processing); a
few are hand-drawn in-tree for codes the upstream doesn't have.

Features: per-sign-type dot colours at low zoom, real StVO SVG icons at high
zoom rotated by `direction`, stacking of supplementary signs (Zusatzzeichen)
toggleable from the UI, permalinks (`?map=zoom/lat/lon`), fallback "grey
badge" with the raw sign code when an SVG isn't in the library.

## QGIS style (SVG sign symbols)

A QGIS QML style auto-loads when you drop the parquet into QGIS — both live in
`output/`. The QML reads SVGs from `viz/symbols/<country>/<code>.svg` using an
absolute path (configured to `\\wsl.localhost\Ubuntu\home\simon\osm_trafficsigns`
in this checkout — adjust in `scripts/build_qml.py` if your repo lives
elsewhere, then re-run the script).

Generate / regenerate the QML:

```bash
uv run python scripts/build_qml.py
```

It writes one `.qml` per parquet next to the parquet in `output/`.

## Sign classification

`scripts/extract_sign_colors.py` derives a `{fill, stroke, svg}` triple for
every sign code from two sources:

1. **The SVG library in `viz/symbols/<country>/`** — fills and strokes are scanned
   from each SVG, bucketed by hue, and mapped to one of five visual
   categories (blue, red ring, yellow, green, white/black).
2. **The parquet's `main_signs`/`sign_list` columns** — each unique code that
   doesn't already have a direct SVG match is resolved via family-walk
   (`274-30` → `274`), country-prefix stripping (`DE:274` → `274`), list-first
   (`1000-32;206` → `1000-32`), and bracket-notation (`274[30]` → `274-30`).
   Rules live in [`scripts/sign_normalize.py`](scripts/sign_normalize.py).

Output: [`viz/data/sign_colors.json`](viz/data/) (machine-readable, consumed
by the MapLibre viewer) and [`viz/SIGN_CLASSIFICATION.md`](viz/SIGN_CLASSIFICATION.md)
(human-readable, generated table per category).

Currently 141 SVGs in `viz/symbols/DE/` (133 from upstream SupaplexOSM + 8
hand-drawn in-repo). Family overrides (e.g. bare `241` → `241-30.svg`) are
hardcoded in `PREFERRED_FAMILY_VARIANT` at the top of the script.

## Project structure

```text
osm_trafficsigns/
├── src/tsp/              the pipeline (CLI = `uv run tsp`)
│   ├── cli.py            entry point
│   ├── parse.py          OSM tag parsing  (Lua: parse_traffic_sign)
│   ├── osmread.py        pyosmium handlers + node/way/zone routing
│   ├── nodes.py          standalone-sign processing  (SQL: traffic_sign_node)
│   ├── ways.py           sign-on-way → node placement (SQL: traffic_sign_way)
│   ├── zones.py          zone-entrance node placement (SQL: traffic_sign_zone)
│   ├── merge.py          three-way merge + dedup     (SQL: merge.sql)
│   └── signlist.py       OSM sign_list normalization (shared with scripts/)
├── scripts/              non-pipeline helpers
│   ├── extract_sign_colors.py  classify SVGs → sign_colors.json + SIGN_CLASSIFICATION.md
│   ├── build_pmtiles.py        parquet → PMTiles via tippecanoe (adds icon_code + stack columns)
│   ├── build_qml.py            generate QGIS QML styles
│   └── make_test_pbf.py        synthetic PBF generator used by the pipeline tests
├── osm/                  input PBFs (gitignored)
├── output/               parquet + QML (parquets gitignored)
├── viz/                  MapLibre web viewer — see viz/README.md
│   └── symbols/          SVG library (organized by country: DE/, AT/, ...)
├── tests/                pytest suite (parsing + end-to-end pipeline)
└── pyproject.toml
```

## Mapping the upstream layout

| Upstream | Here | Status |
| --- | --- | --- |
| `data_preparation_traffic_sign.sh` | `tsp/cli.py` | ✅ |
| `lua/osm_import_traffic_sign.lua` parsing | `tsp/parse.py` | ✅ tested |
| `lua/...` osm2pgsql tables/callbacks | `tsp/osmread.py` | ✅ |
| `sql/traffic_sign_node.sql` | `tsp/nodes.py` | ✅ |
| `sql/traffic_sign_way.sql` | `tsp/ways.py` | ✅ |
| `sql/traffic_sign_zone.sql` | `tsp/zones.py` | ✅ |
| `sql/merge.sql` | `tsp/merge.py` | ✅ |
| PostGIS `traffic_signs` table | GeoParquet output | — |

Each module's docstring contains the step-by-step SQL→GeoPandas port notes
(which `ST_*` function maps to which Shapely call, plus known gotchas).

## Getting a test extract

Geofabrik has ready-made regional `.osm.pbf` downloads — Bremen is ~20 MB,
the smallest German state, used as the dev testcase here:

```bash
mkdir -p osm
curl -L -o osm/bremen-latest.osm.pbf \
  https://download.geofabrik.de/europe/germany/bremen-latest.osm.pbf

uv run tsp -i osm/bremen-latest.osm.pbf -o output/bremen_signs.parquet
```

Or run the unit tests against a synthetic PBF generated by
[`scripts/make_test_pbf.py`](scripts/make_test_pbf.py) (this is what
`pytest` does internally):

```bash
uv run python scripts/make_test_pbf.py    # writes osm/test_signs.osm.pbf
uv run tsp -i osm/test_signs.osm.pbf -o output/test_signs.parquet
```

## Known correctness risks

- **Pipeline not yet diffed against PostGIS upstream.** Tested against a
  synthetic network only. Before production use, run both on the same extract
  and compare.
- **Coordinate rounding.** PostGIS compares vertices exactly; after
  reprojection the "same" OSM node may differ in the last digits. `ways.py` /
  `zones.py` snap coordinates to a tolerance — keep that tolerance consistent.
- **Performance.** The SQL leans on GiST indexes; every "within N metres"
  query in the port must use `GeoDataFrame.sindex`, or it won't scale beyond
  a suburb-sized extract.
- **Zone+regular sign mix in one OSM `traffic_sign` tag.** Upstream Lua
  splits these between the zone layer and the regular way layer, which loses
  the connection in the output. We override that for `zone_status='yes'`
  features (probable mapping mistake with `;`/`,`) and keep both halves in
  the way layer — see [src/tsp/osmread.py](src/tsp/osmread.py#L143).

## License

GPL-3.0-or-later, same as the upstream project.
