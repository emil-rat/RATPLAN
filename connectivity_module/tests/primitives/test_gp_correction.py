"""Tests for GpCorrector's fixed-grid recursive Bayesian update (gp_correction.py), against a synthetic
flat DTM (offline, no live ratmap/Docker needed).

Two invariants are checked that hold by construction, not just empirically:
- zero observations -> the posterior is exactly the prior (model.md §3.1's graceful-degradation claim;
  mu starts at zero and Sigma starts at K_uu, whose diagonal is exactly `kernel.alpha` everywhere - the same
  constant ItmGridScan already fills variance_db with).
- posterior variance is non-increasing everywhere after any observation: `Sigma_jj_new = Sigma_jj_old -
  gain_j * sigma_w_j = Sigma_jj_old - sigma_w_j^2 / innovation_var`, and a squared term divided by a
  positive variance can never be negative - this holds regardless of the kernel's own sign structure.

A third test relies on a fact specific to the *first* observation only: since `Sigma` starts out exactly
equal to `K_uu`, `sigma_w = Sigma @ w = K_uu @ (K_uu^-1 k_xu) = k_xu` exactly - and `k_xu` is entrywise
non-negative (the kernel is a positive exponential everywhere), so `gain = sigma_w / innovation_var` is
entrywise non-negative too. With `mu` starting at zero, the mean shift `gain * (y - 0)` therefore has the
same sign as `y` at every cell - a property that is NOT generally guaranteed after further observations
(once Sigma differs from K_uu), only immediately after construction.
"""

import numpy as np
import pytest
from rasterio.io import MemoryFile
from rasterio.transform import from_origin

from ratplan_terrain.models.geometry import Position
from ratplan_terrain.primitives.terrain import DtmSampler

from ratplan_connectivity.models.coverage import CoverageRaster
from ratplan_connectivity.primitives.gp_correction import GpCorrector
from ratplan_connectivity.primitives.kernel import ArdKernel
from ratplan_connectivity.primitives.scan import ItmGridScan, RadioParams, physics_mean_db

SENDER = Position(lon=17.0, lat=60.0)
_RADIO = RadioParams(tx_power_dbm=10.0, rx_sensitivity_dbm=-70.0, frequency_mhz=433.0)


def _geotiff_bytes(band: np.ndarray, transform, crs: str = "EPSG:4326") -> bytes:
    height, width = band.shape
    with MemoryFile() as memfile:
        with memfile.open(
            driver="GTiff", height=height, width=width, count=1, dtype=band.dtype, crs=crs, transform=transform
        ) as dst:
            dst.write(band, 1)
        return memfile.read()


@pytest.fixture
def flat_dtm() -> DtmSampler:
    transform = from_origin(16.985, 60.015, 0.0001, 0.0001)
    band = np.full((300, 300), 50.0, dtype=np.float32)
    return DtmSampler(data=_geotiff_bytes(band, transform))


_TEST_CELL_SIZE_M = 190.0  # -> a ~6x6 grid for _RADIO's ~550m max range


def _prior_raster(flat_dtm, target_cell_size_m: float = _TEST_CELL_SIZE_M) -> CoverageRaster:
    scan = ItmGridScan(dtm=flat_dtm, radio=_RADIO, target_cell_size_m=target_cell_size_m)
    return scan(SENDER)


def test_zero_observations_posterior_equals_prior(flat_dtm):
    prior = _prior_raster(flat_dtm)
    corrector = GpCorrector(prior=prior, dtm=flat_dtm, sender=SENDER, radio=_RADIO, kernel=ArdKernel())
    posterior = corrector.corrected_raster()
    assert np.allclose(posterior.mean_db, prior.mean_db)
    assert np.allclose(posterior.variance_db, prior.variance_db)


def test_observation_never_increases_variance_anywhere(flat_dtm):
    prior = _prior_raster(flat_dtm)
    corrector = GpCorrector(prior=prior, dtm=flat_dtm, sender=SENDER, radio=_RADIO, kernel=ArdKernel())
    before = corrector.corrected_raster().variance_db.copy()

    m_at_sender = physics_mean_db(flat_dtm, SENDER, SENDER, _RADIO)
    plausible_rssi = _RADIO.tx_power_dbm - m_at_sender
    corrector.observe(SENDER, plausible_rssi)
    after = corrector.corrected_raster().variance_db

    assert np.all(after <= before + 1e-9)
    assert np.any(after < before - 1e-9)  # variance strictly decreased somewhere


def test_first_observation_shifts_mean_in_the_observed_direction(flat_dtm):
    prior = _prior_raster(flat_dtm)
    corrector = GpCorrector(prior=prior, dtm=flat_dtm, sender=SENDER, radio=_RADIO, kernel=ArdKernel())

    # A much weaker-than-predicted RSSI (more path loss than ITM predicted) observed at the sender's cell.
    m_at_sender = physics_mean_db(flat_dtm, SENDER, SENDER, _RADIO)
    weak_rssi = _RADIO.tx_power_dbm - (m_at_sender + 20.0)  # 20 dB worse than predicted -> positive residual
    corrector.observe(SENDER, weak_rssi)

    posterior = corrector.corrected_raster()
    assert np.all(posterior.mean_db >= prior.mean_db - 1e-9)
    assert np.any(posterior.mean_db > prior.mean_db + 1e-9)


def test_repeated_observations_stay_cheap_and_stable(flat_dtm):
    """Not a timing assertion (too environment-dependent) - just confirms many sequential `.observe()`
    calls against the same fixed-size state complete and keep producing finite, sane values, i.e. nothing
    about the update accumulates unboundedly or blows up numerically as observations pile up."""
    prior = _prior_raster(flat_dtm)
    corrector = GpCorrector(prior=prior, dtm=flat_dtm, sender=SENDER, radio=_RADIO, kernel=ArdKernel())
    rng = np.random.default_rng(0)
    for _ in range(30):
        jitter_lon = SENDER.lon + rng.uniform(-0.0005, 0.0005)
        jitter_lat = SENDER.lat + rng.uniform(-0.0005, 0.0005)
        pos = Position(lon=jitter_lon, lat=jitter_lat)
        m = physics_mean_db(flat_dtm, SENDER, pos, _RADIO)
        rssi = _RADIO.tx_power_dbm - m + rng.normal(scale=2.0)
        corrector.observe(pos, rssi)

    posterior = corrector.corrected_raster()
    assert np.all(np.isfinite(posterior.mean_db))
    assert np.all(np.isfinite(posterior.variance_db))
    assert np.all(posterior.variance_db >= -1e-6)
