"""Point-to-point ITM prediction.

The orchestration below is adapted from itmlogic's own upstream example,
scripts/p2p.py (itmlogic_p2p(), MIT-licensed, github.com/edwardoughton/
itmlogic) — that function is example glue code in the itmlogic repo, not
part of the installed itmlogic package (see OPEN_ISSUES.md), so it can't
just be imported. What's unmodified and load-bearing here is itmlogic's
own public subroutines: qerfi, qlrpfl, avar. Everything this function does
is orchestration (building the `prop` dict, calling those subroutines in
the documented order, reshaping the result) — no propagation-model math
has been reimplemented or altered.
"""

import math
from typing import Sequence

import numpy as np
from itmlogic.misc.qerfi import qerfi
from itmlogic.preparatory_subroutines.qlrpfl import qlrpfl
from itmlogic.statistics.avar import avar

from .environment import Climate, GroundConstants, Polarization
from .profile import TerrainProfile
from .results import PathLossEstimate, PointToPointResult

_DB_PER_NEPER = 8.685890

_DEFAULT_RELIABILITY_PCT: Sequence[float] = (1, 10, 50, 90, 99)
_DEFAULT_CONFIDENCE_PCT: Sequence[float] = (50, 90, 10)


def predict_point_to_point(
    profile: TerrainProfile,
    tx_height_m: float,
    rx_height_m: float,
    frequency_mhz: float,
    *,
    ground: GroundConstants = GroundConstants(),
    climate: Climate = Climate.CONTINENTAL_TEMPERATE,
    surface_refractivity_n_units: float = 314.0,
    polarization: Polarization = Polarization.HORIZONTAL,
    reliability_pct: Sequence[float] = _DEFAULT_RELIABILITY_PCT,
    confidence_pct: Sequence[float] = _DEFAULT_CONFIDENCE_PCT,
) -> PointToPointResult:
    """Predict point-to-point path loss over a terrain profile using ITM.

    Parameters
    ----------
    profile : the terrain elevation profile between transmitter and
        receiver (see TerrainProfile).
    tx_height_m, rx_height_m : antenna heights above ground, in metres.
    frequency_mhz : operating frequency in MHz.
    ground : terrain electrical constants (relative permittivity,
        conductivity). Defaults are itmlogic's own example values, not
        calibrated for any specific terrain — see OPEN_ISSUES.md.
    climate : ITM climate code. Default continental temperate.
    surface_refractivity_n_units : surface refractivity in N-units.
    polarization : horizontal or vertical.
    reliability_pct, confidence_pct : quantiles to evaluate. Output
        contains one PathLossEstimate per (reliability, confidence) pair.

    Returns
    -------
    PointToPointResult
    """
    prop: dict = {
        "fmhz": frequency_mhz,
        "d": profile.distance_km,
        "hg": [tx_height_m, rx_height_m],
        "ipol": int(polarization),
        "eps": ground.relative_permittivity,
        "sgm": ground.conductivity_s_per_m,
        "klim": int(climate),
        "ens0": surface_refractivity_n_units,
        "lvar": 5,
        "gma": 157e-9,
        "klimx": 0,
        "mdvarx": 11,
    }

    elevations = list(profile.elevations_m)
    pfl = [len(elevations) - 1, 0.0] + elevations

    dkm = prop["d"]
    xkm = dkm // pfl[0]
    pfl[1] = dkm * 1000 / pfl[0]

    prop["pfl"] = pfl
    prop["kwx"] = 0
    prop["wn"] = prop["fmhz"] / 47.7
    prop["ens"] = prop["ens0"]
    prop["gme"] = prop["gma"] * (1 - 0.04665 * math.exp(prop["ens"] / 179.3))

    zq = complex(prop["eps"], 376.62 * prop["sgm"] / prop["wn"])
    zgnd = np.sqrt(zq - 1)
    if prop["ipol"] != 0:
        zgnd = zgnd / zq
    prop["zgnd"] = zgnd

    zr = qerfi([x / 100 for x in reliability_pct])
    zc = qerfi([x / 100 for x in confidence_pct])

    prop = qlrpfl(prop)

    free_space_loss_db = _DB_PER_NEPER * np.log(2 * prop["wn"] * prop["dist"])

    estimates = []
    for jr, rel in enumerate(reliability_pct):
        for jc, conf in enumerate(confidence_pct):
            avar1, prop = avar(zr[jr], 0, zc[jc], prop)
            estimates.append(
                PathLossEstimate(
                    reliability_pct=rel,
                    confidence_pct=conf,
                    loss_db=float(free_space_loss_db + avar1),
                )
            )

    return PointToPointResult(
        free_space_loss_db=float(free_space_loss_db),
        estimates=estimates,
    )
