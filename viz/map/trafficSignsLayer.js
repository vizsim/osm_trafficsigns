// OSM traffic-signs source + three layers, all keyed on the `icon_code`
// feature property (built by scripts/build_pmtiles.py — the canonical sign
// code derived from sign_list, e.g. "274[30],..." -> "274-30").
//   - dots (circle) for zoom 9–ICON_MIN_ZOOM
//   - fallback-labels (symbol/text) for codes without a colour entry — shows
//     the raw code beside an extra-prominent amber dot so unmapped signs
//     stand out for inspection
//   - icons (symbol/SVG) for zoom ICON_MIN_ZOOM and up

import {
    trafficSignsConfig,
    trafficSignsStyle,
    trafficSignsDotsLayerId,
    trafficSignsFallbackLabelLayerId,
    trafficSignsIconsLayerId,
    trafficSignsOverlayTextLayerId,
    trafficSignsPrimaryFallbackLabelLayerId,
    trafficSignsStackIconLayerId,
    trafficSignsStackTextLayerId,
    trafficSignsStackFallbackLabelLayerId,
    trafficSignsLayerIds,
    ICON_MIN_ZOOM,
    STACK_DEPTH,
} from '../config.js';
import {
    addSourceIfMissing,
    addLayerIfMissing,
    setLayerVisibility,
} from './mapSafeOps.js';
import { STACK_TEXT_BOX_ID, OVERLAY_TEXT_BG_ID, HOVER_GLOW_ID } from '../utils/trafficSignIcons.js';

const trafficSignsHoverGlowPrimaryLayerId = 'osm-traffic-signs-hover-glow-primary';
const trafficSignsHoverGlowStackLayerId = (slot) => `osm-traffic-signs-hover-glow-stack-${slot}`;
// Filter used as the "no-op" / hidden state on hover-glow layers.
const NO_MATCH_FILTER = ['==', ['literal', 1], ['literal', 0]];

// OSM `direction` = bearing the sign's face points to (toward oncoming traffic).
// For map rendering we want the icon "lying flat" oriented along the driver's
// travel direction (so the icon reads upright when you look ALONG the road in
// the direction of travel) — that's `direction + 180`. Matches Supaplex's
// SVG rendering convention.
const DIRECTION_ROTATE_EXPR = [
    '%', ['+', ['number', ['get', 'direction'], 0], 180], 360,
];

export function addTrafficSignsSource(map) {
    addSourceIfMissing(map, trafficSignsConfig.sourceId, {
        type: 'vector',
        url: trafficSignsConfig.pmtiles,
    });
}

/**
 * MapLibre forbids more than one zoom-based subexpression per property — so we
 * can't put separate `interpolate(zoom)` blocks inside a `match`. Instead we
 * keep ONE outer `interpolate(zoom)` and use a `match` per zoom stop to pick
 * the known-vs-fallback value.
 *
 * Each stop pair is `[zoom, value]` where `value` is either a constant or a
 * `['match', key, ...known: knownValue, fallbackValue]` expression.
 */
function buildZoomMatchExpr(stops, knownCodes) {
    const flat = ['interpolate', ['linear'], ['zoom']];
    const key = ['to-string', ['get', 'icon_code']];
    for (const [zoom, knownValue, fallbackValue] of stops) {
        flat.push(zoom);
        if (!knownCodes?.length) {
            flat.push(fallbackValue);
            continue;
        }
        const matchExpr = ['match', key];
        for (const c of knownCodes) matchExpr.push(c, knownValue);
        matchExpr.push(fallbackValue);
        flat.push(matchExpr);
    }
    return flat;
}

function buildRadiusExpr(knownCodes) {
    return buildZoomMatchExpr(trafficSignsStyle.dotRadiusStops, knownCodes);
}

function buildStrokeWidthExpr(knownCodes) {
    return buildZoomMatchExpr(trafficSignsStyle.dotStrokeWidthStops, knownCodes);
}

function buildDotsSpec(signColors) {
    const defaults = {
        fill: trafficSignsStyle.dotColor,
        stroke: trafficSignsStyle.dotStrokeColor,
    };
    const colorExprs = signColors?.colorExpressions?.(defaults);
    const fill = colorExprs?.fillExpr ?? defaults.fill;
    const stroke = colorExprs?.strokeExpr ?? defaults.stroke;
    const knownCodes = signColors?.knownCodes ?? [];
    return {
        id: trafficSignsDotsLayerId,
        type: 'circle',
        source: trafficSignsConfig.sourceId,
        'source-layer': trafficSignsConfig.sourceLayer,
        minzoom: trafficSignsConfig.minzoom,
        maxzoom: ICON_MIN_ZOOM,
        paint: {
            'circle-color': fill,
            'circle-radius': buildRadiusExpr(knownCodes),
            'circle-stroke-color': stroke,
            'circle-stroke-width': buildStrokeWidthExpr(knownCodes),
            'circle-opacity': 0.95,
        },
    };
}

/**
 * Text layer that shows the raw `main_signs` code next to fallback dots.
 * Filtered to features whose code is NOT in the colors map.
 */
function buildFallbackLabelSpec(knownCodes) {
    const filter = knownCodes?.length
        ? ['!', ['in', ['to-string', ['get', 'icon_code']], ['literal', knownCodes]]]
        // No knownCodes loaded -> show labels for nothing (avoid visual noise).
        : ['==', 1, 0];
    return {
        id: trafficSignsFallbackLabelLayerId,
        type: 'symbol',
        source: trafficSignsConfig.sourceId,
        'source-layer': trafficSignsConfig.sourceLayer,
        minzoom: trafficSignsConfig.minzoom,
        maxzoom: ICON_MIN_ZOOM,
        filter,
        layout: {
            'text-field': ['to-string', ['get', 'icon_code']],
            'text-size': trafficSignsStyle.fallbackLabelSize,
            'text-anchor': 'left',
            'text-offset': [0.7, 0],
            'text-allow-overlap': false,
            'text-ignore-placement': false,
        },
        paint: {
            'text-color': trafficSignsStyle.fallbackLabelColor,
            'text-halo-color': trafficSignsStyle.fallbackLabelHalo,
            'text-halo-width': 1.4,
        },
    };
}

/**
 * Build the icon-size expression for the primary icons layer:
 * `interpolate(zoom, ..., match(code, perCode*scale, ..., fallback))`.
 *
 * MapLibre forbids zoom expressions below the top level of step/interpolate,
 * so we can't simply multiply two expressions — we have to bake the per-code
 * scale into each zoom stop. For codes without an explicit scale (scaleMap
 * miss), scale defaults to 1.0.
 */
function buildIconSizeExpr(stops, codesWithSvg, scaleMap = {}) {
    const expr = ['interpolate', ['linear'], ['zoom']];
    const key = ['to-string', ['get', 'icon_code']];
    for (const [zoom, knownValue, fallbackValue] of stops) {
        expr.push(zoom);
        if (!codesWithSvg?.length) {
            expr.push(fallbackValue);
            continue;
        }
        const matchExpr = ['match', key];
        for (const c of codesWithSvg) {
            const scale = scaleMap[c] ?? 1.0;
            matchExpr.push(c, knownValue * scale);
        }
        matchExpr.push(fallbackValue);
        expr.push(matchExpr);
    }
    return expr;
}

function buildIconsSpec(codesWithSvg, scaleMap) {
    return {
        id: trafficSignsIconsLayerId,
        type: 'symbol',
        source: trafficSignsConfig.sourceId,
        'source-layer': trafficSignsConfig.sourceLayer,
        minzoom: ICON_MIN_ZOOM,
        maxzoom: trafficSignsConfig.maxzoom,
        layout: {
            'icon-image': ['to-string', ['get', 'icon_code']],
            'icon-size': buildIconSizeExpr(trafficSignsStyle.iconSizeStops, codesWithSvg, scaleMap),
            'icon-rotate': DIRECTION_ROTATE_EXPR,
            'icon-rotation-alignment': 'map',
            'icon-allow-overlap': true,
            'icon-ignore-placement': true,
        },
        paint: {
            'icon-opacity': trafficSignsStyle.iconOpacity,
        },
    };
}

/**
 * Add all traffic-sign layers if not already present.
 *
 * @param {object} map
 * @param {import('../utils/signColors.js').SignColorBundle|null} [signColors]
 */
/**
 * Per-slot icon-offset (in icon-LOCAL pixels, zoom-interpolated). Multiplied
 * by icon-size at runtime AND rotated with icon-rotate, so stack items hang
 * in the sign's local "down" direction at every zoom.
 */
function buildSlotIconOffsetExpr(slot) {
    const stops = trafficSignsStyle.stackSlotIconOffsetStops[slot];
    const expr = ['interpolate', ['linear'], ['zoom']];
    for (const [zoom, px] of stops) {
        expr.push(zoom, ['literal', [0, px]]);
    }
    return expr;
}

/**
 * Per-slot text-offset (in EM, zoom-interpolated). Used together with
 * text-rotate=direction and text-rotation-alignment='map' so the offset
 * direction follows the sign's facing.
 */
function buildSlotTextOffsetExpr(slot) {
    const stops = trafficSignsStyle.stackSlotTextOffsetStops[slot];
    const expr = ['interpolate', ['linear'], ['zoom']];
    for (const [zoom, em] of stops) {
        expr.push(zoom, ['literal', [0, em]]);
    }
    return expr;
}

function buildStackIconSpec(slot) {
    const codeProp = `stack_${slot}_code`;
    return {
        id: trafficSignsStackIconLayerId(slot),
        type: 'symbol',
        source: trafficSignsConfig.sourceId,
        'source-layer': trafficSignsConfig.sourceLayer,
        minzoom: ICON_MIN_ZOOM,
        maxzoom: trafficSignsConfig.maxzoom,
        filter: ['!=', ['to-string', ['get', codeProp]], ''],
        layout: {
            // Default hidden — the "Zusatzzeichen anzeigen" toggle turns it on.
            visibility: 'none',
            'icon-image': ['to-string', ['get', codeProp]],
            'icon-size': trafficSignsStyle.stackIconSize,
            // Anchor at the icon's top so icon-offset lands on the top edge.
            'icon-anchor': 'top',
            // Stack items inherit the primary sign's facing direction.
            'icon-rotate': DIRECTION_ROTATE_EXPR,
            'icon-rotation-alignment': 'map',
            // icon-offset is in icon-LOCAL pixels (multiplied by icon-size).
            // Zoom-interpolated so the gap to the primary stays compact at
            // low zoom too. Rotates with icon-rotate, so a sign facing east
            // places its stack to the west (in the sign's own "down" dir),
            // not straight down on screen.
            'icon-offset': buildSlotIconOffsetExpr(slot),
            'icon-allow-overlap': true,
            'icon-ignore-placement': true,
        },
        paint: {
            'icon-opacity': 0.92,
        },
    };
}

function buildStackTextSpec(slot) {
    const textProp = `stack_${slot}_text`;
    return {
        id: trafficSignsStackTextLayerId(slot),
        type: 'symbol',
        source: trafficSignsConfig.sourceId,
        'source-layer': trafficSignsConfig.sourceLayer,
        minzoom: ICON_MIN_ZOOM,
        maxzoom: trafficSignsConfig.maxzoom,
        filter: ['!=', ['to-string', ['get', textProp]], ''],
        layout: {
            visibility: 'none',
            'text-field': ['to-string', ['get', textProp]],
            'text-size': trafficSignsStyle.stackTextSize,
            'text-anchor': 'top',
            // Rotate position + glyphs with the sign's facing.
            'text-rotate': DIRECTION_ROTATE_EXPR,
            'text-rotation-alignment': 'map',
            'text-offset': buildSlotTextOffsetExpr(slot),
            'text-allow-overlap': true,
            'text-ignore-placement': true,
            // White background box behind the text (icon-text-fit stretches
            // the box image to the text's bounding box plus padding).
            'icon-image': STACK_TEXT_BOX_ID,
            'icon-text-fit': 'both',
            'icon-text-fit-padding': [3, 6, 3, 6],     // top, right, bottom, left (px)
            'icon-rotate': DIRECTION_ROTATE_EXPR,
            'icon-rotation-alignment': 'map',
            'icon-allow-overlap': true,
            'icon-ignore-placement': true,
        },
        paint: {
            'text-color': trafficSignsStyle.stackTextColor,
            'text-halo-color': trafficSignsStyle.stackTextHalo,
            'text-halo-width': 0.6,
            'icon-opacity': 0.95,
        },
    };
}

/**
 * Build a small label layer that sits ABOVE a fallback (grey) icon so the
 * user can identify what sign code that fallback represents.
 *
 * `codeProp`            — feature property holding the sign code (e.g. `icon_code`
 *                          or `stack_1_code`)
 * `textOffsetExpr`      — zoom-interpolated text-offset expression in EM. Use a
 *                          NEGATIVE Y for primary (above feature center) or a
 *                          slightly-less-than-stack-text-offset for stack slots
 *                          (above the slot's icon).
 * `extraFilter`         — optional extra filter combined with "code set + not in
 *                          codesWithSvg".
 * `hiddenByDefault`     — set visibility:'none' so the supplementary toggle
 *                          controls it (used for stack slots).
 */
function buildFallbackTextLayer({ id, codeProp, textOffsetExpr, codesWithSvg, hiddenByDefault }) {
    const layout = {
        'text-field': ['to-string', ['get', codeProp]],
        'text-size': trafficSignsStyle.fallbackHighZoomTextSize,
        // Anchor at the text's centre so the label box sits ON TOP of the
        // grey fallback dot (the box covers most of the dot and reads as
        // the badge itself, instead of floating beside it).
        'text-anchor': 'center',
        // Rotate position + glyphs with the sign's facing so the label
        // stays oriented with the rotated icon group.
        'text-rotate': DIRECTION_ROTATE_EXPR,
        'text-rotation-alignment': 'map',
        'text-offset': textOffsetExpr,
        'text-allow-overlap': true,
        'text-ignore-placement': true,
        // White box behind the text (icon-text-fit stretches the box).
        'icon-image': STACK_TEXT_BOX_ID,
        'icon-text-fit': 'both',
        'icon-text-fit-padding': [3, 6, 3, 6],
        'icon-rotate': DIRECTION_ROTATE_EXPR,
        'icon-rotation-alignment': 'map',
        'icon-allow-overlap': true,
        'icon-ignore-placement': true,
    };
    if (hiddenByDefault) layout.visibility = 'none';
    return {
        id,
        type: 'symbol',
        source: trafficSignsConfig.sourceId,
        'source-layer': trafficSignsConfig.sourceLayer,
        minzoom: ICON_MIN_ZOOM,
        maxzoom: trafficSignsConfig.maxzoom,
        // Show only when the code is set AND not in codesWithSvg (i.e. the
        // icon is going to render as the grey fallback bitmap).
        filter: ['all',
            ['!=', ['to-string', ['get', codeProp]], ''],
            ['!', ['in', ['to-string', ['get', codeProp]], ['literal', codesWithSvg ?? []]]],
        ],
        layout,
        paint: {
            'text-color': trafficSignsStyle.stackTextColor,
            'text-halo-color': trafficSignsStyle.stackTextHalo,
            'text-halo-width': 0.6,
            'icon-opacity': 0.95,
        },
    };
}

/** EM offset for the primary fallback text: zero — primary icon is anchored
 *  at the feature centre (default), so text-anchor='center' + offset=[0,0]
 *  lands the label on the dot. */
function buildPrimaryFallbackTextOffsetExpr() {
    return ['literal', [0, 0]];
}

/** Zoom-interpolated EM offset for a STACK fallback text — landed at the
 *  stack icon's CENTRE so the code label sits ON the grey dot. */
function buildStackFallbackTextOffsetExpr(slot) {
    const stops = trafficSignsStyle.stackSlotFallbackTextOffsetStops[slot];
    const expr = ['interpolate', ['linear'], ['zoom']];
    for (const [zoom, em] of stops) {
        expr.push(zoom, ['literal', [0, em]]);
    }
    return expr;
}

function buildOverlayTextSpec() {
    return {
        id: trafficSignsOverlayTextLayerId,
        type: 'symbol',
        source: trafficSignsConfig.sourceId,
        'source-layer': trafficSignsConfig.sourceLayer,
        minzoom: ICON_MIN_ZOOM,
        maxzoom: trafficSignsConfig.maxzoom,
        // Only run for features that explicitly carry an overlay_text — built
        // by scripts/build_pmtiles.py from the shared-family-collapse logic
        // (e.g. 262-3.5 → icon_code "262" + overlay_text "3,5 t").
        filter: ['!=', ['to-string', ['get', 'overlay_text']], ''],
        layout: {
            'text-field': ['to-string', ['get', 'overlay_text']],
            'text-size': trafficSignsStyle.overlayTextSize,
            'text-anchor': 'center',
            'text-allow-overlap': true,
            'text-ignore-placement': true,
            // Match the primary icon's rotation so the overlay travels with
            // the sign (so "3,5 t" sits inside the rotated 262 ring).
            'text-rotate': DIRECTION_ROTATE_EXPR,
            'text-rotation-alignment': 'map',
            'text-font': ['Noto Sans Bold'],
            // Solid white pill behind the text — covers the SVG's printed
            // "5,5" cleanly. icon-text-fit stretches the round image so
            // for "3,5 t" we get a horizontal pill, for single-digit "6"
            // we get a near-circle. 9-slice keeps the ends round.
            'icon-image': OVERLAY_TEXT_BG_ID,
            'icon-text-fit': 'both',
            'icon-text-fit-padding': trafficSignsStyle.overlayTextFitPadding,
            'icon-rotate': DIRECTION_ROTATE_EXPR,
            'icon-rotation-alignment': 'map',
            'icon-allow-overlap': true,
            'icon-ignore-placement': true,
        },
        paint: {
            'text-color': trafficSignsStyle.overlayTextColor,
            'icon-opacity': 1.0,
        },
    };
}

/**
 * Hover-glow layers — render a soft amber circle BELOW the icon/dot. Filter
 * defaults to no-match; setHoverState updates it to the hovered code/text so
 * a single feature lights up.
 */
function buildHoverGlowPrimarySpec() {
    return {
        id: trafficSignsHoverGlowPrimaryLayerId,
        type: 'symbol',
        source: trafficSignsConfig.sourceId,
        'source-layer': trafficSignsConfig.sourceLayer,
        minzoom: trafficSignsConfig.minzoom,
        maxzoom: trafficSignsConfig.maxzoom,
        filter: NO_MATCH_FILTER,
        layout: {
            'icon-image': HOVER_GLOW_ID,
            // Sized roughly to be slightly larger than the icon/dot at each
            // zoom so it haloes the sign rather than disappearing under it.
            // The z22 stop clamps growth past z18 (same reason as iconSizeStops).
            'icon-size': ['interpolate', ['linear'], ['zoom'],
                9, 0.10,
                12, 0.18,
                ICON_MIN_ZOOM, 0.38,
                15, 0.62,
                18, 1.25,
                22, 1.25,
            ],
            'icon-allow-overlap': true,
            'icon-ignore-placement': true,
        },
        paint: {
            'icon-opacity': 0.9,
        },
    };
}

// Typical Zusatzschild SVG half-height in icon-local px. Most Zusatzschilder
// are 600×300-ish wide rectangles (e.g. 1008-34 is 600×330, 1010-XX similar),
// so 150 is a good approximation. Square supplementary codes (e.g. 244.1,
// 283-XX) end up with the glow ~30 px above their centre at z18; the glow is
// fuzzy enough that this is acceptable.
const STACK_ICON_SVG_HALF = 150;
// CONSTANT ratio between glow icon-size and stack icon-size at every zoom.
// Critical for correctness: if the ratio varied with zoom, MapLibre's linear
// interpolation between stops would land the glow off-centre at intermediate
// zooms (because the product of two linearly-interpolated values isn't itself
// linearly interpolated). Picking ~3.75 makes the glow about 1.6× wider than
// the stack icon on screen — 256-px glow bitmap × (3.75 × stackSize) ≈
// 1.6 × 600-px sign SVG × stackSize.
const STACK_GLOW_SIZE_RATIO = 3.75;

/** Extract `[[z, v], ...]` from a `['interpolate', 'linear', ['zoom'], z, v, ...]` */
function stopsFromInterpolate(expr) {
    const out = [];
    for (let i = 3; i < expr.length; i += 2) out.push([expr[i], expr[i + 1]]);
    return out;
}

/**
 * Build the glow stack icon-size as EXACTLY `STACK_GLOW_SIZE_RATIO × stackIconSize`
 * at every zoom stop. Constant ratio is required for the offset math below to
 * stay valid under MapLibre's linear-between-stops interpolation.
 */
function buildGlowStackSizeExpr() {
    const stackStops = stopsFromInterpolate(trafficSignsStyle.stackIconSize);
    const expr = ['interpolate', ['linear'], ['zoom']];
    for (const [z, v] of stackStops) {
        expr.push(z, v * STACK_GLOW_SIZE_RATIO);
    }
    return expr;
}

/**
 * Glow-offset stops for a stack slot, computed so the glow's CENTRE (anchor
 * 'center') lands exactly on the stack icon's CENTRE at every zoom — including
 * zooms BETWEEN the stops, thanks to constant `STACK_GLOW_SIZE_RATIO`.
 *
 *   stack_center_screen = (stack_offset + 300) × stackSize
 *   glow_center_screen  = glow_offset × glowSize
 *                       = glow_offset × (STACK_GLOW_SIZE_RATIO × stackSize)
 *   ⇒ glow_offset = (stack_offset + 300) / STACK_GLOW_SIZE_RATIO
 */
function buildGlowStackOffsetExpr(slot) {
    const stackOffsetStops = trafficSignsStyle.stackSlotIconOffsetStops[slot];
    const expr = ['interpolate', ['linear'], ['zoom']];
    for (const [z, stackOffset] of stackOffsetStops) {
        const glowOffset = (stackOffset + STACK_ICON_SVG_HALF) / STACK_GLOW_SIZE_RATIO;
        expr.push(z, ['literal', [0, glowOffset]]);
    }
    return expr;
}

function buildHoverGlowStackSpec(slot) {
    return {
        id: trafficSignsHoverGlowStackLayerId(slot),
        type: 'symbol',
        source: trafficSignsConfig.sourceId,
        'source-layer': trafficSignsConfig.sourceLayer,
        minzoom: ICON_MIN_ZOOM,
        maxzoom: trafficSignsConfig.maxzoom,
        filter: NO_MATCH_FILTER,
        layout: {
            'icon-image': HOVER_GLOW_ID,
            'icon-size': buildGlowStackSizeExpr(),
            // anchor=center + computed offset puts the glow centre exactly on
            // the stack icon centre. (Stack icon itself uses anchor=top.)
            'icon-anchor': 'center',
            'icon-offset': buildGlowStackOffsetExpr(slot),
            'icon-rotate': DIRECTION_ROTATE_EXPR,
            'icon-rotation-alignment': 'map',
            'icon-allow-overlap': true,
            'icon-ignore-placement': true,
        },
        paint: {
            'icon-opacity': 0.9,
        },
    };
}

export function addTrafficSignsLayer(map, signColors = null) {
    const codesWithSvg = signColors?.codesWithSvg ?? [];

    // Primary glow sits at the BOTTOM of the traffic-sign stack so it haloes
    // dots/icons rather than covering them.
    addLayerIfMissing(map, buildHoverGlowPrimarySpec());
    addLayerIfMissing(map, buildDotsSpec(signColors));
    addLayerIfMissing(map, buildFallbackLabelSpec(signColors?.knownCodes ?? []));
    addLayerIfMissing(map, buildIconsSpec(codesWithSvg, signColors?.scaleMap));
    addLayerIfMissing(map, buildOverlayTextSpec());
    // Primary fallback label sits ABOVE the grey fallback icon when icon_code
    // is unmapped. Not gated by the supplementary toggle — part of primary.
    addLayerIfMissing(map, buildFallbackTextLayer({
        id: trafficSignsPrimaryFallbackLabelLayerId,
        codeProp: 'icon_code',
        textOffsetExpr: buildPrimaryFallbackTextOffsetExpr(),
        codesWithSvg,
        hiddenByDefault: false,
    }));
    // Stack layers: glow first (so it sits below the icon), then icons
    // (so text sits above them in z-order), then text-replacement layers,
    // then fallback labels for slot icons.
    for (let slot = 1; slot <= STACK_DEPTH; slot++) {
        addLayerIfMissing(map, buildHoverGlowStackSpec(slot));
    }
    for (let slot = 1; slot <= STACK_DEPTH; slot++) {
        addLayerIfMissing(map, buildStackIconSpec(slot));
    }
    for (let slot = 1; slot <= STACK_DEPTH; slot++) {
        addLayerIfMissing(map, buildStackTextSpec(slot));
    }
    for (let slot = 1; slot <= STACK_DEPTH; slot++) {
        addLayerIfMissing(map, buildFallbackTextLayer({
            id: trafficSignsStackFallbackLabelLayerId(slot),
            codeProp: `stack_${slot}_code`,
            textOffsetExpr: buildStackFallbackTextOffsetExpr(slot),
            codesWithSvg,
            hiddenByDefault: true,   // tied to the "Zusatzzeichen anzeigen" toggle
        }));
    }
}

/** Primary layers — dots, fallback labels, icons, primary fallback label.
 *  Always governed by the main "Verkehrszeichen anzeigen" toggle. */
const primaryLayerIds = [
    trafficSignsHoverGlowPrimaryLayerId,
    trafficSignsDotsLayerId,
    trafficSignsFallbackLabelLayerId,
    trafficSignsIconsLayerId,
    trafficSignsOverlayTextLayerId,
    trafficSignsPrimaryFallbackLabelLayerId,
];

/** Stack (supplementary) layers — icon, text, fallback label per slot.
 *  Governed by the "Zusatzzeichen anzeigen" sub-toggle. */
const supplementaryLayerIds = (() => {
    const ids = [];
    for (let i = 1; i <= STACK_DEPTH; i++) {
        ids.push(trafficSignsHoverGlowStackLayerId(i));
        ids.push(trafficSignsStackIconLayerId(i));
        ids.push(trafficSignsStackTextLayerId(i));
        ids.push(trafficSignsStackFallbackLabelLayerId(i));
    }
    return ids;
})();

/**
 * Update visibility for both layer groups.
 *
 * @param {boolean} main          — primary layers (dots, fallback, icons)
 * @param {boolean} supplementary — stack layers (only effective when main is on)
 */
export function setTrafficSignsVisibility(map, { main, supplementary }) {
    for (const id of primaryLayerIds) setLayerVisibility(map, id, main);
    const stackVisible = main && supplementary;
    for (const id of supplementaryLayerIds) setLayerVisibility(map, id, stackVisible);
}

// ─── Hover / hide interactions (driven by the top-N counter rows) ──────────

function hasLayer(map, id) {
    try { return Boolean(map.getLayer(id)); } catch { return false; }
}

/**
 * Light up the hover-glow halo for the sign(s) whose code/text the user is
 * hovering. Driven by setFilter — cheap per-frame work.
 *
 * @param {object|null} hovered — `null` to clear, or
 *        `{section: 'primary'|'stack', kind: 'code'|'text', value: string}`
 */
export function setHoverState(map, hovered) {
    const primaryMatch = (hovered?.section === 'primary' && hovered.kind === 'code') ? hovered.value : null;
    const stackCodeMatch = (hovered?.section === 'stack' && hovered.kind === 'code') ? hovered.value : null;
    const stackTextMatch = (hovered?.section === 'stack' && hovered.kind === 'text') ? hovered.value : null;

    if (hasLayer(map, trafficSignsHoverGlowPrimaryLayerId)) {
        const filter = primaryMatch
            ? ['==', ['to-string', ['get', 'icon_code']], primaryMatch]
            : NO_MATCH_FILTER;
        map.setFilter(trafficSignsHoverGlowPrimaryLayerId, filter);
    }

    for (let slot = 1; slot <= STACK_DEPTH; slot++) {
        const layerId = trafficSignsHoverGlowStackLayerId(slot);
        if (!hasLayer(map, layerId)) continue;
        let filter = NO_MATCH_FILTER;
        if (stackCodeMatch) {
            filter = ['==', ['to-string', ['get', `stack_${slot}_code`]], stackCodeMatch];
        } else if (stackTextMatch) {
            filter = ['==', ['to-string', ['get', `stack_${slot}_text`]], stackTextMatch];
        }
        map.setFilter(layerId, filter);
    }
}

/** Build an `in` membership check, or `null` for an empty set. */
function inExpr(prop, values) {
    if (!values?.length) return null;
    return ['in', ['to-string', ['get', prop]], ['literal', values]];
}

/** Wrap a base opacity with a "0 if hidden, else base" case. */
function hiddenOpacity(base, check) {
    if (!check) return base;
    return ['case', check, 0, base];
}

function applyOp(map, layerId, prop, baseValue, check) {
    if (!hasLayer(map, layerId)) return;
    map.setPaintProperty(layerId, prop, hiddenOpacity(baseValue, check));
}

/**
 * Hide selected codes/texts by driving their layer opacities to zero.
 *
 * @param {object} hidden — `{ primary: string[], stackCodes: string[], stackTexts: string[] }`
 */
export function setHiddenState(map, { primary = [], stackCodes = [], stackTexts = [] } = {}) {
    const primaryCheck = inExpr('icon_code', primary);

    applyOp(map, trafficSignsIconsLayerId, 'icon-opacity', trafficSignsStyle.iconOpacity, primaryCheck);
    applyOp(map, trafficSignsDotsLayerId, 'circle-opacity', 0.95, primaryCheck);
    applyOp(map, trafficSignsFallbackLabelLayerId, 'text-opacity', 1.0, primaryCheck);
    applyOp(map, trafficSignsPrimaryFallbackLabelLayerId, 'text-opacity', 1.0, primaryCheck);
    applyOp(map, trafficSignsPrimaryFallbackLabelLayerId, 'icon-opacity', 0.95, primaryCheck);
    applyOp(map, trafficSignsOverlayTextLayerId, 'text-opacity', 1.0, primaryCheck);
    applyOp(map, trafficSignsOverlayTextLayerId, 'icon-opacity', 1.0, primaryCheck);

    for (let slot = 1; slot <= STACK_DEPTH; slot++) {
        const codeCheck = inExpr(`stack_${slot}_code`, stackCodes);
        const textCheck = inExpr(`stack_${slot}_text`, stackTexts);

        applyOp(map, trafficSignsStackIconLayerId(slot), 'icon-opacity', 0.92, codeCheck);
        applyOp(map, trafficSignsStackFallbackLabelLayerId(slot), 'text-opacity', 1.0, codeCheck);
        applyOp(map, trafficSignsStackFallbackLabelLayerId(slot), 'icon-opacity', 0.95, codeCheck);
        applyOp(map, trafficSignsStackTextLayerId(slot), 'text-opacity', 1.0, textCheck);
        applyOp(map, trafficSignsStackTextLayerId(slot), 'icon-opacity', 0.95, textCheck);
    }
}
