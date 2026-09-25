"""Requires Docker and the ratplan-itwom-service image built (see ../../itwom/Dockerfile) with the
real-elevation-grid terrain wiring (see ../../itwom/wrapper/itwom_cli.py). Uses a real ratmap snapshot's
height.tif (no server needed) rather than a synthetic scenario — synthetic base+ridge terrain no longer
exists as a code path (see ratplan_terrain.primitives.terrain_profile.elevation_grid_from_dtm).

Building the real grid needs `ratplan_terrain` (RATPLAN's root package) installed alongside this package's own
`.venv`: `.venv/Scripts/pip install -e ../..` from here.
"""

from pathlib import Path

import pytest

from ratplan_itwom import ElevationGrid, Site, predict_point_to_point

SNAPSHOT_HEIGHT_TIF = (
    Path(__file__).resolve().parents[4]
    / "ratmap"
    / "snapshots"
    / "real_map_scenario_north"
    / "data"
    / "height.tif"
)

pytestmark = [
    pytest.mark.docker,
    pytest.mark.skipif(
        not SNAPSHOT_HEIGHT_TIF.exists(), reason=f"no ratmap snapshot found at {SNAPSHOT_HEIGHT_TIF}"
    ),
]

TX = Site(lat=59.556343, lon_deg_east=17.654258, height_m=10.0)
RX = Site(lat=59.569076, lon_deg_east=17.690677, height_m=2.0)


def _real_grid(n: int = 60) -> ElevationGrid:
    from ratplan_terrain.models.geometry import Position
    from ratplan_terrain.primitives.terrain import DtmSampler
    from ratplan_terrain.primitives.terrain_profile import elevation_grid_from_dtm

    dtm = DtmSampler(path=SNAPSHOT_HEIGHT_TIF)
    return elevation_grid_from_dtm(
        dtm, Position(lon=TX.lon_deg_east, lat=TX.lat), Position(lon=RX.lon_deg_east, lat=RX.lat), n=n
    )


def _flattened(grid: ElevationGrid) -> ElevationGrid:
    n_lat, n_lon = len(grid.values_m), len(grid.values_m[0])
    mean = sum(sum(row) for row in grid.values_m) / (n_lat * n_lon)
    return ElevationGrid(
        min_lat=grid.min_lat,
        max_lat=grid.max_lat,
        min_lon_deg_east=grid.min_lon_deg_east,
        max_lon_deg_east=grid.max_lon_deg_east,
        values_m=[[mean] * n_lon for _ in range(n_lat)],
    )


def test_itwom_on_real_terrain():
    result = predict_point_to_point(TX, RX, frequency_mhz=433.0, terrain=_real_grid(), use_itwom=True)
    assert result.model == "ITWOM Version 3.0"
    assert result.free_space_loss_db > 0
    assert result.path_loss_db > result.free_space_loss_db


def test_real_terrain_relief_changes_result_vs_flattened_version():
    """Proves the elevation grid actually reaches the container and affects its output -- same tx/rx/
    frequency, only the terrain relief differs (real DTM vs. that same grid flattened to its own mean)."""
    real_grid = _real_grid()
    flat_grid = _flattened(real_grid)

    real_result = predict_point_to_point(TX, RX, frequency_mhz=433.0, terrain=real_grid, use_itwom=True)
    flat_result = predict_point_to_point(TX, RX, frequency_mhz=433.0, terrain=flat_grid, use_itwom=True)

    # Free-space loss only depends on distance/frequency, not terrain -- should match regardless.
    assert real_result.free_space_loss_db == pytest.approx(flat_result.free_space_loss_db, abs=0.5)
    assert real_result.path_loss_db != pytest.approx(flat_result.path_loss_db, abs=1e-6)


def test_classic_itm_also_accepts_real_terrain():
    result = predict_point_to_point(TX, RX, frequency_mhz=433.0, terrain=_real_grid(), use_itwom=False)
    assert result.model == "Longley-Rice"
    assert result.path_loss_db > result.free_space_loss_db
