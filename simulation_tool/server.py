"""FastAPI dev server for RATPLAN's simulation tool -- a visual frontend over the *real* Scan/GP-
correction pipeline (`connectivity_module/ratplan_connectivity`). Click to place a relay node and see
its real `ItmGridScan` coverage raster; click to place a manually-entered RSSI reading and see the real
`GpCorrector` reshape that raster. Single active relay at a time -- placing a new one discards the
previous relay's corrector and observations (no multi-relay yet). See README.md for scope/setup;
`architecture.md` §8/§9 for how this relates to `mapviz/` (terrain+roads sanity tool, deliberately not
wired to Scan) and `rattfallan-demo` (broken against this backend, UI-patterns-only reference).

No reimplementation of scan/GP/coverage math here -- this module is thin wiring around
`ItmGridScan`/`GpCorrector`/`CoverageRaster` plus the same hillshade-rendering helper `mapviz/server.py`
already hand-rolls (terrain shading has no backend equivalent; it's pure rendering math, not planning
logic).

Run: `.venv/Scripts/uvicorn simulation_tool.server:app --reload` from RATPLAN/.
Needs a ratmap snapshot's data/ dir (height.tif + roads.geojson) -- defaults to
../ratmap/snapshots/real_map_scenario_north/data, overridable via RATPLAN_SIMULATION_TOOL_DATA_DIR
(same convention as mapviz's own RATPLAN_MAPVIZ_DATA_DIR).
"""

from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from ratplan_connectivity.models.coverage import CoverageRaster
from ratplan_connectivity.primitives.gp_correction import GpCorrector
from ratplan_connectivity.primitives.kernel import ArdKernel
from ratplan_connectivity.primitives.scan import ItmGridScan, RadioParams
from ratplan_terrain.models.geometry import Position
from ratplan_terrain.primitives.terrain import DtmSampler

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent
FRONTEND_DIR = HERE / "frontend"

DATA_DIR = Path(
    os.environ.get(
        "RATPLAN_SIMULATION_TOOL_DATA_DIR",
        str(REPO_ROOT.parent / "ratmap" / "snapshots" / "real_map_scenario_north" / "data"),
    )
)
HEIGHT_PATH = DATA_DIR / "height.tif"
ROADS_PATH = DATA_DIR / "roads.geojson"

# Same hillshade convention mapviz/server.py and rattfallan-demo/scenario_builder/server.py's
# _compute_hillshade use (gdaldem's own defaults: NW light, 45deg altitude), so terrain here looks
# identical to both those tools' own terrain layer.
HILLSHADE_MAX_DIM = 800
AZIMUTH_DEG = 315.0
ALTITUDE_DEG = 45.0

# ItmGridScan's own library defaults (target_cell_size_m=25.0, max_extent_m=1500.0) give a 120x120
# grid -- 14,400 non-vectorized predict_point_to_point calls (scan.py's __call__ loops one ITM call per
# cell), too slow to feel interactive on a map click. No performance budget has ever been set for
# Scan() (architecture.md §9); these are a heuristic stopgap picked to keep placement responsive, not a
# validated number -- tune via the env vars below if it's still too slow (or too coarse) on your machine.
CELL_SIZE_M = float(os.environ.get("SIMULATION_TOOL_CELL_SIZE_M", "50.0"))
MAX_EXTENT_M = float(os.environ.get("SIMULATION_TOOL_MAX_EXTENT_M", "800.0"))

_dtm: DtmSampler | None = DtmSampler(path=str(HEIGHT_PATH)) if HEIGHT_PATH.exists() else None
_radio = RadioParams()  # fixed defaults, no UI override yet -- see README.md
# GP kernel lengthscales, overridable per env var so their spatial reach can be tuned without editing
# code -- an unset var falls through to ArdKernel's own (placeholder, uncalibrated) default, so the
# defaults live only in kernel.py.
_KERNEL_ENV = {
    "lengthscale_position": "SIMULATION_TOOL_LS_POSITION_M",
    "lengthscale_elevation": "SIMULATION_TOOL_LS_ELEVATION_M",
    "lengthscale_distance": "SIMULATION_TOOL_LS_DISTANCE_M",
    "lengthscale_bearing": "SIMULATION_TOOL_LS_BEARING",
    "lengthscale_los_count": "SIMULATION_TOOL_LS_LOS_COUNT",
}
_kernel = ArdKernel(**{field_name: float(os.environ[var]) for field_name, var in _KERNEL_ENV.items() if var in os.environ})
_scan = (
    ItmGridScan(dtm=_dtm, radio=_radio, kernel=_kernel, target_cell_size_m=CELL_SIZE_M, max_extent_m=MAX_EXTENT_M)
    if _dtm is not None
    else None
)


@dataclass
class _RelayState:
    position: Position
    corrector: GpCorrector
    observations: list[dict[str, float]] = field(default_factory=list)


_relay: _RelayState | None = None


def _compute_hillshade(elevation: np.ndarray, cell_size_m: float, azimuth_deg: float, altitude_deg: float) -> np.ndarray:
    """Standard surface-normal-dot-light-vector hillshade -- same formula gdaldem's `hillshade` uses,
    copied from mapviz/server.py. Row increases southward (image convention), so eastward slope is
    d/d_col directly but northward slope is the negation of d/d_row."""
    dz_drow, dz_dcol = np.gradient(elevation, cell_size_m)
    dzdx, dzdy = dz_dcol, -dz_drow

    az, alt = math.radians(azimuth_deg), math.radians(altitude_deg)
    lx, ly, lz = math.cos(alt) * math.sin(az), math.cos(alt) * math.cos(az), math.sin(alt)

    illum = (-dzdx * lx - dzdy * ly + lz) / np.sqrt(dzdx**2 + dzdy**2 + 1.0)
    return np.round(np.clip(illum, 0.0, 1.0) * 255).astype(int)


def _load_hillshade() -> dict[str, Any] | None:
    """Computed once at startup, not per-request -- terrain doesn't move. Reuses the real
    `DtmSampler.elevation_grid()` (a decimated-read rendering helper already living in
    `ratplan_terrain`) instead of mapviz's own hand-rolled rasterio read."""
    if _dtm is None:
        return None
    grid = _dtm.elevation_grid(max_dim=HILLSHADE_MAX_DIM)
    intensity = _compute_hillshade(grid["elevation_m"], grid["cell_size_m"], AZIMUTH_DEG, ALTITUDE_DEG)
    n_rows, n_cols = intensity.shape
    return {"n_rows": n_rows, "n_cols": n_cols, "intensity": intensity.tolist(), "corners": grid["corners"]}


_hillshade = _load_hillshade()


def _serialize_raster(raster: CoverageRaster) -> dict[str, Any]:
    """`CoverageRaster` row 0 is `min_lat` (south), but a north-up map image needs row 0 = north --
    flipped here, server-side, so the frontend's one shared grid-painting helper can treat every JSON
    grid it receives (hillshade and coverage alike) as row-0-north uniformly. `margin_db` is
    `tx_power_dbm - rx_sensitivity_dbm - mean_db`, the same formula `covered_from_margin` computes
    internally to decide `covered` -- exposed here as a continuous display value, not reimplemented."""
    margin_db = np.flipud(_radio.tx_power_dbm - _radio.rx_sensitivity_dbm - raster.mean_db)
    covered = np.flipud(raster.covered)
    corners = [  # nw, ne, se, sw -- same order mapviz's hillshade corners already use
        [raster.min_lon, raster.max_lat],
        [raster.max_lon, raster.max_lat],
        [raster.max_lon, raster.min_lat],
        [raster.min_lon, raster.min_lat],
    ]
    return {
        "n_rows": raster.n_rows,
        "n_cols": raster.n_cols,
        "covered": covered.tolist(),
        "margin_db": [[round(float(v), 1) for v in row] for row in margin_db],
        "corners": corners,
    }


class RelayRequest(BaseModel):
    lon: float
    lat: float


class ObserveRequest(BaseModel):
    lon: float
    lat: float
    rssi_dbm: float


app = FastAPI(title="RATPLAN simulation_tool")


@app.get("/api/hillshade")
def get_hillshade() -> dict[str, Any]:
    if _hillshade is None:
        raise HTTPException(status_code=404, detail=f"no height.tif found at {HEIGHT_PATH}")
    return _hillshade


@app.get("/api/roads")
def get_roads() -> dict[str, Any]:
    """Serves the snapshot's already-derived roads.geojson as-is, same as mapviz/server.py."""
    if not ROADS_PATH.exists():
        raise HTTPException(status_code=404, detail=f"no roads.geojson found at {ROADS_PATH}")
    return json.loads(ROADS_PATH.read_text(encoding="utf-8"))


@app.post("/api/relay")
def post_relay(body: RelayRequest) -> dict[str, Any]:
    global _relay
    if _dtm is None or _scan is None:
        raise HTTPException(status_code=503, detail=f"no height.tif found at {HEIGHT_PATH} -- Scan needs real terrain")
    position = Position(lon=body.lon, lat=body.lat)
    try:
        prior = _scan(position)
        corrector = GpCorrector(
            prior=prior, dtm=_dtm, sender=position, radio=_radio, kernel=_kernel, n_profile_samples=_scan.n_profile_samples
        )
    except Exception as exc:  # ITM/profile edge cases at an unusual position -- surface, don't crash the process
        raise HTTPException(status_code=500, detail=f"scan failed: {exc}") from exc
    _relay = _RelayState(position=position, corrector=corrector)
    return {"relay": {"lon": position.lon, "lat": position.lat}, "raster": _serialize_raster(corrector.corrected_raster())}


@app.post("/api/observe")
def post_observe(body: ObserveRequest) -> dict[str, Any]:
    if _relay is None:
        raise HTTPException(status_code=400, detail="place a relay before adding observations")
    position = Position(lon=body.lon, lat=body.lat)
    try:
        _relay.corrector.observe(position, body.rssi_dbm)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"observe failed: {exc}") from exc
    _relay.observations.append({"lon": position.lon, "lat": position.lat, "rssi_dbm": body.rssi_dbm})
    return {"observations": _relay.observations, "raster": _serialize_raster(_relay.corrector.corrected_raster())}


@app.post("/api/reset")
def post_reset() -> dict[str, Any]:
    global _relay
    _relay = None
    return {"ok": True}


@app.get("/api/state")
def get_state() -> dict[str, Any]:
    """Lets the frontend restore relay/observations/raster after a page refresh instead of desyncing
    from server truth (the server, not the browser, is where `_relay` actually lives)."""
    if _relay is None:
        return {"relay": None, "observations": [], "raster": None}
    return {
        "relay": {"lon": _relay.position.lon, "lat": _relay.position.lat},
        "observations": _relay.observations,
        "raster": _serialize_raster(_relay.corrector.corrected_raster()),
    }


# Order matters: Starlette matches mounts/routes in registration order, and a root "/" mount would
# otherwise swallow "/api/..." requests too -- so those are registered above, this goes last.
app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
