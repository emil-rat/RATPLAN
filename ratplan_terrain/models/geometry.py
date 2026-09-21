"""WGS84 position type + conversion to ratmap's own working CRS (EPSG:3006).

Positions are canonically WGS84 lon/lat everywhere in ratplan_terrain — matching ratmap's API boundary CRS —
and converted to the metric working CRS only where metric math is actually needed (distance, coverage
radii). Matching ratmap's own working CRS (rather than picking an unrelated one) means data built from a
ratmap response doesn't need a second reprojection on top of ratmap's own.
"""

from __future__ import annotations

from dataclasses import dataclass

from pyproj import Transformer

WGS84_CRS = "EPSG:4326"
WORKING_CRS = "EPSG:3006"

_TO_WORKING = Transformer.from_crs(WGS84_CRS, WORKING_CRS, always_xy=True)
_TO_WGS84 = Transformer.from_crs(WORKING_CRS, WGS84_CRS, always_xy=True)


@dataclass(frozen=True)
class Position:
    """A WGS84 lon/lat point, rounded to ~0.1m precision so identical sample points generated
    independently compare equal and hash the same."""

    lon: float
    lat: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "lon", round(self.lon, 6))
        object.__setattr__(self, "lat", round(self.lat, 6))

    def to_working(self) -> tuple[float, float]:
        x, y = _TO_WORKING.transform(self.lon, self.lat)
        return (x, y)

    @staticmethod
    def from_working(x: float, y: float) -> "Position":
        lon, lat = _TO_WGS84.transform(x, y)
        return Position(lon=lon, lat=lat)

    def distance_m(self, other: "Position") -> float:
        ax, ay = self.to_working()
        bx, by = other.to_working()
        return ((ax - bx) ** 2 + (ay - by) ** 2) ** 0.5
