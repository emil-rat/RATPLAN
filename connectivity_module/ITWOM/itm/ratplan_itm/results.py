from dataclasses import dataclass
from typing import Sequence


@dataclass(frozen=True)
class PathLossEstimate:
    reliability_pct: float
    confidence_pct: float
    loss_db: float


@dataclass(frozen=True)
class PointToPointResult:
    free_space_loss_db: float
    estimates: Sequence[PathLossEstimate]

    def loss_db(self, reliability_pct: float, confidence_pct: float) -> float:
        for estimate in self.estimates:
            if (
                estimate.reliability_pct == reliability_pct
                and estimate.confidence_pct == confidence_pct
            ):
                return estimate.loss_db
        raise KeyError(
            f"no estimate for reliability={reliability_pct}, "
            f"confidence={confidence_pct} — was it requested?"
        )
