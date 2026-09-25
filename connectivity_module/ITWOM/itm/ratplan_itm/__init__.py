"""RATPLAN's ITM module — a thin, swappable wrapper around itmlogic.

Scope: point-to-point path-loss prediction only (architecture.md §3). Takes
a terrain profile and link parameters, returns predicted path loss at
requested reliability/confidence quantiles. Does not do DEM/profile
extraction (that's ratmap's job) and does not do ITWOM (that runs as a
separate service per architecture.md §3.1/§4.2, not in this module).
"""

from .environment import Climate, GroundConstants, Polarization
from .profile import TerrainProfile
from .point_to_point import predict_point_to_point
from .results import PathLossEstimate, PointToPointResult

__all__ = [
    "Climate",
    "GroundConstants",
    "Polarization",
    "TerrainProfile",
    "predict_point_to_point",
    "PathLossEstimate",
    "PointToPointResult",
]
