// Lazy-load traffic-sign SVGs into the MapLibre style on demand.
//
// MapLibre fires "styleimagemissing" with an image id whenever a symbol layer
// references an unknown icon. We register a handler that maps the id (a raw
// `main_signs` value from the parquet, e.g. "274-50" or "DE242.1") to a local
// SVG path and registers it under the same id.

import { trafficSignsConfig } from '../config.js';

const DEFAULT_ID = trafficSignsConfig.defaultIconId;

/** Image id for the white background rectangle behind stack text labels. */
export const STACK_TEXT_BOX_ID = 'stack-text-box';

/** Image id for the white CIRCULAR background behind overlay text on 262
 *  (tonnage) signs. Stretched via icon-text-fit to fit the text width/height,
 *  resulting in an ellipse/pill shape sized to the overlay. */
export const OVERLAY_TEXT_BG_ID = 'overlay-text-bg';

/** Codes we've tried to load, to avoid repeated fetches for the same id. */
const tried = new Set();

/**
 * Module-level resolvers supplied by setupTrafficSignImageHandler.
 * - svgAliasResolver: code → SVG basename (e.g. "244" → "244.1").
 * - colorLookupResolver: code → {fill, stroke, svg?} JSON entry. Used to
 *   generate a coloured circle bitmap as a fallback for codes that have
 *   a colour assignment but no SVG (e.g. "310" Ortstafel = yellow/black).
 */
let svgAliasResolver = null;
let colorLookupResolver = null;

/**
 * Normalize a raw sign code into a `<country>/<filename>` path suffix.
 * Returns null when the code can't reasonably map to an SVG (free text, etc.).
 */
function codeToPathSuffix(rawId, countryCode = 'DE') {
    if (!rawId || typeof rawId !== 'string') return null;
    // First chance: the JSON-driven alias map handles family/parquet edge
    // cases (e.g. "244" -> "244.1", "1000-33" -> "1000-10").
    const aliased = svgAliasResolver?.(rawId);
    if (aliased) return `${countryCode}/${aliased}.svg`;
    // Fallback: parse the code ourselves. Take only the first code in a
    // "1000-32;206" combo and strip a country prefix like "DE242.1" -> "242.1".
    let code = rawId.split(';')[0].trim();
    const m = code.match(/^([A-Z]{2})(.+)$/);
    if (m) code = m[2];
    // Reject free-text annotations.
    if (!/^[0-9][0-9A-Za-z.\-]*$/.test(code)) return null;
    return `${countryCode}/${code}.svg`;
}

/**
 * Build the fallback icon: a filled grey circle with a darker ring. The
 * grey palette is deliberate — amber is reserved for real yellow signs (e.g.
 * city-limit "Ortstafel"), so fallbacks need a different colour family.
 *
 * Size + pixelRatio are tuned to match the visual footprint of upstream
 * StVO SVGs (≈ 600×600 @ pixelRatio 2 = effective 300pt). At pixelRatio 1
 * a 200×200 bitmap is 200pt — close enough that the same icon-size scale
 * applies. Without this, the default was rendering as a ~3px dot at low zoom.
 */
function createDefaultImageData(size = 200) {
    const data = new Uint8ClampedArray(size * size * 4);
    const r = size / 2;
    const ringInner = r - size * 0.10;  // ring is ~10% of the diameter
    // gray-300 inside (#d1d5db), gray-800 ring (#1f2937).
    const fill = [209, 213, 219, 240];
    const ring = [31, 41, 55, 250];
    for (let y = 0; y < size; y++) {
        for (let x = 0; x < size; x++) {
            const d = Math.hypot(x - r, y - r);
            const i = (y * size + x) * 4;
            if (d <= ringInner) {
                data[i] = fill[0]; data[i + 1] = fill[1]; data[i + 2] = fill[2]; data[i + 3] = fill[3];
            } else if (d <= r) {
                data[i] = ring[0]; data[i + 1] = ring[1]; data[i + 2] = ring[2]; data[i + 3] = ring[3];
            }
        }
    }
    return { width: size, height: size, data };
}

/** Register the default icon once after style load. */
export function addDefaultTrafficSignIcon(map) {
    if (!map || map.hasImage?.(DEFAULT_ID)) return;
    const { width, height, data } = createDefaultImageData();
    // pixelRatio 1 so the bitmap's pixel size == map points — matches the
    // effective size of SVG icons rendered at their viewBox dimensions.
    map.addImage(DEFAULT_ID, { width, height, data }, { pixelRatio: 1 });
}

/** "#rrggbb" → [r, g, b]. Tolerates leading `#`. */
function hexToRgb(hex) {
    const n = parseInt(String(hex).replace(/^#/, ''), 16);
    return [(n >> 16) & 0xff, (n >> 8) & 0xff, n & 0xff];
}

/**
 * Build a coloured fallback circle bitmap (fill + ring). Same dimensions as
 * createDefaultImageData so on-screen sizing stays consistent across codes.
 */
function createColoredCircleImageData(fillHex, strokeHex, size = 200) {
    const [fr, fg, fb] = hexToRgb(fillHex);
    const [sr, sg, sb] = hexToRgb(strokeHex);
    const data = new Uint8ClampedArray(size * size * 4);
    const r = size / 2;
    const ringInner = r - size * 0.10;
    for (let y = 0; y < size; y++) {
        for (let x = 0; x < size; x++) {
            const d = Math.hypot(x - r, y - r);
            const i = (y * size + x) * 4;
            if (d <= ringInner) {
                data[i] = fr; data[i + 1] = fg; data[i + 2] = fb; data[i + 3] = 240;
            } else if (d <= r) {
                data[i] = sr; data[i + 1] = sg; data[i + 2] = sb; data[i + 3] = 250;
            }
        }
    }
    return { width: size, height: size, data };
}

/**
 * Register a fallback bitmap under `id` — coloured if the code has a colour
 * entry in sign_colors.json, otherwise the default grey.
 */
function registerFallbackBitmap(map, id) {
    if (map.hasImage(id)) return;
    const entry = colorLookupResolver?.(id);
    const img = (entry?.fill && entry?.stroke)
        ? createColoredCircleImageData(entry.fill, entry.stroke)
        : createDefaultImageData();
    map.addImage(id, img, { pixelRatio: 1 });
}

/**
 * Build the white-with-dark-edge box used as a background behind stack text
 * labels (`icon-text-fit: 'both'` stretches this to fit the text). Uses 9-slice
 * `stretchX`/`stretchY` so the corner edges stay crisp when stretched.
 */
function createStackTextBoxImageData(size = 16) {
    const data = new Uint8ClampedArray(size * size * 4);
    const fill = [255, 255, 255, 240];     // mostly opaque white
    const border = [55, 65, 81, 230];      // slate-700-ish
    for (let y = 0; y < size; y++) {
        for (let x = 0; x < size; x++) {
            const i = (y * size + x) * 4;
            const onBorder = x === 0 || x === size - 1 || y === 0 || y === size - 1;
            const c = onBorder ? border : fill;
            data[i] = c[0]; data[i + 1] = c[1]; data[i + 2] = c[2]; data[i + 3] = c[3];
        }
    }
    return { width: size, height: size, data };
}

/** Register the stack text box image. Call once after style load. */
export function addStackTextBoxImage(map) {
    if (!map || map.hasImage?.(STACK_TEXT_BOX_ID)) return;
    const img = createStackTextBoxImageData();
    // 9-slice: stretch only the middle pixels (1..size-1), keep the 1px
    // border at full resolution so it doesn't blur when icon-text-fit
    // expands the image to fit the text.
    const inner = [[1, img.width - 1]];
    map.addImage(STACK_TEXT_BOX_ID,
        { width: img.width, height: img.height, data: img.data },
        { pixelRatio: 1, stretchX: inner, stretchY: inner, content: [1, 1, img.width - 1, img.height - 1] }
    );
}

/**
 * Build a solid-white filled rectangle for the overlay-text background.
 * `icon-text-fit: 'both'` stretches this image to fit the text box plus
 * padding, producing a clean rectangle of any aspect ratio. We deliberately
 * use no border, no transparency, and no 9-slice areas — that keeps the
 * shape consistent under icon-rotate (a rotated circle-with-AA-edges showed
 * stretching artefacts at non-axis-aligned angles).
 */
function createOverlayTextBgImageData(size = 8) {
    const data = new Uint8ClampedArray(size * size * 4);
    for (let i = 0; i < data.length; i += 4) {
        data[i] = 255; data[i + 1] = 255; data[i + 2] = 255; data[i + 3] = 255;
    }
    return { width: size, height: size, data };
}

/** Image id for the soft hover glow bitmap. */
export const HOVER_GLOW_ID = 'hover-glow';

/**
 * Build a soft radial-gradient circle in amber: opaque centre, transparent
 * edge, quadratic falloff. Used by the hover-glow layers to highlight the
 * sign whose row the user is hovering in the top-N counter.
 */
function createHoverGlowImageData(size = 256) {
    const data = new Uint8ClampedArray(size * size * 4);
    const r = size / 2;
    // amber-400 (#fbbf24) — reads as "highlight" without competing with the
    // amber used for real yellow signs (those are smaller in the icon).
    const cr = 251, cg = 191, cb = 36;
    for (let y = 0; y < size; y++) {
        for (let x = 0; x < size; x++) {
            const d = Math.hypot(x - r, y - r);
            if (d >= r) continue;     // outside circle → fully transparent
            const t = d / r;          // 0 at centre, 1 at edge
            const a = (1 - t) * (1 - t);   // quadratic falloff
            const i = (y * size + x) * 4;
            data[i] = cr; data[i + 1] = cg; data[i + 2] = cb;
            data[i + 3] = Math.round(255 * a);
        }
    }
    return { width: size, height: size, data };
}

/** Register the hover-glow image. Call once after style load. */
export function addHoverGlowImage(map) {
    if (!map || map.hasImage?.(HOVER_GLOW_ID)) return;
    const img = createHoverGlowImageData();
    map.addImage(HOVER_GLOW_ID,
        { width: img.width, height: img.height, data: img.data },
        { pixelRatio: 1 }
    );
}

/** Register the overlay text background image. Call once after style load. */
export function addOverlayTextBgImage(map) {
    if (!map || map.hasImage?.(OVERLAY_TEXT_BG_ID)) return;
    const img = createOverlayTextBgImageData();
    // No stretchX/stretchY: MapLibre scales the whole image uniformly to fit
    // the text bounding box. For a uniform solid-white bitmap that's exactly
    // what we want — a clean filled rectangle regardless of rotation.
    map.addImage(OVERLAY_TEXT_BG_ID,
        { width: img.width, height: img.height, data: img.data },
        { pixelRatio: 1 }
    );
}

function fetchAndAddImage(map, id, url) {
    // `cache: 'default'` (vs. force-cache) so a previously-404'd response
    // can be re-fetched when the SVG is added to the library later. The
    // browser still HTTP-caches successful fetches per the response headers.
    fetch(url, { cache: 'default' })
        .then((res) => {
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            return res.text();
        })
        .then((svg) => new Promise((resolve, reject) => {
            const dataUrl = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(svg);
            const img = new Image();
            img.onload = () => {
                try {
                    if (!map.hasImage(id)) map.addImage(id, img, { pixelRatio: 2 });
                    resolve();
                } catch (e) { reject(e); }
            };
            img.onerror = reject;
            img.src = dataUrl;
        }))
        .catch(() => {
            // Fallback: register a circle under the missing id so MapLibre
            // stops asking. Uses the code's classification colours if it has
            // any, else grey.
            registerFallbackBitmap(map, id);
        });
}

/**
 * Attach the styleimagemissing handler. Call once after map.on('load').
 *
 * @param {object} map
 * @param {object} [signColors] — the bundle from utils/signColors.loadSignColors().
 *   - `svgAlias(code)`: returns the SVG basename to fetch (e.g. "244" → "244.1")
 *   - `colorLookup(code)`: returns the full JSON entry `{fill, stroke, svg?}`,
 *     used to generate a coloured fallback circle for codes that have a
 *     colour assignment but no SVG (e.g. "310" Ortstafel = yellow/black).
 */
export function setupTrafficSignImageHandler(map, signColors) {
    if (!map) return;
    svgAliasResolver = signColors?.svgAlias || null;
    colorLookupResolver = signColors?.colorLookup || null;
    map.on('styleimagemissing', (event) => {
        const id = event.id;
        if (!id || id === DEFAULT_ID || tried.has(id)) return;
        tried.add(id);

        // Look up the code in sign_colors.json. Three cases:
        //   - entry with svg: known SVG, fetch it
        //   - entry without svg: known colour-only code (e.g. "310" Ortstafel,
        //     MANUAL_COLOR_ENTRIES), render a coloured circle, no fetch
        //   - no entry at all: unknown code. Skip the fetch (it would 404 for
        //     codes that genuinely don't have an SVG, e.g. 241/251/299) and
        //     register a generic greyscale fallback.
        const entry = colorLookupResolver?.(id);
        if (!entry || !entry.svg) {
            registerFallbackBitmap(map, id);
            return;
        }

        const suffix = codeToPathSuffix(id);
        if (!suffix) {
            registerFallbackBitmap(map, id);
            return;
        }
        fetchAndAddImage(map, id, trafficSignsConfig.iconBaseUrl + suffix);
    });
}
