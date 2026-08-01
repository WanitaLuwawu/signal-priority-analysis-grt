import requests, zipfile, io, ssl, os
from requests.adapters import HTTPAdapter

class WeakDHAdapter(HTTPAdapter):
    def init_poolmanager(self, *args, **kwargs):
        ctx = ssl.create_default_context()
        ctx.set_ciphers("DEFAULT:@SECLEVEL=1")
        kwargs["ssl_context"] = ctx
        super().init_poolmanager(*args, **kwargs)

os.makedirs("data/gtfs", exist_ok=True)

session = requests.Session()
session.mount("https://", WeakDHAdapter())

print("Downloading GRT static GTFS...")
r = session.get(
    "https://webapps.regionofwaterloo.ca/api/grt-routes/api/staticfeeds/1",
    timeout=30
)
r.raise_for_status()
print(f"  Downloaded {len(r.content)/1024:.1f} KB")

with zipfile.ZipFile(io.BytesIO(r.content)) as z:
    z.extractall("data/gtfs")
    print(f"  Extracted: {z.namelist()}")

print("✅ GTFS static feed ready")