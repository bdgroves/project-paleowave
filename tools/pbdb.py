"""
Weekly: ask the Paleobiology Database for every ichthyosaur occurrence in Nevada, and write
site/pbdb_live.json. The page compares it with the 30 records the model was trained on, so it says
plainly when PBDB has records (or places) the model has never seen.

    python tools/pbdb.py
"""
import json
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
URL = "https://paleobiodb.org/data1.2/occs/list.json?" + urllib.parse.urlencode({
    "base_name": "Ichthyosauria", "lngmin": -120.1, "lngmax": -114.0, "latmin": 35.0, "latmax": 42.1,
    "show": "coords,loc,strat,ref,acc", "vocab": "pbdb", "limit": "all"})       # Nevada's box; filtered to the state below

req = urllib.request.Request(URL, headers={"User-Agent": "PaleoWave (github.com/bdgroves/project-paleowave)"})
with urllib.request.urlopen(req, timeout=120) as r:
    js = json.loads(r.read())
recs = [r for r in js.get("records", []) if r.get("state") in ("Nevada", "NV")]
keep = ("occurrence_no", "collection_no", "identified_name", "accepted_name", "early_interval", "late_interval",
        "max_ma", "min_ma", "lng", "lat", "state", "county", "formation", "member", "ref_author", "ref_pubyr",
        "geogscale", "latlng_precision")
out = {"checked": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ"), "source": URL,
       "records": [{k: r.get(k) for k in keep if r.get(k) is not None} for r in recs]}
(ROOT / "site").mkdir(exist_ok=True)
(ROOT / "site" / "pbdb_live.json").write_text(json.dumps(out, indent=0, ensure_ascii=False))
print(f"PBDB: {len(recs)} ichthyosaur occurrences in Nevada")
