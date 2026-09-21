"""Offline end-to-end check: real DTM (a ratmap snapshot's height.tif, no server needed) -> real
elevation profile -> real ITM path loss. Skipped if the sibling ratmap snapshot isn't present locally
(it's ratmap's own downloaded data, not part of this repo)."""

from pathlib import Path

import pytest

from ratplan_terrain.models.geometry import Position
from ratplan_terrain.primitives.terrain import DtmSampler
from ratplan_terrain.primitives.terrain_profile import terrain_profile_from_dtm

SNAPSHOT_HEIGHT_TIF = (
    Path(__file__).resolve().parents[2].parent / "ratmap" / "snapshots" / "real_map_scenario_north" / "data" / "height.tif"
)

pytestmark = pytest.mark.skipif(
    not SNAPSHOT_HEIGHT_TIF.exists(), reason=f"no ratmap snapshot found at {SNAPSHOT_HEIGHT_TIF}"
)

TX = Position(lon=17.654258, lat=59.556343)
RX = Position(lon=17.690677, lat=59.569076)


def test_terrain_profile_from_real_dtm_feeds_itm():
    from ratplan_itm import predict_point_to_point

    dtm = DtmSampler(path=SNAPSHOT_HEIGHT_TIF)
    profile = terrain_profile_from_dtm(dtm, TX, RX, n_samples=32)

    assert profile.distance_km == pytest.approx(2.5, abs=0.5)
    assert len(profile.elevations_m) == 32
    assert all(0.0 < e < 500.0 for e in profile.elevations_m)  # sane Swedish terrain range

    result = predict_point_to_point(profile, tx_height_m=10.0, rx_height_m=2.0, frequency_mhz=433.0)
    assert result.free_space_loss_db > 0
    # Real terrain over a few km should lose noticeably more than pure free space.
    assert result.loss_db(reliability_pct=50, confidence_pct=50) > result.free_space_loss_db
