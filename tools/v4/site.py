"""
PaleoWave v4: turn data/v4 into what the page reads (site/v4). Runs anywhere; no network.

    python tools/v4/site.py

Writes site/v4/units.geojson (the Triassic marine units, by tier), site/v4/targets.geojson,
site/v4/score.png + score.json (the top 10% of the search area, as a map overlay), site/v4/summary.json.
"""
import json
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from PIL import Image
from rasterio.warp import Resampling, calculate_default_transform, reproject, transform_bounds

ROOT = Path(__file__).resolve().parents[2]
D = ROOT / "data" / "v4"
S = ROOT / "site" / "v4"
S.mkdir(parents=True, exist_ok=True)

u = gpd.read_file(D / "units.geojson")
u["name"] = u.L_NAME
dis = u.dissolve(by=["tier", "name"], as_index=False)[["tier", "name", "geometry"]]
dis["geometry"] = dis.geometry.simplify(0.0008)
dis.to_file(S / "units.geojson", driver="GeoJSON", COORDINATE_PRECISION=4)

T = pd.read_csv(D / "targets.csv")
feats = []
for _, t in T.iterrows():
    tid = f"T{int(t['rank']):02d}"
    feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [round(t.lon, 5), round(t.lat, 5)]},
                  "properties": {"id": tid, "rank": int(t["rank"]), "unit": t.unit.replace("within 300 m of mapped unit", "just outside a mapped Triassic edge"), "tierA": bool(t.tierA), "land": t.land,
                                 "km_known": float(t.km_known), "slope": round(float(t.slope), 1),
                                 "panel": f"v4/{tid}.jpg" if (S / f"{tid}.jpg").exists() else None}})
(S / "targets.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": feats}))

# Score overlay: cells in the top 10% of the search area, warped to Web Mercator for Leaflet.
with rasterio.open(D / "score_90m.tif") as src:
    dst_crs = "EPSG:3857"
    tf, w, h = calculate_default_transform(src.crs, dst_crs, src.width, src.height, *src.bounds, resolution=180)
    arr = np.full((h, w), np.nan, "float32")
    reproject(rasterio.band(src, 1), arr, src_transform=src.transform, src_crs=src.crs, dst_transform=tf, dst_crs=dst_crs,
              resampling=Resampling.max, dst_nodata=np.nan)
    b = rasterio.transform.array_bounds(h, w, tf)
    west, south, east, north = transform_bounds(dst_crs, "EPSG:4326", b[1], b[0], b[3], b[2])
rgba = np.zeros((h, w, 4), "uint8")
top = np.nan_to_num(arr) >= 0.9
hi = np.nan_to_num(arr) >= 0.97
rgba[top] = (224, 173, 68, 150)
rgba[hi] = (192, 57, 43, 200)
Image.fromarray(rgba, "RGBA").save(S / "score.png", optimize=True)
(S / "score.json").write_text(json.dumps({"bounds": [[south, west], [north, east]]}))

E = json.loads((D / "eval.json").read_text())
keep = ("ensemble", "logistic", "forest", "forest_no_distance", "forest_satellite", "forest_terrain", "distance_only", "exposure")
summary = {"geology": E["geology"], "model": E["model"], "features": E["features"],
           "evals": {k: {kk: v for kk, v in E["evals"][k].items()} for k in keep if k in E["evals"]},
           "importance": E["evals"].get("forest_importance"),
           "places": [{k: p[k] for k in ("place", "n", "precise", "formation", "in_area", "km_to_units")} for p in E["places"]],
           "targets": {"total": len(T), "tierA": int(T.tierA.sum()), "tierB": int((~T.tierA).sum()),
                       "median_km_known": float(T.km_known.median()),
                       "units": T[T.tierA].unit.str.split(";").str[0].str.replace("within 300 m of mapped unit", "next to a mapped unit").value_counts().to_dict()}}
(S / "summary.json").write_text(json.dumps(summary, indent=1))
print(json.dumps(summary["targets"], indent=1))
print("overlay", round(top.mean(), 3), "of the frame;", w, "x", h)
