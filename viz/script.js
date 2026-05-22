// Bootstrap the MapLibre map and wire the traffic-signs layer.

import {
    initialMapConfig,
    mapAttribution,
    mapStyles,
    trafficSignsConfig,
} from './config.js';
import {
    addTrafficSignsSource,
    addTrafficSignsLayer,
    setTrafficSignsVisibility,
} from './map/trafficSignsLayer.js';
import { trafficSignsLayerIds } from './config.js';
import { loadSignColors } from './utils/signColors.js';
import { parseMapFromSearchParams, buildMapParam, updateUrlMapParam } from './utils/permalink.js';
import {
    addDefaultTrafficSignIcon,
    addStackTextBoxImage,
    addOverlayTextBgImage,
    addHoverGlowImage,
    setupTrafficSignImageHandler,
} from './utils/trafficSignIcons.js';
import { updateTopSigns, initTopSignsInteraction } from './ui/topSignsCounter.js';
import {
    addBasemapLayers,
    setMapBasemap,
    setMapRelief,
    setMapBuildings,
} from './map/basemapControls.js';

if (typeof maplibregl === 'undefined' || typeof pmtiles === 'undefined') {
    console.error('maplibregl or pmtiles missing — check <script> tags in index.html');
} else {
    const protocol = new pmtiles.Protocol();
    maplibregl.addProtocol('pmtiles', protocol.tile);

    // Honor ?map=zoom/lat/lon from the URL so deep links restore the view.
    const urlMap = typeof window !== 'undefined'
        ? parseMapFromSearchParams(new URL(window.location.href).searchParams)
        : null;

    const map = new maplibregl.Map({
        container: 'map',
        style: mapStyles.light,
        center: urlMap ? urlMap.center : initialMapConfig.center,
        zoom: urlMap ? urlMap.zoom : initialMapConfig.zoom,
        // Cap at 21.9 — the traffic-sign layers have maxzoom=22, so going to
        // 22 exactly hides every icon. Stopping just short keeps them visible.
        maxZoom: 21.9,
        attributionControl: false,
    });
    // Expose for in-browser debugging (devtools console).
    if (typeof window !== 'undefined') window.map = map;

    // Keep the URL's ?map param in sync as the user pans/zooms.
    map.on('moveend', () => {
        const c = map.getCenter();
        updateUrlMapParam(buildMapParam([c.lng, c.lat], map.getZoom()));
    });

    function refreshTopSigns() {
        updateTopSigns(map, {
            showSupplementary: Boolean(toggleSupplementaryCheckbox?.checked),
        });
    }
    // moveend fires immediately when the user stops interacting, but tiles
    // at the NEW zoom level (e.g. switching from icons → dots when zooming
    // past z13) may not be rendered yet — queryRenderedFeatures would return
    // stale data. So we refresh twice: once on moveend for instant feedback,
    // and again on the next `idle` (= everything painted). Guarded against
    // pile-up if the user pans rapidly.
    let idleRefreshPending = false;
    function scheduleIdleRefresh() {
        if (idleRefreshPending) return;
        idleRefreshPending = true;
        map.once('idle', () => {
            idleRefreshPending = false;
            refreshTopSigns();
        });
    }
    map.on('moveend', () => {
        refreshTopSigns();
        scheduleIdleRefresh();
    });
    map.once('idle', refreshTopSigns);   // initial render

    map.addControl(new maplibregl.AttributionControl({
        customAttribution: mapAttribution,
        compact: true,
    }));
    // visualizePitch: true renders the pitch indicator on the compass button —
    // matches the gradients2osm UI and makes the "third" control visible
    // even when bearing=0.
    map.addControl(new maplibregl.NavigationControl({ visualizePitch: true }), 'top-left');

    /** Cached colors bundle (rawMap, knownCodes, svgAlias, colorExpressions). */
    let signColors = null;

    function setupTrafficSigns() {
        addBasemapLayers(map);
        addDefaultTrafficSignIcon(map);
        addStackTextBoxImage(map);
        addOverlayTextBgImage(map);
        addHoverGlowImage(map);
        setupTrafficSignImageHandler(map, signColors);
        addTrafficSignsSource(map);
        addTrafficSignsLayer(map, signColors);
    }

    map.on('load', async () => {
        signColors = await loadSignColors();
        setupTrafficSigns();
        // Sync the layer visibility to whatever state the checkboxes are in
        // RIGHT NOW. Firefox restores checkbox state across reloads but the
        // map layers default to their layer-spec visibility — without this
        // call the toggle and the actual rendered state can disagree on load.
        applyTrafficSignsVisibility();
        initTopSignsInteraction(map);

        // Click on a sign -> small popup with sign_list + osm link.
        const onSignClick = (e) => {
            const f = e.features?.[0];
            if (!f) return;
            const p = f.properties || {};
            const osmId = p.osm_id;
            const osmLink = osmId
                ? `<a href="https://www.openstreetmap.org/${p.source === 'node' ? 'node' : 'way'}/${osmId}" target="_blank" rel="noopener">OSM ${p.source} ${osmId}</a>`
                : '';
            const html = `
                <div class="popup">
                    <div class="popup__codes">${(p.sign_list || p.main_signs || '').toString().replace(/,/g, '<br>')}</div>
                    <dl class="popup__meta">
                        ${p.highway ? `<dt>highway</dt><dd>${p.highway}</dd>` : ''}
                        ${p.direction != null ? `<dt>direction</dt><dd>${p.direction}°</dd>` : ''}
                    </dl>
                    ${osmLink}
                </div>`;
            new maplibregl.Popup({ closeButton: true })
                .setLngLat(e.lngLat)
                .setHTML(html)
                .addTo(map);
        };
        const onEnter = () => { map.getCanvas().style.cursor = 'pointer'; };
        const onLeave = () => { map.getCanvas().style.cursor = ''; };
        for (const layerId of trafficSignsLayerIds) {
            map.on('click', layerId, onSignClick);
            map.on('mouseenter', layerId, onEnter);
            map.on('mouseleave', layerId, onLeave);
        }
    });

    // ── Karte panel (bottom-left): basemap + relief + 3D buildings ──────
    const mapSettingsToggle = document.getElementById('map-settings-toggle');
    const mapSettingsPanel = document.getElementById('map-settings-panel');
    const mapSettingsPanelToggle = document.getElementById('map-settings-panel-toggle');
    const basemapButtons = Array.from(document.querySelectorAll('.basemap-btn[data-basemap]'));
    const reliefToggle = document.getElementById('toggle-relief');
    const buildingsToggle = document.getElementById('toggle-buildings');

    // Panel starts EXPANDED in our UX (gradients2osm starts collapsed —
    // there we hide it explicitly). Sync the toggle button visibility:
    // - panel visible → toggle button hidden (aria-expanded=true)
    // - panel collapsed → toggle button visible
    function syncMapSettingsVisibility() {
        const collapsed = mapSettingsPanel.classList.contains('is-collapsed');
        mapSettingsToggle.setAttribute('aria-expanded', String(!collapsed));
    }
    function toggleMapSettings() {
        mapSettingsPanel.classList.toggle('is-collapsed');
        syncMapSettingsVisibility();
    }
    mapSettingsToggle?.addEventListener('click', toggleMapSettings);
    mapSettingsPanelToggle?.addEventListener('click', toggleMapSettings);
    syncMapSettingsVisibility();

    function syncBasemapButtons(active) {
        for (const btn of basemapButtons) {
            btn.classList.toggle('selected', btn.dataset.basemap === active);
        }
    }
    let currentBasemap = 'positron';
    for (const btn of basemapButtons) {
        btn.addEventListener('click', () => {
            currentBasemap = btn.dataset.basemap;
            setMapBasemap(map, currentBasemap);
            syncBasemapButtons(currentBasemap);
        });
    }
    reliefToggle?.addEventListener('change', (e) => {
        setMapRelief(map, e.target.checked);
    });
    buildingsToggle?.addEventListener('change', (e) => {
        setMapBuildings(map, e.target.checked);
    });

    // Layer-visibility toggles. The "supplementary" toggle only takes effect
    // when the main toggle is on (the helper enforces that), so the user
    // can leave it checked and it'll re-activate when they turn signs back on.
    const toggleSignsCheckbox = document.getElementById('toggle-traffic-signs-layer');
    const toggleSupplementaryCheckbox = document.getElementById('toggle-supplementary-layer');
    const toggleSupplementaryRow = toggleSupplementaryCheckbox?.closest('.legend-toggle-row');
    function applyTrafficSignsVisibility() {
        const main = Boolean(toggleSignsCheckbox?.checked);
        const supplementary = Boolean(toggleSupplementaryCheckbox?.checked);
        setTrafficSignsVisibility(map, { main, supplementary });
        // Visually mark the supplementary toggle as inactive whenever the
        // main toggle is off — its checked state still persists, it just has
        // no effect on the map until "Verkehrszeichen" is back on.
        if (toggleSupplementaryRow) {
            toggleSupplementaryRow.classList.toggle('legend-toggle-row--inactive', !main);
        }
        if (toggleSupplementaryCheckbox) {
            toggleSupplementaryCheckbox.disabled = !main;
        }
    }
    toggleSignsCheckbox?.addEventListener('change', () => {
        applyTrafficSignsVisibility();
        refreshTopSigns();
    });
    toggleSupplementaryCheckbox?.addEventListener('change', () => {
        applyTrafficSignsVisibility();
        refreshTopSigns();
    });

    // Info-panel minimize: collapses to just the header. The bottom-left
    // info button (toggle-info) restores it from fully hidden if the user
    // somehow ends up there.
    const infoPanel = document.querySelector('.info-panel');
    const infoPanelToggle = document.getElementById('info-panel-toggle');
    infoPanelToggle?.addEventListener('click', () => {
        const collapsed = infoPanel.classList.toggle('is-collapsed');
        infoPanelToggle.setAttribute('aria-expanded', String(!collapsed));
        infoPanelToggle.setAttribute(
            'title', collapsed ? 'Panel erweitern' : 'Panel minimieren',
        );
    });
    document.getElementById('toggle-info')?.addEventListener('click', () => {
        // Toggle full hide (the bottom-left "i" button) — independent of the
        // header-collapse state.
        if (!infoPanel) return;
        infoPanel.style.display = infoPanel.style.display === 'none' ? 'flex' : 'none';
    });
}
