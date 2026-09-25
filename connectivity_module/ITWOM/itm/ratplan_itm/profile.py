"""Terrain profile input contract for point-to-point prediction.

Deliberately decoupled from DEM/GIS extraction (no fiona/pyproj/rasterio
here) — producing a TerrainProfile from ratmap's DEM data is a separate
concern, out of scope for this module. See OPEN_ISSUES.md.
"""

from dataclasses import dataclass
from typing import Sequence


@dataclass(frozen=True)
class TerrainProfile:
    """Evenly spaced elevation samples along the straight line from
    transmitter to receiver.

    Attributes
    ----------
    distance_km : total straight-line distance between transmitter and
        receiver, in kilometres.
    elevations_m : elevation samples in metres, evenly spaced from the
        transmitter end to the receiver end (inclusive of both endpoints).
        Must contain at least 2 points.
    """

    distance_km: float
    elevations_m: Sequence[float]

    def __post_init__(self) -> None:
        if self.distance_km <= 0:
            raise ValueError("distance_km must be positive")
        if len(self.elevations_m) < 2:
            raise ValueError("elevations_m must contain at least 2 points")
