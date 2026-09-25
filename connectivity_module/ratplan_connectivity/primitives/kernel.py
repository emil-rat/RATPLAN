"""`ArdKernel` — the covariance function for the GP residual (model.md §3.1's `k(x, x')`), extended per
§3.5 option 3 to correlate on the augmented feature vector from `features.py` instead of raw position
alone.

    k(z_i, z_j) = alpha * exp( -sum_d |z_i,d - z_j,d| / l_d )

A product of one 1-D exponential (Matérn-1/2) kernel per feature dimension — matches Gudmundson's
isotropic exponential shadowing-correlation term (model.md §2) when only the position dimensions are used,
and stays positive-definite once more dimensions are added (a product of PD kernels is PD). Dimensions are
grouped where they share one physical meaning rather than each getting an independent lengthscale: `x_m`
and `y_m` share `lengthscale_position` (no basis yet for anisotropic-in-plane behavior), `bearing_sin` and
`bearing_cos` share `lengthscale_bearing` (they're one angular quantity, not two independent ones).
`distance_m` (range from the sender) gets its own `lengthscale_distance` rather than sharing
`lengthscale_position` — it's a derived, sender-relative radial coordinate, not another absolute-position
axis, so there's no reason to assume the same decorrelation scale applies.

**Read this before changing the lengthscale defaults.** Because the feature distances are *summed* inside
the exponent (not the kernel values multiplied *after* separately deciding relevance), two cells that are
far apart in raw position still get a small kernel value even if every other feature matches exactly —
unless `lengthscale_position` is set *longer* than the physical shadowing decorrelation distance a plain
Gudmundson kernel would use. That's what actually makes "similar, not just close" happen: a longer position
lengthscale turns raw distance into a soft envelope, letting elevation/bearing/LOS similarity do the
discriminating work within it. Setting `lengthscale_position` equal to (or shorter than) the physical `β`
collapses this kernel back to being effectively isotropic, no matter how tight the other lengthscales are.

All parameters below are placeholder, overridable constants — no Nordic-forest field measurement of the
shadowing decorrelation distance exists yet (model.md §3.6), so these are illustrative magnitudes, not
calibrated values, in the same spirit as `ratplan_itm.GroundConstants`'/`Climate`'s own uncalibrated
defaults.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ratplan_connectivity.primitives.features import GridFeatures


@dataclass(frozen=True)
class ArdKernel:
    alpha: float = 36.0  # prior residual variance, dB^2 (~6 dB shadowing std - placeholder)
    sigma2: float = 4.0  # measurement noise variance, dB^2 (~2 dB RSSI noise std - placeholder)
    lengthscale_position: float = 150.0  # meters - deliberately longer than the ~50m placeholder beta
    lengthscale_elevation: float = 20.0  # meters
    lengthscale_distance: float = 150.0  # meters - range-from-sender band width, same order as position
    lengthscale_bearing: float = 0.5  # dimensionless (sin/cos units, range [-1, 1])
    lengthscale_los_count: float = 1.0  # obstruction-count units

    def _lengthscales(self) -> np.ndarray:
        """One lengthscale per column of `features.FEATURE_NAMES` / `GridFeatures.values`."""
        return np.array(
            [
                self.lengthscale_position,
                self.lengthscale_position,
                self.lengthscale_elevation,
                self.lengthscale_distance,
                self.lengthscale_bearing,
                self.lengthscale_bearing,
                self.lengthscale_los_count,
            ]
        )

    def self_variance(self) -> float:
        """`k(x, x) == alpha` for any `x` — every feature distance to itself is zero."""
        return self.alpha

    def matrix(self, features: GridFeatures) -> np.ndarray:
        """The full `N x N` kernel matrix over `features` (`K_uu`, `gp_correction.py`). Accumulates the
        per-dimension distance sum one dimension at a time rather than broadcasting an `(N, N, 7)` array,
        to keep peak memory at `O(N^2)` instead of `O(N^2 * n_features)`."""
        z = features.values
        n = z.shape[0]
        total = np.zeros((n, n), dtype=np.float64)
        for col, lengthscale in zip(z.T, self._lengthscales()):
            total += np.abs(col[:, None] - col[None, :]) / lengthscale
        return self.alpha * np.exp(-total)

    def cross(self, z_obs: np.ndarray, features: GridFeatures) -> np.ndarray:
        """`k(z_obs, z_j)` for every cell `j` in `features` — shape `(N,)`."""
        z = features.values
        total = np.zeros(z.shape[0], dtype=np.float64)
        for col, obs_val, lengthscale in zip(z.T, z_obs, self._lengthscales()):
            total += np.abs(col - obs_val) / lengthscale
        return self.alpha * np.exp(-total)
