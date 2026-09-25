"""Environmental/ground parameters for ITM point-to-point prediction.

Defaults mirror itmlogic's own scripts/p2p.py example (relative
permittivity 15, conductivity 0.005 S/m, continental temperate climate,
314 N-units surface refractivity) — these are generic values, not
calibrated for Nordic/Swedish terrain. See OPEN_ISSUES.md.
"""

from dataclasses import dataclass
from enum import IntEnum


class Climate(IntEnum):
    EQUATORIAL = 1
    CONTINENTAL_SUBTROPICAL = 2
    MARITIME_SUBTROPICAL = 3
    DESERT = 4
    CONTINENTAL_TEMPERATE = 5
    MARITIME_TEMPERATE_OVERLAND = 6
    MARITIME_TEMPERATE_OVERSEA = 7


class Polarization(IntEnum):
    HORIZONTAL = 0
    VERTICAL = 1


@dataclass(frozen=True)
class GroundConstants:
    relative_permittivity: float = 15.0
    conductivity_s_per_m: float = 0.005
