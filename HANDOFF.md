# Handoff — Brooks Groves projects (October 4, 2026)

Paste or attach this at the start of a new chat. It covers where things stand on the 30 Day Map Challenge 2026, PaleoWave, IceWave and the brooksgroves.com site.

## Working with Brooks

- Brooks uses Windows PowerShell, so give PowerShell commands.
- Start every repo session with a fresh `git pull`; bots and cloud runs push often.
- Use Roboto in documents.
- In emails, put links inside the words, never as bare URLs.
- Say plainly when something was wrong, including your own earlier conclusions. The corrections belong in the record.
- The blog (brooksgroves.com/blog) is friendly and warm. A post that reads sharp or critical is off-brand.
- "Same treatment" for a project means: a backend, an honest UI, live data, a check on the live site, a blog post, and listings on the site (homepage card, support story, writing list, blog index, tags, paleontology hub if relevant).

## Security rules

- Never write secrets or API keys into files.
- Secrets live in GitHub repo secrets: `EARTHDATA_*` and `USGS_API_KEY` in rainier-snowpack, `MAPBOX_TOKEN` in 30DayMapChallenge.
- Don't paste tokens into chat.
- The Mapbox token must never be written to any repo file.
- The Strava map must never reveal home (800 m trim).
- "Parcels at Risk" (private addresses) is excluded.
- The geocaching pocket-query GPX stays out of the repo; it has other cachers' logs and exact coordinates, and Geocaching's terms limit sharing. Only the reduced `finds.csv` (positions rounded to 0.01°) is committed.
- Untappd: map breweries only, never where Brooks drank. The venue "Western State Hospital" appears in the check-ins.
- Day 16 answers: trailhead names only, never X handles.

## Environment notes (cloud sandbox)

- The sandbox shell can't reach most outside sites. PBDB, Overpass, USGS 3DEP, Sentinel-2/STAC, WA DNR and brooksgroves.com all fail, so everything that needs the network runs in GitHub Actions.
- Pages can't be enabled through the API proxy; Brooks does that in Settings → Pages → main / root.
- **Probe pattern:** the `bdgroves/cascadia-wx` repo, branch `v2`, has a "Probe" workflow (`probe.yml`, input `script`). It runs a Python script from `tools/` and force-pushes `tools/probe_out*` to the `probe-out` branch. Read it with `git fetch --force origin probe-out:probe-out`, then `git show probe-out:tools/probe_out.txt`.
- **Live screenshots:** the `bdgroves/lahar-watch` repo has a "shoot" workflow (`shoot.yml`, input `script`) that runs a Playwright script, e.g. `tools/shoot_ice.mjs` or `tools/shoot_v4.mjs`. Output lands on the `shots` branch as `tools/shots/*.png` and `errors.txt`.
- **Local Playwright:** use the Chromium at `/opt/pw-browsers/chromium-1194/chrome-linux/chrome` and set `TZ=America/Los_Angeles`.
- **Job logs:** the API can't fetch them (the blob redirect is blocked). Read annotations through the check-runs API instead, or have workflows commit their own logs (the v4/v5 workflows do).

## PaleoWave — github.com/bdgroves/project-paleowave · brooksgroves.com/project-paleowave

The page is live (Pages enabled October 4).

**The October recheck (earlier v1–v3 models):**
- The 30 records sit at 18 places. Holding out whole places, the model recognises 7 of 16 places it hadn't seen.
- Ruggedness was measured two different ways for fossil sites and background points (7.7 vs 1.9 per unit of slope).
- **Corrected later the same day:** I first blamed a "too coarse 1:500,000 map" for no targets landing on Triassic rock. In fact the old Triassic layer left out the Luning and Gabbs units altogether.

**Version 4 (the current model):**
- Code is in `tools/v4/`: `geology.py`, `model.py`, `panels.py` and `site.py`. The workflow is `.github/workflows/v4.yml` (manual dispatch, input `step`; it caches tiles in `/tmp/v4cache`).
- **Rock:** the formation-level Geologic Map of Nevada (Crafford 2007, USGS DS 249, `249.zip`, layer `NevadaGeology.shp`).
  - Tier A is the ichthyosaur formations: Prida, Favret, Augusta Mountain, Cane Spring, Natchez Pass, Luning, Gabbs, Sunrise and Lower Triassic marine rocks.
  - Tier B is other marine Triassic rock.
  - The search area adds a 1 km buffer: 8,530 km², about 3% of Nevada. 9 of the 16 known places fall inside it.
- **Features**, on a 30 m UTM 11N grid:
  - From USGS 3DEP: slope, relief and topographic position (TPI at 300 m and 1 km).
  - From Sentinel-2 (median of three summer scenes): NDVI, bare-soil index, a carbonate index (B11/B12) and an iron index.
  - Distance to the mapped units.
  - 450 m averages of the slope and satellite measures.
- **Land:** BLM surface management. Berlin–Ichthyosaur State Park is excluded using its OpenStreetMap outline.
- **Model:** a random forest and a logistic regression, averaged as background percentiles.
- **Test:** leave one place out, along with any training place within 5 km.
  - Known places land at a median of the 86th percentile; 8 of 9 in the top quarter, 3 of 9 in the top tenth.
  - Satellite evidence alone: 79th percentile. Terrain alone: 61st. Distance to the rock alone: 61st. A hand-built "bare limestone" index: 45th, worse than chance.
- **Disclosed mistake:** the first v4 run scored each known place at the barest cell nearby (a selection bias), which inflated it to 7 of 9 in the top tenth. Fixed, that version gave 0 of 9. The current version is the third one tried.
- **Targets:** `data/v4/targets.csv`, 40 in all (T01–T30 tier A, T31–T40 tier B). All are on BLM land, at least 2 km from known places and 1.5 km from each other.
  - Close-ups are in `site/v4/T##.jpg`. T07 has no close-up (3DEP returned 502).
  - The page section is `#v4`. `site/v4/score.png` overlays the top 10% / top 3% of the search area.
- **Weekly:** `paleowave.yml` runs Mondays at 13:17 UTC (PBDB check plus build and check). The first check found 28 records, none new; 2 *Omphalosaurus* records are no longer filed as ichthyosaurs.

**Next:**
- More known places. Exact locality data has been requested from the Cincinnati Museum Center; the Field Museum is next.
- Field-walk some Luning and Augusta Mountains targets.

## IceWave — github.com/bdgroves/project-ice-wave · brooksgroves.com/project-ice-wave

The page is live (Pages enabled October 4).

**The recheck:** `tools/check.py` writes `site/checks.json`, with scikit-learn pinned at 1.9.1 because the counts shift between versions.
- **E02 "validation":** E02 is 69 km from the Coyote Canyon Mammoth Site (its outline is OSM way 1363154300) and sits on a flattened water patch in the Yakima Valley. The dig has run since 2008, with the bones found in 1999. The final model ranks E02 23rd of 25.
- **East model's 36/40:** every background point got a default lithology score of 0.5, so "not 0.5" meant "fossil". It reproduces as 37/40. Without that score, holding out whole places, AUC is 0.65 (10 of 28 places found, while flagging 18% of background).
- **Zero terrain:** 23 of 40 east records (all of Montana plus 5 in Idaho) had all-zero terrain, so the model learned that zeros mean fossils. The top 6 east targets are on water: Lake Bryan, Lower Granite Lake, Bear Lake, Waptus Lake, Lake Wallula and others.
- **West model:** AUC 0.890 drops to 0.63 on terrain alone. 6 of its 31 records are in British Columbia.
- **Modern animals in the west data:** 6 of the 31 records are modern museum specimens, including a horse, bison and elk from Woodland Park Zoo, Hoh River elk from 1915, and others. They're listed in `data/checks/modern_records.json`.
- **Not megafauna:** 16 of the 40 east records are small animals or birds.

**v5, "Where to look instead":**
- `tools/v5/quarries.py` takes all 859 active WA DNR surface-mine permits and looks up what each is cut into on the WA DNR 1:100,000 geologic map (layer 11).
  - 478 are in Ice Age ground: 117 flood deposits, 25 loess, 10 lake/bog, 326 glacial.
  - The Coyote Canyon pit (Mahaffey Rock Pit #1, permit 11422) is on loess and ranks 185th of 859. That's a check, not a blind test.
- It also pulls Ice Age finds from PBDB and iDigBio (fossil specimens only): 71 records at 14 places.
- **Outputs:** `data/v5/quarries.csv`, `quarries.geojson`, `finds.geojson` and `eval.json`. eval.json includes new and closed permits.
- **Workflows:**
  - The weekly `icewave.yml` (Mondays 13:23 UTC) runs `osm.py` (only once) → `pbdb.py` → `quarries.py` → `build.py` → `check.py`.
  - `v5.yml` is the manual dispatch.
- The page sections are `#pits` (map, cards, the 20 biggest eastern pits) plus the original recheck cards and target tables.
- Supporting finds: Coyote Canyon (quarry), the Sequim mastodon (backhoe pond), Wenas Creek (road crew) and a Seattle tusk (apartment dig).

**Next:**
- Possibly contact big eastern pit operators.
- Possibly add natural exposures (cutbanks in Touchet beds).
- The old 5-state model needs a full rebuild, not tuning.

## brooksgroves.com (bdgroves/bdgroves.github.io)

- **Posts:**
  - `blog/paleowave-rechecked-post.html` and `blog/icewave-rechecked-post.html` ("IceWave, Rechecked: My Mammoth Model Found Rivers").
  - Both now end with an "Update, later the same day" box covering v4 and the pits.
  - Images are in `blog/img/paleowave/` and `blog/img/icewave/`.
- **Listings updated:** the homepage (nav link, support story, project card, writing list kept at 9 items), `blog/index.html`, `tags.html` (POSTS array) and `paleontology.html`.
  - On the hub, the IceWave validation banner and block were replaced with a correction; the cards are updated with v4 and pit stats.
  - Small hub fix: PaleoWave #7 "was v2 #3".

## 30 Day Map Challenge 2026 — bdgroves/30DayMapChallenge (site brooksgroves.com/30DayMapChallenge/2026/)

**Workflows:**
- `dmc-2026-render.yml` (input: day) installs gfortran, git-adds `card.jpg` and `share`, and fails loudly if the push doesn't land.
- `dmc-2026-build.yml` builds the site.

**Toolkit:** `dmc` (`place_labels`, `label`), `basemap.mapbox`, `terrain.dem`, and `fetch`. `build.py` writes the share cards, `share/day-NN.html` with Open Graph tags, and the gallery (share buttons, "Go deeper" links).

**Done:**
- Days 6, 9–14, 16 (set up), 17, 19, 21, 23, 26, 27 and 29.
- Day 10 is FORTRAN line-printer SYMAP (`BIGCRK.f`).
- Day 29 is the Rainier melt-out map.

**Pending:**
- Day 7: on the day.
- Day 16: map the X replies as Brooks pastes them (trailhead names only).
- Day 20: GBIF DOI.
- Day 21: re-render after OSM edits.
- Day 22: `places.csv`.
- Day 27: lonboard.
- Day 30: the hot-spring napkin map. Frame `napkin.jpg` when Brooks provides it, and add the story link (memoir.brooksgroves.com/cattle-guard.html) on Nov 30.
- Optional: an Earthdata secret for Day 17.
- Iron Door Saloon napkin: they have no personalized napkins. The reply draft asks for plain bar napkins plus anything with the logo; Brooks fills in [address] and sends it.

## Other repos touched this session

- **cascadia-wx v2:** probe scripts `tools/p_*.py` (`p_icewave`, `p_fossil`–`p_fossil5`).
- **lahar-watch:** shoot scripts `tools/shoot_ice.mjs` and `tools/shoot_v4.mjs`.
