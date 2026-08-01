import pandas as pd
import geopandas as gpd
import numpy as np
import osmnx as ox
import os

os.makedirs("data/osm", exist_ok=True)
os.makedirs("outputs", exist_ok=True)

# 1. Load stop volumes & directional bearings
print("Loading stop data and bearings...")
stops_df = pd.read_csv("data/peak_buses_with_delays.csv", dtype={"stop_id": str})
bearings_df = pd.read_csv("data/stop_bearings.csv", dtype={"stop_id": str})

# Map 0–360° bearings to 4 Cardinal Directions
def bearing_to_cardinal(b):
    if (b >= 315) or (b < 45):
        return "Northbound"
    elif 45 <= b < 135:
        return "Eastbound"
    elif 135 <= b < 225:
        return "Southbound"
    else:
        return "Westbound"

bearings_df["cardinal_dir"] = bearings_df["bearing"].apply(bearing_to_cardinal)

# Group by stop_id AND cardinal direction to count trips in each heading
stop_headings = (
    bearings_df.groupby(["stop_id", "cardinal_dir"])
    .agg(
        avg_bearing=("bearing", "mean"),
        heading_trip_count=("trip_id", "count")
    )
    .reset_index()
)

# Merge back with the main stop attributes
stops_directional = stops_df.merge(stop_headings, on="stop_id", how="inner")
print(f"  Directional stop-heading combinations: {len(stops_directional):,}")

# Convert to GeoDataFrame
stops_gdf = gpd.GeoDataFrame(
    stops_directional,
    geometry=gpd.points_from_xy(stops_directional["stop_lon"], stops_directional["stop_lat"]),
    crs="EPSG:4326"
)

# 2. Fetch traffic signals from OSM
print("\nFetching traffic signals from OpenStreetMap...")
PLACE = "Regional Municipality of Waterloo, Ontario, Canada"
G = ox.graph_from_place(PLACE, network_type="drive")
nodes, _ = ox.graph_to_gdfs(G)

signals = nodes[nodes["highway"] == "traffic_signals"].copy().reset_index()
print(f"  Signalized intersections found: {len(signals):,}")

# 3. Reproject to UTM Zone 17N (Metres)
print("\nReprojecting to UTM Zone 17N (EPSG:32617)...")
stops_utm = stops_gdf.to_crs("EPSG:32617")
signals_utm = signals.to_crs("EPSG:32617")

# 4. Find Nearest Signal per Stop Heading Direction
print("\nFinding nearest signal within 150m for each stop heading...")

MAX_SEARCH_DIST = 150.0  # Metres

# Spatial join nearest signals within 150 meters directly
matches = gpd.sjoin_nearest(
    stops_utm,
    signals_utm[["osmid", "geometry"]],
    how="inner",
    max_distance=MAX_SEARCH_DIST,
    distance_col="distance_m"
)

# Map original signal geometries to calculate bearings cleanly
signals_map = signals_utm.set_index("osmid")["geometry"]
matches["signal_point"] = matches["osmid"].map(signals_map)

# Calculate compass bearing from Stop Point -> Signal Point
def compute_bearing_vector(x1, y1, x2, y2):
    dx = x2 - x1
    dy = y2 - y1
    angle = np.degrees(np.arctan2(dx, dy))
    return angle % 360

matches["signal_bearing"] = compute_bearing_vector(
    matches.geometry.x,
    matches.geometry.y,
    matches["signal_point"].x,
    matches["signal_point"].y
)

# Calculate angular difference between bus travel heading and signal position
def angular_diff(a1, a2):
    diff = np.abs(a1 - a2) % 360
    return np.minimum(diff, 360 - diff)

matches["heading_signal_diff"] = angular_diff(
    matches["avg_bearing"],
    matches["signal_bearing"]
)

# Keep signals that are roughly in front of the bus direction (within ±60° cone)
AHEAD_CONE_ANGLE = 60.0
ahead_matches = matches[matches["heading_signal_diff"] <= AHEAD_CONE_ANGLE].copy()

# Pick the single nearest downstream signal per (stop_id, cardinal_dir)
nearest_directional_signals = (
    ahead_matches.sort_values("distance_m")
    .groupby(["stop_id", "cardinal_dir"])
    .first()
    .reset_index()
)

print(f"  Matched {len(nearest_directional_signals):,} stop-heading pairs to downstream signals")

# 5. Save Results
output_cols = [
    "stop_id", "stop_name", "peak_buses", "cardinal_dir", "heading_trip_count",
    "avg_bearing", "osmid", "distance_m", "heading_signal_diff", "geometry"
]

# Retain only existing output columns
available_cols = [c for c in output_cols if c in nearest_directional_signals.columns]

output_gdf = gpd.GeoDataFrame(
    nearest_directional_signals[available_cols],
    geometry="geometry",
    crs="EPSG:32617"
)

output_gdf.to_file("outputs/directional_stop_signals.geojson", driver="GeoJSON")
print(f"\n✅ Saved → outputs/directional_stop_signals.geojson")

# Print Sample Results
print("\n--- Sample Nearest Signals by Stop Heading ---")
print(
    output_gdf[["stop_id", "stop_name", "cardinal_dir", "distance_m", "osmid"]]
    .head(10)
    .to_string(index=False)
)