"""`MissionInput` — every field is named directly in `KONTEXT.md`'s "Indata" section (the source-of-truth
mission brief), not inherited from the archived project's `pseudocode-v2.md`/`mission.py`.

Which of these actually get consumed by the DP's search (as opposed to carried through to output, or not
wired up yet) is a `planner/dp.py` decision, not fixed here — see that module once it exists.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ratplan_terrain.models.geometry import Position


@dataclass(frozen=True)
class MissionInput:
    # Uppdragsformulering (KONTEXT.md §Indata, "Uppdragsformuleringen")
    target: Position
    """Mål: plats dit råttan ska ta sig."""
    battery_requirement_wh: float
    """Krav på batteri vid mål: hur mycket batteri råttan behöver ha kvar för att utföra sitt uppdrag."""
    max_mission_time_s: float
    """Tidskrav: hur lång tid gruppen har att få råttan till mål."""

    # Anges av gruppchef/navigatör
    puck_count: int
    """Antalet puckar tillgängligt — caps `relay_count_max` in the DP's beam search (model.md §5)."""
    min_enemy_standoff_m: float
    """Hur nära fienden vi vågar vara — a soft penalty in `Evaluate`, not a hard filter (model.md §6)."""

    # Från ledningssystem och ratmap — all optional, not all wired into the DP yet
    enemy_positions: tuple[Position, ...] = field(default_factory=tuple)
    """Senast kända positioner av fienden."""
    friendly_positions: tuple[Position, ...] = field(default_factory=tuple)
    """Position av sidoförband."""
    other_rat_routes: tuple[tuple[Position, ...], ...] = field(default_factory=tuple)
    """Andra råttor och deras planerade vägar."""
    user_drawn_routes: tuple[tuple[Position, ...], ...] = field(default_factory=tuple)
    """Användarinlagda vägar."""
    closed_road_ids: frozenset[str] = field(default_factory=frozenset)
    """Mineringar/avstängda vägar."""
