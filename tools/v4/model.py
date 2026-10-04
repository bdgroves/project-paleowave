"""
PaleoWave v4: the rock, the exposure, and the land.

    python tools/v4/model.py          # in CI (needs 3DEP, Sentinel-2, BLM; ~1 hour first run, cached after)

1. Rock. Units from the Geologic Map of Nevada (Crafford 2007, 1:250,000, formation-level names):
   tier A = the formations Nevada's ichthyosaurs come from (Prida, Favret, Augusta Mountain, Cane
   Spring, Natchez Pass, Luning, Gabbs, Sunrise, Lower Triassic marine rocks); tier B = other marine
   Triassic sedimentary units. The search area is both, plus 300 m for map error.
2. Exposure, on a 30 m grid (UTM 11N): from USGS 3DEP, slope, relief and topographic position; from
   Sentinel-2 summer scenes (2023-2025, clouds masked, median), greenness, bare-ground index, a
   carbonate index (limestone absorbs at 2.3 µm, so B11/B12 rises) and an iron index.
3. Land. BLM surface management: who manages each cell. Berlin-Ichthyosaur State Park is excluded.
4. Model. Known places (PBDB records with coordinates to the second or 3+ decimals, merged within
   1 km) against random cells from the same rock. Logistic regression and a small random forest,
   each tested by leaving one known place out at a time and asking where it ranks among all cells
   in the search area. The baseline is the same test with no model at all (a random cell: 50%).
5. Targets. The best cells, at least 1.5 km apart and 2 km from any known place, on BLM land.

Writes data/v4/: features_sample.csv, eval.json, targets.csv, score_90m.tif, units.geojson.
"""
import json
import math
import os
import time
import urllib.parse
import urllib.request
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from rasterio.enums import Resampling
from rasterio.features import rasterize
from rasterio.transform import from_origin
from rasterio.vrt import WarpedVRT
from scipy import ndimage
from shapely.geometry import box, mapping

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "v4"
OUT.mkdir(parents=True, exist_ok=True)
CACHE = Path(os.environ.get("V4_CACHE", "/tmp/v4cache"))
(CACHE / "tiles").mkdir(parents=True, exist_ok=True)
UA = {"User-Agent": "PaleoWave v4 (github.com/bdgroves/project-paleowave)"}
CRS = "EPSG:32611"
RES = 30
TILE = 12000                  # m; tiles are 400 x 400 cells
PAD = 1050                    # m of extra DEM around each tile, for the 1 km topographic position
TIER_A = (r"Prida|Favret|Augusta|Cane Sp|Natchez|Star Peak|Luning|Gabbs|Sunrise|Thaynes|Lower Triassic sedimentary")
TIER_B = (r"Dun Glen|Winnemucca|Grass Valley|Raspberry|Tobin|Dixie Valley|Auld Lang Syne|Marine sedimentary rocks|"
          r"Candelaria|Osobb|Limestone and dolomite|shale, sand, and siltstone|upper subunit|lower subunit|intermediate subunit")
FEATS = ["slope", "relief", "tpi300", "tpi1000", "north", "ndvi", "bsi", "carb", "iron"]
T0 = time.time()


def log(*a):
    print(f"[{time.time() - T0:6.0f}s]", *a, flush=True)


def fetch(url, data=None, timeout=180, tries=4):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, data=data, headers=UA)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except Exception as e:  # noqa: BLE001
            log("  retry", i, str(e)[:120], url[:100])
            time.sleep(5 * (i + 1))
    return None


# ── 1. rock ──────────────────────────────────────────────────────────────
src = next(Path("/tmp/ds249").rglob("NevadaGeology.shp"), None)
if src is None:
    import io
    import zipfile
    zipfile.ZipFile(io.BytesIO(fetch("https://pubs.usgs.gov/ds/2007/249/downloads/249.zip", timeout=600))).extractall("/tmp/ds249")
    src = next(Path("/tmp/ds249").rglob("NevadaGeology.shp"))
geo = gpd.read_file(src).to_crs(CRS)
name = geo["L_NAME"].fillna("").astype(str)
sym = geo["FMATN"].fillna("").astype(str)
isA = name.str.contains(TIER_A, case=False, regex=True) & sym.str.contains("TR")
isB = ~isA & sym.str.contains("TR") & name.str.contains(TIER_B, case=False, regex=True)
units = geo[isA | isB].copy()
units["tier"] = np.where(isA[isA | isB], "A", "B")
units = units[["FMATN", "L_NAME", "GEOLOGICFM", "tier", "geometry"]]
log("units:", units.groupby("tier").apply(lambda d: round(d.area.sum() / 1e6)).to_dict(), "km²")
units.to_crs(4326).assign(geometry=lambda d: d.geometry.simplify(0.0002)).to_file(OUT / "units.geojson", driver="GeoJSON")
area = units.buffer(300).union_all()
uA = units[units.tier == "A"].union_all()

# Known places
recs = pd.DataFrame(json.load(open(ROOT / "site" / "pbdb_live.json"))["records"])
recs["lat"], recs["lng"] = recs.lat.astype(float), recs.lng.astype(float)
prec = recs.latlng_precision.astype(str)
recs["precise"] = prec.isin(["seconds", "3", "4", "5", "6"])
kp = gpd.GeoDataFrame(recs, geometry=gpd.points_from_xy(recs.lng, recs.lat), crs=4326).to_crs(CRS)
xy = np.c_[kp.geometry.x, kp.geometry.y]
from scipy.cluster.hierarchy import fcluster, linkage   # noqa: E402
kp["place"] = fcluster(linkage(xy, "single"), 1000, "distance")
places = kp.groupby("place").agg(x=("geometry", lambda g: g.x.mean()), y=("geometry", lambda g: g.y.mean()),
                                 n=("occurrence_no", "size"), precise=("precise", "any"),
                                 formation=("formation", lambda s: ";".join(sorted({str(v) for v in s if v == v}))),
                                 occ=("occurrence_no", lambda s: ",".join(map(str, s)))).reset_index()
places["in_area"] = [area.contains(gpd.points_from_xy([x], [y])[0]) for x, y in zip(places.x, places.y)]
places["km_to_units"] = [round(units.distance(gpd.points_from_xy([x], [y])[0]).min() / 1000, 2) for x, y in zip(places.x, places.y)]
log(f"known places: {len(places)} ({places.precise.sum()} precise); in search area: {places.in_area.sum()}")
log(places[["place", "n", "precise", "formation", "in_area", "km_to_units"]].to_string())

# ── 2. tiles ─────────────────────────────────────────────────────────────
x0, y0, x1, y1 = area.bounds
tiles = []
for tx in np.arange(math.floor(x0 / TILE) * TILE, x1, TILE):
    for ty in np.arange(math.floor(y0 / TILE) * TILE, y1, TILE):
        b = box(tx, ty, tx + TILE, ty + TILE)
        if b.intersects(area):
            tiles.append((int(tx), int(ty)))
log(f"tiles: {len(tiles)}")


def dem_tile(tx, ty):
    f = CACHE / "tiles" / f"dem_{tx}_{ty}.tif"
    if not f.exists():
        bx = (tx - PAD, ty - PAD, tx + TILE + PAD, ty + TILE + PAD)
        n = (TILE + 2 * PAD) // RES
        q = urllib.parse.urlencode({"bbox": ",".join(map(str, bx)), "bboxSR": 32611, "imageSR": 32611, "size": f"{n},{n}",
                                    "format": "tiff", "pixelType": "F32", "interpolation": "RSP_BilinearInterpolation",
                                    "noDataInterpretation": "esriNoDataMatchAny", "f": "image"})
        b = fetch("https://elevation.nationalmap.gov/arcgis/rest/services/3DEPElevation/ImageServer/exportImage?" + q)
        if not b or len(b) < 5000:
            return None
        f.write_bytes(b)
    with rasterio.open(f) as s:
        z = s.read(1).astype("float32")
    z[(z < -500) | (z > 5000)] = np.nan
    return z


def terrain(z):
    zf = np.where(np.isnan(z), np.nanmean(z), z)
    gy, gx = np.gradient(zf, RES)
    slope = np.degrees(np.arctan(np.hypot(gx, gy)))
    north = -gy / (np.hypot(gx, gy) + 1e-6)              # +1 = facing north (rows run south)
    relief = ndimage.maximum_filter(zf, 5) - ndimage.minimum_filter(zf, 5)
    tpi300 = zf - ndimage.uniform_filter(zf, 21)
    tpi1000 = zf - ndimage.uniform_filter(zf, 67)
    p = PAD // RES
    cut = lambda a: a[p:-p, p:-p]                          # noqa: E731
    return {"slope": cut(slope), "relief": cut(relief), "tpi300": cut(tpi300), "tpi1000": cut(tpi1000), "north": cut(north)}


STAC = "https://earth-search.aws.element84.com/v1/search"


def s2_tile(tx, ty):
    f = CACHE / "tiles" / f"s2_{tx}_{ty}.npz"
    if f.exists():
        d = np.load(f)
        return {k: d[k] for k in d.files}
    bb = gpd.GeoSeries([box(tx, ty, tx + TILE, ty + TILE)], crs=CRS).to_crs(4326).total_bounds
    body = json.dumps({"collections": ["sentinel-2-l2a"], "bbox": list(map(float, bb)), "limit": 40,
                       "datetime": "2023-06-15T00:00:00Z/2025-09-30T00:00:00Z",
                       "query": {"eo:cloud_cover": {"lt": 5}}, "sortby": [{"field": "properties.eo:cloud_cover", "direction": "asc"}]}).encode()
    js = json.loads(fetch(STAC, data=body) or b"{}")
    items = [i for i in js.get("features", []) if int(i["properties"]["datetime"][5:7]) in (6, 7, 8, 9)]
    # prefer scenes whose footprint covers the tile centre, then least cloud; three scenes, different dates
    cx, cy = (bb[0] + bb[2]) / 2, (bb[1] + bb[3]) / 2
    from shapely.geometry import Point, shape
    items = [i for i in items if shape(i["geometry"]).contains(Point(cx, cy))] or items
    picked, days = [], set()
    for i in items:
        d = i["properties"]["datetime"][:10]
        if d not in days:
            picked.append(i)
            days.add(d)
        if len(picked) == 3:
            break
    n = TILE // RES
    tf = from_origin(tx, ty + TILE, RES, RES)
    stack = {k: [] for k in ("B02", "B04", "B08", "B11", "B12")}
    for it in picked:
        a = it["assets"]
        hrefs = {"B02": a["blue"]["href"], "B04": a["red"]["href"], "B08": a["nir"]["href"], "B11": a["swir16"]["href"],
                 "B12": a["swir22"]["href"], "SCL": a["scl"]["href"]}
        arrs = {}
        try:
            for k, h in hrefs.items():
                with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", GDAL_HTTP_MAX_RETRY="4", GDAL_HTTP_RETRY_DELAY="2"):
                    with rasterio.open(h) as s, WarpedVRT(s, crs=CRS, transform=tf, width=n, height=n,
                                                           resampling=Resampling.nearest if k == "SCL" else Resampling.average) as v:
                        arrs[k] = v.read(1).astype("float32")
        except Exception as e:  # noqa: BLE001
            log("  s2 read failed", it["id"], str(e)[:100])
            continue
        bad = ~np.isin(arrs["SCL"], [4, 5, 7])           # keep vegetation, bare soil, unclassified
        for k in stack:
            b = arrs[k] / 10000.0
            b[bad | (arrs[k] == 0)] = np.nan
            stack[k].append(b)
    if not stack["B04"]:
        return None
    m = {k: np.nanmedian(np.stack(v), axis=0) for k, v in stack.items()}
    out = {"ndvi": (m["B08"] - m["B04"]) / (m["B08"] + m["B04"] + 1e-6),
           "bsi": ((m["B11"] + m["B04"]) - (m["B08"] + m["B02"])) / ((m["B11"] + m["B04"]) + (m["B08"] + m["B02"]) + 1e-6),
           "carb": m["B11"] / (m["B12"] + 1e-6), "iron": m["B04"] / (m["B02"] + 1e-6)}
    out = {k: v.astype("float32") for k, v in out.items()}
    np.savez_compressed(f, **out)
    return out


def land_tile(tx, ty):
    f = CACHE / "tiles" / f"land_{tx}_{ty}.npy"
    if f.exists():
        return np.load(f)
    q = urllib.parse.urlencode({"geometry": f"{tx},{ty},{tx + TILE},{ty + TILE}", "geometryType": "esriGeometryEnvelope", "inSR": 32611,
                                "spatialRel": "esriSpatialRelIntersects", "outFields": "ADMIN_AGENCY_CODE", "returnGeometry": "true",
                                "outSR": 32611, "f": "geojson"})
    b = fetch("https://gis.blm.gov/arcgis/rest/services/lands/BLM_Natl_SMA_LimitedScale/MapServer/1/query?" + q)
    n = TILE // RES
    code = np.zeros((n, n), "uint8")                       # 0 unknown, 1 BLM, 2 USFS, 3 private, 4 other public
    if b:
        g = json.loads(b).get("features", [])
        val = {"BLM": 1, "USFS": 2, "PVT": 3}
        shapes = [(f["geometry"], val.get(f["properties"].get("ADMIN_AGENCY_CODE"), 4)) for f in g if f.get("geometry")]
        if shapes:
            code = rasterize(shapes, out_shape=(n, n), transform=from_origin(tx, ty + TILE, RES, RES), fill=0, dtype="uint8")
    np.save(f, code)
    return code


# Berlin-Ichthyosaur State Park: no collecting there, so it's never a target. Outline from OpenStreetMap.
bisp = None
b = fetch("https://overpass-api.de/api/interpreter", data=urllib.parse.urlencode({"data": '[out:json][timeout:60];'
          'relation["name"~"Berlin.Ichthyosaur"];out geom;way["name"~"Berlin.Ichthyosaur"];out geom;'}).encode())
if b:
    from shapely.geometry import Polygon
    from shapely.ops import unary_union
    polys = []
    for e in json.loads(b).get("elements", []):
        rings = [e["geometry"]] if e["type"] == "way" else [m["geometry"] for m in e.get("members", []) if m.get("role") == "outer" and m.get("geometry")]
        for r in rings:
            if r and len(r) > 3:
                polys.append(Polygon([(p["lon"], p["lat"]) for p in r]))
    if polys:
        bisp = gpd.GeoSeries([unary_union(polys)], crs=4326).to_crs(CRS).iloc[0].buffer(0)
        log(f"Berlin-Ichthyosaur State Park: {bisp.area / 1e6:.1f} km²")
if bisp is None:
    log("Berlin-Ichthyosaur SP outline not found; excluding 3 km around the park's fossil shelter instead")
    bisp = gpd.GeoSeries(gpd.points_from_xy([-117.5914], [38.8767]), crs=4326).to_crs(CRS).iloc[0].buffer(3000)

# ── 3. features, tile by tile ────────────────────────────────────────────
rng = np.random.default_rng(42)
samples, tile_store, missing = [], {}, 0
for k, (tx, ty) in enumerate(tiles):
    z = dem_tile(tx, ty)
    if z is None:
        missing += 1
        continue
    t = terrain(z)
    s2 = s2_tile(tx, ty)
    if s2 is None:
        missing += 1
        log("  no Sentinel-2 for tile", tx, ty)
        continue
    land = land_tile(tx, ty)
    n = TILE // RES
    tf = from_origin(tx, ty + TILE, RES, RES)
    inside = rasterize([(mapping(area.intersection(box(tx, ty, tx + TILE, ty + TILE))), 1)], out_shape=(n, n), transform=tf, fill=0, dtype="uint8").astype(bool)
    tierA = rasterize([(mapping(uA.buffer(300).intersection(box(tx, ty, tx + TILE, ty + TILE))), 1)], out_shape=(n, n), transform=tf, fill=0, dtype="uint8").astype(bool) if uA.buffer(300).intersects(box(tx, ty, tx + TILE, ty + TILE)) else np.zeros((n, n), bool)
    park = rasterize([(mapping(bisp), 1)], out_shape=(n, n), transform=tf, fill=0, dtype="uint8").astype(bool) if bisp.intersects(box(tx, ty, tx + TILE, ty + TILE)) else np.zeros((n, n), bool)
    F = {**t, **s2}
    # smooth to ~90 m so a point's features don't hinge on one cell (records are good to ~30-100 m at best)
    F = {f: ndimage.uniform_filter(np.nan_to_num(v, nan=np.nanmedian(v) if np.isfinite(v).any() else 0), 3).astype("float32") for f, v in F.items()}
    ok = inside & np.isfinite(F["ndvi"])
    tile_store[(tx, ty)] = {"F": F, "ok": ok, "tierA": tierA, "land": land, "park": park}
    rr, cc = np.where(ok)
    if len(rr):
        pick = rng.choice(len(rr), size=min(len(rr), max(20, int(len(rr) * 0.01))), replace=False)
        for i in pick:
            samples.append({"tx": tx, "ty": ty, "r": rr[i], "c": cc[i], "x": tx + (cc[i] + 0.5) * RES, "y": ty + TILE - (rr[i] + 0.5) * RES,
                            "tierA": bool(tierA[rr[i], cc[i]]), **{f: float(F[f][rr[i], cc[i]]) for f in FEATS}})
    if k % 10 == 0:
        log(f"tile {k + 1}/{len(tiles)}: cells in area {ok.sum()}")
log(f"tiles with data: {len(tile_store)}, missing: {missing}; background sample: {len(samples)}")
bg = pd.DataFrame(samples)
N_CELLS = sum(int(v["ok"].sum()) for v in tile_store.values())


def cell_at(x, y):
    tx, ty = int(math.floor(x / TILE) * TILE), int(math.floor(y / TILE) * TILE)
    st = tile_store.get((tx, ty))
    if st is None:
        return None
    c, r = int((x - tx) // RES), int((ty + TILE - y) // RES)
    return st, r, c


def feats_near(x, y, radius=90):
    """Features at the best-exposed cell within `radius` m of a record (coordinates carry error)."""
    out = None
    for dx in range(-radius, radius + 1, RES):
        for dy in range(-radius, radius + 1, RES):
            got = cell_at(x + dx, y + dy)
            if got is None:
                continue
            st, r, c = got
            v = {f: float(st["F"][f][r, c]) for f in FEATS}
            if out is None or v["bsi"] > out["bsi"]:
                out = v
    return out


pres = []
for _, p in places.iterrows():
    v = feats_near(p.x, p.y, 90 if p.precise else 450)
    pres.append(v)
places["has_feats"] = [v is not None for v in pres]
P = pd.DataFrame([v if v else {f: np.nan for f in FEATS} for v in pres])
log("places with features:", int(places.has_feats.sum()))
pd.concat([places.drop(columns=[]), P], axis=1).to_csv(OUT / "places_features.csv", index=False)
bg.sample(min(len(bg), 4000), random_state=1).to_csv(OUT / "features_sample.csv", index=False)

# ── 4. models, tested by leaving one place out ───────────────────────────
from sklearn.ensemble import RandomForestClassifier   # noqa: E402
from sklearn.linear_model import LogisticRegression    # noqa: E402
from sklearn.pipeline import make_pipeline             # noqa: E402
from sklearn.preprocessing import StandardScaler       # noqa: E402

train_ok = places.has_feats & places.precise & places.in_area
Xp, Xb = P[train_ok.values][FEATS].to_numpy(), bg[FEATS].to_numpy()
log(f"training places: {train_ok.sum()}")


def make(kind):
    if kind == "logistic":
        return make_pipeline(StandardScaler(), LogisticRegression(C=0.3, class_weight="balanced", max_iter=2000))
    return RandomForestClassifier(n_estimators=300, min_samples_leaf=20, max_depth=4, class_weight="balanced", random_state=42, n_jobs=-1)


def exposure(D):
    """No-model baseline: bare, carbonate-bright, sloping ground."""
    z = lambda a: (a - bg[a.name].mean()) / (bg[a.name].std() + 1e-9)   # noqa: E731
    return z(D["bsi"]) + z(D["carb"]) - z(D["ndvi"]) + 0.5 * z(D["slope"])


def pctile(score_place, score_bg):
    return float((score_bg < score_place).mean())


evals = {}
test_idx = np.where((places.has_feats & places.in_area).values)[0]
for kind in ("logistic", "forest", "exposure"):
    rows = []
    for i in test_idx:
        keep = train_ok.values.copy()
        keep[i] = False
        # also drop training places within 5 km of the test place, so neighbours can't vouch for it
        d = np.hypot(places.x - places.x[i], places.y - places.y[i]).to_numpy()
        keep &= d > 5000
        if kind == "exposure":
            s_p = float(exposure(P.iloc[[i]][FEATS].assign()).iloc[0])
            s_b = exposure(bg[FEATS]).to_numpy()
        else:
            Xtr = np.r_[P[keep][FEATS].to_numpy(), Xb]
            ytr = np.r_[np.ones(keep.sum()), np.zeros(len(Xb))]
            m = make(kind).fit(Xtr, ytr)
            s_p = float(m.predict_proba(P.iloc[[i]][FEATS].to_numpy())[0, 1])
            s_b = m.predict_proba(Xb)[:, 1]
        rows.append({"place": int(places.place[i]), "formation": places.formation[i], "precise": bool(places.precise[i]),
                     "percentile": round(pctile(s_p, s_b), 3), "trained_on": int(keep.sum())})
    r = pd.DataFrame(rows)
    evals[kind] = {"places": rows, "median_percentile": round(float(r.percentile.median()), 3),
                   "top10": int((r.percentile >= 0.9).sum()), "top25": int((r.percentile >= 0.75).sum()), "n": len(r)}
    log(f"{kind}: held-out places' median percentile {evals[kind]['median_percentile']:.2f}; "
        f"top 10%: {evals[kind]['top10']}/{len(r)}; top 25%: {evals[kind]['top25']}/{len(r)}")
best = max(("logistic", "forest", "exposure"), key=lambda k: (evals[k]["median_percentile"], evals[k]["top10"]))
log("best:", best)

# geology alone: how many places does the rock filter catch, and how much of Nevada does it keep?
geo_eval = {"places": int(len(places)), "in_area": int(places.in_area.sum()), "precise_in_area": int((places.in_area & places.precise).sum()),
            "area_km2": round(area.area / 1e6), "tierA_km2": round(units[units.tier == "A"].area.sum() / 1e6),
            "tierB_km2": round(units[units.tier == "B"].area.sum() / 1e6), "cells": N_CELLS}

# ── 5. score every cell, pick targets ────────────────────────────────────
final = None if best == "exposure" else make(best).fit(np.r_[Xp, Xb], np.r_[np.ones(len(Xp)), np.zeros(len(Xb))])
if best == "logistic":
    lr = final[-1]
    evals["logistic_coef"] = dict(zip(FEATS, map(lambda v: round(float(v), 3), lr.coef_[0])))
    log("coefficients (standardised):", evals["logistic_coef"])
if best == "forest":
    evals["forest_importance"] = dict(zip(FEATS, map(lambda v: round(float(v), 3), final.feature_importances_)))
bg_scores = exposure(bg[FEATS]).to_numpy() if best == "exposure" else final.predict_proba(Xb)[:, 1]
cands = []
# coarse score raster for the map: 90 m, max of each 3x3 block
gx0, gy1 = x0 - x0 % 90, y1 + (90 - y1 % 90)
W, H = int((x1 - gx0) // 90) + 1, int((gy1 - y0) // 90) + 1
coarse = np.full((H, W), np.nan, "float32")
for (tx, ty), st in tile_store.items():
    F, ok = st["F"], st["ok"]
    D = pd.DataFrame({f: F[f][ok] for f in FEATS})
    sc = exposure(D).to_numpy() if best == "exposure" else final.predict_proba(D.to_numpy())[:, 1]
    S = np.full(ok.shape, np.nan, "float32")
    S[ok] = sc
    pct = np.searchsorted(np.sort(bg_scores), S) / len(bg_scores)
    pct[~ok] = np.nan
    # coarse raster
    n = S.shape[0] // 3
    blk = np.nanmax(pct[: n * 3, : n * 3].reshape(n, 3, n, 3).swapaxes(1, 2).reshape(n, n, 9), axis=2) if np.isfinite(pct).any() else None
    if blk is not None:
        r0, c0 = int((gy1 - (ty + TILE)) // 90), int((tx - gx0) // 90)
        sub = coarse[r0:r0 + n, c0:c0 + n]
        coarse[r0:r0 + sub.shape[0], c0:c0 + sub.shape[1]] = np.fmax(sub, blk[: sub.shape[0], : sub.shape[1]])
    good = ok & (pct >= 0.98) & ~st["park"]
    rr, cc = np.where(good)
    for r, c in zip(rr, cc):
        cands.append((float(pct[r, c]), tx + (c + 0.5) * RES, ty + TILE - (r + 0.5) * RES, int(st["land"][r, c]), bool(st["tierA"][r, c]),
                      {f: round(float(F[f][r, c]), 3) for f in FEATS}))
cands.sort(key=lambda t: -t[0])
log(f"cells in the top 2%: {len(cands)}")
with rasterio.open(OUT / "score_90m.tif", "w", driver="GTiff", width=W, height=H, count=1, dtype="float32", crs=CRS,
                   transform=from_origin(gx0, gy1, 90, 90), nodata=np.nan, compress="deflate") as d:
    d.write(coarse, 1)

kx, ky = places.x.to_numpy(), places.y.to_numpy()
picked = []
LAND = {0: "unknown", 1: "BLM", 2: "Forest Service", 3: "private", 4: "other public"}
for s, x, y, lc, ta, fv in cands:
    if lc != 1:
        continue
    if np.hypot(kx - x, ky - y).min() < 2000:
        continue
    if any(math.hypot(x - p["x"], y - p["y"]) < 1500 for p in picked):
        continue
    picked.append({"x": x, "y": y, "percentile": round(s, 4), "land": LAND[lc], "tierA": ta,
                   "km_known": round(float(np.hypot(kx - x, ky - y).min() / 1000), 1), **fv})
    if len(picked) == 40:
        break
T = pd.DataFrame(picked)
if len(T):
    ll = gpd.GeoSeries(gpd.points_from_xy(T.x, T.y), crs=CRS).to_crs(4326)
    T.insert(0, "lat", ll.y.round(5))
    T.insert(1, "lon", ll.x.round(5))
    unit_at = gpd.sjoin(gpd.GeoDataFrame(T, geometry=gpd.points_from_xy(T.x, T.y), crs=CRS), units[["L_NAME", "tier", "geometry"]], how="left", predicate="within")
    T["unit"] = unit_at.groupby(level=0).L_NAME.first().reindex(T.index).fillna("within 300 m of " + "mapped unit")
    T.insert(0, "rank", range(1, len(T) + 1))
T.to_csv(OUT / "targets.csv", index=False)
json.dump({"model": best, "evals": evals, "geology": geo_eval, "features": FEATS,
           "places": places.drop(columns=["x", "y"]).to_dict("records"), "targets": len(T),
           "tiles": len(tiles), "tiles_missing": missing, "seconds": round(time.time() - T0)},
          open(OUT / "eval.json", "w"), indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o))
log("done; targets:", len(T))
