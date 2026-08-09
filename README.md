# Signal Priority Analysis — Grand River Transit (GRT)

By combining static and real-time GTFS data from GRT with spatial 
data from OpenStreetMap, this project aims to rank signalized 
intersections across the Waterloo Region by TSP implementation priority.

> **Status: Ongoing** — Real-time delay data is being collected 
> through August and September 2026 to capture operating conditions 
> before and after the University of Waterloo and Conestoga College 
> fall semester start, when ridership on key corridors increases 
> significantly. Rankings will be recalculated following completion 
> of the collection period.
---

## What is Transit Signal Priority?

Transit Signal Priority is a traffic management strategy that 
modifies signal timing in real time to reduce delays for buses 
approaching intersections. TSP is most effective at 
intersections with high bus volumes, recurring schedule delays, 
and stops positioned 30–80m upstream of the signal, where buses 
can complete passenger boarding while a priority request is still 
active at the stop line.

Identifying the right intersections for TSP requires combining 
operational data (how many buses pass through an intersection 
during peak hours, how consistently they run late) with spatial 
data (where signals are relative to bus stops, and in which 
approach direction). This analysis automates that process for 
the full GRT network.

---

## Methodology

### 1. Static GTFS Parsing
Peak-hour bus volumes (7–9 AM and 4–6 PM) were calculated for 
every stop in the GRT network using `trips.txt`, `stop_times.txt`, 
and `calendar_dates.txt`. Service IDs containing "Weekday" were 
used to filter to representative weekday service, yielding 28,267 
peak weekday stop visits across 2,257 stops.

### 2. Directional Bearing Analysis
Rather than treating each stop as a single point, the analysis 
preserves travel direction. For each peak-hour trip, the compass 
bearing from the previous stop to the next stop was computed using 
the haversine formula. Bearings were grouped into four cardinal 
directions (N/S/E/W) using 90° bins — consistent with standard 
4-way intersection geometry in the Kitchener-Waterloo grid street 
network — yielding 309 directional stop-heading combinations across 
301 unique stops.

### 3. Spatial Join with Signalized Intersections
Traffic signal locations were retrieved from OpenStreetMap using 
`osmnx`, returning 534 signalized intersections across Waterloo 
Region. Stops were matched to their nearest downstream signal using 
a 150m search radius and a ±60° forward cone filter, ensuring only signals 
ahead of the bus are considered. This yielded 309 matched 
stop-direction to signal pairs across 237 unique signals.

### 4. Real-Time Delay Collection
Schedule adherence data was collected automatically using a GitHub 
Actions workflow that fetches the GRT GTFS-RT trip updates feed 
twice daily during peak hours (AM and PM). Each snapshot is parsed 
to compute the difference between scheduled and actual arrival 
times per stop, filtered to exclude anomalies outside the 
–5 to +30 minute range, and appended to a cumulative dataset.

**Current collection status:**
- Snapshots collected: 11
- Delay records: 83,376
- Date range: August 1 – August 7, 2026
- Network average peak delay: 44.5 seconds
- Stops with delay data: 2,187

Collection continues through September 2026 to capture the 
operational impact of the University of Waterloo and Conestoga 
College fall semester start.

### 5. TSP Priority Scoring
Each signal was scored using a composite index:

| Component | Weight | Description |
|---|---|---|
| Peak bus volume | 40% | Directional trip count normalised to network maximum |
| Schedule delay | 25% | Average delay normalised to 90-second benchmark |
| Signal proximity | 20% | Distance score — closer stops score higher |
| Directional coverage | 15% | Number of distinct approach directions served |

Signals were classified into three priority tiers based on their 
composite score.

---

## Current Results

> Note: Results reflect 11 snapshots collected during the week of 
> August 1–7, 2026. Rankings will be updated following the 
> August–September collection period.

### Priority Tier Summary

| Tier | Count | Score Range |
|---|---|---|
| High Priority | 2 | ≥ 65 |
| Medium Priority | 89 | 40–64 |
| Low Priority | 146 | < 40 |
| **Total ranked** | **237** | |

### Top 5 TSP Candidate Intersections

| Rank | Intersection | Score | Peak Buses | Avg Delay |
|---|---|---|---|---|
| 1 | Kitchener City Hall Station | 66.3 | 55 | 36.5 sec |
| 2 | Glasgow / Westmount | 65.1 | 32 | 98.6 sec |
| 3 | Frederick Station (Frederick / King) | 62.8 | 47 | 57.2 sec |
| 4 | Westmount / Block Line | 61.4 | 38 | 116.2 sec |
| 5 | Bleams / Thistledown | 61.4 | 31 | 127.8 sec |

### Key Findings

- **Glasgow corridor** (Glasgow/Westmount, Glasgow/Eden, 
  Westmount/Queens) appears consistently across the top rankings 
  with above-average delays, suggesting a recurring congestion 
  pattern warranting corridor-level TSP consideration rather than 
  isolated intersection treatment.

- **Hazel/Columbia** ranks in the top 10 by bus volume (68 peak 
  buses) but carries only 13.7 seconds average delay — indicating 
  the intersection is already operating efficiently. TSP here would 
  maintain performance under increased future demand rather than 
  address an existing problem.

- **King/University Ave**, while one of GRT's busiest corridors, 
  shows moderate delay (44.4 sec) when averaged across the full 
  week — lower than single-snapshot analysis suggested. This 
  highlights the importance of multi-snapshot data collection over 
  point-in-time analysis.

---

## Interactive Map

<!-- Add screenshot here -->

The interactive map (`outputs/complete_signal_network_map.html`) 
displays all 534 OSM signals colour-coded by TSP priority tier, 
with popups showing score, volume, delay, and stop information for 
each candidate. Transit stop locations are available as a toggleable 
overlay layer.

---

## Project Structure

Install with:
```bash
pip install -r requirements.txt
```

---

## Limitations & Future Work

- **Bearing estimation** uses stop-to-stop geometry rather than 
  GPS vehicle headings from the GTFS-RT vehicle positions feed. 
  Integrating actual vehicle bearings would reduce directional 
  matching uncertainty from ±15° to approximately ±2–3°.

- **OSM signal completeness** — OpenStreetMap is a community-maintained 
  dataset and signal coverage may vary across the network. Intersections 
  without OSM signal tags would not appear in the spatial join regardless 
  of their transit demand.

- **Cardinal direction binning** uses 90° bins which work well on 
  Kitchener-Waterloo's grid street network but may miscategorize 
  stops on curved or diagonal roads. This is distinct from the 
  60° forward cone filter, which ensures only downstream signals 
  are considered — it does not correct for upstream binning errors.

- **Priority thresholds** are preliminary and will be recalibrated 
  following the full August–September data collection period.

- **Single network scope** — analysis covers GRT only. A 
  multi-agency extension to GO Transit stops within the region 
  would provide a more complete picture of signal demand.

---

## Data Sources

- **GRT GTFS Static Feed** — Region of Waterloo Open Data  
  `https://webapps.regionofwaterloo.ca/api/grt-routes/api/staticfeeds/1`
- **GRT GTFS-RT Feed** — Region of Waterloo  
  `https://webapps.regionofwaterloo.ca/api/grt-routes/api/tripupdates/1`
- **Traffic Signal Locations** — OpenStreetMap via osmnx  
  `https://www.openstreetmap.org`
