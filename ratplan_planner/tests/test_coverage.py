import numpy as np
import pytest

from ratplan_terrain.models.geometry import Position
from ratplan_planner.models.coverage import CoverageRaster, covered_from_margin


def _square_raster(covered: list[list[bool]]) -> CoverageRaster:
    return CoverageRaster(
        min_lat=59.0, max_lat=59.01, min_lon=18.0, max_lon=18.01, covered=np.array(covered, dtype=bool)
    )


def test_covers_true_inside_covered_cell():
    raster = _square_raster([[True, True], [True, True]])
    assert raster.covers(Position(lon=18.0, lat=59.0))


def test_covers_false_outside_extent():
    raster = _square_raster([[True, True], [True, True]])
    assert not raster.covers(Position(lon=19.0, lat=60.0))


def test_boundary_cells_only_covered_cells_adjacent_to_uncovered():
    # 3x3 grid, only the center cell is covered -> center is its own boundary cell
    covered = [[False, False, False], [False, True, False], [False, False, False]]
    raster = CoverageRaster(min_lat=59.0, max_lat=59.02, min_lon=18.0, max_lon=18.02, covered=np.array(covered))
    assert raster.boundary_cells() == {(1, 1)}


def test_eligible_near_boundary_of_irregular_shape():
    # An L-shaped covered region: eligibility should follow the real shape, not a circle.
    covered = [
        [True, True, True, True, True],
        [True, False, False, False, False],
        [True, False, False, False, False],
    ]
    raster = CoverageRaster(min_lat=59.0, max_lat=59.02, min_lon=18.0, max_lon=18.04, covered=np.array(covered))

    # The far tip of the "L"'s horizontal bar (min_lat, max_lon) is covered and is itself a boundary cell
    # (uncovered neighbors above and to the right) despite being far from the sender in straight-line terms.
    bar_tip = Position(lon=18.04, lat=59.0)
    assert raster.eligible(bar_tip, edge_tolerance_cells=0)

    # A cell in the L's uncovered notch is never eligible, however small the tolerance.
    uncovered_pos = Position(lon=18.03, lat=59.01)
    assert not raster.eligible(uncovered_pos, edge_tolerance_cells=5)


def test_or_unions_coverage_from_both_rasters():
    a = _square_raster([[True, False], [False, False]])
    b = CoverageRaster(
        min_lat=59.005, max_lat=59.015, min_lon=18.005, max_lon=18.015,
        covered=np.array([[True, True], [True, True]]),
    )
    merged = a | b
    assert merged.covers(Position(lon=18.0, lat=59.0))
    assert merged.covers(Position(lon=18.01, lat=59.01))


def test_covered_array_cast_to_bool():
    raster = CoverageRaster(
        min_lat=59.0, max_lat=59.01, min_lon=18.0, max_lon=18.01,
        covered=np.array([[1, 0], [0, 1]]),
    )
    assert raster.covered.dtype == bool


def test_mean_and_variance_default_to_zero_filled():
    raster = _square_raster([[True, False], [False, True]])
    assert raster.mean_db.shape == raster.covered.shape
    assert np.all(raster.mean_db == 0.0)
    assert np.all(raster.variance_db == 0.0)


def test_covered_from_margin_true_when_margin_nonnegative():
    mean_db = np.array([70.0, 130.0])  # tx=30, sensitivity=-100 -> max_loss=130
    variance_db = np.array([9.0, 9.0])
    covered = covered_from_margin(mean_db, variance_db, tx_power_dbm=30.0, rx_sensitivity_dbm=-100.0)
    assert covered.tolist() == [True, True]  # margin = 60 and 0 -> both >= 0
    assert not covered_from_margin(
        np.array([131.0]), np.array([9.0]), tx_power_dbm=30.0, rx_sensitivity_dbm=-100.0
    )[0]


def test_or_keeps_lower_mean_db_where_both_cover():
    a = CoverageRaster(
        min_lat=59.0, max_lat=59.01, min_lon=18.0, max_lon=18.01,
        covered=np.array([[True, True], [True, True]]),
        mean_db=np.array([[80.0, 80.0], [80.0, 80.0]]),
        variance_db=np.array([[4.0, 4.0], [4.0, 4.0]]),
    )
    b = CoverageRaster(
        min_lat=59.0, max_lat=59.01, min_lon=18.0, max_lon=18.01,
        covered=np.array([[True, True], [True, True]]),
        mean_db=np.array([[60.0, 60.0], [60.0, 60.0]]),  # better (lower) link estimate everywhere
        variance_db=np.array([[2.0, 2.0], [2.0, 2.0]]),
    )
    merged = a | b
    assert np.all(merged.mean_db == 60.0)
    assert np.all(merged.variance_db == 2.0)


def test_or_keeps_sole_coverer_values_where_only_one_covers():
    a = CoverageRaster(
        min_lat=59.0, max_lat=59.01, min_lon=18.0, max_lon=18.01,
        covered=np.array([[True, False], [False, False]]),
        mean_db=np.array([[42.0, 0.0], [0.0, 0.0]]),
        variance_db=np.array([[5.0, 0.0], [0.0, 0.0]]),
    )
    b = CoverageRaster(
        min_lat=59.0, max_lat=59.01, min_lon=18.0, max_lon=18.01,
        covered=np.array([[False, False], [False, False]]),
    )
    merged = a | b
    assert merged.mean_db[0, 0] == pytest.approx(42.0)
    assert merged.variance_db[0, 0] == pytest.approx(5.0)
