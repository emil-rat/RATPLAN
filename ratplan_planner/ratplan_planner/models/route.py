"""One leg of a road route between two positions — the unit `Router`/`BatteryModel` operate on."""

from __future__ import annotations

from dataclasses import dataclass

from ratplan_terrain.models.geometry import Position


@dataclass(frozen=True)
class RouteLeg:
    """A single road-graph hop from `start` to `end` along `road_ids`, in drive order. `route()`
    (`Router`, still to be implemented — OPEN_ISSUES.md's "Archive carryover audit" entry) produces these;
    `BatteryModel(leg)` and the DP's `cost_seconds` accumulation both consume them."""

    start: Position
    end: Position
    road_ids: tuple[str, ...]
    distance_m: float
    cost_seconds: float
