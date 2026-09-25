from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Site:
    """A transmitter or receiver location.

    lon_deg_east follows the usual convention (positive = east of
    Greenwich) — the client converts to SPLAT!'s own west-positive
    convention internally; callers never need to think about it.
    """

    lat: float
    lon_deg_east: float
    height_m: float


@dataclass(frozen=True)
class GroundConstants:
    relative_permittivity: float = 15.0
    conductivity_s_per_m: float = 0.005


@dataclass(frozen=True)
class ElevationGrid:
    """Real terrain fed to the service — a coarse regular grid of elevations over a WGS84 bbox, sampled
    from ratmap's DTM (see ratplan_terrain.primitives.terrain_profile.elevation_grid_from_dtm). The service
    bilinear-interpolates into this grid to fill its own SPLAT!-native terrain tile, clamping lookups
    outside the grid to its own edges — the grid only needs to cover the link itself, not a whole
    1x1-degree tile.

    values_m: row = ascending latitude, col = ascending longitude, shape (n_lat, n_lon).
    """

    min_lat: float
    max_lat: float
    min_lon_deg_east: float
    max_lon_deg_east: float
    values_m: list[list[float]]


@dataclass(frozen=True)
class ItwomResult:
    model: str  # "ITWOM Version 3.0" or "Longley-Rice"
    path_loss_db: float
    free_space_loss_db: Optional[float]
