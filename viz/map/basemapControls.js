// Basemap / terrain / building overlays added on top of the Positron host
// style. Adapted from gradients2osm's initMap.js — same pattern: register
// raster layers eagerly, hillshade + 3D buildings lazily (DEM tilejson +
// planet tilejson fetches eagerly when the source exists, even if its
// layer is hidden, so we only add them on first toggle).

const OSM_CARTO_SOURCE_ID = 'osm-carto-source';
const OSM_CARTO_LAYER_ID = 'osm-carto-layer';
const ESRI_SOURCE_ID = 'esri-imagery-source';
const ESRI_LAYER_ID = 'esri-imagery-layer';
const TERRAIN_DEM_SOURCE_ID = 'terrain-dem';
const HILLSHADE_LAYER_ID = 'hillshade-layer';
const BUILDINGS_SOURCE_ID = 'ofm-buildings-source';
const BUILDINGS_LAYER_ID = 'ofm-3d-buildings';
const TERRAIN_DEM_TILEJSON_URL = 'https://tiles.mapterhorn.com/tilejson.json';
const BUILDINGS_VECTOR_URL = 'https://tiles.openfreemap.org/planet';

// Blue atmospheric sky for the 3D terrain view.
const SKY_STYLE = {
    'sky-color': '#199EF3',
    'sky-horizon-blend': 0.7,
    'horizon-color': '#f0f8ff',
    'horizon-fog-blend': 0.8,
    'fog-color': '#2c7fb8',
    'fog-ground-blend': 0.9,
    'atmosphere-blend': ['interpolate', ['linear'], ['zoom'], 0, 1, 12, 0],
};

// Everything we add ourselves; the rest belongs to the Positron host style
// and gets hidden when a raster basemap (OSM/Esri) is active.
const OWN_LAYERS = new Set([
    OSM_CARTO_LAYER_ID,
    ESRI_LAYER_ID,
    HILLSHADE_LAYER_ID,
    BUILDINGS_LAYER_ID,
]);

function firstSymbolLayer(map) {
    for (const layer of map.getStyle()?.layers || []) {
        if (layer.type === 'symbol') return layer.id;
    }
    return undefined;
}

/** Add the OSM Carto + Esri raster layers (hidden by default). Call once
 *  per style.load — the layers go BELOW the first Positron symbol layer
 *  so labels stay on top during the brief moment of switching. */
export function addBasemapLayers(map) {
    if (!map || map.getSource(OSM_CARTO_SOURCE_ID)) return;
    const beforeId = firstSymbolLayer(map);

    map.addSource(OSM_CARTO_SOURCE_ID, {
        type: 'raster',
        tiles: ['https://tile.openstreetmap.org/{z}/{x}/{y}.png'],
        tileSize: 256,
        attribution: '© OpenStreetMap contributors',
    });
    map.addLayer({
        id: OSM_CARTO_LAYER_ID, type: 'raster', source: OSM_CARTO_SOURCE_ID,
        layout: { visibility: 'none' },
    }, beforeId);

    map.addSource(ESRI_SOURCE_ID, {
        type: 'raster',
        tiles: ['https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'],
        tileSize: 256,
        attribution: 'Tiles © Esri',
    });
    map.addLayer({
        id: ESRI_LAYER_ID, type: 'raster', source: ESRI_SOURCE_ID,
        layout: { visibility: 'none' },
    }, beforeId);
}

function ensureTerrainArtifacts(map) {
    if (map.getSource(TERRAIN_DEM_SOURCE_ID)) return;
    map.addSource(TERRAIN_DEM_SOURCE_ID, {
        type: 'raster-dem',
        url: TERRAIN_DEM_TILEJSON_URL,
        tileSize: 512,
        encoding: 'terrarium',
        attribution: '© Mapterhorn',
    });
    map.addLayer({
        id: HILLSHADE_LAYER_ID,
        type: 'hillshade',
        source: TERRAIN_DEM_SOURCE_ID,
        layout: { visibility: 'none' },
        paint: {
            'hillshade-exaggeration': 0.35,
            'hillshade-illumination-anchor': 'map',
        },
    }, firstSymbolLayer(map));
}

function ensureBuildingsArtifacts(map) {
    if (map.getSource(BUILDINGS_SOURCE_ID)) return;
    map.addSource(BUILDINGS_SOURCE_ID, {
        type: 'vector',
        url: BUILDINGS_VECTOR_URL,
    });
    map.addLayer({
        id: BUILDINGS_LAYER_ID,
        type: 'fill-extrusion',
        source: BUILDINGS_SOURCE_ID,
        'source-layer': 'building',
        minzoom: 14,
        layout: { visibility: 'none' },
        paint: {
            'fill-extrusion-color': 'hsl(35, 8%, 85%)',
            'fill-extrusion-height': [
                'max',
                ['coalesce', ['to-number', ['get', 'render_height']], 12],
                ['coalesce', ['to-number', ['get', 'render_min_height']], 0],
            ],
            'fill-extrusion-base': ['coalesce', ['to-number', ['get', 'render_min_height']], 0],
            'fill-extrusion-opacity': 0.8,
        },
    });
}

/** Switch between basemaps. `basemap` ∈ {'positron','osm','satellite'}.
 *  When OSM or Esri is active, ALL host-Positron layers get hidden so the
 *  raster basemap shows clean (no label bleed-through). */
export function setMapBasemap(map, basemap) {
    if (!map) return;
    const showOsm = basemap === 'osm';
    const showEsri = basemap === 'satellite';
    const hideHost = showOsm || showEsri;

    if (map.getLayer(OSM_CARTO_LAYER_ID)) {
        map.setLayoutProperty(OSM_CARTO_LAYER_ID, 'visibility', showOsm ? 'visible' : 'none');
    }
    if (map.getLayer(ESRI_LAYER_ID)) {
        map.setLayoutProperty(ESRI_LAYER_ID, 'visibility', showEsri ? 'visible' : 'none');
    }
    // Hide host Positron layers when a raster basemap is on. Don't touch
    // our own layers (basemaps, hillshade, buildings) or the traffic-sign
    // layers (handled by setTrafficSignsVisibility).
    for (const layer of map.getStyle()?.layers || []) {
        if (OWN_LAYERS.has(layer.id)) continue;
        if (layer.id.startsWith('osm-traffic-signs')) continue;
        map.setLayoutProperty(layer.id, 'visibility', hideHost ? 'none' : 'visible');
    }
}

export function setMapRelief(map, enabled) {
    if (!map) return;
    if (enabled) ensureTerrainArtifacts(map);
    if (map.getLayer(HILLSHADE_LAYER_ID)) {
        map.setLayoutProperty(HILLSHADE_LAYER_ID, 'visibility', enabled ? 'visible' : 'none');
    }
    if (map.getSource(TERRAIN_DEM_SOURCE_ID)) {
        map.setTerrain(enabled ? { source: TERRAIN_DEM_SOURCE_ID, exaggeration: 1 } : null);
    }
    if (typeof map.setSky === 'function') {
        map.setSky(enabled ? SKY_STYLE : undefined);
    }
    // Tilt the camera so the 3D terrain is actually visible when enabling.
    if (!map.isMoving()) {
        if (enabled && map.getPitch() < 45) {
            map.easeTo({ pitch: 55, duration: 700 });
        } else if (!enabled && map.getPitch() > 5) {
            map.easeTo({ pitch: 0, duration: 500 });
        }
    }
}

export function setMapBuildings(map, enabled) {
    if (!map) return;
    if (enabled) ensureBuildingsArtifacts(map);
    if (map.getLayer(BUILDINGS_LAYER_ID)) {
        map.setLayoutProperty(BUILDINGS_LAYER_ID, 'visibility', enabled ? 'visible' : 'none');
    }
}
