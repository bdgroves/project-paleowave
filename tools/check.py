"""
Re-check PaleoWave's numbers from the files in this repo, and write site/checks.json.

Three questions, each answered only from committed data, so anyone can run it:

1. How well does the terrain model find a fossil place it has never seen? The notebooks' leave-one-out
   held out one PBDB *record* at a time, but the 30 records sit at 18 places (six at Merriam's 1906
   collecting site alone), so the held-out record's twins stayed in training. This holds out whole
   places instead, on the v1/v2 feature table (features_pbdb_terrain.csv + the background points),
   the only feature set whose comparison points are in the repo. v3's rasters aren't committed, so its
   numbers can't be re-checked here.
2. Was ruggedness measured the same way for fossil sites and for comparison points? TRI at the fossil
   sites came from the 8 m DEM (mean difference to 8 neighbours); for background points it came from an
   ~18 m fetch as |z - 3x3 mean|. The ratio TRI / tan(slope) shows whether the two agree.
3. Do the targets sit on the mapped Triassic marine rocks? Distance from every v3 target and every known
   record to the TRc / TRmt polygons in data/geology/triassic_marine.shp.

    python tools/check.py
"""
import json
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import KFold

ROOT = Path(__file__).resolve().parents[1]
D = ROOT / "data"
F = ["elevation_m", "slope_deg", "aspect_deg", "tri"]
RF = dict(n_estimators=300, max_depth=6, class_weight="balanced", random_state=42, n_jobs=-1)

pres = pd.read_csv(D / "features_pbdb_terrain.csv")
bg = pd.read_csv(D / "pbdb" / "paleowave_background_proper.csv")
pres["place"] = pres.latitude.round(3).astype(str) + "," + pres.longitude.round(3).astype(str)
Xb = bg[F].values


def held_out(groups):
    p = np.zeros(len(pres))
    for g in pd.unique(groups):
        te = groups == g
        X = np.vstack([pres.loc[~te, F].values, Xb])
        y = np.r_[np.ones((~te).sum()), np.zeros(len(Xb))]
        p[te] = RandomForestClassifier(**RF).fit(X, y).predict_proba(pres.loc[te, F].values)[:, 1]
    return p


by_record = held_out(np.arange(len(pres)))
by_place = held_out(pres["place"].values)
bgp = np.zeros(len(bg))
for tr, te in KFold(5, shuffle=True, random_state=0).split(Xb):
    m = RandomForestClassifier(**RF).fit(np.vstack([pres[F].values, Xb[tr]]), np.r_[np.ones(len(pres)), np.zeros(len(tr))])
    bgp[te] = m.predict_proba(Xb[te])[:, 1]
y = np.r_[np.ones(len(pres)), np.zeros(len(bg))]
place_recall = pres.assign(p=by_place).groupby("place").p.mean()

# ruggedness: same yardstick?
def ratio(d):
    d = d[(d.slope_deg > 1) & (d.elevation_m > 0)]
    return float((d.tri / np.tan(np.radians(d.slope_deg))).median())

# the targets and the mapped Triassic
geo = gpd.read_file(D / "geology" / "triassic_marine.shp").to_crs(32611)
tri_union = geo.union_all()
t = pd.read_csv(D / "model" / "paleowave_v3_top50.csv")
tg = gpd.GeoSeries(gpd.points_from_xy(t.longitude, t.latitude), crs=4326).to_crs(32611)
t_km = tg.distance(tri_union) / 1000
k = pd.read_csv(D / "model" / "paleowave_v3_training_features.csv")
kg = gpd.GeoSeries(gpd.points_from_xy(k.longitude, k.latitude), crs=4326).to_crs(32611)
k_km = kg.distance(tri_union) / 1000

out = {
    "records": int(len(k)), "places": int(k[["latitude", "longitude"]].round(4).drop_duplicates().shape[0]),
    "largest_place_records": int(k.groupby(["latitude", "longitude"]).size().max()),
    "v12": {
        "records": int(len(pres)), "places": int(pres.place.nunique()), "background": int(len(bg)),
        "recall_by_record": round(float((by_record >= 0.5).mean()), 3),
        "recall_by_place_records": round(float((by_place >= 0.5).mean()), 3),
        "places_found": int((place_recall >= 0.5).sum()),
        "background_flagged": round(float((bgp >= 0.5).mean()), 3),
        "auc_by_record": round(float(roc_auc_score(y, np.r_[by_record, bgp])), 3),
        "auc_by_place": round(float(roc_auc_score(y, np.r_[by_place, bgp])), 3),
    },
    "tri": {"fossil_ratio": round(ratio(pres), 2), "background_ratio": round(ratio(bg), 2),
            "fossil_median": round(float(pres.tri.median()), 2), "background_median": round(float(bg.tri.median()), 2),
            "background_elev_zero": int((bg.elevation_m == 0).sum())},
    "geology": {"targets_on_unit": int((t_km < 0.05).sum()), "targets": int(len(t)),
                "target_median_km": round(float(t_km.median()), 1), "target_max_km": round(float(t_km.max()), 1),
                "records_on_unit": int((k_km < 0.05).sum()), "record_median_km": round(float(k_km.median()), 1)},
}
(ROOT / "site").mkdir(exist_ok=True)
(ROOT / "site" / "checks.json").write_text(json.dumps(out, indent=1))
print(json.dumps(out, indent=1))
