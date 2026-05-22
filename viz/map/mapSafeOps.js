// Tiny defensive helpers around the MapLibre API.

export function hasSource(map, id) {
    return Boolean(map && map.getSource && map.getSource(id));
}

export function hasLayer(map, id) {
    return Boolean(map && map.getLayer && map.getLayer(id));
}

export function addSourceIfMissing(map, id, spec) {
    if (!map || hasSource(map, id)) return;
    map.addSource(id, spec);
}

export function addLayerIfMissing(map, spec, beforeId) {
    if (!map || hasLayer(map, spec.id)) return;
    if (beforeId && hasLayer(map, beforeId)) map.addLayer(spec, beforeId);
    else map.addLayer(spec);
}

export function setLayerVisibility(map, id, visible) {
    if (!hasLayer(map, id)) return;
    map.setLayoutProperty(id, 'visibility', visible ? 'visible' : 'none');
}
