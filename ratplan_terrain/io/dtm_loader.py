"""Builds a `DtmSampler` from either of RATPLAN's two real-terrain sources: a live ratmap server (bulk
snapshot export, one HTTP call per mission bbox) or a pre-baked ratmap snapshot's `height.tif` read
straight off disk (the same file `mapviz/server.py` reads, no server needed). Exactly one of
`ratmap_url`/`snapshot_path` must be given — there's no default/fallback between them, the caller decides
which real-terrain source it has available.
"""

from __future__ import annotations

from pathlib import Path

from ratplan_terrain.io.ratmap_client import RatmapClient
from ratplan_terrain.primitives.terrain import DtmSampler


def load_dtm(
    bbox: tuple[float, float, float, float],
    *,
    ratmap_url: str | None = None,
    snapshot_path: str | Path | None = None,
) -> DtmSampler:
    if (ratmap_url is None) == (snapshot_path is None):
        raise ValueError("pass exactly one of ratmap_url or snapshot_path")

    if snapshot_path is not None:
        return DtmSampler(path=snapshot_path)

    with RatmapClient(ratmap_url) as client:
        data = client.fetch_height(bbox)
    if data is None:
        raise ValueError(f"ratmap has no height data for bbox {bbox}")
    return DtmSampler(data=data)
