"""FastAPI dev server for RATPLAN's visual test map -- terrain hillshade and
the road network, nothing else. See README.md / architecture.md §9 for scope:
this is a scaffold for eyeballing real terrain/road data while `rattfallan/`
gets built, not a rebuild of `rattfallan-demo`'s presentation tool (no
placement, routing, coverage heatmap, or scenario save/load here).

Run: `.venv/Scripts/uvicorn mapviz.server:app --reload` from RATPLAN/.
Needs a ratmap snapshot's data/ dir (height.tif + roads.geojson) -- defaults
to ../ratmap/snapshots/real_map_scenario_north/data, overridable via
RATPLAN_MAPVIZ_DATA_DIR (same convention as rattfallan-demo's own
RATTFALLAN_MAPS_DATA_DIR).
"""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pyproj import Transformer
from rasterio.enums import Resampling

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent
FRONTEND_DIR = HERE / "frontend"

DATA_DIR = Path(
    os.environ.get(
        "RATPLAN_MAPVIZ_DATA_DIR",
        str(REPO_ROOT.parent / "ratmap" / "snapshots" / "real_map_scenario_north" / "data"),
    )
)
HEIGHT_PATH = DATA_DIR / "height.tif"
ROADS_PATH = DATA_DIR / "roads.geojson"

# Same hillshade convention rattfallan-demo/scenario_builder/server.py's
# _compute_hillshade uses (gdaldem's own defaults: NW light, 45deg altitude)
# so terrain rendered here looks identical to that tool's own layer.
HILLSHADE_MAX_DIM = 800
AZIMUTH_DEG = 315.0
ALTITUDE_DEG = 45.0


def _read_elevation_grid(path: Path, max_dim: int) -> dict[str, Any]:
    """Decimated read of a DTM GeoTIFF -- `out_shape` lets GDAL pull a
    downsampled overview during the read itself rather than loading full
    resolution first, which matters here since a ratmap snapshot's height.tif
    can be several GB. Returns the elevation array, its cell size in meters
    (the raster's own CRS is assumed projected/metric, true for ratmap's
    exports), and its four corners reprojected to WGS84 lon/lat in
    nw/ne/se/sw order -- same corner convention and bounds-only bilinear
    approximation rattfallan-demo's server.py uses for its own hillshade,
    good enough for a rendering-only overlay at this extent."""
    with rasterio.open(path) as ds:
        scale = min(1.0, max_dim / max(ds.width, ds.height))
        out_width = max(1, round(ds.width * scale))
        out_height = max(1, round(ds.height * scale))
        band = ds.read(1, out_shape=(out_height, out_width), resampling=Resampling.average, masked=True)
        elevation = np.ma.filled(band, fill_value=float(band.mean())) if band.mask.any() else band.data
        transform = ds.transform * ds.transform.scale(ds.width / out_width, ds.height / out_height)
        cell_size_m = abs(transform.a)
        left, top = transform * (0, 0)
        right, bottom = transform * (out_width, out_height)
        to_wgs84 = Transformer.from_crs(ds.crs, "EPSG:4326", always_xy=True)
        corners = [list(to_wgs84.transform(x, y)) for x, y in [(left, top), (right, top), (right, bottom), (left, bottom)]]
    return {"elevation_m": elevation.astype(np.float64), "cell_size_m": cell_size_m, "corners": corners}


def _compute_hillshade(elevation: np.ndarray, cell_size_m: float, azimuth_deg: float, altitude_deg: float) -> np.ndarray:
    """Standard surface-normal-dot-light-vector hillshade -- same formula
    gdaldem's `hillshade` uses. Row increases southward (image convention),
    so eastward slope is d/d_col directly but northward slope is the
    negation of d/d_row."""
    dz_drow, dz_dcol = np.gradient(elevation, cell_size_m)
    dzdx, dzdy = dz_dcol, -dz_drow

    az, alt = math.radians(azimuth_deg), math.radians(altitude_deg)
    lx, ly, lz = math.cos(alt) * math.sin(az), math.cos(alt) * math.cos(az), math.sin(alt)

    illum = (-dzdx * lx - dzdy * ly + lz) / np.sqrt(dzdx**2 + dzdy**2 + 1.0)
    return np.round(np.clip(illum, 0.0, 1.0) * 255).astype(int)


def _load_hillshade() -> dict[str, Any] | None:
    if not HEIGHT_PATH.exists():
        return None
    grid = _read_elevation_grid(HEIGHT_PATH, HILLSHADE_MAX_DIM)
    intensity = _compute_hillshade(grid["elevation_m"], grid["cell_size_m"], AZIMUTH_DEG, ALTITUDE_DEG)
    n_rows, n_cols = intensity.shape
    return {"n_rows": n_rows, "n_cols": n_cols, "intensity": intensity.tolist(), "corners": grid["corners"]}


# Computed once at startup, not per-request -- terrain doesn't move, same
# fetch-once-on-load convention rattfallan-demo's server.py uses for its
# own static layers (hillshade/contours/grid).
_hillshade = _load_hillshade()

app = FastAPI(title="RATPLAN mapviz")


@app.get("/api/hillshade")
def get_hillshade() -> dict[str, Any]:
    if _hillshade is None:
        raise HTTPException(status_code=404, detail=f"no height.tif found at {HEIGHT_PATH}")
    return _hillshade


@app.get("/api/roads")
def get_roads() -> dict[str, Any]:
    """Serves the snapshot's already-derived roads.geojson as-is -- produced
    by ratmap's own prepare_visual_data.py fixture, already carrying
    per-category `color`, no processing needed here."""
    if not ROADS_PATH.exists():
        raise HTTPException(status_code=404, detail=f"no roads.geojson found at {ROADS_PATH}")
    return json.loads(ROADS_PATH.read_text(encoding="utf-8"))


# Order matters: Starlette matches mounts/routes in registration order, and a
# root "/" mount would otherwise swallow "/api/..." requests too -- so those
# are registered above, this goes last.
app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
