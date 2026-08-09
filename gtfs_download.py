import requests, zipfile, io, ssl, os
from requests.adapters import HTTPAdapter

# Lower the minimum acceptable key size (SECLEVEL=1) for this session only.
class WeakDHAdapter(HTTPAdapter):
    def init_poolmanager(self, *args, **kwargs):
        ctx = ssl.create_default_context()
        # SECLEVEL=1 allows 1024-bit DH keys (default requires 2048-bit)
        ctx.set_ciphers("DEFAULT:@SECLEVEL=1")
        kwargs["ssl_context"] = ctx
        super().init_poolmanager(*args, **kwargs)

# Create output directory if it doesn't already exist
os.makedirs("data/gtfs", exist_ok=True)

# Mount the custom SSL adapter for all HTTPS requests in this session
session = requests.Session()
session.mount("https://", WeakDHAdapter())

# Download static feed
print("Downloading GRT static GTFS...")
r = session.get(
    "https://webapps.regionofwaterloo.ca/api/grt-routes/api/staticfeeds/1",
    timeout=30
)
# Raise an exception if the server returned an error status code
r.raise_for_status()
print(f"  Downloaded {len(r.content)/1024:.1f} KB")

# Extract content from .zip
with zipfile.ZipFile(io.BytesIO(r.content)) as z:
    z.extractall("data/gtfs")
    print(f"  Extracted: {z.namelist()}")

print("✅ GTFS static feed ready")