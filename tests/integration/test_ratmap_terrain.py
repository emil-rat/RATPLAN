"""Confirms the live-ratmap-API path of ratplan_terrain's real-terrain plumbing end to end: fetch a DTM clip
from a running ratmap, sample it, feed ITM. Needs a locally running ratmap
(`.venv/Scripts/uvicorn ratmap.main:app --workers 1 --reload`, see ../../ratmap/README.md) with height
data covering `TEST_BBOX` — pick a bbox that actually has data in your local `ratmap/data/height/` before
trusting this to mean anything (its `index.json` lists what's covered).
"""

from __future__ import annotations

import pytest

from ratplan_itm import predict_point_to_point
from ratplan_terrain.io.dtm_loader import load_dtm
from ratplan_terrain.models.geometry import Position
from ratplan_terrain.primitives.terrain_profile import terrain_profile_from_dtm

pytestmark = pytest.mark.integration

RATMAP_BASE_URL = "http://127.0.0.1:8000"
TEST_BBOX = (17.84, 59.24, 17.88, 59.28)
TX = Position(lon=17.85, lat=59.25)
RX = Position(lon=17.86, lat=59.26)


def test_live_dtm_fetch_feeds_itm():
    dtm = load_dtm(TEST_BBOX, ratmap_url=RATMAP_BASE_URL)
    profile = terrain_profile_from_dtm(dtm, TX, RX, n_samples=32)

    assert profile.distance_km > 0
    assert len(profile.elevations_m) == 32

    result = predict_point_to_point(profile, tx_height_m=10.0, rx_height_m=2.0, frequency_mhz=433.0)
    assert result.free_space_loss_db > 0
