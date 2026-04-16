const { datacenters, forecasts } = require('./datacenter-data');

// In-memory cache shared across warm invocations of the same container.
const statsCache = new Map();      // gageId -> { byDay: { "MM-DD": {...} }, cachedAt }
const STATS_TTL_MS = 30 * 24 * 60 * 60 * 1000;  // 30 days — baseline barely drifts

const USGS_DV_URL = 'https://waterservices.usgs.gov/nwis/dv/';
const USGS_STAT_URL = 'https://waterservices.usgs.gov/nwis/stat/';

function json(statusCode, body, extraHeaders = {}) {
    return {
        statusCode,
        headers: {
            'Content-Type': 'application/json',
            'Cache-Control': 'public, max-age=300',  // 5 min — datacenter record is stable
            ...extraHeaders
        },
        body: JSON.stringify(body)
    };
}

async function fetchLatestDailyValue(gageId) {
    const url = `${USGS_DV_URL}?sites=${gageId}&parameterCd=00060&format=json&period=P14D`;
    const res = await fetch(url);
    if (!res.ok) throw new Error(`USGS dv HTTP ${res.status}`);
    const data = await res.json();
    const series = data?.value?.timeSeries?.[0]?.values?.[0]?.value || [];
    for (let i = series.length - 1; i >= 0; i--) {
        const v = parseFloat(series[i].value);
        if (Number.isFinite(v) && v >= 0) {
            return { cfs: v, dateTime: series[i].dateTime };
        }
    }
    return null;
}

async function fetchHistoricalStats(gageId) {
    const cached = statsCache.get(gageId);
    if (cached && Date.now() - cached.cachedAt < STATS_TTL_MS) return cached;

    const url =
        `${USGS_STAT_URL}?sites=${gageId}&parameterCd=00060&statReportType=daily` +
        `&statTypeCd=min,p05,p10,p25,p50,p75,p90,p95,max` +
        `&startDT=1991-01-01&endDT=2020-12-31&format=rdb`;
    const res = await fetch(url);
    if (!res.ok) throw new Error(`USGS stat HTTP ${res.status}`);
    const text = await res.text();

    const byDay = {};
    let headers = null;
    for (const line of text.split('\n')) {
        if (!line || line.startsWith('#')) continue;
        const cols = line.split('\t');
        if (cols[0] === 'agency_cd') { headers = cols; continue; }
        if (cols[0] !== 'USGS' || !headers) continue;

        const row = {};
        headers.forEach((h, i) => { row[h] = cols[i]; });

        const m = parseInt(row.month_nu, 10);
        const d = parseInt(row.day_nu, 10);
        if (!Number.isFinite(m) || !Number.isFinite(d)) continue;

        const key = `${String(m).padStart(2, '0')}-${String(d).padStart(2, '0')}`;
        const pts = [];
        const push = (p, field) => {
            const v = parseFloat(row[field]);
            if (Number.isFinite(v)) pts.push([p, v]);
        };
        push(0,   'min_va');
        push(5,   'p05_va');
        push(10,  'p10_va');
        push(25,  'p25_va');
        push(50,  'p50_va');
        push(75,  'p75_va');
        push(90,  'p90_va');
        push(95,  'p95_va');
        push(100, 'max_va');

        // De-duplicate by percentile (keep last), sort by cfs value.
        const byPct = new Map(pts.map(([p, v]) => [p, v]));
        const sorted = [...byPct.entries()].sort((a, b) => a[1] - b[1]);

        byDay[key] = { points: sorted, count: parseInt(row.count_nu, 10) || 0 };
    }

    const entry = { byDay, cachedAt: Date.now() };
    statsCache.set(gageId, entry);
    return entry;
}

function interpolatePercentile(cfs, points) {
    // points: [[pct, cfs], ...] sorted by cfs ascending
    if (!points || points.length === 0) return null;
    if (cfs <= points[0][1]) return points[0][0];
    if (cfs >= points[points.length - 1][1]) return points[points.length - 1][0];
    for (let i = 0; i < points.length - 1; i++) {
        const [p1, v1] = points[i];
        const [p2, v2] = points[i + 1];
        if (cfs >= v1 && cfs <= v2) {
            if (v2 === v1) return p1;
            const frac = (cfs - v1) / (v2 - v1);
            return p1 + frac * (p2 - p1);
        }
    }
    return null;
}

function categorize(pct) {
    if (pct === null || pct === undefined) return null;
    if (pct < 10)  return 'Much Below Normal';
    if (pct < 25)  return 'Below Normal';
    if (pct <= 75) return 'Normal';
    if (pct <= 90) return 'Above Normal';
    return 'Much Above Normal';
}

async function buildStreamflow(gageId) {
    const [current, stats] = await Promise.allSettled([
        fetchLatestDailyValue(gageId),
        fetchHistoricalStats(gageId)
    ]);

    const out = { gage_id: gageId };

    if (current.status === 'fulfilled' && current.value) {
        out.current_cfs = current.value.cfs;
        out.as_of = current.value.dateTime;
    } else {
        out.current_error = current.status === 'rejected'
            ? String(current.reason?.message || current.reason)
            : 'no recent observation';
    }

    if (stats.status === 'fulfilled' && current.status === 'fulfilled' && current.value) {
        // USGS dv dateTime is "YYYY-MM-DDT..." — use the date portion directly
        // to avoid timezone drift when the observation is at local midnight.
        const key = (current.value.dateTime || '').slice(5, 10);
        const dayStats = stats.value.byDay[key] || stats.value.byDay['02-28'];
        if (dayStats) {
            const pct = interpolatePercentile(current.value.cfs, dayStats.points);
            if (pct !== null) {
                out.percentile = Math.round(pct * 10) / 10;
                out.category = categorize(out.percentile);
                out.baseline_years = '1991–2020';
                out.baseline_count = dayStats.count;
            }
        }
    } else if (stats.status === 'rejected') {
        out.stats_error = String(stats.reason?.message || stats.reason);
    }

    return out;
}

exports.handler = async (event) => {
    const id = parseInt(event.queryStringParameters?.id, 10);
    if (!Number.isFinite(id)) {
        return json(400, { error: 'id parameter is required' });
    }

    const record = datacenters[id];
    if (!record) {
        return json(404, { error: 'Not found' });
    }

    const response = { ...record };
    if (record.gage?.id) {
        response.forecast = forecasts[record.gage.id] || [];
        try {
            response.streamflow = await buildStreamflow(record.gage.id);
        } catch (err) {
            response.streamflow = { gage_id: record.gage.id, error: String(err.message || err) };
        }
    }

    return json(200, response);
};
