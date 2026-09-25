"""`CandidateResult`/`PlanResult` — fields named directly from `KONTEXT.md`'s "Utdata" section, plus the
DP bookkeeping model.md §5 needs internally (`battery_consumed_wh`, `relay_chain`, `road_ids`).
"""

from __future__ import annotations

from dataclasses import dataclass

from ratplan_terrain.models.geometry import Position

from ratplan_connectivity.models.coverage import CoverageRaster
from ratplan_planner.models.route import RouteLeg


@dataclass(frozen=True)
class CandidateResult:
    """One proposed way to execute the mission — a starting position, its road path to `target`, and
    every evaluation KONTEXT.md's "Utdata" asks for."""

    start: Position
    road_ids: tuple[str, ...]
    relay_chain: tuple[Position, ...]
    """Ordered puck-drop positions along the route, in drive order."""
    cost_seconds: float
    """Hur lång tid uppdraget tar."""
    battery_consumed_wh: float
    covered_raster: CoverageRaster
    """Täckning i området — private to this one candidate, never pooled across candidates (model.md §5)."""
    samband_probability: float
    """Samband — sannolikhet att kunna nå råttan hela vägen. `Samband(road_ids, covered_raster)`, no
    model yet (model.md §7)."""
    evaluate_score: float
    """0-1 score used for ranking. `Evaluate(position, raster)`, combination rule not yet specified
    (model.md §6)."""
    description: str
    """Beskrivning av väg (skydd, framkomlighet) — qualitative, LLM-generated, never used for ranking."""
    overhead_cover_type: str
    """Flygskyddstyp (hus, träd)."""
    retreat_routes: tuple[RouteLeg, ...]
    """Fria tillbakaryckningsvägar."""
    resupply_feasible: bool
    """Möjlighet till underhåll."""


@dataclass(frozen=True)
class PlanResult:
    """All candidates across relay levels 0..R, ranked by `evaluate_score` (model.md §5's output shape)."""

    candidates: tuple[CandidateResult, ...]
