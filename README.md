## Local Development Setup

### Prerequisites
- **Python 3** installed and available as `python3`.
- **VS Code** with the **Jupyter** and **Python** extensions.

### One-time setup
From the project root, run:
```bash
bash init.sh
```

This creates `venv/`, installs dependencies from `requirements.txt`, and registers pre-commit hooks.

### Running the web app locally
```bash
cd web && make serve
```
This runs `scripts/build_data.py` to regenerate `web/data.js` and `functions/datacenter-data.js`, then starts a local server on [http://localhost:8765](http://localhost:8765) that emulates the Netlify Function. See [`web/README.md`](web/README.md) for details.

---

## Web App: Datacenter Drought & Streamflow Map

An interactive map that plots every datacenter in `input_files/datacenters.csv` alongside a live view of nearby water conditions: current U.S. Drought Monitor classification, observed streamflow at the nearest USGS gage, and a 13-week streamflow forecast.

### Glossary

- **Streamgage (or gage)** — A USGS monitoring station on a river or creek that records water height and computes discharge. Each gage has a numeric ID like `08057000`. The web app assigns every datacenter to its single nearest active gage (great-circle distance). A gage 5 km away is a reasonable local proxy for water availability; 80+ km away it's more of a regional indicator — the distance is shown in the sidebar so you can judge relevance.
- **Discharge / streamflow** — The volume of water flowing past a gage per unit time, in **cubic feet per second (cfs)**. The raw observable.
- **Percentile** — A cfs reading's rank against the historical distribution *for that calendar day-of-year* over a 1991–2020 baseline. A 30th percentile reading means 70% of same-day historical readings were higher. Percentiles make values comparable across seasons and gages.
- **WaterWatch categories** — Standard USGS classification of the percentile:
  - `< 10th` — Much Below Normal
  - `10th–25th` — Below Normal
  - `25th–75th` — Normal
  - `75th–90th` — Above Normal
  - `> 90th` — Much Above Normal
- **U.S. Drought Monitor (USDM)** — A weekly federal drought classification published by the National Drought Mitigation Center. Based on precipitation, soil moisture, PDSI, and other indices — *not* streamflow. Categories D0 (Abnormally Dry) through D4 (Exceptional Drought). The shaded overlay on the map.
- **RDC forecast / River DroughtCast** — A machine-learning ensemble (LSTM + LightGBM) that forecasts streamflow percentile 13 weeks ahead per gage. The bar chart in the sidebar.
- **PDSI** — Palmer Drought Severity Index. Not used on the live map, but produced by the notebooks in this repo for historical analysis.

### What you see on the map

| Layer | Source | Retrieved | Cached |
|---|---|---|---|
| Drought shading (USDM polygons, D0–D4) | [USDM ArcGIS FeatureServer](https://services5.arcgis.com/0OTVzJS4K09zlixn/ArcGIS/rest/services/USDM_current/FeatureServer/0) (CORS-enabled) | Client-side on page load | Browser HTTP cache only |
| Datacenter markers | `input_files/datacenters.csv` | Baked into `web/data.js` at build time | Static |

### What you see in the sidebar (on click)

| Card | Source | Retrieved | Cached |
|---|---|---|---|
| Current Streamflow (cfs, percentile, category) | USGS NWIS Daily Values (`waterservices.usgs.gov/nwis/dv/`) + Daily Statistics (`/nwis/stat/`) | Netlify Function per click | In-memory per function container; historical stats TTL = 30 days |
| 13-Week Streamflow Forecast | [USGS River DroughtCast CDN](https://dfi09q69oy2jm.cloudfront.net/visualizations/streamflow-drought-forecasts/conditions/) (14 weekly CSVs, `conditions_w0.csv`–`conditions_w13.csv`) | Fetched live at build time; parquet fallback if CDN is down | Refreshes every Netlify build |
| Datacenter Info (operator, power, address…) | `input_files/datacenters.csv` | Baked into `functions/datacenter-data.js` at build time | Static |

### Build-time vs runtime data

`scripts/build_data.py` runs at build time (locally via `make serve`, in CI via `netlify.toml`) and produces two files:

- **`web/data.js`** — `FeatureCollection` of datacenter coordinates + IDs only. Public, ~150 KB.
- **`functions/datacenter-data.js`** — Per-datacenter metadata and nearest-gage assignment, plus the full RDC forecast time series keyed by gage ID. Server-side only, ~4.4 MB.

The build:
1. Reads `datacenters.csv` (4,682 rows).
2. Fetches the 14 weekly forecast CSVs (`conditions_w0.csv`–`conditions_w13.csv`) from the [USGS River DroughtCast CDN](https://dfi09q69oy2jm.cloudfront.net/visualizations/streamflow-drought-forecasts/conditions/). Week 0 is the current observed condition; weeks 1–13 are forecasts. Each CSV has columns `StaID, dt, pd` (station ID, date, percentile). If the CDN is unreachable, falls back to the most recent local parquet snapshot in `input_files/`.
3. Fetches lat/lng + site name for every forecast gage via the [USGS NWIS site service](https://waterservices.usgs.gov/nwis/site/) (batched ~200 IDs per request). Results cached locally at `.build-cache/stations.json` so subsequent builds only refetch newly-introduced gages.
4. Uses a `BallTree` (haversine metric) to assign each datacenter to its nearest gage, writing `nearest_station_id` and `distance_km` into the datacenter record.

At runtime (each click), the Netlify Function at `functions/datacenter.js`:
1. Looks up the datacenter record by numeric ID.
2. Fetches the gage's latest daily-mean discharge from USGS `nwis/dv/` (14-day lookback, takes most recent non-null).
3. Fetches the gage's 1991–2020 day-of-year percentile table from USGS `nwis/stat/` (min, p05, p10, p25, p50, p75, p90, p95, max per day-of-year). The historical distribution for a given gage barely drifts, so responses are held in an in-memory cache (`STATS_TTL_MS = 30 days`) shared across warm invocations.
4. Linearly interpolates today's cfs into the day-of-year percentile curve to produce a percentile and a category label.
5. Returns the combined payload: datacenter metadata + gage assignment + forecast time series + live streamflow.

### Refresh cadence

| Item | Refresh |
|---|---|
| USDM polygons | Published every Thursday morning (US/Eastern) by the National Drought Mitigation Center. No action required — fetched live. |
| USGS live streamflow | New observations arrive throughout the day; the app fetches the most recent available value per click. |
| USGS historical percentile table | Static (1991–2020 window). Cached 30 days per function container. |
| RDC 13-week forecast | Fetched live from the USGS CDN at every Netlify build. A GitHub Actions cron (`.github/workflows/weekly-forecast-refresh.yml`) triggers a rebuild every Wednesday at 6 PM UTC. Manual rebuilds also pick up fresh data. |
| Datacenter inventory | Only refreshes when `input_files/datacenters.csv` is updated and the build script is re-run. |

### Scheduled forecast refresh (setup required)

A GitHub Actions workflow at `.github/workflows/weekly-forecast-refresh.yml` triggers a Netlify rebuild every Wednesday at 6 PM UTC so the site picks up fresh RDC forecasts from the USGS CDN.

**One-time setup:**
1. In **Netlify** → Site settings → Build hooks, create a hook named "Weekly forecast refresh" and copy the URL.
2. In **GitHub** → Settings → Secrets → Actions, create a repository secret named `NETLIFY_BUILD_HOOK` with that URL as the value.

The workflow can also be triggered manually from the Actions tab.

### Known limitations

- **Gage coverage is uneven.** Some datacenters are assigned to a gage 50–100 km away, especially in rural Texas and the arid West. The `distance_km` field in the sidebar makes this visible. A large distance means "regional hydrological context," not "the creek next door."
- **Some gages don't report.** Around ~5% of the 2,939 forecast-eligible gages have no recent daily value (discontinued, seasonal, or currently offline). The sidebar shows "Live reading unavailable" and falls back to the forecast.

---

## PDSI Resampling & Trend Analysis

This project focuses on the **temporal resampling** of high-resolution climate data (gridMET) and the identification of **seasonal drought trends** in West Des Moines, Iowa (2022-2025).

### **Core Objectives:**
* **Data Resampling:** Aggregating 5-day pentad resolution into monthly arithmetic means for climate monitoring.
* **Trend Visualization:** Identifying seasonal variations in the Palmer Drought Severity Index (PDSI) using standardized classification thresholds.

### **Latest Analysis Result:**
![Monthly PDSI Analysis](output_files/Monthly%20PDSI%20analysis.png)
*Figure 1: High-contrast visualization of monthly PDSI trends, highlighting the rapid hydrological shifts observed in 2025.*

### **Methodology & Standards:**
Data processing is performed via **Python (Pandas/Seaborn)**. To ensure international scientific alignment, visualization thresholds follow the standardized **Palmer Drought Severity Index** categories:
* **<-3.0**: Severe/Extreme Drought (Brown)
* **-2.0 to -2.9**: Moderate Drought (Orange)
* **-1.9 to 1.9**: Near Normal (Neutral)
* **>2.0**: Unusually Moist (Green)

### **Repository Contents:**
* **Input:** [`pentads_pdsi_wdm_2022_2025.csv`](input_files/pentads_pdsi_wdm_2022_2025.csv) — Original 5-day resolution data.
* **Notebook:** [`PDSI_pentads_to_monthly_Des_Moines_2022_2025.ipynb`](notebooks/PDSI_pentads_to_monthly_Des_Moines_2022_2025.ipynb) — Main processing pipeline (Cleaning  → Resampling → Plotting).
* **Output:** [`monthly_pdsi_wdm_2022_2025.csv`](output_files/monthly_pdsi_wdm_2022_2025.csv) — Final processed monthly dataset.
