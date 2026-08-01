import os
import pandas as pd
import numpy as np
from datetime import datetime, timezone
from google.transit import gtfs_realtime_pb2

# File Paths
GTFS_DIR = "data/gtfs"
REALTIME_DIR = "data/realtime"
PB_FILE = os.path.join(REALTIME_DIR, "trip_updates.pb")
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

# 2. Parse GTFS real-time timestamps
print("\n--- 2. Parsing Realtime Timestamps & Calculating Delays ---")


def decode_rt_timestamps(pb_path):
    if not os.path.exists(pb_path):
        print(f"  ⚠️ Warning: File not found at '{pb_path}'.")
        return pd.DataFrame(columns=["trip_id", "stop_id", "stop_sequence", "rt_arrival_time"])

    feed = gtfs_realtime_pb2.FeedMessage()
    with open(pb_path, "rb") as f:
        feed.ParseFromString(f.read())

    records = []
    for entity in feed.entity:
        if entity.HasField("trip_update"):
            tu = entity.trip_update
            trip_id = str(tu.trip.trip_id)

            for st in tu.stop_time_update:
                rt_time = None
                if st.HasField("arrival") and st.arrival.HasField("time"):
                    rt_time = st.arrival.time
                elif st.HasField("departure") and st.departure.HasField("time"):
                    rt_time = st.departure.time

                if rt_time is not None:
                    records.append({
                        "trip_id": trip_id,
                        "stop_id": str(st.stop_id).strip(),
                        "stop_sequence": str(st.stop_sequence),
                        "rt_arrival_time": rt_time
                    })

    return pd.DataFrame(records)


rt_df = decode_rt_timestamps(PB_FILE)
print(f"  ✅ Extracted {len(rt_df):,} real-time predictions from 401 active trip updates.")

if not rt_df.empty:
    # Merge real-time arrival timestamps with static schedule
    merged_rt = rt_df.merge(
        stop_times[["trip_id", "stop_id", "arrival_time"]],
        on=["trip_id", "stop_id"],
        how="inner"
    )

    # Convert static arrival_time ("HH:MM:SS") + today's date into Unix timestamp
    today_date_str = datetime.now().strftime("%Y-%m-%d")


    def convert_to_unix(row):
        try:
            time_str = row["arrival_time"].strip()
            hours, minutes, seconds = map(int, time_str.split(":"))

            # Handle late-night GTFS times (e.g. 25:10:00 -> next day 01:10:00)
            day_offset = hours // 24
            hours = hours % 24

            dt = datetime.strptime(today_date_str, "%Y-%m-%d")
            dt = dt.replace(hour=hours, minute=minutes, second=seconds)

            # Add day offset if arrival hour was >= 24
            if day_offset > 0:
                dt = dt + pd.Timedelta(days=day_offset)

            # Assume local time offset (EDT = UTC-4)
            timestamp_sec = int(dt.replace(tzinfo=timezone.utc).timestamp()) + (4 * 3600)
            return timestamp_sec
        except Exception:
            return None


    merged_rt["sched_unix"] = merged_rt.apply(convert_to_unix, axis=1)

    # Delay = Real-time Unix Timestamp - Scheduled Unix Timestamp (in seconds)
    merged_rt["delay_sec"] = merged_rt["rt_arrival_time"] - merged_rt["sched_unix"]

    # Filter extreme anomalies/outliers (keep delays between -5 mins and +30 mins)
    valid_delays = merged_rt[(merged_rt["delay_sec"] >= -300) & (merged_rt["delay_sec"] <= 1800)]

    # Aggregate delays per stop ID
    delay_summary = valid_delays.groupby("stop_id").agg(
        avg_snapshot_delay_sec=("delay_sec", "mean"),
        max_snapshot_delay_sec=("delay_sec", "max"),
        sample_count=("delay_sec", "count")
    ).reset_index()
else:
    delay_summary = pd.DataFrame(
        columns=["stop_id", "avg_snapshot_delay_sec", "max_snapshot_delay_sec", "sample_count"])

# ==============================================================================
# SECTION 3: COMBINE STATIC + REALTIME & SAVE
# ==============================================================================
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