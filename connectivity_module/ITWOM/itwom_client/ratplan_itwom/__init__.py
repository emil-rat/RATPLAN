"""RATPLAN's client for the ITWOM service (../itwom).

This package is RATPLAN's own code (no GPL content) and never imports or
links anything from ../itwom — it only shells out to `docker run` and
exchanges JSON over stdin/stdout, per architecture.md §3.1's arm's-length
containment strategy. See ../itwom/README.md for the service side.
"""

from .client import predict_point_to_point
from .types import ElevationGrid, GroundConstants, Site, ItwomResult

__all__ = [
    "predict_point_to_point",
    "GroundConstants",
    "Site",
    "ElevationGrid",
    "ItwomResult",
]
