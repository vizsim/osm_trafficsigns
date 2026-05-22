# viz — MapLibre + PMTiles preview

Browser-based viewer for the OSM traffic-sign parquet. Stack:

- **MapLibre GL JS** (CDN) for the map
- **PMTiles** (`felt/tippecanoe` → `.pmtiles`, served as a static file)
- **OpenFreeMap Positron / Dark** as basemap
- StVO sign SVGs from [SupaplexOSM](https://github.com/SupaplexOSM/traffic_sign_processing),
  loaded lazily via MapLibre's `styleimagemissing` event

## One-time setup (from repo root)

```bash
# 1. Build the sign-colour classification (JSON + auto-generated doc)
uv run python scripts/extract_sign_colors.py

# 2. Build the PMTiles from output/bremen_signs.parquet
uv run python scripts/build_pmtiles.py
```

The SVG library lives in `viz/symbols/<country>/` (committed in-repo, no fetch
step needed). Step 2 requires `tippecanoe` on `$PATH` — `apt`-installable
on Ubuntu/Debian, or build from source: <https://github.com/felt/tippecanoe>.

To target a different parquet:

```bash
uv run python scripts/build_pmtiles.py <parquet-basename>
# e.g. scripts/build_pmtiles.py munich_signs → viz/data/munich_signs.pmtiles
```

## Run locally

```bash
python3 -m http.server 8000 --directory viz
# open http://localhost:8000/
```

Or from the repo root, serving the whole tree:

```bash
python3 -m http.server 8000
# open http://localhost:8000/viz/
```

The viewer auto-detects which prefix it's being served from (via
`new URL('./', window.location.href)`), so both work.

## Layout

```text
viz/
├── index.html               entry HTML
├── script.js                map init + UI wiring
├── style.css
├── config.js                basemap URLs, source/layer ids, sizing curves, stack offsets
├── map/
│   ├── mapSafeOps.js        defensive add/remove helpers
│   └── trafficSignsLayer.js source + 11 symbol/circle layer specs (see below)
├── utils/
│   ├── trafficSignIcons.js  styleimagemissing handler + default-icon bitmap + text-box bitmap
│   ├── signColors.js        loads sign_colors.json → MapLibre `match` expressions
│   └── permalink.js         ?map=zoom/lat/lon URL sync
├── symbols/                 SVG library (StVO sign icons, organized by country)
├── data/                    PMTiles + sign_colors.json (PMTiles + JSON tracked)
└── SIGN_CLASSIFICATION.md   auto-generated per-sign colour reference
```

## Features

### Layers (11 total)

The viewer builds three groups of layers, all keyed on a normalized
`icon_code` feature property (computed in `scripts/build_pmtiles.py` so
combinations like `DE:274[30],"Altenheim","Schule"` resolve to `274-30`):

```text
zoom 9–13   primary dots  (circle, colored by sign category)
            fallback labels (text next to dot for unmapped codes)

zoom 13+    primary icon (SVG, rotated by `direction`)
            primary fallback label (code badge on grey dot when no SVG)

            stack 1 icon (SVG slot 1 — offset down in sign-local frame)
            stack 1 text (white-box label slot 1 — for free-text annotations)
            stack 1 fallback label (code badge on grey dot, slot 1)
            ...same for stack 2 and stack 3
```

Stack layers are gated by the **"Zusatzzeichen anzeigen"** sub-toggle in the
UI (default off — primary only). Stack items render in the sign's local
"down" direction so they hang from the rotated primary like supplementary
plates on a real signpost.

### Sign colour classification

The dots layer's `circle-color` / `circle-stroke-color` use MapLibre `match`
expressions built from `viz/data/sign_colors.json` at load time. Each known
sign code maps to one of five visual categories — see
[SIGN_CLASSIFICATION.md](SIGN_CLASSIFICATION.md) for the per-code table:

| Category | Fill | Stroke | Example codes |
| --- | --- | --- | --- |
| Vorschrift / Information | `#1953a4` blue | `#ffffff` | 237, 240, 244, 325 |
| Verbot / Warnung | `#ffffff` | `#dc1414` red ring | 274, 101, 250, 260 |
| Wegweiser | `#fcd116` yellow | `#1a1a1a` | (yellow guide signs) |
| Autobahn | `#1a7f3c` green | `#ffffff` | (motorway-info) |
| Zusatzzeichen | `#ffffff` | `#1a1a1a` | 1000-*, 1022-10 |

Unmatched codes fall back to a **grey** dot (`#d1d5db`) — distinct from the
yellow category so real yellow signs don't get confused with fallbacks. At
high zoom the grey dot carries the raw code as a white-box badge so you can
identify the sign.

### Sign-icon resolution at high zoom

For codes that *have* an SVG in the library, the `styleimagemissing` handler
([utils/trafficSignIcons.js](utils/trafficSignIcons.js)) fetches it lazily
the first time MapLibre asks for that image id. The same JSON also exposes
a `svg` alias per code so e.g. bare `244` renders as `244.1.svg` (the only
244-variant) and `274[30]` renders as `274-30.svg`.

For codes *without* an SVG, the handler registers a generic 200×200 grey
circle under that id — that's the fallback bitmap.

### Permalinks

Pan/zoom writes the current view back to `?map=zoom/lat/lon` via
[utils/permalink.js](utils/permalink.js) (e.g. `?map=14/53.08/8.81`). Sharing
a URL deep-links to that view on load. Lifted 1:1 from the
[mapillary_coverage_analysis](https://github.com/vizsim/mapillary_coverage_analysis)
reference project.

### Other UI

- **Dark mode toggle** (bottom-left) — re-applies all layers on style change
- **Info-panel toggle** (bottom-left "i") — show/hide the legend panel
- **Click any sign** — popup with `sign_list`, `highway`, `direction`, OSM link

## Customisation

Most knobs live in [config.js](config.js):

| Setting | What |
| --- | --- |
| `ICON_MIN_ZOOM` | Zoom at which dots → icons (default `13`) |
| `STACK_DEPTH` | Max stack items rendered per feature (default `3`) — must match `STACK_DEPTH` in `scripts/build_pmtiles.py` |
| `trafficSignsStyle.iconSizeStops` | Per-zoom SVG icon size |
| `trafficSignsStyle.stackIconSize` | Per-zoom stack icon size (smaller than primary) |
| `trafficSignsStyle.stackSlotIconOffsetStops` | Per-slot, per-zoom offset of stack items below the primary |
| `trafficSignsStyle.stackSlotFallbackTextOffsetStops` | Per-slot, per-zoom offset of the code badge on a fallback dot |
| `trafficSignsStyle.dotColor` / `dotStrokeColor` | Fallback dot colour |
| `initialMapConfig.center` / `.zoom` | Default view when no permalink |

When you add new SVGs to `viz/symbols/<country>/`, re-run
`scripts/extract_sign_colors.py` to refresh the JSON + classification doc.
