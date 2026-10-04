# 🌊 Project PaleoWave

<p align="center">
  <img src="assets/paleowave_flag.png" width="520" alt="Project PaleoWave flag: an ichthyosaur over a wave beside the outline of Nevada"/>
</p>

<p align="center">
  <b>Where might central Nevada's Triassic ichthyosaurs still be buried?</b><br>
  A terrain model of the places they've been found, fifty places it points to, and an honest look at how far to trust it.
</p>

**[→ The page: brooksgroves.com/project-paleowave](https://brooksgroves.com/project-paleowave/)**

---

## The idea

About 240 million years ago central Nevada was the floor of a warm sea. Ichthyosaurs, dolphin-shaped marine reptiles, some as long as a bus, lived and died in it, and their bones are in the limestone of the Humboldt Range, the Augusta Mountains and the Shoshone Mountains. The Paleobiology Database (PBDB) records them at a handful of places.

PaleoWave learns what the ground looks like at those places (elevation, slope, aspect, ruggedness and topographic position) from USGS 3DEP elevation, compares it with ground elsewhere, and scores candidate spots by how alike they look. Bones end up where the sea floor was and come to light where erosion strips it, so basins and lower slopes tend to score better than ridge crests.

The current model (v3) trains two random forests: one for the north (the Middle Triassic Prida and Favret formations, north of 39.5°N) and one for the south (the Late Triassic Luning and Gabbs).

## Rechecked, October 2026

Coming back to this project, I re-checked its numbers from the files in this repo ([`tools/check.py`](tools/check.py), which writes [`site/checks.json`](site/checks.json)). Three earlier claims held up less well than they looked, and the old README overstated them:

| What the README said | What the files show |
|---|---|
| Leave-one-out recall 65% (north) and 71% (south); v1/v2 found 89% of held-out sites | The 30 training records sit at only **18 places** (six at one spot, Merriam's 1906 site). Leaving out one record left its twins in training. Leaving out whole places, the v1/v2 model recognises **7 of 16** places it hadn't seen (26% of records). v3's rasters aren't in the repo, so its figures can't be re-checked here, but its test had the same flaw. |
| Ruggedness (TRI) is "the single strongest predictor" | In v1 and v2, TRI at the fossil sites came from the 8 m DEM with one formula; at the comparison points, from an ~18 m fetch with another. Per unit of slope it's **7.7 at the fossil sites and 1.9 at the comparison points**, so the top feature was partly measuring the measurement. v3 fixed this by sampling every point from the same 90 m rasters, but v3 only re-ranked the candidates that v1 and v2 had found. |
| v3 scores "every candidate pixel within the TRc formation extent" | **None of the 50 targets** is on the Triassic marine units of the state geologic map (median 18 km away). I put that down to the map being too coarse, but I was wrong about that as well: the layer v3 used kept only two of the state map's Triassic units and left out the Luning and Gabbs rocks altogether. On the full 1:250,000 map, formation by formation, 11 of the 28 current records sit on mapped Triassic marine rock and 14 are within a kilometre of it. Version 4 (below) uses that map. |

Smaller corrections: v3's #2 target was described as new to v3, but it was v2 #16 and v1 #9. v3's #7 was v2 #3, not v2 #1. Luning and Gabbs are Late Triassic, not lateral equivalents of the Middle Triassic Prida. *Shonisaurus popularis* is huge, and Nevada's state fossil, but it isn't the largest Triassic ichthyosaur known. The "LiDAR" close-ups are 3DEP elevation at about 15 m.

**What still holds:** tested on whole held-out places, the v1/v2 model still separates fossil terrain from random terrain well (AUC 0.87, against 0.98 the old way) and flags only 2% of random comparison points. It has learned something real about where the known sites sit. It just knows 18 places, and none of its targets has been walked yet. **Treat the targets as places to go and look, not as predictions.**

## Version 4: where to look now

Fossils turn up where three things line up: **the right rock**, **that rock bare and eroding**, and **ground you're allowed to walk**. Version 4 (October 2026) is built that way.

1. **Rock.** Only the Triassic marine formations on the Geologic Map of Nevada (Crafford 2007, USGS Data Series 249, compiled at 1:250,000 and named formation by formation), plus a kilometre for map and coordinate error. Tier A is the formations Nevada's ichthyosaurs come from (Prida, Favret, Augusta Mountain, Cane Spring, Natchez Pass, Luning, Gabbs, Sunrise, Lower Triassic marine rocks); tier B is other marine Triassic rock. Together that's 8,530 km², about 3% of Nevada, and 9 of the 16 known places are in it.
2. **Exposure**, on a 30 m grid: slope, relief and topographic position from USGS 3DEP; greenness, a bare-ground index, a carbonate index and an iron index from Sentinel-2 summer scenes (2023–2025, clouds masked, median of three), each also averaged over about 450 m (a whole hillside).
3. **Land.** BLM surface management; targets are on BLM land and outside Berlin–Ichthyosaur State Park.
4. **Model.** A random forest and a logistic regression, averaged, trained on the known places with good coordinates against random ground from the same search area.

**The test.** Each known place in the search area was left out in turn, with every training place within 5 km of it, and ranked against all 9.5 million cells of the search area:

| Evidence | Held-out places' median percentile | In the top quarter | In the top tenth |
|---|---|---|---|
| **All of it (the model)** | **86th** | **8 of 9** | **3 of 9** |
| Satellite only | 79th | 5 of 9 | 1 of 9 |
| Terrain only | 61st | 0 of 9 | 0 of 9 |
| Distance to the mapped rock only | 61st | 2 of 9 | 2 of 9 |
| A hand-built "bare limestone" index, no learning | 45th | 0 of 9 | 0 of 9 |

A random cell would be the 50th percentile. It's a real signal, not a strong one, and nine test places is very few. **I also have to own a mistake:** my first v4 run said 7 of 9 places landed in the top tenth. I had scored each known place at the barest cell within 90 m, a head start no random cell got. Scored fairly, that version put 0 of 9 in the top tenth. The version above is the third I tried, chosen after seeing the second, so its numbers flatter it a little.

**Forty places to look:** [`data/v4/targets.csv`](data/v4/targets.csv). T01–T30 are in tier A formations (13 in the Luning, 8 in the Augusta Mountain and Cane Spring, 5 in the Natchez Pass, and 4 just outside a mapped edge), T31–T40 in tier B. Every target is on BLM land, at least 2 km from a known place and 1.5 km from the next target. Each has a close-up in `site/v4/` (Sentinel-2 beside a 10 m hillshade). Nobody has walked them yet.

| Script | What |
|---|---|
| [`tools/v4/geology.py`](tools/v4/geology.py) | downloads DS 249 and reports which formation each PBDB record sits on |
| [`tools/v4/model.py`](tools/v4/model.py) | the search area, features, test and targets (in CI: `.github/workflows/v4.yml`) |
| [`tools/v4/panels.py`](tools/v4/panels.py) | the close-ups |
| [`tools/v4/site.py`](tools/v4/site.py) | the page's v4 files in `site/v4/` |

## The page

[`index.html`](index.html) is the project's page, served by GitHub Pages: a map of the known places, the 50 targets and the mapped Triassic rocks; the three checks above; the targets table; the 20 terrain close-ups; and the geology. It reads only the files in [`site/`](site/), which are built from the committed model outputs:

| Script | Writes | When |
|---|---|---|
| [`tools/pbdb.py`](tools/pbdb.py) | `site/pbdb_live.json`: every ichthyosaur occurrence PBDB lists in Nevada | Mondays, by GitHub Actions |
| [`tools/build.py`](tools/build.py) | `site/targets.geojson`, `site/known.geojson`, `site/triassic.geojson`, `site/panels/`, and `site/live.json` (what changed in PBDB since the model was trained) | after each PBDB check |
| [`tools/check.py`](tools/check.py) | `site/checks.json`: the re-check above | after each PBDB check |

If PBDB adds an ichthyosaur record in Nevada at a place the model has never seen, the page says so and marks it on the map with a dashed ring. The first check (October 4, 2026) found 28 records, none new, and two of the model's 30 gone: both *Omphalosaurus*, which PBDB no longer files under Ichthyosauria.

```bash
pixi run -e site pbdb     # or: python tools/pbdb.py
pixi run -e site build
pixi run -e site check
python -m http.server     # then open http://localhost:8000
```

## The notebooks

The model itself was built in Jupyter (`pixi run lab`, Windows; the 2.7 GB DEM and the terrain rasters are git-ignored, so the notebooks need them re-downloaded from USGS 3DEP).

| Notebook | What |
|---|---|
| `01_pbdb_harvester` | PBDB ichthyosaur occurrences in Nevada |
| `02_terrain_analysis_final` (and two earlier drafts) | 3DEP 1/9″ DEM, slope, aspect, TRI; features at the known sites |
| `03_ml_model_final` | v1 random forest and the original top-50 candidates |
| `04_geology` | Triassic marine units from the state geologic map |
| `05_lidar_terrain_analysis` | the 20 close-ups and TPI at the candidates |
| `06_model_v2_tpi` | v2: TPI added as a post-hoc adjustment |
| `07_loo_validation` | background grid and leave-one-out (per record; see above) |
| `08_idigbio_harvest` | iDigBio records (Cincinnati Museum Center *Cymbospondylus*, centroid coordinates only) |
| `09_literature_harvest` | seven literature localities, Merriam 1908 to Klein et al. 2020 |
| `10_model_v3_stratified` | v3: north and south models, TPI as a feature, re-ranked candidates |

## Data

| Source | What |
|---|---|
| [PBDB](https://paleobiodb.org) | ichthyosaur occurrences in Nevada (30 in the model; checked weekly for more) |
| USGS 3DEP | 1/9″ DEM (~8 m) and ~15 m fetches for the close-ups |
| NBMG geologic map, via the USGS State Geologic Map Compilation | Triassic marine units (TRc, TRmt) |
| Literature | seven localities, Merriam 1908 to Klein et al. 2020 |
| iDigBio | 15 *Cymbospondylus* records at the Cincinnati Museum Center, coordinates pending |

## What's next

- Score the whole Triassic outcrop with v3, instead of re-ranking the v1/v2 candidate list.
- Test on places held out together, and on whole ranges held out, not single records.
- Use the 1:250,000 county geologic maps, so "is this even Triassic rock?" can become a real filter.
- Retrain with exact locality data: requested from the Cincinnati Museum Center; the Field Museum (PR2251, PR3032) is next.

## If you go

Vertebrate fossils on federal land can be collected only under a permit (Paleontological Resources Preservation Act), and collecting at Berlin–Ichthyosaur State Park isn't allowed at all. If you find bone, photograph it in place with something for scale, note the coordinates, and tell the BLM field office. This project suggests where to look; it doesn't collect. The country is remote and hot: carry water, tell someone your route, and don't count on a signal.

---

<p align="center"><sub>Project PaleoWave · Brooks Groves · <a href="https://brooksgroves.com">brooksgroves.com</a></sub></p>
