"""`ItmGridScan` — the physics-prior `Scan` implementation (model.md §2/§3.1's `m(x)`): grid-samples
`ratplan_itm`'s ITM/Longley-Rice prediction around a sender out to its own link-budget-derived max range.

Always pure physics, never touches observations or GP state — Emil, 2026-09-22: "Scan will always be the
ITWOM/ITM prior distribution. Should never care about the update." See `gp_correction.py` for the Bayesian
correction layer that consumes this raster's output separately.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
from ratplan_itm import Climate, GroundConstants, Polarization, TerrainProfile, predict_point_to_point

from ratplan_terrain.models.geometry import Position
from ratplan_terrain.primitives.terrain import DtmSampler
from ratplan_terrain.primitives.terrain_profile import terrain_profile_from_dtm

from ratplan_planner.models.coverage import CoverageRaster, covered_from_margin
from ratplan_planner.primitives.kernel import ArdKernel

_FREE_SPACE_CONST_DB = 32.44  # FSPL(d_km, f_mhz) = 20*log10(d_km) + 20*log10(f_mhz) + 32.44
_RELIABILITY_PCT = 90.0  # Emil's choice: a conservative point estimate, not the median case
_CONFIDENCE_PCT = 50.0


@dataclass(frozen=True)
class RadioParams:
    """Råttan relay radio link-budget constants. Placeholders (typical low-power UHF/ISM relay figures) —
    not from a real spec sheet yet, overridable once real numbers are available, in the same spirit as
    `ratplan_itm.GroundConstants`'s own uncalibrated defaults (OPEN_ISSUES.md)."""

    tx_power_dbm: float = 30.0
    rx_sensitivity_dbm: float = -100.0
    tx_height_m: float = 2.0
    rx_height_m: float = 2.0
    frequency_mhz: float = 433.0
    ground: GroundConstants = field(default_factory=GroundConstants)
    climate: Climate = Climate.CONTINENTAL_TEMPERATE
    polarization: Polarization = Polarization.HORIZONTAL

    @property
    def max_loss_db(self) -> float:
        return self.tx_power_dbm - self.rx_sensitivity_dbm

    def max_range_m(self) -> float:
        """Closed-form free-space max range implied by the link budget. `ItmGridScan` uses this as one
        input to its grid extent (capped by `max_extent_m` — see its docstring for why free-space range
        alone badly overestimates real range at low antenna height on real terrain)."""
        max_range_km = 10 ** (
            (self.max_loss_db - 20 * math.log10(self.frequency_mhz) - _FREE_SPACE_CONST_DB) / 20
        )
        return max_range_km * 1000.0


@dataclass(frozen=True)
class ItmGridScan:
    """`Scan(position) -> CoverageRaster` via ITM grid-sampling.

    **Extent is capped, resolution is fixed — not the other way around.** An earlier version derived a
    *cell count* from the link budget's closed-form free-space range, holding resolution to whatever that
    implied. Measured against real terrain this was badly wrong: at a 2m antenna height, real ITM path loss
    over this terrain already exceeds a typical link budget within several hundred meters to ~1km, while the
    free-space formula alone suggested tens of km — a >10x overestimate driven by real terrain/ground-effect
    loss at low antenna height, not a bug (this is the exact "ITWOM/ITM alone isn't good enough for our
    terrain and scale" problem `Goal.md` motivates the GP correction layer with). Sizing a *fixed cell count*
    grid off that overestimate wastes almost the whole grid on cells far past any real coverage boundary,
    at a resolution too coarse to ever land near where the boundary actually is.

    So instead: `target_cell_size_m` is a fixed resolution target, and grid extent is
    `min(radio.max_range_m(), max_extent_m)` — the link budget still shrinks the grid for a genuinely
    short-range radio, but `max_extent_m` stops an optimistic free-space number from blowing up the cell
    count for a realistic one. Cell count is derived from extent/resolution, not fixed. Defaults are
    placeholders for a short tactical relay hop (`CLAUDE.md`) — not yet validated for the DP's actual
    per-relay-level performance budget (`architecture.md` §9); see the plan's Verification section."""

    dtm: DtmSampler
    radio: RadioParams = field(default_factory=RadioParams)
    kernel: ArdKernel = field(default_factory=ArdKernel)
    target_cell_size_m: float = 25.0
    max_extent_m: float = 1500.0
    n_profile_samples: int = 32

    def __call__(self, position: Position) -> CoverageRaster:
        extent_m = min(self.radio.max_range_m(), self.max_extent_m)
        n = max(2, math.ceil(2 * extent_m / self.target_cell_size_m))
        sx, sy = position.to_working()
        offsets = np.linspace(-extent_m, extent_m, n)
        grid_x, grid_y = np.meshgrid(sx + offsets, sy + offsets)
        flat_x, flat_y = grid_x.ravel(), grid_y.ravel()
        cell_positions = [Position.from_working(x, y) for x, y in zip(flat_x, flat_y)]
        distances_km = np.hypot(flat_x - sx, flat_y - sy) / 1000.0

        profiles = self.dtm.profiles_m(position, cell_positions, self.n_profile_samples)

        mean_db = np.empty(len(cell_positions), dtype=np.float64)
        for i, distance_km in enumerate(distances_km):
            if distance_km <= 0:
                # The sender's own cell (only reachable if n is odd) - trivially the best possible link,
                # not a valid TerrainProfile input (requires distance_km > 0).
                mean_db[i] = 0.0
                continue
            profile = TerrainProfile(distance_km=float(distance_km), elevations_m=profiles[i].tolist())
            result = predict_point_to_point(
                profile,
                self.radio.tx_height_m,
                self.radio.rx_height_m,
                self.radio.frequency_mhz,
                ground=self.radio.ground,
                climate=self.radio.climate,
                polarization=self.radio.polarization,
                reliability_pct=(_RELIABILITY_PCT,),
                confidence_pct=(_CONFIDENCE_PCT,),
            )
            mean_db[i] = result.loss_db(_RELIABILITY_PCT, _CONFIDENCE_PCT)

        variance_db = np.full(len(cell_positions), self.kernel.self_variance(), dtype=np.float64)
        covered = covered_from_margin(
            mean_db, variance_db, self.radio.tx_power_dbm, self.radio.rx_sensitivity_dbm
        )

        lats = np.array([p.lat for p in cell_positions])
        lons = np.array([p.lon for p in cell_positions])
        return CoverageRaster(
            min_lat=float(lats.min()),
            max_lat=float(lats.max()),
            min_lon=float(lons.min()),
            max_lon=float(lons.max()),
            covered=covered.reshape(n, n),
            mean_db=mean_db.reshape(n, n),
            variance_db=variance_db.reshape(n, n),
        )


def physics_mean_db(
    dtm: DtmSampler, sender: Position, position: Position, radio: RadioParams, n_profile_samples: int = 32
) -> float:
    """A single fresh ITM call for one position — used by `GpCorrector.observe()`, where one point doesn't
    warrant `ItmGridScan`'s batched-grid machinery."""
    distance_km = sender.distance_m(position) / 1000.0
    if distance_km <= 0:
        return 0.0
    profile = terrain_profile_from_dtm(dtm, sender, position, n_profile_samples)
    result = predict_point_to_point(
        profile,
        radio.tx_height_m,
        radio.rx_height_m,
        radio.frequency_mhz,
        ground=radio.ground,
        climate=radio.climate,
        polarization=radio.polarization,
        reliability_pct=(_RELIABILITY_PCT,),
        confidence_pct=(_CONFIDENCE_PCT,),
    )
    return result.loss_db(_RELIABILITY_PCT, _CONFIDENCE_PCT)
