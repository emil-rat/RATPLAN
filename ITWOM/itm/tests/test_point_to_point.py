"""Regression test against itmlogic's own documented example.

The transmitter/receiver pair, frequency, antenna heights and 152-point
surface profile below are itmlogic's own worked example (scripts/p2p.py,
upstream) — Crystal Palace radio transmitter to Mursley, 41.5 MHz, 77.8 km.
Expected values are what ratplan_itm.predict_point_to_point currently
produces against that input, captured as a regression baseline.

This validates that our wrapper is wired correctly against itmlogic's own
subroutines. It is NOT independent validation against NTIA's reference ITM
implementation — see OPEN_ISSUES.md.
"""

import pytest

from ratplan_itm import GroundConstants, TerrainProfile, predict_point_to_point

SURFACE_PROFILE_M = [
    96, 84, 65, 46, 46, 46, 61, 41, 33, 27, 23, 19, 15, 15, 15,
    15, 15, 15, 15, 15, 15, 15, 15, 15, 17, 19, 21, 23, 25, 27,
    29, 35, 46, 41, 35, 30, 33, 35, 37, 40, 35, 30, 51, 62, 76,
    46, 46, 46, 46, 46, 46, 50, 56, 67, 106, 83, 95, 112, 137, 137,
    76, 103, 122, 122, 83, 71, 61, 64, 67, 71, 74, 77, 79, 86, 91,
    83, 76, 68, 63, 76, 107, 107, 107, 119, 127, 133, 135, 137, 142, 148,
    152, 152, 107, 137, 104, 91, 99, 120, 152, 152, 137, 168, 168, 122, 137,
    137, 170, 183, 183, 187, 194, 201, 192, 152, 152, 166, 177, 198, 156, 127,
    116, 107, 104, 101, 98, 95, 103, 91, 97, 102, 107, 107, 107, 103, 98,
    94, 91, 105, 122, 122, 122, 122, 122, 137, 137, 137, 137, 137, 137, 137,
    137, 140, 144, 147, 150, 152, 159,
]


def test_crystal_palace_to_mursley_matches_itmlogic_example():
    profile = TerrainProfile(distance_km=77.8, elevations_m=SURFACE_PROFILE_M)

    result = predict_point_to_point(
        profile,
        tx_height_m=143.9,
        rx_height_m=8.5,
        frequency_mhz=41.5,
        ground=GroundConstants(relative_permittivity=15.0, conductivity_s_per_m=0.005),
    )

    assert result.free_space_loss_db == pytest.approx(102.63, abs=0.01)
    assert result.loss_db(reliability_pct=50, confidence_pct=50) == pytest.approx(
        135.76, abs=0.01
    )
    assert result.loss_db(reliability_pct=1, confidence_pct=50) == pytest.approx(
        128.60, abs=0.01
    )
    assert result.loss_db(reliability_pct=99, confidence_pct=90) == pytest.approx(
        148.44, abs=0.01
    )


def test_rejects_degenerate_profile():
    with pytest.raises(ValueError):
        TerrainProfile(distance_km=1.0, elevations_m=[10.0])
