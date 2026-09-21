"""Bridges a sampled `DtmSampler` into each physics-prior implementation's own terrain input — the
integration contract OPEN_ISSUES.md flagged as not yet built. Deliberately kept out of `ITWOM/itm/` and
`ITWOM/itwom_client/` themselves (both stay DEM/GIS-free by design); this is where that real-terrain
plumbing lives instead.

Requires `ratplan_itm` (`ITWOM/itm/`) and `ratplan_itwom` (`ITWOM/itwom_client/`) installed alongside
`ratplan_terrain` in the same environment — see CLAUDE.md's setup section.
"""

from __future__ import annotations

from ratplan_itm import TerrainProfile
from ratplan_itwom import ElevationGrid

from ratplan_terrain.models.geometry import Position
from ratplan_terrain.primitives.terrain import DtmSampler


def terrain_profile_from_dtm(
    dtm: DtmSampler, tx: Position, rx: Position, n_samples: int = 32
) -> TerrainProfile:
    """A `ratplan_itm.TerrainProfile` sampled from real DTM data, transmitter end to receiver end."""
    return TerrainProfile(
        distance_km=tx.distance_m(rx) / 1000.0,
        elevations_m=dtm.profile_m(tx, rx, n_samples),
    )


def elevation_grid_from_dtm(
    dtm: DtmSampler,
    tx: Position,
    rx: Position,
    margin_frac: float = 0.2,
    n: int = 100,
) -> ElevationGrid:
    """A coarse `ratplan_itwom.ElevationGrid` covering the tx/rx bounding box plus a margin — not the
    full SPLAT!-native 1x1-degree tile. `write_sdf()` on the service side clamps out-of-grid lookups to
    this grid's own edges, so the grid only needs to cover the link itself, not the whole tile; a ~100x100
    grid over a realistic short relay-hop bbox gives far finer effective spacing than the tile-wide
    alternative would at the same point count."""
    min_lon, max_lon = sorted((tx.lon, rx.lon))
    min_lat, max_lat = sorted((tx.lat, rx.lat))

    lon_margin = max((max_lon - min_lon) * margin_frac, 0.002)
    lat_margin = max((max_lat - min_lat) * margin_frac, 0.002)
    min_lon, max_lon = min_lon - lon_margin, max_lon + lon_margin
    min_lat, max_lat = min_lat - lat_margin, max_lat + lat_margin

    grid = dtm.sample_grid(min_lat, max_lat, min_lon, max_lon, n_lat=n, n_lon=n)
    return ElevationGrid(
        min_lat=min_lat,
        max_lat=max_lat,
        min_lon_deg_east=min_lon,
        max_lon_deg_east=max_lon,
        values_m=grid.tolist(),
    )
