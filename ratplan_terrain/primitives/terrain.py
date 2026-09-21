"""DTM height sampling over a DTM GeoTIFF (as returned by ratmap's `GET /api/snapshot/height`, or read
straight off a ratmap snapshot's `height.tif` — see `ratplan_terrain.io.dtm_loader.load_dtm`).

Keeps the dataset open and reads on demand, windowed to just the points a given call actually needs — a
ratmap snapshot's `height.tif` can be several GB at full extent (e.g. `real_map_scenario_north` is
~4GB), far more than any single profile/grid query touches, so eagerly loading the whole band was a real
memory-blowup risk, not just a hypothetical one. Positions are always WGS84 (`Position`, EPSG:4326);
elevation lookups convert to the raster's own CRS (ratmap's raster CRS is EPSG:5845) via a
`pyproj.Transformer`, the same pattern `Position.to_working()` uses for EPSG:3006.

Nodata pixels aren't special-cased: callers only ever sample within a bbox that was itself the basis for
the DTM export, so nodata is expected only outside the raster's own extent — handled by clamping sample
coordinates to the raster's edge pixels (see `_sample_xy`), not by detecting nodata values in the data
itself.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import rasterio
from pyproj import Transformer
from rasterio.windows import Window

from ratplan_terrain.models.geometry import Position

_WGS84_CRS = "EPSG:4326"


class DtmSampler:
    def __init__(self, data: bytes | None = None, path: str | Path | None = None) -> None:
        if (data is None) == (path is None):
            raise ValueError("pass exactly one of data or path")

        if data is not None:
            self._memfile: rasterio.io.MemoryFile | None = rasterio.io.MemoryFile(data)
            self._dataset = self._memfile.open()
        else:
            self._memfile = None
            self._dataset = rasterio.open(path)

        ds = self._dataset
        self._width, self._height = ds.width, ds.height
        raster_crs = ds.crs.to_string()
        self._transform = ds.transform
        inv = ~ds.transform

        self._to_raster = Transformer.from_crs(_WGS84_CRS, raster_crs, always_xy=True)
        self._to_wgs84 = Transformer.from_crs(raster_crs, _WGS84_CRS, always_xy=True)
        self._inv_a, self._inv_b, self._inv_c = inv.a, inv.b, inv.c
        self._inv_d, self._inv_e, self._inv_f = inv.d, inv.e, inv.f

    def close(self) -> None:
        self._dataset.close()
        if self._memfile is not None:
            self._memfile.close()

    def __enter__(self) -> "DtmSampler":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def _raster_xy(self, positions: list[Position]) -> tuple[np.ndarray, np.ndarray]:
        lons = np.array([p.lon for p in positions], dtype=np.float64)
        lats = np.array([p.lat for p in positions], dtype=np.float64)
        xs, ys = self._to_raster.transform(lons, lats)
        return np.asarray(xs), np.asarray(ys)

    def _sample_xy(self, xs: np.ndarray, ys: np.ndarray) -> np.ndarray:
        """Bilinear-sample elevations at raster-CRS coordinates `xs`/`ys` (any shape, returned
        flattened to match). Out-of-bounds coordinates clamp to the raster's edge pixels rather than
        raising — cells near a bbox's edge are expected, and reuse the nearest real data instead of
        failing.

        Reads only the small window of pixels this call's points actually span (plus their immediate
        bilinear neighbors) rather than the whole raster — one `read()` per call, sized to that call's
        own geographic footprint, however large the underlying file is."""
        col = self._inv_a * xs + self._inv_b * ys + self._inv_c
        row = self._inv_d * xs + self._inv_e * ys + self._inv_f

        col = np.clip(col, 0.0, self._width - 1.001)
        row = np.clip(row, 0.0, self._height - 1.001)

        col0 = np.floor(col).astype(np.int64)
        row0 = np.floor(row).astype(np.int64)
        col1 = col0 + 1
        row1 = row0 + 1
        fc = col - col0
        fr = row - row0

        col_min, col_max = int(col0.min()), int(col1.max())
        row_min, row_max = int(row0.min()), int(row1.max())
        window = Window(col_min, row_min, col_max - col_min + 1, row_max - row_min + 1)
        band = self._dataset.read(1, window=window).astype(np.float32, copy=False)

        wc0, wc1 = col0 - col_min, col1 - col_min
        wr0, wr1 = row0 - row_min, row1 - row_min

        v00 = band[wr0, wc0]
        v01 = band[wr0, wc1]
        v10 = band[wr1, wc0]
        v11 = band[wr1, wc1]
        return v00 * (1 - fc) * (1 - fr) + v01 * fc * (1 - fr) + v10 * (1 - fc) * fr + v11 * fc * fr

    def elevation_m(self, pos: Position) -> float:
        xs, ys = self._raster_xy([pos])
        return float(self._sample_xy(xs, ys)[0])

    def profile_m(self, a: Position, b: Position, n_samples: int) -> list[float]:
        """`n_samples` evenly spaced elevations from `a` to `b` inclusive, along the straight line
        between them — terrain is only sampled at each point, not modeled continuously in between, the
        same finite-resolution simplification any real point-to-point ITM profile also makes at a
        finite sample count."""
        ax, ay = self._raster_xy([a])
        bx, by = self._raster_xy([b])
        t = np.linspace(0.0, 1.0, n_samples)
        xs = ax[0] + (bx[0] - ax[0]) * t
        ys = ay[0] + (by[0] - ay[0]) * t
        return self._sample_xy(xs, ys).tolist()

    def profiles_m(self, source: Position, targets: list[Position], n_samples: int) -> np.ndarray:
        """Vectorized `profile_m` for many targets at once — shape `(len(targets), n_samples)`. Lets a
        grid-batched scan sample every cell's line-of-sight profile in one numpy call instead of a
        per-cell Python loop."""
        if not targets:
            return np.empty((0, n_samples), dtype=np.float32)
        sx, sy = self._raster_xy([source])
        tx, ty = self._raster_xy(targets)
        t = np.linspace(0.0, 1.0, n_samples)
        xs = sx[0] + (tx[:, None] - sx[0]) * t[None, :]
        ys = sy[0] + (ty[:, None] - sy[0]) * t[None, :]
        flat = self._sample_xy(xs.ravel(), ys.ravel())
        return flat.reshape(xs.shape)

    def sample_grid(
        self, min_lat: float, max_lat: float, min_lon: float, max_lon: float, n_lat: int, n_lon: int
    ) -> np.ndarray:
        """A regular `n_lat` x `n_lon` grid of elevations over a WGS84 bbox, row = ascending latitude,
        col = ascending longitude. Feeds ITWOM's coarse `ElevationGrid` (see
        `ratplan_terrain.primitives.terrain_profile.elevation_grid_from_dtm`) — SPLAT! needs a whole terrain
        tile rather than a single profile, but doesn't need this DTM's native ~1m resolution to get a
        physically meaningful diffraction result over a short relay hop."""
        lats = np.linspace(min_lat, max_lat, n_lat)
        lons = np.linspace(min_lon, max_lon, n_lon)
        grid_lon, grid_lat = np.meshgrid(lons, lats)
        positions = [Position(lon=float(lo), lat=float(la)) for lo, la in zip(grid_lon.ravel(), grid_lat.ravel())]
        xs, ys = self._raster_xy(positions)
        return self._sample_xy(xs, ys).reshape(n_lat, n_lon)

    def elevation_grid(self, max_dim: int = 800) -> dict:
        """Rendering-only helper for a hillshade layer — not used by any real path-loss computation.
        Returns the whole DTM decimated to at most `max_dim` samples per side, its real-world sample
        spacing in meters (the raster CRS is projected), and the WGS84 lon/lat of its four corners (NW,
        NE, SE, SW). Corner-only reprojection, not per-pixel — fine at this extent.

        Uses a decimated read (`out_shape`) rather than loading the full-resolution band and slicing it —
        the same technique `mapviz/server.py`'s own hillshade reader uses, for the same reason: a DTM can
        be several GB at full resolution, and this only ever needs a `max_dim`-sized preview of it."""
        step = max(1, max(self._height, self._width) // max_dim)
        out_height = -(-self._height // step)
        out_width = -(-self._width // step)
        grid = self._dataset.read(1, out_shape=(out_height, out_width))
        corners_px = [(0, 0), (self._width, 0), (self._width, self._height), (0, self._height)]
        xs, ys = zip(*(self._transform * c for c in corners_px))
        lons, lats = self._to_wgs84.transform(np.array(xs), np.array(ys))
        corners = [[float(lon), float(lat)] for lon, lat in zip(lons, lats)]
        return {"elevation_m": grid, "cell_size_m": abs(self._transform.a) * step, "corners": corners}
