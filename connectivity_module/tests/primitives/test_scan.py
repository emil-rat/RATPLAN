"""Tests for ItmGridScan against a synthetic flat DTM (offline, no live ratmap/Docker needed - same
construction pattern as RATPLAN/tests/primitives/test_terrain.py's flat_dtm fixture).

A weak test radio (tight link budget) and a small `target_cell_size_m` are used throughout so grids stay
small and land comfortably inside the synthetic DTM's extent - real-terrain wall-clock cost at production
defaults is a separate, manual performance check (the plan's Verification section), not something these
unit tests need to exercise.
"""

import math

import numpy as np
import pytest
from rasterio.io import MemoryFile
from rasterio.transform import from_origin

from ratplan_terrain.models.geometry import Position
from ratplan_terrain.primitives.terrain import DtmSampler

from ratplan_connectivity.primitives.kernel import ArdKernel
from ratplan_connectivity.primitives.scan import ItmGridScan, RadioParams

SENDER = Position(lon=17.0, lat=60.0)
_WEAK_RADIO = RadioParams(tx_power_dbm=10.0, rx_sensitivity_dbm=-70.0, frequency_mhz=433.0)
_TEST_CELL_SIZE_M = 140.0  # -> an 8x8-ish grid for _WEAK_RADIO's ~550m max range


def _expected_n(radio: RadioParams, target_cell_size_m: float, max_extent_m: float) -> int:
    """Mirrors ItmGridScan.__call__'s own extent/resolution formula, so these tests don't hardcode a
    number that would silently go stale if the formula's constants ever change."""
    extent_m = min(radio.max_range_m(), max_extent_m)
    return max(2, math.ceil(2 * extent_m / target_cell_size_m))


def _geotiff_bytes(band: np.ndarray, transform, crs: str = "EPSG:4326") -> bytes:
    height, width = band.shape
    with MemoryFile() as memfile:
        with memfile.open(
            driver="GTiff", height=height, width=width, count=1, dtype=band.dtype, crs=crs, transform=transform
        ) as dst:
            dst.write(band, 1)
        return memfile.read()


@pytest.fixture
def flat_dtm() -> DtmSampler:
    # ~3km x 3km, comfortably larger than _WEAK_RADIO's few-hundred-meter max range.
    transform = from_origin(16.985, 60.015, 0.0001, 0.0001)
    band = np.full((300, 300), 50.0, dtype=np.float32)
    return DtmSampler(data=_geotiff_bytes(band, transform))


def test_max_range_m_scales_with_link_budget():
    generous = RadioParams(tx_power_dbm=40.0, rx_sensitivity_dbm=-120.0)
    tight = RadioParams(tx_power_dbm=20.0, rx_sensitivity_dbm=-90.0)
    assert generous.max_range_m() > tight.max_range_m()


def test_extent_capped_by_max_extent_m_for_a_generous_radio(flat_dtm):
    # A radio whose free-space range would be huge (as real generous link budgets are) must not blow up
    # the grid's cell count - max_extent_m caps it, per the fix for the real-terrain finding that free-
    # space range badly overestimates real low-antenna range on this terrain.
    generous_radio = RadioParams(tx_power_dbm=30.0, rx_sensitivity_dbm=-120.0)
    assert generous_radio.max_range_m() > 100_000  # many km of theoretical free-space range
    scan = ItmGridScan(dtm=flat_dtm, radio=generous_radio, target_cell_size_m=100.0, max_extent_m=500.0)
    raster = scan(SENDER)
    expected_n = _expected_n(generous_radio, 100.0, 500.0)
    assert raster.covered.shape == (expected_n, expected_n)


def test_scan_produces_expected_grid_shape(flat_dtm):
    scan = ItmGridScan(dtm=flat_dtm, radio=_WEAK_RADIO, target_cell_size_m=_TEST_CELL_SIZE_M)
    raster = scan(SENDER)
    expected_n = _expected_n(_WEAK_RADIO, _TEST_CELL_SIZE_M, scan.max_extent_m)
    assert raster.covered.shape == (expected_n, expected_n)
    assert raster.mean_db.shape == (expected_n, expected_n)
    assert raster.variance_db.shape == (expected_n, expected_n)


def test_scan_covers_sender_position(flat_dtm):
    scan = ItmGridScan(dtm=flat_dtm, radio=_WEAK_RADIO, target_cell_size_m=_TEST_CELL_SIZE_M)
    raster = scan(SENDER)
    assert raster.covers(SENDER)


def test_scan_variance_db_equals_kernel_prior_alpha(flat_dtm):
    kernel = ArdKernel(alpha=42.0)
    scan = ItmGridScan(dtm=flat_dtm, radio=_WEAK_RADIO, kernel=kernel, target_cell_size_m=_TEST_CELL_SIZE_M)
    raster = scan(SENDER)
    assert np.all(raster.variance_db == 42.0)


def test_scan_mean_db_nondecreasing_with_distance_on_flat_terrain(flat_dtm):
    # Over flat terrain, ITM's predicted path loss should increase monotonically with distance from the
    # sender - a basic physical sanity check, not an exact-value check (real ITM internals aren't
    # independently reproduced here).
    scan = ItmGridScan(dtm=flat_dtm, radio=_WEAK_RADIO, target_cell_size_m=_TEST_CELL_SIZE_M)
    raster = scan(SENDER)
    mid = raster.n_rows // 2
    row = raster.mean_db[mid]
    center = raster.n_cols // 2
    # loss should climb moving away from the sender's own column in either direction
    assert row[0] >= row[center]
    assert row[-1] >= row[center]
