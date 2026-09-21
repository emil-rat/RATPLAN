import numpy as np
import pytest
from rasterio.io import MemoryFile
from rasterio.transform import from_origin

from ratplan_terrain.models.geometry import Position
from ratplan_terrain.primitives.terrain import DtmSampler


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
    # 10x10 grid in degrees (raster CRS = WGS84, so no reprojection distorts the math below),
    # north-west corner at lon=17.0, lat=60.0, 0.01deg pixels -- flat except a distinctive corner value
    # to prove bilinear sampling actually reads real cells, not just returning a constant.
    transform = from_origin(17.0, 60.0, 0.01, 0.01)
    band = np.full((10, 10), 100.0, dtype=np.float32)
    band[0, 0] = 500.0
    return DtmSampler(data=_geotiff_bytes(band, transform))


def test_elevation_m_at_grid_corner_matches_distinctive_value(flat_dtm):
    assert flat_dtm.elevation_m(Position(lon=17.0, lat=60.0)) == pytest.approx(500.0)


def test_elevation_m_away_from_corner_is_flat_value(flat_dtm):
    assert flat_dtm.elevation_m(Position(lon=17.05, lat=59.95)) == pytest.approx(100.0)


def test_out_of_bounds_clamps_to_edge_not_raises(flat_dtm):
    far = flat_dtm.elevation_m(Position(lon=50.0, lat=50.0))
    near_edge = flat_dtm.elevation_m(Position(lon=17.09, lat=59.91))
    assert far == pytest.approx(near_edge, abs=1.0)


def test_profile_m_returns_requested_sample_count(flat_dtm):
    profile = flat_dtm.profile_m(Position(lon=17.01, lat=59.99), Position(lon=17.08, lat=59.92), n_samples=16)
    assert len(profile) == 16
    assert all(v == pytest.approx(100.0) for v in profile)


def test_profiles_m_matches_profile_m_per_target(flat_dtm):
    source = Position(lon=17.01, lat=59.99)
    targets = [Position(lon=17.05, lat=59.95), Position(lon=17.08, lat=59.9)]
    batch = flat_dtm.profiles_m(source, targets, n_samples=8)
    for i, target in enumerate(targets):
        assert batch[i].tolist() == pytest.approx(flat_dtm.profile_m(source, target, n_samples=8))


def test_sample_grid_shape_and_flat_values(flat_dtm):
    grid = flat_dtm.sample_grid(min_lat=59.9, max_lat=59.99, min_lon=17.01, max_lon=17.08, n_lat=5, n_lon=7)
    assert grid.shape == (5, 7)
    assert np.allclose(grid, 100.0)
