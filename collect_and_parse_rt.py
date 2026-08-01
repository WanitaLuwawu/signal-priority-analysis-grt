import os
import ssl
import requests
import pandas as pd
from datetime import datetime, timezone
from requests.adapters import HTTPAdapter
from google.transit import gtfs_realtime_pb2
import pytz

# 1. Fetch .pb
URL = "https://webapps.regionofwaterloo.ca/api/grt-routes/api/tripupdates/1"
GTFS_DIR = "data/gtfs"
OUTPUT_CSV = "data/realtime/delay_records.csv"

os.makedirs("data/realtime", exist_ok=True)

print(f"Fetching realtime feed at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} UTC...")

def fetch_with_ssl_fallback(url):
    # Try plain request first
    try:
        r = requests.get(url, timeout=15)
        r.raise_for_status()
        print("  ✅ Fetched with standard SSL")
        return r.content
    except Exception as e:
        print(f"  ⚠️ Standard SSL failed: {e}")

    # Fall back to relaxed SSL
    try:
        class WeakDHAdapter(HTTPAdapter):
            def init_poolmanager(self, *args, **kwargs):
                ctx = ssl.create_default_context()
                ctx.set_ciphers("DEFAULT:@SECLEVEL=1")
                kwargs["ssl_context"] = ctx
                super().init_poolmanager(*args, **kwargs)

        session = requests.Session()
        session.mount("https://", WeakDHAdapter())
        r = session.get(url, timeout=15)
        r.raise_for_status()
        print("  ✅ Fetched with relaxed SSL")
        return r.content
    except Exception as e:
        print(f"  ❌ Both SSL methods failed: {e}")
        return None

content = fetch_with_ssl_fallback(URL)
if content is None:
    print("Exiting — no data fetched.")
    exit(1)

# 2. Parse .pb into delay records
print("Parsing protobuf feed...")

stop_times = pd.read_csv(f"{GTFS_DIR}/stop_times.txt", dtype=str)

eastern = pytz.timezone("America/Toronto")
today_str = datetime.now(eastern).strftime("%Y-%m-%d")

def scheduled_unix(arrival_time_str, date_str):
    try:
        h, m, s = map(int, arrival_time_str.strip().split(":"))
        day_offset = h // 24
        h = h % 24
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        dt = dt.replace(hour=h, minute=m, second=s)
        if day_offset > 0:
            dt += pd.Timedelta(days=day_offset)
        return int(eastern.localize(dt).timestamp())
    except Exception:
        return None

feed = gtfs_realtime_pb2.FeedMessage()
feed.ParseFromString(content)

records = []
snapshot_time = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

for entity in feed.entity:
    if not entity.HasField("trip_update"):
        continue
    tu = entity.trip_update
    trip_id = str(tu.trip.trip_id)

    for st in tu.stop_time_update:
        rt_time = None
        if st.HasField("arrival") and st.arrival.HasField("time"):
            rt_time = st.arrival.time
        elif st.HasField("departure") and st.departure.HasField("time"):
            rt_time = st.departure.time
        if rt_time is None:
            continue

        stop_id = str(st.stop_id).strip()

        # Look up scheduled time
        sched_row = stop_times[
            (stop_times["trip_id"] == trip_id) &
            (stop_times["stop_id"] == stop_id)
        ]
        if sched_row.empty:
            continue

        sched_unix = scheduled_unix(
            sched_row.iloc[0]["arrival_time"], today_str
        )
        if sched_unix is None:
            continue

        delay_sec = rt_time - sched_unix

        # Filter outliers
        if -300 <= delay_sec <= 1800:
            records.append({
                "snapshot_time": snapshot_time,
                "trip_id": trip_id,
                "stop_id": stop_id,
                "delay_sec": delay_sec
            })

print(f"  Parsed {len(records):,} valid delay records")

if not records:
    print("No valid records — exiting without writing.")
    exit(0)

# 3. Append to cumulative CSV
new_df = pd.DataFrame(records)

if os.path.exists(OUTPUT_CSV):
    existing_df = pd.read_csv(OUTPUT_CSV, dtype=str)
    existing_df["delay_sec"] = existing_df["delay_sec"].astype(float)
    combined_df = pd.concat([existing_df, new_df], ignore_index=True)
    print(f"  Appended to existing CSV ({len(existing_df):,} → {len(combined_df):,} rows)")
else:
    combined_df = new_df
    print(f"  Created new CSV with {len(combined_df):,} rows")

combined_df.to_csv(OUTPUT_CSV, index=False)
print(f"✅ Saved → {OUTPUT_CSV}")