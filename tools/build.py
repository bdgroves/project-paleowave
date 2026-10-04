"""
Build the page's data from the model outputs committed in data/ (nothing is retrained here):

  site/targets.geojson   the v3 top 50, with the close-up terrain panel for the 20 that have one,
                         and how far each sits from the mapped Triassic marine rocks
  site/known.geojson     the training records, grouped into places, with taxa, formation, reference;
                         plus any PBDB record (from site/pbdb_live.json) at a place the model never saw
  site/triassic.geojson  the TRc / TRmt units from the state geologic map, simplified for the web

    python tools/build.py
"""
import json
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
D, S = ROOT / "data", ROOT / "site"
S.mkdir(exist_ok=True)

geo = gpd.read_file(D / "geology" / "triassic_marine.shp")
g32 = geo.to_crs(32611)
union = g32.union_all()
simp = gpd.GeoDataFrame({"unit": geo["ORIG_LABEL"]}, geometry=geo.geometry, crs=geo.crs).dissolve("unit").reset_index()
simp["geometry"] = simp.to_crs(32611).simplify(150).to_crs(4326)
simp["geometry"] = simp.geometry.set_precision(1e-4)
(S / "triassic.geojson").write_text(simp.to_json())

# targets
t = pd.read_csv(D / "model" / "paleowave_v3_top50.csv").sort_values("v3_rank")
lid = pd.read_csv(D / "model" / "paleowave_top20_lidar.csv")
tp = gpd.GeoDataFrame(t, geometry=gpd.points_from_xy(t.longitude, t.latitude), crs=4326)
tp["km_triassic"] = (tp.to_crs(32611).distance(union) / 1000).round(1)
known = pd.read_csv(D / "model" / "paleowave_v3_training_features.csv")


def km(lat, lon, lats, lons):
    return np.sqrt(((lats - lat) * 111.2) ** 2 + ((lons - lon) * 111.2 * np.cos(np.radians(lat))) ** 2)


feats = []
for _, r in tp.iterrows():
    d = km(r.latitude, r.longitude, lid.latitude.values, lid.longitude.values)
    panel = f"P{int(lid.priority.iloc[d.argmin()]):02d}" if d.min() < 0.2 else None
    if panel and not (ROOT / "outputs" / f"lidar_{panel}.png").exists():
        panel = None                                   # close-ups were drawn for P01-P20 only
    nk = km(r.latitude, r.longitude, known.latitude.values, known.longitude.values).min()
    tpi = float(r.tpi)
    feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [round(r.longitude, 4), round(r.latitude, 4)]},
                  "properties": {"rank": int(r.v3_rank), "score": round(float(r.v3_score), 3), "tpi": round(tpi, 1),
                                 "setting": "basin" if tpi < -1 else ("ridge" if tpi > 3 else "slope"),
                                 "rank_v2": None if pd.isna(r.get("rank_v2")) else int(r.rank_v2),
                                 "elev_m": round(float(r.elevation_m)), "slope": round(float(r.slope_deg), 1),
                                 "km_known": round(float(nk), 1), "km_triassic": float(r.km_triassic),
                                 "submodel": r.submodel, "panel": panel}})
(S / "targets.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": feats}))

# known places
pb = pd.read_csv(D / "pbdb" / "pbdb_occurrences_clean.csv")
pb = pb.merge(known[["occurrence_id", "formation_v3"]], on="occurrence_id", how="inner")
places = []
for (lat, lon), g in pb.groupby([pb.latitude.round(4), pb.longitude.round(4)]):
    places.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [lon, lat]},
                   "properties": {"records": int(len(g)), "taxa": sorted(set(g.taxon_name.dropna())),
                                  "formation": g.formation_v3.mode().iloc[0],
                                  "age": f"{g.early_age_ma.max():.0f}–{g.late_age_ma.min():.0f} Ma",
                                  "ref": g.ref.dropna().iloc[0][:180] if g.ref.notna().any() else "",
                                  "in_model": True}})
live_p = S / "pbdb_live.json"
extra = 0
if live_p.exists():
    live = json.loads(live_p.read_text())
    oid = lambda r: str(r["occurrence_no"]) if str(r["occurrence_no"]).startswith("occ:") else f"occ:{r['occurrence_no']}"  # noqa: E731
    model_ids = set(known.occurrence_id)
    live_ids = {oid(r) for r in live["records"]}
    dropped = pb[pb.occurrence_id.isin(model_ids - live_ids)]
    summary = {"checked": live["checked"], "live": len(live["records"]), "model": len(model_ids),
               "still_listed": len(model_ids & live_ids), "new_records": len(live_ids - model_ids),
               "dropped": [{"id": r.occurrence_id, "taxon": r.taxon_name} for r in dropped.itertuples()]}
    seen = {(round(f["geometry"]["coordinates"][1], 2), round(f["geometry"]["coordinates"][0], 2)) for f in places}
    newp = {}
    for r in live["records"]:
        if r.get("lat") is None or oid(r) in model_ids:     # a record the model has, even if PBDB has moved it
            continue
        key = (round(float(r["lat"]), 2), round(float(r["lng"]), 2))
        if key not in seen:
            newp.setdefault(key, []).append(r)
    for (lat, lon), rs in newp.items():
        extra += 1
        places.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [lon, lat]},
                       "properties": {"records": len(rs), "taxa": sorted({r.get("accepted_name") or r.get("identified_name") for r in rs}),
                                      "formation": rs[0].get("formation", ""), "age": f"{rs[0].get('max_ma', '?')}–{rs[0].get('min_ma', '?')} Ma",
                                      "ref": f"{rs[0].get('ref_author', '')} {rs[0].get('ref_pubyr', '')}".strip(), "in_model": False}})
    summary["new_places"] = extra
    (S / "live.json").write_text(json.dumps(summary, indent=1))
(S / "known.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": places}, ensure_ascii=False))
# close-up terrain panels, made web-sized (the full PNGs stay in outputs/)
from PIL import Image  # noqa: E402
(S / "panels").mkdir(exist_ok=True)
for png in sorted((ROOT / "outputs").glob("lidar_P*.png")):
    jp = S / "panels" / (png.stem.replace("lidar_", "") + ".jpg")
    im = Image.open(png).convert("RGB")
    im.thumbnail((1400, 600))
    im.save(jp, quality=82, optimize=True)

print(f"targets {len(feats)} ({sum(1 for f in feats if f['properties']['panel'])} with panels); known places {len(places)} "
      f"({extra} from PBDB not in the model); geology units {len(simp)}")
