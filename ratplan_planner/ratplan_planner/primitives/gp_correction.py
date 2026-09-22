"""`GpCorrector` — the fixed-grid recursive Bayesian filter (model.md §3.1-§3.3) that folds live RSSI
observations into an `ItmGridScan`-produced physics prior, at a per-observation cost that stays flat no
matter how long the UGV has been driving.

**Why a fixed grid, not a plain growing GP.** A plain GP's exact posterior mean is a sum with one weighted
kernel term per *distinct observed input location* — `mu_n(x) = m(x) + sum_i alpha_i * k(x, x_i)` — so both
its size and the cost of updating it grow with the number of observations taken so far (a fresh
`O(n^3)` factorization per update in the naive case). That's fine for "tens of points once," not for a UGV
continuously reporting RSSI while driving. Instead, this commits to a *fixed* set of representation points
— the raster's own `N` cell centers — and tracks a Gaussian belief `(mu, Sigma)` over exactly those points,
forever. This is the standard Subset-of-Regressors / Deterministic-Training-Conditional sparse-GP
construction (Csató & Opper, "Sparse On-line Gaussian Processes," 2002; Quiñonero-Candela & Rasmussen 2005
is the standard unifying survey of this family — not yet in `research/reading_list.md`, worth adding), with
inducing points fixed at the raster grid instead of learned or moved.

**Cost profile.** One `O(N^3)` Cholesky factorization of the prior kernel matrix `K_uu`, done once at
construction (the same time `ItmGridScan` already pays its own per-cell ITM cost) and cached. Every
`.observe()` call after that is `O(N^2)` — two cached triangular solves plus a rank-1-style update of `mu`
and `Sigma` — independent of how many observations have already been folded in.

**Scoping.** Belongs to exactly one relay/target's own `CoverageRaster` — `Scan` is only ever called for
the target and for already-chosen relay-sender positions (never per raw candidate), and `CoverageRaster`s
are already private to one candidate path (`CLAUDE.md`), so one `GpCorrector` per raster is automatically
one independent GP per relay — `model.md` §3.4's stated default precedent, with no extra bookkeeping needed.

**Out of scope for this session**: nothing in this repo yet streams live RSSI at runtime. `GpCorrector` is
a reusable, tested component — not wired into a mission-execution loop, since none exists here yet (that's
`ratak-ai`'s territory, or a future mission-runner). The planning-time DP only ever needs `ItmGridScan`'s
pure prior output, per `CLAUDE.md`'s framing that every `Scan` result is theoretical until a UGV actually
drives there.
"""

from __future__ import annotations

import numpy as np
from scipy.linalg import cho_factor, cho_solve

from ratplan_terrain.models.geometry import Position
from ratplan_terrain.primitives.terrain import DtmSampler

from ratplan_planner.models.coverage import CoverageRaster, covered_from_margin
from ratplan_planner.primitives.features import GridFeatures, features_for_position, features_for_positions
from ratplan_planner.primitives.kernel import ArdKernel
from ratplan_planner.primitives.scan import RadioParams, physics_mean_db


def _cell_center_positions(raster: CoverageRaster) -> list[Position]:
    """Nominal cell centers per `CoverageRaster`'s own regular-lat/lon-grid contract (the same linear
    interpolation `CoverageRaster._cell_of` assumes), in the same row-major order as `raster.covered.ravel()`
    (row = latitude, outer loop; col = longitude, inner loop) — not necessarily bit-identical to whatever
    metric-CRS grid a particular `Scan` implementation actually sampled, but consistent with how every other
    `CoverageRaster` consumer already indexes it."""
    lats = np.linspace(raster.min_lat, raster.max_lat, raster.n_rows)
    lons = np.linspace(raster.min_lon, raster.max_lon, raster.n_cols)
    return [Position(lon=float(lon), lat=float(lat)) for lat in lats for lon in lons]


class GpCorrector:
    """Deliberately the one mutable, stateful object in this pipeline — it owns the `O(N^2)`-sized running
    covariance `Sigma`, which an immutable-dataclass snapshot-per-update would be far too expensive to copy
    on every incoming RSSI reading."""

    def __init__(
        self,
        prior: CoverageRaster,
        dtm: DtmSampler,
        sender: Position,
        radio: RadioParams,
        kernel: ArdKernel,
        n_profile_samples: int = 32,
    ) -> None:
        self._prior = prior
        self._dtm = dtm
        self._sender = sender
        self._radio = radio
        self._kernel = kernel
        self._n_profile_samples = n_profile_samples

        self._cell_positions = _cell_center_positions(prior)
        self._features: GridFeatures = features_for_positions(
            dtm, sender, self._cell_positions, radio.tx_height_m, radio.rx_height_m, n_profile_samples
        )

        k_uu = kernel.matrix(self._features)
        self._cho_factor = cho_factor(k_uu, lower=True)
        self._sigma = k_uu  # current joint covariance belief; starts at the (fixed) prior K_uu
        self._mu = np.zeros(len(self._cell_positions), dtype=np.float64)  # current residual-mean belief

    def observe(self, position: Position, rssi_dbm: float) -> None:
        """One closed-form Bayesian update — no raw observation history is kept; `(self._mu, self._sigma)`
        is both this update's posterior and the next update's prior."""
        m_obs_db = physics_mean_db(
            self._dtm, self._sender, position, self._radio, self._n_profile_samples
        )
        y = self._radio.tx_power_dbm - rssi_dbm - m_obs_db  # observed residual: path loss minus prior mean

        z_obs = features_for_position(
            self._dtm, self._sender, position, self._radio.tx_height_m, self._radio.rx_height_m, self._n_profile_samples
        )
        k_xu = self._kernel.cross(z_obs, self._features)  # (N,)
        w = cho_solve(self._cho_factor, k_xu)  # K_uu^-1 k_xu via the cached factor - O(N^2), not O(N^3)

        sigma_w = self._sigma @ w  # (N,)
        explained_var = float(w @ sigma_w)
        unexplained_var = self._kernel.self_variance() - float(k_xu @ w)
        innovation_var = explained_var + unexplained_var + self._kernel.sigma2

        gain = sigma_w / innovation_var
        residual_prediction = float(w @ self._mu)
        self._mu = self._mu + gain * (y - residual_prediction)
        self._sigma = self._sigma - np.outer(gain, sigma_w)

    def corrected_raster(self) -> CoverageRaster:
        """A pure snapshot — leaves the prior raster untouched. `mean_db`/`variance_db` are the posterior
        `mu*`/`sigma*^2` from model.md §3.1; `covered` is re-derived via the same link-margin threshold
        `ItmGridScan` uses."""
        prior = self._prior
        mean_db = prior.mean_db.ravel() + self._mu
        variance_db = np.diag(self._sigma).copy()
        covered = covered_from_margin(
            mean_db, variance_db, self._radio.tx_power_dbm, self._radio.rx_sensitivity_dbm
        )
        return CoverageRaster(
            min_lat=prior.min_lat,
            max_lat=prior.max_lat,
            min_lon=prior.min_lon,
            max_lon=prior.max_lon,
            covered=covered.reshape(prior.n_rows, prior.n_cols),
            mean_db=mean_db.reshape(prior.n_rows, prior.n_cols),
            variance_db=variance_db.reshape(prior.n_rows, prior.n_cols),
        )
