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
    center: [-98.5, 39.5], // contiguous US center
    zoom: 4.3,
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

// ── Globe atmosphere + datacenter layer ───────────────────────────────────────
map.on('style.load', () => {
    map.setFog({
        color: 'rgb(20, 26, 40)',
        'high-color': 'rgb(10, 15, 30)',
        'horizon-blend': 0.04,
        'space-color': 'rgb(5, 8, 18)',
        'star-intensity': 0.6
    });

    loadDatacenters();
});

// ── Load + display datacenters ────────────────────────────────────────────────
let selectedDcId = null;

function loadDatacenters() {
    map.addSource('datacenters', {
        type: 'geojson',
        data: window.DATACENTER_GEOJSON
    });

    map.addLayer({
        id: 'datacenters-circles',
        type: 'circle',
        source: 'datacenters',
        paint: {
            'circle-radius': [
                'interpolate', ['linear'], ['zoom'],
                3, 4,
                10, 9
            ],
            'circle-color': [
                'case',
                ['boolean', ['feature-state', 'selected'], false],
                '#ff6b35',
                '#4f8ef7'
            ],
            'circle-stroke-width': [
                'case',
                ['boolean', ['feature-state', 'selected'], false],
                2.5,
                1.5
            ],
            'circle-stroke-color': '#ffffff',
            'circle-opacity': 0.9
        }
    });

    map.on('mouseenter', 'datacenters-circles', () => {
        map.getCanvas().style.cursor = 'pointer';
    });
    map.on('mouseleave', 'datacenters-circles', () => {
        map.getCanvas().style.cursor = '';
    });

    map.on('click', 'datacenters-circles', (e) => {
        const feature = e.features[0];

        if (selectedDcId !== null) {
            map.setFeatureState({ source: 'datacenters', id: selectedDcId }, { selected: false });
        }
        selectedDcId = feature.id;
        map.setFeatureState({ source: 'datacenters', id: selectedDcId }, { selected: true });

        updateSidebar(feature.properties);
    });
}

// ── Sidebar update ────────────────────────────────────────────────────────────
function updateSidebar(props) {
    const locationEl = document.getElementById('selected-location');
    const chartsEl   = document.getElementById('charts-container');

    locationEl.innerHTML = `
        <div class="location-badge">
            <span class="dot"></span>
            <span>${props.Name || 'Unknown Datacenter'}</span>
        </div>`;

    const fields = [
        { label: 'Operator',    value: props.Operator },
        { label: 'Location',    value: [props.City, props.State, props.Country].filter(Boolean).join(', ') },
        { label: 'Address',     value: props.Address },
        { label: 'Status',      value: props.Status },
        { label: 'Power',       value: props.Power },
        { label: 'Size',        value: props.Size },
        { label: 'Established', value: props.Established },
    ].filter(f => f.value);

    const rows = fields.map(f => `
        <div class="dc-row">
            <span class="dc-label">${f.label}</span>
            <span class="dc-value">${f.value}</span>
        </div>`).join('');

    chartsEl.innerHTML = `
        <div class="chart-card dc-info">
            <h3>Datacenter Info</h3>
            ${rows}
        </div>
        <div class="chart-card">
            <h3>Coordinates</h3>
            <div class="dc-row">
                <span class="dc-label">Latitude</span>
                <span class="dc-value">${parseFloat(props.Latitude).toFixed(6)}</span>
            </div>
            <div class="dc-row">
                <span class="dc-label">Longitude</span>
                <span class="dc-value">${parseFloat(props.Longitude).toFixed(6)}</span>
            </div>
        </div>`;
}

// ── Expose map for future modules ─────────────────────────────────────────────
window.terraMap = map;
