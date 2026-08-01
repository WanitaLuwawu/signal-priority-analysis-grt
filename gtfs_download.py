import io
import os
import ssl
import zipfile
from datetime import datetime
import requests
from requests.adapters import HTTPAdapter


# 1. Custom SSL Adapter
class CustomSSLAdapter(HTTPAdapter):

    def __init__(self, ssl_context=None, **kwargs):
        self.ssl_context = ssl_context
        super().__init__(**kwargs)

    def init_poolmanager(self, connections, maxsize, block=False, **kwargs):
        kwargs["ssl_context"] = self.ssl_context
        return super().init_poolmanager(
            connections, maxsize, block=block, **kwargs
        )


# Configure lower security level (SECLEVEL=1) for DH cipher compatibility
ctx = ssl.create_default_context()
ctx.set_ciphers("DEFAULT:@SECLEVEL=1")

# Create persistent session with adapter attached
session = requests.Session()
adapter = CustomSSLAdapter(ssl_context=ctx)
session.mount("https://", adapter)

# 2. Download Static GTFS Zip Feed
GTFS_URL = (
    "https://webapps.regionofwaterloo.ca/api/grt-routes/api/staticfeeds/1"
)
STATIC_DIR = "data/gtfs"
os.makedirs(STATIC_DIR, exist_ok=True)

print("--- 1. Downloading Static GTFS Feed ---")
try:
    response = session.get(GTFS_URL, timeout=30)
    response.raise_for_status()
    print(
        f"  ✅ Static Zip downloaded ({len(response.content) / 1024:.1f} KB)"
    )

    with zipfile.ZipFile(io.BytesIO(response.content)) as z:
        z.extractall(STATIC_DIR)
    print(f"  ✅ Extracted text tables to '{STATIC_DIR}/'")

except Exception as e:
    print(f"  ❌ Failed to download static GTFS: {e}")

# 3. Download Realtime GTFS Protocol Buffers
print("\n--- 2. Downloading Realtime GTFS Snapshots (.pb) ---")
REALTIME_DIR = "data/realtime"
os.makedirs(REALTIME_DIR, exist_ok=True)

GTFS_RT_URLS = {
    "trip_updates": "https://webapps.regionofwaterloo.ca/api/grt-routes/api/tripupdates/1",
    "vehicle_positions": "https://webapps.regionofwaterloo.ca/api/grt-routes/api/vehiclepositions/1",
}

timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

for feed_type, url in GTFS_RT_URLS.items():
    try:
        rt_response = session.get(url, timeout=15)

        if rt_response.status_code == 200:
            # 1. Overwrite static file for active pipeline step
            latest_path = os.path.join(REALTIME_DIR, f"{feed_type}.pb")
            with open(latest_path, "wb") as f:
                f.write(rt_response.content)

            # 2. Save timestamped copy for historical archiving
            archive_path = os.path.join(
                REALTIME_DIR, f"{feed_type}_{timestamp}.pb"
            )
            with open(archive_path, "wb") as f:
                f.write(rt_response.content)

            print(
                f"  ✅ Downloaded {feed_type:17s} → {latest_path} ({len(rt_response.content)/1024:.1f} KB)"
            )
        else:
            print(
                f"  ❌ {feed_type} HTTP Error: Status {rt_response.status_code}"
            )

    except Exception as e:
        print(f"  ❌ Error fetching {feed_type}: {e}")

print("\n✅ All data acquisition steps complete!")