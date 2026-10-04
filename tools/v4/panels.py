"""
PaleoWave v4: a close-up of every target, so you can see what you'd be walking to.

For each target in data/v4/targets.csv: a 3 km square of Sentinel-2 true colour (a clear summer
scene) beside a USGS 3DEP hillshade at 10 m, with the mapped Triassic units outlined and the
target marked. Writes site/v4/T##.jpg.

    python tools/v4/panels.py        # in CI
"""
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

import geopandas as gpd
import matplotlib
import numpy as np
import pandas as pd
import rasterio
from rasterio.enums import Resampling
from rasterio.io import MemoryFile
from rasterio.transform import from_origin
from rasterio.vrt import WarpedVRT
from shapely.geometry import box

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "site" / "v4"
OUT.mkdir(parents=True, exist_ok=True)
UA = {"User-Agent": "PaleoWave v4 (github.com/bdgroves/project-paleowave)"}
CRS = "EPSG:32611"
HALF = 1500
RES = 10
N = 2 * HALF // RES
T = pd.read_csv(ROOT / "data" / "v4" / "targets.csv")
units = gpd.read_file(ROOT / "data" / "v4" / "units.geojson").to_crs(CRS)


def fetch(url, data=None, ctype=None, tries=4):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, data=data, headers={**UA, **({"Content-Type": ctype} if ctype else {})})
            with urllib.request.urlopen(req, timeout=180) as r:
                return r.read()
        except Exception as e:  # noqa: BLE001
            print("  retry", i, str(e)[:100], flush=True)
            time.sleep(4 * (i + 1))
    return None


def hillshade(z):
    gy, gx = np.gradient(z, RES)
    slope = np.arctan(np.hypot(gx, gy))
    aspect = np.arctan2(-gx, gy)
    az, alt = np.radians(315), np.radians(40)
    hs = np.sin(alt) * np.cos(slope) + np.cos(alt) * np.sin(slope) * np.cos(az - aspect)
    return np.clip(hs, 0, 1)


for _, t in T.iterrows():
    f = OUT / f"T{int(t['rank']):02d}.jpg"
    if f.exists():
        continue
    x, y = t.x, t.y
    bx = (x - HALF, y - HALF, x + HALF, y + HALF)
    tf = from_origin(bx[0], bx[3], RES, RES)
    q = urllib.parse.urlencode({"bbox": ",".join(map(str, bx)), "bboxSR": 32611, "imageSR": 32611, "size": f"{N},{N}", "format": "tiff",
                                "pixelType": "F32", "interpolation": "RSP_BilinearInterpolation", "f": "image"})
    b = fetch("https://elevation.nationalmap.gov/arcgis/rest/services/3DEPElevation/ImageServer/exportImage?" + q)
    if not b:
        print("no DEM for", t["rank"])
        continue
    with MemoryFile(b) as m, m.open() as s:
        z = s.read(1).astype("float32")
    ll = gpd.GeoSeries(gpd.points_from_xy([x], [y]), crs=CRS).to_crs(4326).iloc[0]
    body = json.dumps({"collections": ["sentinel-2-l2a"], "intersects": {"type": "Point", "coordinates": [ll.x, ll.y]}, "limit": 30,
                       "datetime": "2024-06-01T00:00:00Z/2025-09-30T00:00:00Z", "query": {"eo:cloud_cover": {"lt": 2}},
                       "sortby": [{"field": "properties.eo:cloud_cover", "direction": "asc"}]}).encode()
    js = json.loads(fetch("https://earth-search.aws.element84.com/v1/search", data=body, ctype="application/json") or b"{}")
    items = [i for i in js.get("features", []) if int(i["properties"]["datetime"][5:7]) in (6, 7, 8, 9)]
    rgb, when = None, None
    for it in items[:3]:
        try:
            bands = []
            for k in ("red", "green", "blue"):
                with rasterio.open(it["assets"][k]["href"]) as s, WarpedVRT(s, crs=CRS, transform=tf, width=N, height=N, resampling=Resampling.bilinear) as v:
                    bands.append(v.read(1).astype("float32") / 10000)
            rgb = np.dstack(bands)
            when = it["properties"]["datetime"][:10]
            break
        except Exception as e:  # noqa: BLE001
            print("  s2", str(e)[:100])
    fig, axs = plt.subplots(1, 2, figsize=(12, 6.1), dpi=110)
    ext = (bx[0], bx[2], bx[1], bx[3])
    if rgb is not None:
        lo, hi = np.nanpercentile(rgb, 2), np.nanpercentile(rgb, 98)
        axs[0].imshow(np.clip((rgb - lo) / (hi - lo + 1e-6), 0, 1) ** 0.9, extent=ext)
        axs[0].set_title(f"Sentinel-2, {when}", fontsize=11, loc="left")
    else:
        axs[0].set_title("Sentinel-2: no clear summer scene", fontsize=11, loc="left")
    axs[1].imshow(hillshade(z), cmap="gray", extent=ext, vmin=0, vmax=1)
    axs[1].set_title("3DEP hillshade, 10 m; mapped Triassic units outlined", fontsize=11, loc="left")
    clip = units[units.intersects(box(*bx))]
    for ax in axs:
        if len(clip):
            clip.boundary.plot(ax=ax, color="#e0ad44", linewidth=1.4)
        ax.plot([x], [y], marker="*", ms=18, mfc="#e0ad44", mec="#0d2b1f", mew=1.4)
        ax.plot([bx[0] + 150, bx[0] + 1150], [bx[1] + 150, bx[1] + 150], color="white", lw=3, solid_capstyle="butt")
        ax.text(bx[0] + 650, bx[1] + 230, "1 km", color="white", ha="center", fontsize=9, fontweight="bold")
        ax.set_xlim(bx[0], bx[2])
        ax.set_ylim(bx[1], bx[3])
        ax.set_xticks([])
        ax.set_yticks([])
    fig.suptitle(f"T{int(t['rank']):02d} · {ll.y:.4f}°N {abs(ll.x):.4f}°W · {t.unit}", fontsize=12, x=0.01, ha="left")
    fig.tight_layout()
    fig.savefig(f, pil_kwargs={"quality": 82})
    plt.close(fig)
    print("wrote", f.name, flush=True)
