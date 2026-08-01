import os
import pandas as pd
import numpy as np
from datetime import datetime, timezone

# File Paths
GTFS_DIR = "data/gtfs"
REALTIME_DIR = "data/realtime"
OUTPUT_CSV = "data/peak_buses_with_delays.csv"

# 1. Parse static GTFS tables
print("--- 1. Parsing Static GTFS Data ---")
calendar_dates = pd.read_csv(f"{GTFS_DIR}/calendar_dates.txt", dtype=str)
trips = pd.read_csv(f"{GTFS_DIR}/trips.txt", dtype=str)
stop_times = pd.read_csv(f"{GTFS_DIR}/stop_times.txt", dtype=str)
stops = pd.read_csv(f"{GTFS_DIR}/stops.txt", dtype=str)

# Filter to weekday service IDs
weekday_services = calendar_dates[
    calendar_dates["service_id"].str.contains("Weekday", case=False, na=False)
]["service_id"].unique()

weekday_trips = trips[trips["service_id"].isin(weekday_services)]

# Parse arrival hours and filter to AM/PM Peak periods (7–9 AM and 4–6 PM)
stop_times["arrival_hour"] = stop_times["arrival_time"].str.split(":").str[0].astype(int)

AM_PEAK_START, AM_PEAK_END = 7, 9
PM_PEAK_START, PM_PEAK_END = 16, 18

peak_stop_times = stop_times[
    ((stop_times["arrival_hour"] >= AM_PEAK_START) & (stop_times["arrival_hour"] < AM_PEAK_END)) |
    ((stop_times["arrival_hour"] >= PM_PEAK_START) & (stop_times["arrival_hour"] < PM_PEAK_END))
    ]

# Keep peak visits on weekday trips
peak_weekday = peak_stop_times[
    peak_stop_times["trip_id"].isin(weekday_trips["trip_id"])
]

# Calculate total peak buses per stop ID
buses_per_stop = (
    peak_weekday
    .groupby("stop_id")["trip_id"]
    .nunique()
    .reset_index()
    .rename(columns={"trip_id": "peak_buses"})
)

# Merge stop coordinates and names
stops["stop_lat"] = stops["stop_lat"].astype(float)
stops["stop_lon"] = stops["stop_lon"].astype(float)

static_summary = buses_per_stop.merge(
    stops[["stop_id", "stop_name", "stop_lat", "stop_lon"]],
    on="stop_id",
    how="left"
)
print(f"  ✅ Parsed {len(static_summary):,} static bus stops across peak periods.")

# 2. Parse accumulated delay records from GitHub
print("\n--- 2. Loading Accumulated Delay Records ---")

DELAY_RECORDS_CSV = "data/realtime/delay_records.csv"

if os.path.exists(DELAY_RECORDS_CSV):
    delay_records = pd.read_csv(DELAY_RECORDS_CSV, dtype={"stop_id": str})
    delay_records["delay_sec"] = delay_records["delay_sec"].astype(float)

    # Show coverage summary
    snapshot_count = delay_records["snapshot_time"].nunique()
    print(f"  ✅ Loaded {len(delay_records):,} delay records")
    print(f"  ✅ Across {snapshot_count} snapshots")
    print(f"  Date range: {delay_records['snapshot_time'].min()} → "
          f"{delay_records['snapshot_time'].max()}")

    # Filter outliers
    valid_delays = delay_records[
        (delay_records["delay_sec"] >= -300) &
        (delay_records["delay_sec"] <= 1800)
    ]

    # Aggregate across ALL snapshots per stop
    delay_summary = valid_delays.groupby("stop_id").agg(
        avg_snapshot_delay_sec=("delay_sec", "mean"),
        max_snapshot_delay_sec=("delay_sec", "max"),
        sample_count=("delay_sec", "count")
    ).reset_index()

    delay_summary["avg_snapshot_delay_sec"] = \
        delay_summary["avg_snapshot_delay_sec"].round(1)
    delay_summary["max_snapshot_delay_sec"] = \
        delay_summary["max_snapshot_delay_sec"].round(1)

    print(f"  Stops with delay data: {len(delay_summary):,}")

else:
    print(f"  ⚠️ No delay records found at '{DELAY_RECORDS_CSV}'")
    print(f"     Run the GitHub Action first to collect data.")
    delay_summary = pd.DataFrame(
        columns=["stop_id", "avg_snapshot_delay_sec",
                 "max_snapshot_delay_sec", "sample_count"])

# 3. COMBINE STATIC + REALTIME & SAVE
print("\n--- 3. Merging & Exporting ---")

final_df = static_summary.merge(delay_summary, on="stop_id", how="left")

# Fill stops without live buses in this snapshot with 0
final_df["avg_snapshot_delay_sec"] = final_df["avg_snapshot_delay_sec"].fillna(0).round(1)
final_df["max_snapshot_delay_sec"] = final_df["max_snapshot_delay_sec"].fillna(0).round(1)
final_df["sample_count"] = final_df["sample_count"].fillna(0).astype(int)

# Sort by peak bus volume
final_df = final_df.sort_values("peak_buses", ascending=False)

# Save output
final_df.to_csv(OUTPUT_CSV, index=False)

print(f"✅ Master parsed table saved → {OUTPUT_CSV}")
print("\nTop 10 Stops with Sampled Delays:")
sampled_stops = final_df[final_df["sample_count"] > 0]
if not sampled_stops.empty:
    print(sampled_stops[["stop_id", "stop_name", "peak_buses", "avg_snapshot_delay_sec", "sample_count"]].head(
        10).to_string(index=False))
else:
    print("No matching stop delays found in this snapshot.")