"""httpx client for ratmap's bulk snapshot endpoints — the one HTTP boundary ratplan_terrain crosses to pull
real terrain before a planning run (CLAUDE.md: "it takes one snapshot of the specified mission area per
planning run ... rather than reimplementing map data collection itself").

Only `fetch_height()` is wired up — the road-graph and land-cover endpoints (`/snapshot/graph`,
`/vector/landcover`) are ratmap's job to serve but have no consumer in ratplan_terrain yet (no `GraphSnapshot`
model exists this restart); add them when a real caller needs them, not ahead of need.

Network-only — exercised by `tests/integration/`, not the default offline pytest run (needs a locally
running ratmap: `.venv/Scripts/uvicorn ratmap.main:app --workers 1 --reload`).
"""

from __future__ import annotations

import httpx


def _bbox_param(bbox: tuple[float, float, float, float]) -> str:
    return ",".join(str(v) for v in bbox)


class RatmapClient:
    def __init__(self, base_url: str, timeout: float = 30.0) -> None:
        # ratmap mounts every router under /api (ratmap/main.py's include_router(..., prefix="/api")
        # calls) -- callers pass the bare host (e.g. "http://127.0.0.1:8000").
        self._client = httpx.Client(base_url=f"{base_url.rstrip('/')}/api", timeout=timeout)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "RatmapClient":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def fetch_height(self, bbox: tuple[float, float, float, float]) -> bytes | None:
        """Clipped DTM GeoTIFF bytes, in ratmap's own raster CRS (EPSG:5845) — not reprojected, the
        GeoTIFF is self-describing so `DtmSampler` reads the CRS straight off the file. `None` when
        ratmap has no height data for `bbox`."""
        response = self._client.get("/snapshot/height", params={"bbox": _bbox_param(bbox)})
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response.content
