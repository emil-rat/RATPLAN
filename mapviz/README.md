# mapviz — RATPLAN's visual test map

Terrain hillshade + road network on a MapLibre map, nothing else. See `architecture.md` §9 for the
scope decision: this is a scaffold for eyeballing real terrain/road data while `rattfallan/` gets
built, not a rebuild of `rattfallan-demo`'s presentation tool. No marker placement, routing, coverage
heatmap, or scenario save/load here yet — those land once `rattfallan/`'s own primitives exist to back
them (see `architecture.md` §10's open items).

## Setup

```
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt
```

## Data

Needs a `ratmap` snapshot's `data/` dir, containing `height.tif` and `roads.geojson`. Defaults to
`../ratmap/snapshots/real_map_scenario_north/data` (same sibling-repo layout `rattfallan-demo` assumes);
point it elsewhere with:

```
set RATPLAN_MAPVIZ_DATA_DIR=path\to\snapshot\data
```

If `height.tif` or `roads.geojson` isn't found, the corresponding layer is just skipped — the map still
loads, and the on-screen status line says what's missing.

Startup takes ~30-40s against `real_map_scenario_north`'s ~4GB `height.tif` (decimated read via
`rasterio`'s `out_shape`, computed once at import time — see `server.py`'s `_load_hillshade`). Not a
bug; it's a one-time cost per process start, not per-request.

## Run

```
.venv/Scripts/uvicorn mapviz.server:app --reload
```

from `RATPLAN/`, then open `http://127.0.0.1:8000`.
