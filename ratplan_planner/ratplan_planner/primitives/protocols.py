"""The five swappable primitives the DP (`planner/dp.py`, once written) calls out to. Each is a
`Protocol`, not an ABC — any object with the matching method shape works, no inheritance required.

Modularity (every primitive independently swappable without the DP changing) is the one piece of
`architecture.md` §5's framing the carryover audit did *not* flag as wrong — kept here deliberately.
Everything else about how each primitive computes its result is being re-derived fresh; see each
Protocol's docstring for what's actually decided vs. still open.
"""

from __future__ import annotations

from typing import Protocol

from ratplan_terrain.models.geometry import Position

from ratplan_planner.models.coverage import CoverageRaster
from ratplan_planner.models.route import RouteLeg


class Scan(Protocol):
    """`Scan(position) -> CoverageRaster` — RF/LOS coverage grid around `position`, out to sender max
    range (model.md §2/§3: ITM/ITWOM physics prior, GP/kriging correction not implemented yet). Only ever
    called for the target and for relay-sender positions already chosen — never for every raw candidate.
    Every result is theoretical; only a UGV physically driving to a position and dropping a puck during
    mission execution makes a placement real. A result belongs to exactly one candidate path's own
    `covered_raster` — never pooled or shared across candidates.

    Grid resolution/extent for a real implementation (calling `ratplan_itm`/`ratplan_itwom` per cell via
    `ratplan_terrain`) is not decided yet — needs a performance budget first (architecture.md §10)."""

    def __call__(self, position: Position) -> CoverageRaster: ...


class Evaluate(Protocol):
    """`Evaluate(position, raster) -> (score, description)` — quantitative 0-1 `score` (cover/exposure +
    assistance, model.md §6) used for ranking, plus a qualitative LLM-generated `description` carried
    through to output but never used for ranking. Combination rule not yet specified — model.md §6."""

    def __call__(self, position: Position, raster: CoverageRaster) -> tuple[float, str]: ...


class BatteryModel(Protocol):
    """`BatteryModel(leg) -> wh_consumed` — energy-consumption model per route leg, independent of
    `Evaluate`. No model yet — model.md §7."""

    def __call__(self, leg: RouteLeg) -> float: ...


class Samband(Protocol):
    """`Samband(road_ids, covered_raster) -> probability` — probability of maintaining comms the entire
    route, not just at candidate endpoints. No model yet — model.md §7."""

    def __call__(self, road_ids: tuple[str, ...], covered_raster: CoverageRaster) -> float: ...


class Router(Protocol):
    """`route(start, end) -> RouteLeg` — cost of the cheapest road path between two positions.

    Deliberately left unimplemented here. Emil's 2026-09-22 routing-source decision: a local road-graph
    port (for performance/offline use), re-justified rather than ported as-is from the archived project —
    that means documenting the symmetric-cost assumption (`route(a, b) == route(b, a)`) explicitly and
    adding a check against `ratmap`'s own weight function, not silently duplicating it
    (OPEN_ISSUES.md's carryover-audit entry). Not built yet."""

    def __call__(self, start: Position, end: Position) -> RouteLeg: ...
