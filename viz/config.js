// Viz config for OSM Traffic Signs MapLibre app.

const PMTILES_PREFIX = 'pmtiles://';
// Resolve URLs relative to the index.html location, so the app works whether
// the dev server's root is the repo root (http://host/viz/) or viz/ itself
// (http://host/). `new URL('./', href)` gives the directory of the current page.
const docBase = typeof window !== 'undefined'
    ? new URL('./', window.location.href).href
    : './';

export const mapStyles = {
    light: 'https://tiles.openfreemap.org/styles/positron',
    dark: 'https://tiles.openfreemap.org/styles/dark',
};

export const mapAttribution =
    'MapLibre | Schilder: © OpenStreetMap-Mitwirkende, Symbole: ' +
    '<a href="https://github.com/SupaplexOSM/traffic_sign_processing" target="_blank" rel="noopener">SupaplexOSM</a>';

export const initialMapConfig = {
    // Berlin Mitte — overview at zoom 11 so the whole dataset is visible.
    center: [13.404, 52.520],
    zoom: 11,
};

/** Zoom threshold: dots below, SVG icons at and above. */
export const ICON_MIN_ZOOM = 13;

/** How many additional sign-list items to render below the primary icon.
 *  Must match STACK_DEPTH in scripts/build_pmtiles.py. */
export const STACK_DEPTH = 3;

export const trafficSignsConfig = {
    sourceId: 'osm-traffic-signs',
    sourceLayer: 'traffic_signs',
    pmtiles: `${PMTILES_PREFIX}${docBase}data/berlin_signs.pmtiles`,
    minzoom: 9,
    maxzoom: 22,
    // Resolved relative to this file (viz/config.js), so it always points to
    // <repo-root>/symbols/ regardless of where viz/ is served from. Avoids the
    // need for the viz/symbols → ../symbols dev-time symlink (which static
    // hosts like GitHub Pages don't follow).
    iconBaseUrl: new URL('../symbols/', import.meta.url).href,
    defaultIconId: 'traffic-sign-default',
};

export const trafficSignsStyle = {
    // SVG icon-size stops as [zoom, sizeWithSvg, sizeFallback]. Codes that
    // resolve to a real SVG render at the smaller size; codes that fall back
    // to the amber default circle render ~50% larger so they stand out for
    // inspection (the user explicitly asked for this — fallbacks were too
    // tiny to notice). Built into a single interpolate(zoom) + nested match
    // in trafficSignsLayer.js.
    // The z22 row duplicates z18 — it clamps the linear interpolation so
    // MapLibre doesn't extrapolate aggressively beyond z18 (which would
    // make icons balloon and spread the stack far apart at maxZoom 21.9).
    iconSizeStops: [
        [ICON_MIN_ZOOM, 0.094, 0.153],
        [15, 0.153, 0.230],
        [18, 0.306, 0.476],
        [22, 0.306, 0.476],
    ],
    iconOpacity: 0.95,
    // Default dot styling — used when the code has no entry in sign_colors.json.
    // Grey (not amber) because amber is reserved for real yellow signs (e.g.
    // city-limit "Ortstafel"). Fallback dots are intentionally larger so
    // unmapped codes still stand out for inspection.
    dotColor: '#d1d5db',
    dotStrokeColor: '#1f2937',
    // Per-zoom stops as [zoom, valueForKnownCodes, valueForFallback].
    // Built into a single interpolate(zoom) + nested match in trafficSignsLayer.js
    // (MapLibre forbids more than one zoom-based subexpression per property).
    dotRadiusStops: [
        [9, 1.6, 2.4],
        [12, 3.0, 4.5],
        [ICON_MIN_ZOOM, 3.5, 5.5],
    ],
    dotStrokeWidthStops: [
        [9, 0.4, 0.6],
        [12, 0.8, 1.0],
        [ICON_MIN_ZOOM, 1.0, 1.2],
    ],
    // Fallback text label (code shown beside the grey dot).
    fallbackLabelColor: '#1f2937',
    fallbackLabelHalo: '#ffffff',
    fallbackLabelSize: [
        'interpolate', ['linear'], ['zoom'],
        9, 9,
        12, 10,
        ICON_MIN_ZOOM, 11,
    ],
    // Fallback labels at zoom ≥ ICON_MIN_ZOOM sit centered ON the grey icon
    // (the box covers most of the dot so the code reads as the badge itself).
    fallbackHighZoomTextSize: 11,
    // Stack-slot fallback text-offset (in EM) calibrated to land the text
    // centre at the slot icon's centre — i.e. on the dot, not above it.
    //   text-offset_em = (icon-offset_local + 100) × stackIconSize / textSize
    // (the +100 accounts for the 200×200 bitmap rendering with anchor=top,
    // so the centre is half the bitmap height below the offset point.)
    stackSlotFallbackTextOffsetStops: {
        1: [
            [ICON_MIN_ZOOM, 1.68],
            [15, 2.96],
            [17.5, 6.4],
            [18, 7.2],
            [22, 7.2],
        ],
        2: [
            [ICON_MIN_ZOOM, 2.56],
            [15, 4.78],
            [17.5, 10.61],
            [18, 12.09],
            [22, 12.09],
        ],
        3: [
            [ICON_MIN_ZOOM, 3.44],
            [15, 6.60],
            [17.5, 14.87],
            [18, 17.03],
            [22, 17.03],
        ],
    },
    // ----- Stack styling (sign_list items 2..N rendered below the primary) -----
    // Stack items are drawn slightly smaller than the primary so the primary
    // remains visually dominant. Code items render as icons, text items as
    // labels — both placed at the same screen offset per slot via *-translate.
    stackIconSize: [
        'interpolate', ['linear'], ['zoom'],
        ICON_MIN_ZOOM, 0.068,
        15, 0.111,
        18, 0.204,
        22, 0.204,   // clamp beyond z18 — see iconSizeStops comment
    ],
    stackTextSize: [
        'interpolate', ['linear'], ['zoom'],
        ICON_MIN_ZOOM, 10,
        18, 14,
        22, 14,
    ],
    stackTextColor: '#1a1a1a',
    stackTextHalo: '#ffffff',
    // Overlay text rendered on top of icons of `SHARED_FAMILY_BASES` codes
    // (e.g. "3,5 t" on a 262 sign that means a 3.5 t weight limit). Sized
    // to sit comfortably inside the sign's white area without touching the
    // red ring (~20% of the icon's on-screen diameter).
    overlayTextSize: [
        'interpolate', ['linear'], ['zoom'],
        ICON_MIN_ZOOM, 16,
        15, 24,
        18, 48,
    ],
    overlayTextColor: '#1a1a1a',
    // Padding around the overlay text for icon-text-fit on the pill bg.
    // Small values keep the pill snug around the text.
    overlayTextFitPadding: [2, 5, 2, 5],
    // Per-slot icon-offset in the icon's LOCAL pixel space (rotates with
    // icon-rotate=direction, so stack items hang in the sign's own "down"
    // direction). The value is multiplied by stackIconSize internally; we
    // want each slot's *screen* offset to be roughly:
    //   primaryRadius + cumulativeStackHeights + smallGap
    // Since primary/stack icon-size ratios are roughly constant across zoom,
    // a single icon-offset value works at every zoom.
    // Per-slot icon-offset, ZOOM-INTERPOLATED so the on-screen distance
    // between primary and stack stays compact across zooms. (A single
    // value scaled only by icon-size made the gap balloon at low zoom.)
    // Values are in icon-LOCAL pixels (rotates with icon-rotate).
    // Delta between slots reduced by factor 0.65 so all 3 stack items fit
    // closer to the primary at high zoom (target ≈ 55 px screen gap at z18+).
    stackSlotIconOffsetStops: {
        1: [
            [ICON_MIN_ZOOM, 104],
            [15, 169],
            [17.5, 273],
            [18, 301],
            [22, 301],
        ],
        2: [
            [ICON_MIN_ZOOM, 208],
            [15, 328],
            [17.5, 512],
            [18, 570],
            [22, 570],
        ],
        3: [
            [ICON_MIN_ZOOM, 312],
            [15, 487],
            [17.5, 756],
            [18, 839],
            [22, 839],
        ],
    },
    // Matching text-offset stops in EM (multiplied by text-size).
    stackSlotTextOffsetStops: {
        1: [
            [ICON_MIN_ZOOM, 1.28],
            [15, 2.08],
            [17.5, 4.64],
            [18, 5.44],
            [22, 5.44],
        ],
        2: [
            [ICON_MIN_ZOOM, 2.53],
            [15, 3.95],
            [17.5, 8.90],
            [18, 10.38],
            [22, 10.38],
        ],
        3: [
            [ICON_MIN_ZOOM, 3.78],
            [15, 5.82],
            [17.5, 13.06],
            [18, 15.27],
            [22, 15.27],
        ],
    },
};

export const trafficSignsDotsLayerId = 'osm-traffic-signs-dots';
export const trafficSignsFallbackLabelLayerId = 'osm-traffic-signs-fallback-labels';
export const trafficSignsIconsLayerId = 'osm-traffic-signs-symbols';
export const trafficSignsOverlayTextLayerId = 'osm-traffic-signs-overlay-text';
export const trafficSignsPrimaryFallbackLabelLayerId = 'osm-traffic-signs-primary-fallback-label';
export const trafficSignsStackIconLayerId = (slot) => `osm-traffic-signs-stack-${slot}-icon`;
export const trafficSignsStackTextLayerId = (slot) => `osm-traffic-signs-stack-${slot}-text`;
export const trafficSignsStackFallbackLabelLayerId = (slot) => `osm-traffic-signs-stack-${slot}-fallback-label`;

const stackLayerIds = [];
for (let i = 1; i <= STACK_DEPTH; i++) {
    stackLayerIds.push(trafficSignsStackIconLayerId(i));
    stackLayerIds.push(trafficSignsStackTextLayerId(i));
    stackLayerIds.push(trafficSignsStackFallbackLabelLayerId(i));
}

export const trafficSignsLayerIds = [
    trafficSignsDotsLayerId,
    trafficSignsFallbackLabelLayerId,
    trafficSignsIconsLayerId,
    trafficSignsOverlayTextLayerId,
    trafficSignsPrimaryFallbackLabelLayerId,
    ...stackLayerIds,
];
