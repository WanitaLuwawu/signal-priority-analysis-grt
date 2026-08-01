import os
import geopandas as gpd
import pandas as pd
import numpy as np

os.makedirs("outputs", exist_ok=True)

# 1. Load directional stop-signal dataset & live delays
print("Loading directional stop-signal data and realtime delays...")
df = gpd.read_file("outputs/directional_stop_signals.geojson")
delays_df = pd.read_csv("data/peak_buses_with_delays.csv", dtype={"stop_id": str})

print(f"  Total stop-signal directional pairs: {len(df):,}")

# Ensure clean string joining
df["stop_id"] = df["stop_id"].astype(str)

# Merge real-time snapshot delay data onto spatial stop-signals
df = df.merge(
    delays_df[["stop_id", "avg_snapshot_delay_sec"]],
    on="stop_id",
    how="left"
)
df["avg_snapshot_delay_sec"] = df["avg_snapshot_delay_sec"].fillna(0)

# 2. Linear Component Normalization
# Volume Score (relative to maximum heading volume)
max_heading_volume = df["heading_trip_count"].max()
df["volume_score"] = df["heading_trip_count"] / max_heading_volume if max_heading_volume > 0 else 0

# Delay Score (Capped at 180 seconds / 3 minutes for 100% score)
df["delay_score"] = np.clip(df["avg_snapshot_delay_sec"] / 180.0, 0, 1)

# 3. Aggregate by Signal (OSMID)
signal_summary = df.groupby("osmid").agg(
    total_peak_buses=("heading_trip_count", "sum"),
    max_volume_score=("volume_score", "max"),
    max_delay_score=("delay_score", "max"),
    avg_delay_sec=("avg_snapshot_delay_sec", "mean"),
    min_stop_distance_m=("distance_m", "min"),
    unique_stops_served=("stop_id", "nunique"),
    unique_directions_served=("cardinal_dir", "nunique"),
    stops_list=("stop_name", lambda x: " | ".join(x.unique()))
).reset_index()

# 4. Calculate Final Composite TSP Score
# Proximity Score: 1.0 at 0m distance -> 0.0 at 150m boundary
signal_summary["norm_proximity"] = np.clip(1.0 - (signal_summary["min_stop_distance_m"] / 150.0), 0, 1)

# Multi-Directional Score: Ratio out of 4 possible directions (0.25 to 1.0)
signal_summary["norm_directions"] = signal_summary["unique_directions_served"] / 4.0

# Composite Formula: 40% Volume + 25% Delay + 20% Proximity + 15% Coverage
signal_summary["tsp_score"] = (
    (signal_summary["max_volume_score"] * 40) +
    (signal_summary["max_delay_score"] * 25) +
    (signal_summary["norm_proximity"] * 20) +
    (signal_summary["norm_directions"] * 15)
).round(1)

# Assign Priority Tiers
def assign_priority(score):
    if score >= 65:
        return "High Priority"
    elif score >= 40:
        return "Medium Priority"
    else:
        return "Low Priority"

signal_summary["tsp_priority"] = signal_summary["tsp_score"].apply(assign_priority)
signal_summary = signal_summary.sort_values("tsp_score", ascending=False)

# 5. Save Priority Rankings
signal_summary.to_csv("outputs/tsp_candidate_rankings.csv", index=False)
print("\n✅ Saved → outputs/tsp_candidate_rankings.csv")

print("\n--- Top 15 High-Priority TSP Candidate Signals ---")
top_cols = [
    "osmid", "tsp_priority", "tsp_score", "total_peak_buses",
    "avg_delay_sec", "min_stop_distance_m", "stops_list"
]
print(signal_summary[top_cols].head(15).to_string(index=False))