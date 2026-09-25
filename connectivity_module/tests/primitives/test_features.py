"""Tests for features.py's augmented feature-vector extraction, against synthetic in-memory DTMs (offline,
no live ratmap needed - same construction pattern as RATPLAN/tests/primitives/test_terrain.py's flat_dtm).
"""

import math

import numpy as np
import pytest
from rasterio.io import MemoryFile
from rasterio.transform import from_origin

from ratplan_terrain.models.geometry import Position
from ratplan_terrain.primitives.terrain import DtmSampler

from ratplan_connectivity.primitives.features import FEATURE_NAMES, N_FEATURES, features_for_position, features_for_positions


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
    transform = from_origin(17.0, 60.0, 0.001, 0.001)
    band = np.full((200, 200), 100.0, dtype=np.float32)
    return DtmSampler(data=_geotiff_bytes(band, transform))


@pytest.fixture
def ridge_dtm() -> DtmSampler:
    # Flat except a wide ridge (columns 90-110, ~1.1km at this latitude) between the two test endpoints,
    # tall enough to obstruct a low-antenna line-of-sight link regardless of exactly which columns the
    # profile's evenly-spaced samples happen to land on.
    transform = from_origin(17.0, 60.0, 0.001, 0.001)
    band = np.full((200, 200), 100.0, dtype=np.float32)
    band[:, 90:110] = 300.0
    return DtmSampler(data=_geotiff_bytes(band, transform))


def test_feature_names_and_count():
    assert len(FEATURE_NAMES) == N_FEATURES == 7


def test_empty_batch_returns_empty_matrix(flat_dtm):
    features = features_for_positions(flat_dtm, Position(lon=17.05, lat=59.95), [], tx_height_m=2.0, rx_height_m=2.0)
    assert features.values.shape == (0, N_FEATURES)


def test_position_features_match_working_crs_offset_and_elevation(flat_dtm):
    sender = Position(lon=17.05, lat=59.95)
    east = Position(lon=17.06, lat=59.95)  # due east of sender, same latitude
    sender_x, sender_y = sender.to_working()
    features = features_for_positions(flat_dtm, sender, [east], tx_height_m=2.0, rx_height_m=2.0)
    x, y, elevation, distance, sin_b, cos_b, _los = features.values[0]
    assert x > sender_x  # moved east -> larger working-CRS easting than the sender's own
    assert y == pytest.approx(sender_y, abs=50.0)  # ~no north/south movement
    assert elevation == pytest.approx(100.0)
    assert distance == pytest.approx(math.hypot(x - sender_x, y - sender_y))
    assert sin_b == pytest.approx(1.0, abs=0.05)  # due east -> bearing 90 deg -> sin=1, cos=0
    assert cos_b == pytest.approx(0.0, abs=0.05)


def test_distance_m_zero_at_sender_and_grows_with_range(flat_dtm):
    sender = Position(lon=17.05, lat=59.95)
    near = Position(lon=17.051, lat=59.95)
    far = Position(lon=17.06, lat=59.95)
    features = features_for_positions(flat_dtm, sender, [sender, near, far], tx_height_m=2.0, rx_height_m=2.0)
    dist_sender, dist_near, dist_far = features.values[:, 3]
    assert dist_sender == pytest.approx(0.0, abs=1e-6)
    assert 0.0 < dist_near < dist_far


def test_bearing_defaults_at_zero_distance(flat_dtm):
    sender = Position(lon=17.05, lat=59.95)
    features = features_for_positions(flat_dtm, sender, [sender], tx_height_m=2.0, rx_height_m=2.0)
    assert features.values[0][4] == pytest.approx(0.0)
    assert features.values[0][5] == pytest.approx(1.0)


def test_bearing_periodic_embedding_keeps_near_north_points_close(flat_dtm):
    sender = Position(lon=17.05, lat=59.95)
    near_north_east = Position(lon=17.055, lat=59.96)  # bearing a few degrees east of due north
    near_north_west = Position(lon=17.045, lat=59.96)  # bearing a few degrees west of due north
    due_south = Position(lon=17.05, lat=59.94)
    features = features_for_positions(
        flat_dtm, sender, [near_north_east, near_north_west, due_south], tx_height_m=2.0, rx_height_m=2.0
    )
    nne, nnw, south = features.values[0, 4:6], features.values[1, 4:6], features.values[2, 4:6]
    close_dist = np.linalg.norm(nne - nnw)
    far_dist = np.linalg.norm(nne - south)
    # A raw-angle feature would see near_north_east/near_north_west as ~360 degrees apart (straddling the
    # 0/360 wraparound); the sin/cos embedding correctly shows them as close, and both far from due south.
    assert close_dist < far_dist


def test_los_obstruction_count_zero_over_flat_terrain(flat_dtm):
    sender = Position(lon=17.0, lat=59.95)
    target = Position(lon=17.19, lat=59.95)
    features = features_for_position(flat_dtm, sender, target, tx_height_m=10.0, rx_height_m=10.0)
    assert features[6] == 0.0


def test_los_obstruction_count_positive_when_ridge_blocks_low_antennas(ridge_dtm):
    sender = Position(lon=17.0, lat=59.95)
    target = Position(lon=17.19, lat=59.95)
    features = features_for_position(
        ridge_dtm, sender, target, tx_height_m=1.0, rx_height_m=1.0, n_profile_samples=64
    )
    assert features[6] > 0
