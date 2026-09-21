# ratplan-itm

RATPLAN's ITM (Longley-Rice) point-to-point path-loss module. Wraps
[itmlogic](https://github.com/edwardoughton/itmlogic) (MIT) as-is —
unmodified upstream subroutines, no fork of the algorithm.

Scope, per [`../architecture.md`](../architecture.md) §3: this module
computes point-to-point path loss over a given terrain profile. It is the
physics-based mean surface `m(x)` that RATPLAN's GP/kriging correction
layer (architecture.md §2) is built on top of. It does **not**:

- extract terrain profiles from a DEM (that's `ratmap`'s job — this module
  takes a plain `TerrainProfile`, decoupled from any GIS stack),
- implement ITWOM (that runs as a separate service per architecture.md
  §3.1/§4.2, not in-process, not in this module),
- do anything with the GP/residual/online-update layer (architecture.md §2)
  — this module only produces the prior mean.

Deliberately isolated in its own folder with its own `pyproject.toml` and
`.venv` so it's independently installable/testable and swappable (e.g. for
a wrapper around NTIA's own C++ reference implementation) without touching
the rest of RATPLAN.

## Usage

```python
from ratplan_itm import TerrainProfile, predict_point_to_point

profile = TerrainProfile(distance_km=12.4, elevations_m=[...])  # from ratmap's DEM, e.g. via
                                                                 # ratplan_terrain.primitives.terrain_profile.
                                                                 # terrain_profile_from_dtm()

result = predict_point_to_point(
    profile,
    tx_height_m=2.0,
    rx_height_m=1.5,
    frequency_mhz=433.0,
)

result.loss_db(reliability_pct=50, confidence_pct=50)
```

`ground`, `climate`, and `surface_refractivity_n_units` are overridable —
current defaults are itmlogic's own example values, **not** calibrated for
Swedish/Nordic terrain. See [`../OPEN_ISSUES.md`](../OPEN_ISSUES.md).

## Setup

```
python -m venv .venv
.venv/Scripts/python.exe -m pip install -e ".[dev]"
.venv/Scripts/python.exe -m pytest
```

## Provenance note

`itmlogic`'s installed package does not ship a ready-made point-to-point
entry point — `itmlogic_p2p()` exists only as example glue code in the
upstream repo's `scripts/p2p.py`, not in the pip package. `point_to_point.py`
in this module is our own orchestration, adapted from that upstream example
(MIT), calling itmlogic's actual public subroutines (`qerfi`, `qlrpfl`,
`avar`) unmodified. See the docstring in `point_to_point.py` and
`OPEN_ISSUES.md` for detail.
