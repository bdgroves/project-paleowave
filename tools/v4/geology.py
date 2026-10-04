"""
PaleoWave v4, step 1: the rock.

Downloads the Geologic Map of Nevada (Crafford 2007, USGS Data Series 249, compiled at 1:250,000),
keeps every unit that can hold Triassic marine rock, and writes data/v4/triassic_units.geojson.
Also reports how far each PBDB ichthyosaur record is from each unit, so we can see which units
the known finds actually come from.

    python tools/v4/geology.py
"""
import io
import json
import re
import urllib.request
import zipfile
from pathlib import Path

import geopandas as gpd
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "v4"
OUT.mkdir(parents=True, exist_ok=True)
CACHE = Path("/tmp/ds249")
URL = "https://pubs.usgs.gov/ds/2007/249/downloads/249.zip"

if not CACHE.exists():
    req = urllib.request.Request(URL, headers={"User-Agent": "PaleoWave (github.com/bdgroves/project-paleowave)"})
    with urllib.request.urlopen(req, timeout=600) as r:
        zipfile.ZipFile(io.BytesIO(r.read())).extractall(CACHE)
files = sorted(p for p in CACHE.rglob("*") if p.is_file())
print("files:", len(files))
for p in files:
    if p.suffix.lower() in (".shp", ".e00", ".gdb", ".mdb", ".zip", ".txt", ".xml") or p.is_dir():
        print("  ", p.relative_to(CACHE), p.stat().st_size)
# inner zips
for z in [p for p in files if p.suffix.lower() == ".zip"]:
    zipfile.ZipFile(z).extractall(z.with_suffix(""))
shps = sorted(CACHE.rglob("*.shp"))
print("shapefiles:", [str(s.relative_to(CACHE)) for s in shps])
geo = gpd.read_file(next(CACHE.rglob("NevadaGeology.shp")))
print("NevadaGeology:", len(geo), geo.crs, geo.columns.tolist())
for c in ("FMATN", "L_NAME", "GEOLOGICFM", "STATEMAP"):
    print(c, geo[c].astype(str).value_counts().head(15).to_dict())
lab = "FMATN"
labs = geo[lab].astype(str)
tri = labs.str.contains("TR", regex=False) | geo["GEOLOGICFM"].astype(str).str.contains(
    "Triassic|Luning|Gabbs|Prida|Favret|Star Peak|Augusta|Natchez|Grantsville|Sunrise|Thaynes|Dunlap|Auld Lang|Grass Valley|Raspberry|Winnemucca|Dixie Valley|Tobin|Cane Spring|Excelsior", case=False, regex=True)
show = geo[tri].assign(km2=geo[tri].to_crs(32611).area / 1e6).groupby([lab, "GEOLOGICFM", "L_NAME"], dropna=False).km2.sum().sort_values(ascending=False)
print("Triassic-bearing units (km2):")
print(show.head(80).to_string())
g = geo[tri].to_crs(4326)
g = g.dissolve(by=lab, as_index=False, aggfunc="first")
g["geometry"] = g.geometry.simplify(0.0003)
g[[lab, "GEOLOGICFM", "L_NAME", "geometry"]].rename(columns={lab: "unit"}).to_file(OUT / "triassic_units.geojson", driver="GeoJSON")

recs = pd.DataFrame(json.load(open(ROOT / "site" / "pbdb_live.json"))["records"])
pts = gpd.GeoDataFrame(recs, geometry=gpd.points_from_xy(recs.lng.astype(float), recs.lat.astype(float)), crs=4326).to_crs(32611)
gu = g.to_crs(32611)
rows = []
on = geo.to_crs(32611)
for _, r in pts.iterrows():
    d = gu.distance(r.geometry) / 1000
    i = d.idxmin()
    hit = on[on.contains(r.geometry)]
    rows.append({"occ": r.occurrence_no, "formation": r.get("formation"), "lat": r.lat, "lng": r.lng, "prec": r.get("latlng_precision"),
                 "on_unit": ";".join(hit[lab].astype(str) + ":" + hit["GEOLOGICFM"].astype(str)), "nearest_TR": gu.loc[i, lab], "km": round(float(d.min()), 2)})
rep = pd.DataFrame(rows)
print(rep.to_string())
rep.to_csv(OUT / "records_geology.csv", index=False)
