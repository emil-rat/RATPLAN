"""`CoverageRaster` — the concrete result of `Scan(position)` (model.md §2/§3), and the reachable-cell-
boundary eligibility filter re-derived 2026-09-22 (model.md §5) to replace the archived project's
isotropic-circle `near_edge` formula, which the OPEN_ISSUES.md carryover audit found doesn't hold for a
real DTM-LOS-shaped raster.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

import numpy as np

from ratplan_terrain.models.geometry import Position

_NEIGHBOR_OFFSETS = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]


def covered_from_margin(
    mean_db: np.ndarray, variance_db: np.ndarray, tx_power_dbm: float, rx_sensitivity_dbm: float
) -> np.ndarray:
    """The link-margin/Φ threshold (model.md §4): a cell is covered iff its predicted connectivity
    probability `Φ(margin/σ*)` is at least 50%, i.e. iff `margin >= 0` — margin being how much power
    budget is left after `mean_db`'s predicted path loss. Shared by `ItmGridScan` (physics-only prior,
    `variance_db` a flat kernel-prior constant) and `GpCorrector.corrected_raster()` (posterior mean/
    variance) so both derive `covered` the same way."""
    margin = tx_power_dbm - rx_sensitivity_dbm - mean_db
    sigma = np.sqrt(np.maximum(variance_db, 1e-12))
    return margin / sigma >= 0.0


@dataclass(frozen=True)
class CoverageRaster:
    """A regular lat/lon grid of covered/uncovered cells, sender-relative. `covered[row, col]` is True
    iff `Scan`'s underlying physics prior (± GP correction, model.md §3) predicts a usable link at that
    cell. `mean_db`/`variance_db` carry the continuous posterior mean path loss and residual variance per
    cell that `covered` is derived from (`covered_from_margin`) — `Evaluate`/`Samband`/`GpCorrector` read
    these directly; the DP's eligibility/BFS logic only ever reads `covered`. Grid resolution/extent are
    decided by whichever `Scan` implementation produced this raster — not fixed here. `row 0` is
    `min_lat`, `col 0` is `min_lon`.

    `mean_db`/`variance_db` default to zero-filled arrays when omitted, so code that only cares about
    boolean coverage (existing tests, callers that build a raster by hand) doesn't need to supply them."""

    min_lat: float
    max_lat: float
    min_lon: float
    max_lon: float
    covered: np.ndarray
    mean_db: np.ndarray | None = None
    variance_db: np.ndarray | None = None

    def __post_init__(self) -> None:
        if self.covered.dtype != bool:
            object.__setattr__(self, "covered", self.covered.astype(bool))
        if self.mean_db is None:
            object.__setattr__(self, "mean_db", np.zeros(self.covered.shape, dtype=np.float64))
        if self.variance_db is None:
            object.__setattr__(self, "variance_db", np.zeros(self.covered.shape, dtype=np.float64))

    @property
    def n_rows(self) -> int:
        return self.covered.shape[0]

    @property
    def n_cols(self) -> int:
        return self.covered.shape[1]

    def _lat_res(self) -> float:
        return (self.max_lat - self.min_lat) / max(self.n_rows - 1, 1)

    def _lon_res(self) -> float:
        return (self.max_lon - self.min_lon) / max(self.n_cols - 1, 1)

    def _cell_of(self, pos: Position) -> tuple[int, int] | None:
        if not (self.min_lat <= pos.lat <= self.max_lat and self.min_lon <= pos.lon <= self.max_lon):
            return None
        lat_span = self.max_lat - self.min_lat
        lon_span = self.max_lon - self.min_lon
        # round(), not int(): float subtraction can put an exact grid point at e.g. 0.999999999996
        # instead of 1.0, and truncating would silently pick the wrong cell.
        row = round((pos.lat - self.min_lat) / lat_span * (self.n_rows - 1)) if lat_span else 0
        col = round((pos.lon - self.min_lon) / lon_span * (self.n_cols - 1)) if lon_span else 0
        row = min(max(row, 0), self.n_rows - 1)
        col = min(max(col, 0), self.n_cols - 1)
        return row, col

    def covers(self, pos: Position) -> bool:
        """True iff `pos` falls inside the raster's extent and its cell is covered. A position outside
        the raster's extent is never covered — `Scan`'s extent is bounded by sender max range (model.md
        §2), so "outside the grid" and "uncovered" are the same fact, not missing data."""
        cell = self._cell_of(pos)
        return cell is not None and bool(self.covered[cell])

    def boundary_cells(self) -> set[tuple[int, int]]:
        """Covered cells with at least one 8-connected uncovered (or off-grid) neighbor — the raster's
        real, terrain-shaped edge."""
        boundary: set[tuple[int, int]] = set()
        for row in range(self.n_rows):
            for col in range(self.n_cols):
                if not self.covered[row, col]:
                    continue
                for dr, dc in _NEIGHBOR_OFFSETS:
                    nr, nc = row + dr, col + dc
                    if not (0 <= nr < self.n_rows and 0 <= nc < self.n_cols) or not self.covered[nr, nc]:
                        boundary.add((row, col))
                        break
        return boundary

    def cell_steps_to_boundary(self, pos: Position) -> int | None:
        """BFS distance, in raster cells, from `pos`'s cell to the nearest boundary cell — over covered
        cells only. None if `pos` isn't covered, or the raster has no boundary (fully covered/uncovered)."""
        start = self._cell_of(pos)
        if start is None or not self.covered[start]:
            return None
        boundary = self.boundary_cells()
        if not boundary:
            return None
        if start in boundary:
            return 0

        visited = {start}
        frontier = deque([(start, 0)])
        while frontier:
            (row, col), steps = frontier.popleft()
            for dr, dc in _NEIGHBOR_OFFSETS:
                nr, nc = row + dr, col + dc
                nxt = (nr, nc)
                if not (0 <= nr < self.n_rows and 0 <= nc < self.n_cols):
                    continue
                if not self.covered[nxt] or nxt in visited:
                    continue
                if nxt in boundary:
                    return steps + 1
                visited.add(nxt)
                frontier.append((nxt, steps + 1))
        return None

    def eligible(self, pos: Position, edge_tolerance_cells: int) -> bool:
        """Hard eligibility filter (model.md §5): `pos` is eligible to extend a relay chain behind this
        raster's sender iff it's covered and within `edge_tolerance_cells` raster-graph steps of the
        raster's real boundary — not a fraction of a theoretical max range."""
        steps = self.cell_steps_to_boundary(pos)
        return steps is not None and steps <= edge_tolerance_cells

    def __or__(self, other: "CoverageRaster") -> "CoverageRaster":
        """Union of two rasters' coverage, re-gridded onto the tighter of the two resolutions over their
        combined extent (nearest-cell lookup into each source, not interpolation). Used to fold a
        newly-placed relay's `Scan` into a path's running `covered_raster` (model.md §5's recurrence) —
        never to pool coverage across different candidate paths.

        For a cell covered by both sources, keeps the lower `mean_db` (the better of the two link
        estimates) and its matching `variance_db`; a cell covered by only one source keeps that source's
        values. A cell covered by neither keeps zero-filled continuous fields — never read downstream,
        since only `covered` drives the DP's eligibility/BFS logic."""
        min_lat, max_lat = min(self.min_lat, other.min_lat), max(self.max_lat, other.max_lat)
        min_lon, max_lon = min(self.min_lon, other.min_lon), max(self.max_lon, other.max_lon)
        lat_res = min(self._lat_res(), other._lat_res()) or 1.0
        lon_res = min(self._lon_res(), other._lon_res()) or 1.0
        n_rows = max(int(round((max_lat - min_lat) / lat_res)) + 1, 1)
        n_cols = max(int(round((max_lon - min_lon) / lon_res)) + 1, 1)

        merged_covered = np.zeros((n_rows, n_cols), dtype=bool)
        merged_mean = np.zeros((n_rows, n_cols), dtype=np.float64)
        merged_variance = np.zeros((n_rows, n_cols), dtype=np.float64)
        for row in range(n_rows):
            lat = min_lat + row / max(n_rows - 1, 1) * (max_lat - min_lat)
            for col in range(n_cols):
                lon = min_lon + col / max(n_cols - 1, 1) * (max_lon - min_lon)
                pos = Position(lon=lon, lat=lat)

                self_cell = self._cell_of(pos)
                self_covered = self_cell is not None and bool(self.covered[self_cell])
                other_cell = other._cell_of(pos)
                other_covered = other_cell is not None and bool(other.covered[other_cell])

                merged_covered[row, col] = self_covered or other_covered
                if self_covered and other_covered:
                    use_self = self.mean_db[self_cell] <= other.mean_db[other_cell]
                    src, cell = (self, self_cell) if use_self else (other, other_cell)
                elif self_covered:
                    src, cell = self, self_cell
                elif other_covered:
                    src, cell = other, other_cell
                else:
                    src, cell = None, None
                if src is not None:
                    merged_mean[row, col] = src.mean_db[cell]
                    merged_variance[row, col] = src.variance_db[cell]
        return CoverageRaster(min_lat, max_lat, min_lon, max_lon, merged_covered, merged_mean, merged_variance)
