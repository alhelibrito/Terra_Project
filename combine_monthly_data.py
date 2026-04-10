#!/usr/bin/env python
"""
Build a single monthly table for 2022–2025 combining:

  - Observed monthly streamflow at Walnut Creek (USGS-05484800)
  - 1991–2020 baseline P5/P10/P25/P50 streamflow percentiles for each calendar month
  - Monthly PDSI for West Des Moines, IA (resampled from gridMET pentads)
  - Microsoft data center monthly water use

Output:  output_files/combined_monthly_2022_2025.csv

Requires the USGS_API_KEY environment variable for the Statistics API.
"""

import os
import pandas as pd
import numpy as np
import requests
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.dates as mdates


# ──────────────────────────────────────────────────────────────────────
# CONFIGURATION
# ──────────────────────────────────────────────────────────────────────

SITE_ID = "USGS-05484800"  # Walnut Creek at Des Moines, IA
PARAM_CODE = "00060"  # Discharge, ft³/s

BASELINE_START = "1991-01-01"
BASELINE_END = "2020-12-31"
RECENT_START = "2022-01-01"
RECENT_END = "2025-12-31"

STATS_BASE = "https://api.waterdata.usgs.gov/statistics/v0"

PDSI_FILE = "input_files/pentads_pdsi_wdm_2022_2025.csv"
WATER_USE_FILE = "input_files/microsoft_water_use_2022_2025.csv"
OUTPUT_FILE = "output_files/combined_monthly_2022_2025.csv"


# ──────────────────────────────────────────────────────────────────────
# 1. STREAMFLOW (USGS observationIntervals)
# ──────────────────────────────────────────────────────────────────────


def _add_api_key(params: dict) -> dict:
    key = os.getenv("USGS_API_KEY")
    if not key:
        raise ValueError("USGS_API_KEY env var not set")
    return {**params, "api_key": key}


def _unnest_rows(df: pd.DataFrame, nested_col: str) -> pd.DataFrame:
    """Expand a column of list-of-records into separate rows."""
    records = []
    for _, row in df.iterrows():
        nested = row[nested_col]
        if isinstance(nested, list):
            meta = row.drop(nested_col).to_dict()
            for rec in nested:
                records.append({**meta, **rec})
    return pd.DataFrame(records) if records else pd.DataFrame()


def fetch_observation_intervals(start: str, end: str) -> pd.DataFrame:
    """Fetch observationIntervals records from the USGS Statistics API."""
    params = _add_api_key(
        {
            "monitoring_location_id": SITE_ID,
            "parameter_code": PARAM_CODE,
            "start_date": start,
            "end_date": end,
        }
    )
    print(f"Fetching observationIntervals: {start} → {end}")
    resp = requests.get(f"{STATS_BASE}/observationIntervals", params=params, timeout=120)
    resp.raise_for_status()
    data = resp.json()

    if isinstance(data, list):
        df = pd.DataFrame(data)
    elif isinstance(data, dict) and "results" in data:
        df = pd.DataFrame(data["results"])
    elif isinstance(data, dict) and "features" in data:
        df = pd.DataFrame([f["properties"] for f in data["features"]])
    else:
        raise ValueError(f"Unexpected API response shape: {type(data)}")

    df = _unnest_rows(df, "data")
    df = _unnest_rows(df, "values")
    print(f"  Retrieved {len(df)} records")
    return df


def _filter_monthly_arithmetic_mean(df: pd.DataFrame) -> pd.DataFrame:
    """Filter observationIntervals output to monthly arithmetic_mean rows."""
    monthly = df[
        df["interval_type"].str.contains("month", case=False, na=False)
    ].copy()
    monthly = monthly[monthly["computation"] == "arithmetic_mean"]
    monthly["value"] = pd.to_numeric(monthly["value"], errors="coerce")
    monthly["_date"] = pd.to_datetime(monthly["start_date"])
    monthly["year"] = monthly["_date"].dt.year
    monthly["month"] = monthly["_date"].dt.month
    return monthly


def compute_baseline_percentiles(baseline_raw: pd.DataFrame) -> pd.DataFrame:
    """P5/P10/P25/P50 for each calendar month, computed across baseline years."""
    monthly = _filter_monthly_arithmetic_mean(baseline_raw)

    def pct(p):
        return lambda x: np.nanpercentile(x.dropna(), p)

    return (
        monthly.groupby("month")["value"]
        .agg(p5=pct(5), p10=pct(10), p25=pct(25), p50=pct(50))
        .reset_index()
    )


def extract_recent_streamflow(recent_raw: pd.DataFrame) -> pd.DataFrame:
    """Recent monthly observed streamflow as (year, month, streamflow_cfs)."""
    monthly = _filter_monthly_arithmetic_mean(recent_raw)
    return monthly[["year", "month", "value"]].rename(
        columns={"value": "streamflow_cfs"}
    )


# ──────────────────────────────────────────────────────────────────────
# 2. PDSI  (gridMET pentads → monthly mean)
# ──────────────────────────────────────────────────────────────────────


def load_monthly_pdsi(path: str) -> pd.DataFrame:
    """Load pentad PDSI CSV and resample to monthly arithmetic means."""
    df = pd.read_csv(path, skiprows=1, names=["date", "pdsi"])
    df["date"] = pd.to_datetime(df["date"], dayfirst=True, errors="coerce")
    df = df.dropna(subset=["date"]).set_index("date")
    df["pdsi"] = pd.to_numeric(df["pdsi"], errors="coerce")

    monthly = df["pdsi"].resample("MS").mean().reset_index()
    monthly["year"] = monthly["date"].dt.year
    monthly["month"] = monthly["date"].dt.month
    return monthly[["year", "month", "pdsi"]]


# ──────────────────────────────────────────────────────────────────────
# 3. Microsoft data center water use (wide → long)
# ──────────────────────────────────────────────────────────────────────


def load_microsoft_water_use(path: str) -> pd.DataFrame:
    """Reshape the wide year × month water-use CSV into (year, month, water_use)."""
    raw = pd.read_csv(path)
    # First column holds e.g. "2022 Microsoft"; extract the year
    raw = raw.rename(columns={raw.columns[0]: "label"})
    raw["year"] = raw["label"].str.extract(r"(\d{4})").astype(int)

    month_cols = [
        "January", "February", "March", "April", "May", "June",
        "July", "August", "September", "October", "November", "December",
    ]

    long = raw.melt(
        id_vars="year",
        value_vars=month_cols,
        var_name="month_name",
        value_name="datacenter_water_use",
    )
    long["month"] = pd.to_datetime(long["month_name"], format="%B").dt.month
    long["datacenter_water_use"] = pd.to_numeric(
        long["datacenter_water_use"], errors="coerce"
    )
    return long[["year", "month", "datacenter_water_use"]]


# ──────────────────────────────────────────────────────────────────────
# 4. Combine
# ──────────────────────────────────────────────────────────────────────


def build_combined_table() -> pd.DataFrame:
    # Streamflow
    baseline_raw = fetch_observation_intervals(BASELINE_START, BASELINE_END)
    recent_raw = fetch_observation_intervals(RECENT_START, RECENT_END)
    baseline_pct = compute_baseline_percentiles(baseline_raw)
    recent_flow = extract_recent_streamflow(recent_raw)

    # PDSI + water use
    pdsi = load_monthly_pdsi(PDSI_FILE)
    water_use = load_microsoft_water_use(WATER_USE_FILE)

    # Spine: every month in 2022–2025
    months = pd.date_range(RECENT_START, RECENT_END, freq="MS")
    spine = pd.DataFrame(
        {"month": months, "year": months.year, "month_num": months.month}
    )

    combined = (
        spine.merge(
            recent_flow.rename(columns={"month": "month_num"}),
            on=["year", "month_num"],
            how="left",
        )
        .merge(baseline_pct.rename(columns={"month": "month_num"}), on="month_num", how="left")
        .merge(
            pdsi.rename(columns={"month": "month_num"}),
            on=["year", "month_num"],
            how="left",
        )
        .merge(
            water_use.rename(columns={"month": "month_num"}),
            on=["year", "month_num"],
            how="left",
        )
    )

    combined = combined[
        [
            "month",
            "streamflow_cfs",
            "p5",
            "p10",
            "p25",
            "p50",
            "pdsi",
            "datacenter_water_use",
        ]
    ].sort_values("month").reset_index(drop=True)

    return combined


# ──────────────────────────────────────────────────────────────────────
# 5. Plot
# ──────────────────────────────────────────────────────────────────────

# Colors shared between bars and their corresponding threshold lines
COLOR_P5    = "#c0392b"  # red
COLOR_P10   = "#8e44ad"  # purple
COLOR_P25   = "#e67e22"  # orange
COLOR_P50   = "#2980b9"  # blue
COLOR_ABOVE = "#27ae60"  # green (≥ P50)


def _bar_color(flow, p5, p10, p25, p50):
    """Color matching the lowest percentile threshold the bar falls below."""
    if pd.isna(flow):
        return "#bdc3c7"
    if flow < p5:
        return COLOR_P5
    if flow < p10:
        return COLOR_P10
    if flow < p25:
        return COLOR_P25
    if flow < p50:
        return COLOR_P50
    return COLOR_ABOVE


def plot_combined_table(table: pd.DataFrame, output_path: str | None = None) -> None:
    """
    Three stacked panels sharing a 2022–2025 monthly time axis:
      1. Walnut Creek streamflow with P5/P10/P25/P50 baseline lines
      2. PDSI for West Des Moines
      3. Microsoft data center water use
    """
    fig, (ax_flow, ax_pdsi, ax_water) = plt.subplots(
        3, 1, figsize=(14, 11), sharex=True
    )

    months = table["month"]
    bar_width = 20  # days

    # ── Panel 1: streamflow ────────────────────────────────────────────
    flow_colors = [
        _bar_color(row["streamflow_cfs"], row["p5"], row["p10"], row["p25"], row["p50"])
        for _, row in table.iterrows()
    ]
    ax_flow.bar(
        months, table["streamflow_cfs"],
        color=flow_colors, alpha=0.85, width=bar_width, zorder=2,
    )
    ax_flow.plot(months, table["p50"], color=COLOR_P50, linestyle="--",
                 linewidth=1.6, marker="o", markersize=3, zorder=3, label="Baseline P50")
    ax_flow.plot(months, table["p25"], color=COLOR_P25, linestyle="--",
                 linewidth=1.6, marker="s", markersize=3, zorder=3, label="Baseline P25")
    ax_flow.plot(months, table["p10"], color=COLOR_P10, linestyle=":",
                 linewidth=1.4, marker="^", markersize=3, zorder=3, label="Baseline P10")
    ax_flow.plot(months, table["p5"],  color=COLOR_P5,  linestyle=":",
                 linewidth=1.4, marker="v", markersize=3, zorder=3, label="Baseline P5")

    ax_flow.set_ylabel("Discharge (ft³/s)")
    ax_flow.set_title(
        "Walnut Creek Monthly Streamflow vs. 1991–2020 Baseline  (USGS-05484800)",
        fontsize=12, fontweight="bold", loc="left",
    )
    ax_flow.yaxis.grid(True, linestyle=":", alpha=0.5)
    ax_flow.set_axisbelow(True)

    bar_legend = [
        mpatches.Patch(color=COLOR_ABOVE, alpha=0.85, label="Flow ≥ P50"),
        mpatches.Patch(color=COLOR_P50,   alpha=0.85, label="P25 ≤ flow < P50"),
        mpatches.Patch(color=COLOR_P25,   alpha=0.85, label="P10 ≤ flow < P25"),
        mpatches.Patch(color=COLOR_P10,   alpha=0.85, label="P5 ≤ flow < P10"),
        mpatches.Patch(color=COLOR_P5,    alpha=0.85, label="Flow < P5"),
    ]
    line_handles, _ = ax_flow.get_legend_handles_labels()
    ax_flow.legend(handles=bar_legend + line_handles, fontsize=8, loc="upper left", ncol=2)

    # ── Panel 2: PDSI ──────────────────────────────────────────────────
    ax_pdsi.plot(months, table["pdsi"], color="#8e6e2a", linewidth=1.6, marker="o", markersize=4)
    ax_pdsi.fill_between(months, table["pdsi"], 0,
                         where=table["pdsi"] < 0, color="#c0392b", alpha=0.25, label="Drier")
    ax_pdsi.fill_between(months, table["pdsi"], 0,
                         where=table["pdsi"] >= 0, color="#2980b9", alpha=0.25, label="Wetter")
    ax_pdsi.axhline(0, color="black", linestyle="--", linewidth=1)
    ax_pdsi.set_ylabel("PDSI")
    ax_pdsi.set_title(
        "Palmer Drought Severity Index — West Des Moines, IA (gridMET)",
        fontsize=12, fontweight="bold", loc="left",
    )
    ax_pdsi.yaxis.grid(True, linestyle=":", alpha=0.5)
    ax_pdsi.set_axisbelow(True)
    ax_pdsi.legend(fontsize=8, loc="upper left")

    # ── Panel 3: Microsoft data center water use ──────────────────────
    water_millions = table["datacenter_water_use"] / 1e6
    ax_water.bar(months, water_millions, color="#16a085", alpha=0.85, width=bar_width, zorder=2)
    ax_water.set_ylabel("Water use (million gal)")
    ax_water.set_title(
        "Microsoft Data Center Monthly Water Use",
        fontsize=12, fontweight="bold", loc="left",
    )
    ax_water.yaxis.grid(True, linestyle=":", alpha=0.5)
    ax_water.set_axisbelow(True)

    # ── Shared x-axis formatting ───────────────────────────────────────
    ax_water.xaxis.set_major_locator(mdates.YearLocator())
    ax_water.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ax_water.xaxis.set_minor_locator(mdates.MonthLocator())
    ax_water.set_xlabel("Month")

    fig.suptitle(
        "Combined Monthly Indicators (2022–2025)",
        fontsize=14, fontweight="bold", y=1.00,
    )
    plt.tight_layout()

    if output_path:
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        fig.savefig(output_path, dpi=150, bbox_inches="tight")
        print(f"Saved combined plot to:           {output_path}")

    plt.show()


# ──────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    table = build_combined_table()

    print("\n" + "=" * 90)
    print("COMBINED MONTHLY TABLE (2022–2025)")
    print("=" * 90)
    print(table.to_string(index=False))

    os.makedirs("output_files", exist_ok=True)
    table.to_csv(OUTPUT_FILE, index=False)
    print(f"\nSaved combined monthly table to: {OUTPUT_FILE}")

    plot_combined_table(table, output_path="output_files/combined_monthly_2022_2025.png")
