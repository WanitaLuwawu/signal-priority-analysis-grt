import pandas as pd
import numpy as np
import os
from scipy.stats import circmean, circstd

GTFS_DIR = "data/gtfs"

# 1. Load required tables
print("Loading tables...")
stop_times = pd.read_csv(f"{GTFS_DIR}/stop_times.txt", dtype=str)
stops      = pd.read_csv(f"{GTFS_DIR}/stops.txt",      dtype=str)
trips      = pd.read_csv(f"{GTFS_DIR}/trips.txt",      dtype=str)
calendar_dates = pd.read_csv(f"{GTFS_DIR}/calendar_dates.txt", dtype=str)

# 2. Attach stop coordinates
stops["stop_lat"] = stops["stop_lat"].astype(float)
stops["stop_lon"] = stops["stop_lon"].astype(float)

stop_times["stop_sequence"] = stop_times["stop_sequence"].astype(int)
all_st = stop_times.merge(
    stops[["stop_id", "stop_lat", "stop_lon"]],
    on="stop_id", how="left"
)

# 3. Compute next stop coordinates on unfiltered trip data
print("Computing next stops per trip on full sequences...")
all_st = all_st.sort_values(["trip_id", "stop_sequence"])

# Get the immediate next stop coordinates in sequence
all_st["next_lat"] = all_st.groupby("trip_id")["stop_lat"].shift(-1)
all_st["next_lon"] = all_st.groupby("trip_id")["stop_lon"].shift(-1)

# Drop last stops of trips (they don't have a next stop)
all_st = all_st.dropna(subset=["next_lat", "next_lon"])

# 4. Bearing calculation function
def compute_bearing(lat1, lon1, lat2, lon2):
    """
    Compute compass bearing (0–360°) from point 1 to point 2.
    """
    lat1, lon1, lat2, lon2 = map(np.radians, [lat1, lon1, lat2, lon2])
    d_lon = lon2 - lon1
    x = np.sin(d_lon) * np.cos(lat2)
    y = (np.cos(lat1) * np.sin(lat2) -
         np.sin(lat1) * np.cos(lat2) * np.cos(d_lon))
    bearing = np.degrees(np.arctan2(x, y))
    return bearing % 360

print("Computing bearings...")
all_st["bearing"] = compute_bearing(
    all_st["stop_lat"].values,
    all_st["stop_lon"].values,
    all_st["next_lat"].values,
    all_st["next_lon"].values
)

# 5. NOW Filter to weekday peak trips
print("Filtering to weekday peak trips...")
weekday_services = calendar_dates[
    calendar_dates["service_id"].str.contains("Weekday", case=False)
]["service_id"].unique()

weekday_trips = trips[trips["service_id"].isin(weekday_services)]["trip_id"]

all_st["arrival_hour"] = all_st["arrival_time"].str.split(":").str[0].astype(int)

peak_weekday_st = all_st[
    (((all_st["arrival_hour"] >= 7)  & (all_st["arrival_hour"] < 9)) |
     ((all_st["arrival_hour"] >= 16) & (all_st["arrival_hour"] < 18))) &
    (all_st["trip_id"].isin(weekday_trips))
].copy()

print(f"  Peak weekday stop visits: {len(peak_weekday_st):,}")

# 6. Sanity Checks with Circular Math
print("\n--- All City Hall stops and their bearings ---")
city_hall_all = peak_weekday_st[
    peak_weekday_st["stop_id"].isin(
        stops[stops["stop_name"].str.contains("City Hall", case=False)]["stop_id"]
    )
]

summary = (city_hall_all
           .groupby(["stop_id", "bearing"])["trip_id"]
           .count()
           .reset_index()
           .rename(columns={"trip_id": "trip_count"})
           .sort_values(["stop_id", "bearing"]))

print(summary.to_string(index=False))

# Check bearing spread using circular statistics
print("\n--- Bearing spread per stop_id (Circular Stats) ---")
def circ_dispersion(degrees):
    # Standard deviation of angles in degrees
    rads = np.radians(degrees)
    return np.degrees(circstd(rads))

bearing_spread = (peak_weekday_st
                  .groupby("stop_id")["bearing"]
                  .agg(
                      circ_mean=lambda x: np.degrees(circmean(np.radians(x))) % 360,
                      circ_std=circ_dispersion,
                      trip_count="count"
                  )
                  .reset_index()
                  .sort_values("circ_std", ascending=False))

print(f"Mean circular std dev across all stops: {bearing_spread['circ_std'].mean():.2f}°")
print(f"Stops with high direction variance (std > 20°): {(bearing_spread['circ_std'] > 20).sum()}")

print("\nTop 10 stops with highest direction variance:")
print(bearing_spread.head(10).to_string(index=False))

# 7. Save for clustering step
os.makedirs("data", exist_ok=True)
peak_weekday_st[["trip_id", "stop_id", "stop_sequence", "bearing"]].to_csv(
    "data/stop_bearings.csv", index=False
)
print(f"\n✅ Saved → data/stop_bearings.csv")