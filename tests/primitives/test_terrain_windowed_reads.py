"""Proves DtmSampler reads windowed subsets sized to the query, not the whole raster -- the fix for the
ArrayMemoryError a full ~4GB ratmap snapshot's height.tif triggered under memory pressure (DtmSampler used
to load the entire band in __init__). Uses a moderately large (not multi-GB) synthetic raster on disk,
written block-by-block so creating the fixture itself never holds the full array in memory either.
"""

from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

import ratplan_terrain.primitives.terrain as terrain_module
from ratplan_terrain.models.geometry import Position
from ratplan_terrain.primitives.terrain import DtmSampler

SIZE = 5000  # 5000x5000 float32 = 100MB -- large enough that "read it all" vs. "read a window" is a
             # clear, easy-to-assert difference, small enough to build quickly in a test.


@pytest.fixture(scope="module")
def big_raster(tmp_path_factory) -> Path:
    path = tmp_path_factory.mktemp("dtm") / "big.tif"
    transform = from_origin(10.0, 65.0, 0.0001, 0.0001)  # arbitrary small pixel spacing
    with rasterio.open(
        path, "w", driver="GTiff", height=SIZE, width=SIZE, count=1, dtype="float32", crs="EPSG:4326",
        transform=transform,
    ) as dst:
        block = 500
        for row_off in range(0, SIZE, block):
            rows = min(block, SIZE - row_off)
            # A distinctive per-cell pattern (not a constant) so later checks compare against a real,
            # position-dependent reference value, not just "some flat number."
            row_idx = np.arange(row_off, row_off + rows)[:, None]
            col_idx = np.arange(SIZE)[None, :]
            data = (row_idx + col_idx).astype(np.float32)
            dst.write(data, 1, window=rasterio.windows.Window(0, row_off, SIZE, rows))
    return path


def test_construction_does_not_read_the_band(big_raster):
    with patch.object(rasterio.io.DatasetReader, "read") as mock_read:
        DtmSampler(path=big_raster)
    mock_read.assert_not_called()


def test_construction_holds_no_full_array(big_raster):
    dtm = DtmSampler(path=big_raster)
    assert not hasattr(dtm, "_band")


def _spy_on_window_construction(windows: list) -> object:
    real_window = terrain_module.Window

    def spy(*args, **kwargs):
        window = real_window(*args, **kwargs)
        windows.append(window)
        return window

    return patch.object(terrain_module, "Window", side_effect=spy)


def test_point_query_reads_a_small_window_not_the_whole_raster(big_raster):
    dtm = DtmSampler(path=big_raster)
    windows: list = []
    with _spy_on_window_construction(windows):
        dtm.elevation_m(Position(lon=10.05, lat=64.95))
    assert len(windows) == 1
    assert windows[0].width * windows[0].height < 100  # a couple of pixels, nowhere near SIZE*SIZE


def test_profile_query_reads_a_window_bounded_by_the_profile_not_the_full_raster(big_raster):
    dtm = DtmSampler(path=big_raster)
    a = Position(lon=10.05, lat=64.95)
    b = Position(lon=10.06, lat=64.94)
    windows: list = []
    with _spy_on_window_construction(windows):
        dtm.profile_m(a, b, n_samples=16)
    assert len(windows) == 1
    assert windows[0].width * windows[0].height < (SIZE * SIZE) // 100  # well under 1% of the full raster


def test_windowed_values_match_a_full_array_reference(big_raster):
    """Independent correctness check: replicate the same bilinear math directly against the full
    in-memory array (no windowing at all) and confirm it agrees with DtmSampler's windowed result."""
    dtm = DtmSampler(path=big_raster)
    a = Position(lon=10.05, lat=64.95)
    b = Position(lon=10.06, lat=64.94)
    windowed = dtm.profile_m(a, b, n_samples=8)

    with rasterio.open(big_raster) as ds:
        full_band = ds.read(1).astype(np.float32)

    ax, ay = dtm._raster_xy([a])
    bx, by = dtm._raster_xy([b])
    t = np.linspace(0.0, 1.0, 8)
    xs = ax[0] + (bx[0] - ax[0]) * t
    ys = ay[0] + (by[0] - ay[0]) * t
    col = np.clip(dtm._inv_a * xs + dtm._inv_b * ys + dtm._inv_c, 0.0, dtm._width - 1.001)
    row = np.clip(dtm._inv_d * xs + dtm._inv_e * ys + dtm._inv_f, 0.0, dtm._height - 1.001)
    col0, row0 = np.floor(col).astype(np.int64), np.floor(row).astype(np.int64)
    col1, row1 = col0 + 1, row0 + 1
    fc, fr = col - col0, row - row0
    v00, v01 = full_band[row0, col0], full_band[row0, col1]
    v10, v11 = full_band[row1, col0], full_band[row1, col1]
    reference = (v00 * (1 - fc) * (1 - fr) + v01 * fc * (1 - fr) + v10 * (1 - fc) * fr + v11 * fc * fr).tolist()

    assert windowed == pytest.approx(reference)
