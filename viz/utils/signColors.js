// Load per-sign color + svg-alias lookups (built by scripts/extract_sign_colors.py).
// Exposes:
//   - rawMap:     the underlying { code -> {fill, stroke, svg} } object
//   - knownCodes: list of all keys (used to filter the fallback text layer)
//   - svgAlias(): code -> svg basename (used by the icon handler)
//   - colorExpressions(defaults): MapLibre match expressions for paint props

const COLORS_URL = new URL('../data/sign_colors.json', import.meta.url).href;

/**
 * @returns {Promise<SignColorBundle | null>} null when JSON fetch fails.
 *
 * @typedef {Object} SignColorBundle
 * @property {Record<string, {fill:string, stroke:string, svg:string}>} rawMap
 * @property {string[]} knownCodes
 * @property {(code: string) => string | undefined} svgAlias
 * @property {(defaults: {fill:string, stroke:string}) => {fillExpr:any, strokeExpr:any}} colorExpressions
 */
export async function loadSignColors() {
    try {
        const res = await fetch(COLORS_URL);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const rawMap = await res.json();
        const knownCodes = Object.keys(rawMap);
        // Codes that resolve to a *real* SVG icon at zoom ≥ICON_MIN_ZOOM.
        // Codes in `knownCodes` but NOT here will render as the default
        // amber circle and need bigger icon-size so they remain prominent.
        const codesWithSvg = knownCodes.filter((c) => typeof rawMap[c]?.svg === 'string');
        return {
            rawMap,
            knownCodes,
            codesWithSvg,
            svgAlias: (code) => rawMap[code]?.svg,
            // Full entry lookup — used by the styleimagemissing handler to
            // generate a coloured fallback bitmap for codes that have a
            // colour assignment but no SVG (e.g. `310` Ortstafel).
            colorLookup: (code) => rawMap[code],
            colorExpressions: (defaults) => buildColorExpressions(rawMap, defaults),
            // Per-code icon-size scale (derived from each SVG's viewBox max
            // dimension). Wide signs (e.g. 449 = 4374×4656) have scale < 1.0
            // so they don't dwarf the square StVO signs. Plain JS map for
            // callers to bake into their own match expressions.
            scaleMap: buildScaleMap(rawMap),
        };
    } catch (e) {
        console.warn('Could not load sign_colors.json — falling back to defaults', e);
        return null;
    }
}

/** Extract the per-code scale factors as a plain `{ code: scale }` map.
 *  Codes without a scale entry default to 1.0 (handled by callers). */
function buildScaleMap(map) {
    const out = {};
    for (const [code, entry] of Object.entries(map)) {
        if (typeof entry?.scale === 'number') {
            out[code] = entry.scale;
        }
    }
    return out;
}


function buildColorExpressions(map, defaults) {
    const fillStops = [];
    const strokeStops = [];
    for (const [code, colors] of Object.entries(map)) {
        if (!colors || !code) continue;
        fillStops.push(code, colors.fill || defaults.fill);
        strokeStops.push(code, colors.stroke || defaults.stroke);
    }
    // `icon_code` is the canonical sign code computed by build_pmtiles.py
    // (e.g. "274-30" from sign_list "274[30],..."). Codes that didn't
    // normalize fall through to the default (fallback) branch.
    const key = ['to-string', ['get', 'icon_code']];
    return {
        fillExpr: ['match', key, ...fillStops, defaults.fill],
        strokeExpr: ['match', key, ...strokeStops, defaults.stroke],
    };
}
