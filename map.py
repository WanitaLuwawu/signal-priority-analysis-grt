import os
import folium
import geopandas as gpd
import pandas as pd

# 1. Load Data
print("Loading signals, TSP rankings, and transit stops...")
# Load master signals file (contains all traffic signals in the network)
all_signals_gdf = gpd.read_file("data/osm/signals.geojson")

# Load pre-calculated TSP candidate rankings
rankings_df = pd.read_csv("outputs/tsp_candidate_rankings.csv")

# Load GTFS / Directional stops dataset
directional_stops_gdf = gpd.read_file("outputs/directional_stop_signals.geojson")

# 2. Projection & Coordinate Extraction
# Ensure CRS is EPSG:4326 (WGS84) for signals
if all_signals_gdf.crs and all_signals_gdf.crs.to_epsg() != 4326:
    all_signals_gdf = all_signals_gdf.to_crs(epsg=4326)

all_signals_gdf["latitude"] = all_signals_gdf.geometry.y
all_signals_gdf["longitude"] = all_signals_gdf.geometry.x

# Ensure CRS is EPSG:4326 for stops
if directional_stops_gdf.crs and directional_stops_gdf.crs.to_epsg() != 4326:
    directional_stops_gdf = directional_stops_gdf.to_crs(epsg=4326)

# Deduplicate stops to unique stop_ids for clean map markers
unique_stops = directional_stops_gdf.drop_duplicates(subset=["stop_id"]).copy()
unique_stops["latitude"] = unique_stops.geometry.y
unique_stops["longitude"] = unique_stops.geometry.x

# 3. Merge Baseline Signals with Candidate Rankings
map_df = pd.merge(all_signals_gdf, rankings_df, on="osmid", how="left")
map_df["tsp_priority"] = map_df["tsp_priority"].fillna("Non-Candidate")

# 4. Build Folium Map
map_center = [map_df["latitude"].mean(), map_df["longitude"].mean()]
m = folium.Map(location=map_center, zoom_start=13, tiles="cartodbpositron")

# Color mapping dictionary
priority_colors = {
    "High Priority": "#d9534f",  # Red
    "Medium Priority": "#f0ad4e",  # Orange
    "Low Priority": "#5bc0de",  # Light Blue
    "Non-Candidate": "#a0a0a0"  # Muted Grey
}

# Create Feature Groups for Signal Tiers
fg_high = folium.FeatureGroup(name="🔴 High Priority (≥ 65)")
fg_medium = folium.FeatureGroup(name="🟠 Medium Priority (40–64)")
fg_low = folium.FeatureGroup(name="🔵 Low Priority (< 40)")
fg_non_candidate = folium.FeatureGroup(name="⚪ Non-Candidate Signals", show=True)

# Create Feature Group and Marker Cluster for Transit Stops
fg_stops = folium.FeatureGroup(name="🚏 Transit Stops", show=True)

groups = {
    "High Priority": fg_high,
    "Medium Priority": fg_medium,
    "Low Priority": fg_low,
    "Non-Candidate": fg_non_candidate
}

# 5. Populate Signal Markers
print("Populating signal markers on map...")
for _, row in map_df.iterrows():
    priority = row["tsp_priority"]
    color = priority_colors[priority]
    target_group = groups[priority]

    if priority == "Non-Candidate":
        radius = 3.5
        fill_opacity = 0.4
        popup_html = f"""
        <div style="font-family: Arial, sans-serif; line-height: 1.4;">
            <b>OSM ID:</b> {row['osmid']}<br>
            <b>Street Count:</b> {row.get('street_count', 'N/A')}<br>
            <i style="color: #777;">Did not qualify for TSP ranking</i>
        </div>
        """
        tooltip = f"Signal {row['osmid']} (Non-Candidate)"
    else:
        radius = 8.5 if priority == "High Priority" else (7 if priority == "Medium Priority" else 5.5)
        fill_opacity = 0.85

        delay_val = row.get("avg_delay_sec", 0)
        delay_str = f"{delay_val:.1f} s" if pd.notnull(delay_val) else "N/A"

        popup_html = f"""
        <div style="font-family: Arial, sans-serif; min-width: 220px; line-height: 1.4;">
            <h4 style="margin: 0 0 5px 0; color: #222;">OSM ID: {row['osmid']}</h4>
            <b style="color: {color}; font-size: 13px;">{priority}</b> 
            (Score: <b>{row['tsp_score']:.1f}</b>)
            <hr style="margin: 8px 0; border: 0; border-top: 1px solid #ccc;">
            <b>Peak Bus Volume:</b> {int(row['total_peak_buses'])} buses<br>
            <b>Avg Realtime Delay:</b> {delay_str}<br>
            <b>Nearest Stop Distance:</b> {row['min_stop_distance_m']:.1f} m<br>
            <b>Stops Served:</b> {int(row['unique_stops_served'])}<br>
            <hr style="margin: 8px 0; border: 0; border-top: 1px solid #ccc;">
            <p style="margin: 0; font-size: 0.85em; color: #444;">
                <b>Stops:</b> {row['stops_list']}
            </p>
        </div>
        """
        tooltip = f"Signal {row['osmid']} — Score: {row['tsp_score']} ({priority})"

    folium.CircleMarker(
        location=[row["latitude"], row["longitude"]],
        radius=radius,
        color=color,
        fill=True,
        fill_color=color,
        fill_opacity=fill_opacity,
        weight=1.2,
        popup=folium.Popup(popup_html, max_width=320),
        tooltip=tooltip
    ).add_to(target_group)

# 6. Populate Transit Stop Markers
print("Populating transit stop markers into cluster layer...")
for _, stop_row in unique_stops.iterrows():
    stop_popup_html = f"""
    <div style="font-family: Arial, sans-serif; min-width: 180px; line-height: 1.4;">
        <h4 style="margin: 0 0 5px 0; color: #2B4C7E;">🚏 {stop_row['stop_name']}</h4>
        <b>Stop ID:</b> {stop_row['stop_id']}<br>
        <b>Serving Signal (OSMID):</b> {stop_row.get('osmid', 'N/A')}<br>
        <b>Dist to Signal:</b> {stop_row.get('distance_m', 0):.1f} m
    </div>
    """

    folium.CircleMarker(
        location=[stop_row["latitude"], stop_row["longitude"]],
        radius=4,
        color="#2B4C7E",  # Dark Navy Blue
        fill=True,
        fill_color="#3498DB",  # Sky Blue fill
        fill_opacity=0.9,
        weight=1,
        popup=folium.Popup(stop_popup_html, max_width=250),
        tooltip=f"Stop {stop_row['stop_id']}: {stop_row['stop_name']}"
    ).add_to(fg_stops)

# Add Signal & Stop Feature Groups to Map
fg_high.add_to(m)
fg_medium.add_to(m)
fg_low.add_to(m)
fg_non_candidate.add_to(m)
fg_stops.add_to(m)

# Add Layer Control UI (top-right)
folium.LayerControl(collapsed=False).add_to(m)

# 7. Add Custom Floating Legend (bottom-left)
legend_html = """
<div style="position: fixed; bottom: 30px; left: 30px; width: 200px; height: 165px; 
            background-color: white; border:2px solid grey; z-index:9999; font-size:13px;
            padding: 10px; border-radius: 6px; font-family: Arial, sans-serif;">
    <b>Map Layers & Priority</b><br><br>
    <i style="background: #d9534f; width: 12px; height: 12px; float: left; margin-right: 8px; margin-top: 2px; border-radius: 50%;"></i> High (≥ 65)<br>
    <i style="background: #f0ad4e; width: 12px; height: 12px; float: left; margin-right: 8px; margin-top: 4px; border-radius: 50%;"></i> Medium (40–64)<br>
    <i style="background: #5bc0de; width: 12px; height: 12px; float: left; margin-right: 8px; margin-top: 4px; border-radius: 50%;"></i> Low (&lt; 40)<br>
    <i style="background: #a0a0a0; width: 10px; height: 10px; float: left; margin-right: 8px; margin-top: 5px; border-radius: 50%;"></i> Non-Candidate<br>
    <i style="background: #3498DB; border: 1px solid #2B4C7E; width: 10px; height: 10px; float: left; margin-right: 8px; margin-top: 5px; border-radius: 50%;"></i> Transit Stop<br>
</div>
"""
m.get_root().html.add_child(folium.Element(legend_html))

# 8. Save Map
os.makedirs("outputs", exist_ok=True)
output_path = "outputs/complete_signal_network_map.html"
m.save(output_path)
print(f"\n✅ Map built with all signals AND transit stops! Saved → {output_path}")