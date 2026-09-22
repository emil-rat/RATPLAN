"""Augmented feature vectors for the ARD kernel (model.md §3.5 option 3, `kernel.py`) — position plus
terrain-relative context, so the kernel can correlate cells that are *similar*, not just close. Everything
here is derived from data `ratplan_terrain`/`ratplan_itm` already produce (no land-cover: confirmed via
`ratplan_terrain/io/ratmap_client.py`'s own note that it has no consumer here yet).

Feature order is fixed and shared by `kernel.ArdKernel`: (x_m, y_m, elevation_m, bearing_sin, bearing_cos,
los_obstruction_count) — working-CRS position, ground elevation at the point, unit bearing from the sender
(sin/cos rather than a raw angle, so 359° and 1° aren't treated as maximally different), and a count of how
many terrain samples along the sender-to-point line pierce the straight tx/rx sightline — a proxy for
"where ITM's own free-space/diffraction assumption is likely violated," deliberately not a restatement of
raw elevation (model.md §3.5's caveat about not duplicating what `m(x)` already encodes).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np
from pyproj import Transformer

from ratplan_terrain.models.geometry import WGS84_CRS, WORKING_CRS, Position
from ratplan_terrain.primitives.terrain import DtmSampler

FEATURE_NAMES = ("x_m", "y_m", "elevation_m", "bearing_sin", "bearing_cos", "los_obstruction_count")
N_FEATURES = len(FEATURE_NAMES)

_TO_WORKING = Transformer.from_crs(WGS84_CRS, WORKING_CRS, always_xy=True)


@dataclass(frozen=True)
class GridFeatures:
    """One feature vector per position, columns in `FEATURE_NAMES` order."""

    values: np.ndarray  # shape (n, N_FEATURES)

    def __len__(self) -> int:
        return self.values.shape[0]


def _to_working_xy(positions: Sequence[Position]) -> tuple[np.ndarray, np.ndarray]:
    lons = np.array([p.lon for p in positions], dtype=np.float64)
    lats = np.array([p.lat for p in positions], dtype=np.float64)
    xs, ys = _TO_WORKING.transform(lons, lats)
    return np.asarray(xs), np.asarray(ys)


def features_for_positions(
    dtm: DtmSampler,
    sender: Position,
    positions: Sequence[Position],
    tx_height_m: float,
    rx_height_m: float,
    n_profile_samples: int = 32,
) -> GridFeatures:
    """Feature vectors for a batch of positions relative to one sender — the raster's own grid cells, or
    a single observed position wrapped in a length-1 list. One `DtmSampler.profiles_m` call for the whole
    batch; ground elevation and LOS-obstruction-count are both read off the same sampled profiles rather
    than issuing separate DTM reads."""
    n = len(positions)
    if n == 0:
        return GridFeatures(values=np.empty((0, N_FEATURES), dtype=np.float64))

    sx, sy = _to_working_xy([sender])
    xs, ys = _to_working_xy(positions)
    dx, dy = xs - sx[0], ys - sy[0]
    dist = np.hypot(dx, dy)
    # bearing_sin/cos = sin/cos(atan2(dx, dy)) without the trig call; at dist==0 (observation at the
    # sender's own position) bearing is undefined, default to (0, 1) — harmless, since x/y already match
    # the sender exactly there and dominate the kernel distance.
    safe_dist = np.where(dist > 0, dist, 1.0)
    bearing_sin = np.where(dist > 0, dx / safe_dist, 0.0)
    bearing_cos = np.where(dist > 0, dy / safe_dist, 1.0)

    profiles = dtm.profiles_m(sender, list(positions), n_profile_samples)  # (n, n_profile_samples)
    tx_ground_m = profiles[:, 0]
    rx_ground_m = profiles[:, -1]
    tx_top = tx_ground_m + tx_height_m
    rx_top = rx_ground_m + rx_height_m
    t = np.linspace(0.0, 1.0, n_profile_samples)
    sightline = tx_top[:, None] + t[None, :] * (rx_top - tx_top)[:, None]
    los_obstruction_count = np.sum(profiles > sightline, axis=1).astype(np.float64)

    values = np.stack([xs, ys, rx_ground_m, bearing_sin, bearing_cos, los_obstruction_count], axis=-1)
    return GridFeatures(values=values)


def features_for_position(
    dtm: DtmSampler, sender: Position, position: Position, tx_height_m: float, rx_height_m: float, n_profile_samples: int = 32
) -> np.ndarray:
    """Feature vector (shape `(N_FEATURES,)`) for a single position — used for a single incoming
    observation, where batching over `features_for_positions` would be overkill."""
    return features_for_positions(dtm, sender, [position], tx_height_m, rx_height_m, n_profile_samples).values[0]
