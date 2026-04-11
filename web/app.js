// ─────────────────────────────────────────────────────────────────────────────
//  Terra Project — app.js
//  Map: Mapbox GL JS v3.20.0 with OpenStreetMap raster tiles
// ─────────────────────────────────────────────────────────────────────────────

mapboxgl.accessToken = MAPBOX_TOKEN; // defined in config.js

// ── OSM tile style (no Mapbox tile costs) ────────────────────────────────────
const OSM_STYLE = {
    version: 8,
    glyphs: 'https://demotiles.maplibre.org/font/{fontstack}/{range}.pbf',
    sources: {
        osm: {
            type: 'raster',
            tiles: ['https://tile.openstreetmap.org/{z}/{x}/{y}.png'],
            tileSize: 256,
            attribution:
                '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank">OpenStreetMap</a> contributors'
        }
    },
    layers: [
        {
            id: 'osm-tiles',
            type: 'raster',
            source: 'osm',
            minzoom: 0,
            maxzoom: 19
        }
    ]
};

// ── Initialise map ────────────────────────────────────────────────────────────
const map = new mapboxgl.Map({
    container: 'map',
    style: OSM_STYLE,
    center: [0, 20],       // longitude, latitude
    zoom: 2,
    projection: 'globe',   // renders as a 3-D globe at low zoom levels
    antialias: true
});

// Navigation controls (zoom + compass)
map.addControl(new mapboxgl.NavigationControl(), 'top-right');

// Full-screen control
map.addControl(new mapboxgl.FullscreenControl(), 'top-right');

// Scale bar
map.addControl(
    new mapboxgl.ScaleControl({ maxWidth: 120, unit: 'metric' }),
    'bottom-right'
);

// ── Globe atmosphere (cosmetic, only visible at low zoom) ─────────────────────
map.on('style.load', () => {
    map.setFog({
        color: 'rgb(20, 26, 40)',
        'high-color': 'rgb(10, 15, 30)',
        'horizon-blend': 0.04,
        'space-color': 'rgb(5, 8, 18)',
        'star-intensity': 0.6
    });
});

// ── Click interaction ─────────────────────────────────────────────────────────
let activeMarker = null;

map.on('click', (e) => {
    const { lng, lat } = e.lngLat;

    // Replace previous marker
    if (activeMarker) activeMarker.remove();

    const el = document.createElement('div');
    el.className = 'click-marker';

    activeMarker = new mapboxgl.Marker({ element: el, anchor: 'center' })
        .setLngLat([lng, lat])
        .addTo(map);

    updateSidebar(lng, lat);
});

// ── Sidebar update ────────────────────────────────────────────────────────────
function updateSidebar(lng, lat) {
    const locationEl = document.getElementById('selected-location');
    const chartsEl   = document.getElementById('charts-container');

    const fmtLng = `${Math.abs(lng).toFixed(4)}° ${lng >= 0 ? 'E' : 'W'}`;
    const fmtLat = `${Math.abs(lat).toFixed(4)}° ${lat >= 0 ? 'N' : 'S'}`;

    locationEl.innerHTML = `
        <div class="location-badge">
            <span class="dot"></span>
            <span>${fmtLat}, ${fmtLng}</span>
        </div>`;

    // Placeholder until real charts are wired in
    chartsEl.innerHTML = `
        <div class="chart-card">
            <h3>Selected coordinates</h3>
            <p style="font-size:0.85rem; color: var(--text-secondary); line-height:1.6;">
                Longitude: <strong style="color:var(--text-primary)">${lng.toFixed(6)}</strong><br/>
                Latitude: &nbsp;<strong style="color:var(--text-primary)">${lat.toFixed(6)}</strong>
            </p>
        </div>
        <div class="chart-card">
            <h3>Data charts</h3>
            <p style="font-size:0.82rem; color:var(--text-muted); line-height:1.5;">
                Chart panels will be added here for the selected location.
            </p>
        </div>`;
}

// ── Expose map for future modules ─────────────────────────────────────────────
window.terraMap = map;
