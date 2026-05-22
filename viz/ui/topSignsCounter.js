// Top-N counter for sign codes currently rendered in the viewport.
//
// Counts `icon_code` across the visible primary-icon and primary-dot layers
// (exactly one of those is rendered at any zoom thanks to minzoom/maxzoom),
// and — when the supplementary toggle is on — also counts the `stack_N_code`
// / `stack_N_text` properties on each feature.
//
// Two row interactions:
//   - Hover  → that code's signs get boosted in size on the map.
//   - Click  → that code's signs are hidden on the map, row gets a veil.

import {
    trafficSignsConfig,
    ICON_MIN_ZOOM,
} from '../config.js';
import { setHoverState, setHiddenState } from '../map/trafficSignsLayer.js';

const TOP_N = 10;
const STACK_SLOTS = [1, 2, 3];

// Row key format: "<section>:<kind>:<value>"
//   section = primary | stack
//   kind    = code | text
//   value   = the code string or text string
function makeKey(section, kind, value) {
    return `${section}:${kind}:${value}`;
}
function parseKey(key) {
    if (!key) return null;
    const idx1 = key.indexOf(':');
    const idx2 = key.indexOf(':', idx1 + 1);
    return {
        section: key.slice(0, idx1),
        kind: key.slice(idx1 + 1, idx2),
        value: key.slice(idx2 + 1),
    };
}

// Interaction state. Hovered is a single key (or null). Hidden is a Set.
let hoveredKey = null;
const hiddenKeys = new Set();
let cachedMap = null;

// Small debounce before the map glow follows the mouse — keeps the map from
// flickering when the user just slides past rows on the way to somewhere else.
const HOVER_APPLY_DELAY_MS = 80;
let hoverApplyTimer = null;
function scheduleHoverApply() {
    if (hoverApplyTimer) clearTimeout(hoverApplyTimer);
    hoverApplyTimer = setTimeout(() => {
        hoverApplyTimer = null;
        applyHover();
    }, HOVER_APPLY_DELAY_MS);
}

/** Push only the hover-glow filter to the map. Hover events use this — */
/** cheap (4 setFilter calls), called on every mouseover/mouseout.        */
function applyHover() {
    if (!cachedMap) return;
    setHoverState(cachedMap, parseKey(hoveredKey));
}

/** Push only the per-feature opacity filters that drive the click-to-hide */
/** state. Called from click handlers and once per layer rebuild, NOT on   */
/** hover (hover doesn't change which features are hidden).                */
function applyHidden() {
    if (!cachedMap) return;
    const primary = [];
    const stackCodes = [];
    const stackTexts = [];
    for (const k of hiddenKeys) {
        const p = parseKey(k);
        if (p.section === 'primary') primary.push(p.value);
        else if (p.kind === 'code') stackCodes.push(p.value);
        else stackTexts.push(p.value);
    }
    setHiddenState(cachedMap, { primary, stackCodes, stackTexts });
}

function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, (c) => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
    }[c]));
}

function renderCodeRow(section, code, count, country, iconBaseUrl) {
    // background-image silently no-paints on 404 — no broken-image icon, no
    // onerror dance needed. URL-encode path components defensively.
    const url = `${iconBaseUrl}${encodeURIComponent(country)}/${encodeURIComponent(code)}.svg`;
    const key = makeKey(section, 'code', code);
    const hiddenCls = hiddenKeys.has(key) ? ' top-signs-item--hidden' : '';
    return `<div class="top-signs-item${hiddenCls}" data-key="${escapeHtml(key)}">
        <span class="top-signs-icon" style="background-image:url('${escapeHtml(url)}')"></span>
        <span class="top-signs-label">${escapeHtml(code)}</span>
        <span class="count-badge">${count}</span>
    </div>`;
}

function renderTextRow(section, text, count) {
    const key = makeKey(section, 'text', text);
    const hiddenCls = hiddenKeys.has(key) ? ' top-signs-item--hidden' : '';
    return `<div class="top-signs-item${hiddenCls}" data-key="${escapeHtml(key)}">
        <span class="top-signs-text">${escapeHtml(text)}</span>
        <span class="count-badge">${count}</span>
    </div>`;
}

function renderList(containerId, section, sortedEntries, country, iconBaseUrl) {
    const el = document.getElementById(containerId);
    if (!el) return;
    if (sortedEntries.length === 0) {
        el.innerHTML = '<div class="top-signs-empty">– keine sichtbar –</div>';
        return;
    }
    el.innerHTML = sortedEntries.map(([key, count]) => {
        if (key.startsWith('text:')) return renderTextRow(section, key.slice(5), count);
        return renderCodeRow(section, key.slice(5), count, country, iconBaseUrl);
    }).join('');
}

/** Attach delegated hover + click handlers once. Idempotent via dataset flag. */
export function initTopSignsInteraction(map) {
    cachedMap = map;
    for (const id of ['top-signs-primary-list', 'top-signs-stack-list']) {
        const el = document.getElementById(id);
        if (!el || el.dataset.tsiWired === '1') continue;
        el.dataset.tsiWired = '1';

        el.addEventListener('mouseover', (e) => {
            const row = e.target.closest('.top-signs-item');
            if (!row || !el.contains(row)) return;
            if (row.classList.contains('top-signs-item--hidden')) return;
            if (hoveredKey === row.dataset.key) return;
            hoveredKey = row.dataset.key;
            scheduleHoverApply();
        });
        el.addEventListener('mouseout', (e) => {
            const row = e.target.closest('.top-signs-item');
            if (!row || !el.contains(row)) return;
            // Only clear if we're actually leaving the row (not just bubbling).
            const next = e.relatedTarget;
            if (next && row.contains(next)) return;
            if (hoveredKey === row.dataset.key) {
                hoveredKey = null;
                scheduleHoverApply();
            }
        });
        el.addEventListener('click', (e) => {
            const row = e.target.closest('.top-signs-item');
            if (!row || !el.contains(row)) return;
            const k = row.dataset.key;
            if (hiddenKeys.has(k)) {
                hiddenKeys.delete(k);
                row.classList.remove('top-signs-item--hidden');
            } else {
                hiddenKeys.add(k);
                row.classList.add('top-signs-item--hidden');
                // Hovering a row that's now hidden would leave a stale glow.
                if (hoveredKey === k) {
                    hoveredKey = null;
                    applyHover();
                }
            }
            applyHidden();
        });
    }
}

/** Update both top-N lists from features in the viewport. */
export function updateTopSigns(map, { showSupplementary }) {
    cachedMap = map;
    // Use querySourceFeatures (not queryRenderedFeatures) so we catch features
    // whose primary icon doesn't render — e.g. free-text-only Zusatzschilder
    // (`icon_code = ""`) that the icons layer skips at zoom ≥ ICON_MIN_ZOOM.
    // Trade-off: we get features from ALL loaded tiles (including outside the
    // viewport) and must bbox-filter + dedupe by osm_id ourselves.
    if (!map.getSource(trafficSignsConfig.sourceId)) return;
    const allFeatures = map.querySourceFeatures(trafficSignsConfig.sourceId, {
        sourceLayer: trafficSignsConfig.sourceLayer,
    });
    const b = map.getBounds();
    const w = b.getWest(), e = b.getEast();
    const s = b.getSouth(), n = b.getNorth();
    const seen = new Set();
    const features = [];
    for (const f of allFeatures) {
        const coords = f.geometry?.coordinates;
        if (!coords) continue;
        const [lng, lat] = coords;
        if (lng < w || lng > e || lat < s || lat > n) continue;
        // Tippecanoe's tile buffer means the same feature can appear in 2-3
        // adjacent tiles. Dedupe by osm_id + coords (osm_id alone isn't unique
        // — way-derived signs share the parent way's id).
        const key = `${f.properties.osm_id}:${lng.toFixed(7)}:${lat.toFixed(7)}`;
        if (seen.has(key)) continue;
        seen.add(key);
        features.push(f);
    }

    const primary = new Map();
    const stack = new Map();
    let country = 'DE';

    for (const f of features) {
        const p = f.properties || {};
        if (p.country_code) country = p.country_code;

        const code = p.icon_code;
        if (code) {
            const k = `code:${code}`;
            primary.set(k, (primary.get(k) || 0) + 1);
        }

        if (showSupplementary) {
            for (const i of STACK_SLOTS) {
                const c = p[`stack_${i}_code`];
                const t = p[`stack_${i}_text`];
                if (c) {
                    const k = `code:${c}`;
                    stack.set(k, (stack.get(k) || 0) + 1);
                } else if (t) {
                    const k = `text:${t}`;
                    stack.set(k, (stack.get(k) || 0) + 1);
                }
            }
        }
    }

    const sortDesc = (m) => [...m.entries()].sort((a, b) => b[1] - a[1]).slice(0, TOP_N);
    const iconBaseUrl = trafficSignsConfig.iconBaseUrl;

    renderList('top-signs-primary-list', 'primary', sortDesc(primary), country, iconBaseUrl);

    const totalEl = document.getElementById('top-signs-primary-total');
    if (totalEl) {
        const total = [...primary.values()].reduce((a, b) => a + b, 0);
        totalEl.textContent = total ? `(${total} sichtbar)` : '';
    }

    const stackSection = document.getElementById('top-signs-stack-section');
    if (stackSection) {
        if (showSupplementary) {
            stackSection.style.display = '';
            renderList('top-signs-stack-list', 'stack', sortDesc(stack), country, iconBaseUrl);
        } else {
            stackSection.style.display = 'none';
        }
    }

    // Stack header hint: at zoom < ICON_MIN_ZOOM the stack layers are below
    // their minzoom (not rendered on the map), so we tell the user. At higher
    // zoom we show the total stack-item count, analog to the primary header.
    const stackHint = document.getElementById('top-signs-stack-hint');
    if (stackHint) {
        if (!showSupplementary) {
            stackHint.textContent = '';
        } else if (map.getZoom() < ICON_MIN_ZOOM) {
            stackHint.textContent = '(nicht sichtbar)';
        } else {
            const stackTotal = [...stack.values()].reduce((a, b) => a + b, 0);
            stackHint.textContent = stackTotal ? `(${stackTotal} sichtbar)` : '';
        }
    }

    // Re-apply hidden state — dark-mode style change rebuilds layers with
    // default paint, so click-hidden codes would re-appear without this.
    applyHidden();
}
