# ratplan-itwom-client

RATPLAN's own code (no GPL content). Calls the ITWOM service
([`../itwom`](../itwom), GPL-2.0) via `docker run -i`, exchanging JSON over
stdin/stdout — the arm's-length boundary architecture.md §3.1 requires.
Structurally parallel to [`../itm`](../itm)'s `ratplan_itm` package, but a
different input contract: this client gives the service lat/lon sites plus
a coarse real-elevation grid (the service bilinear-fills its own SPLAT!-
native terrain tile from it), where `ratplan_itm` takes a pre-extracted
elevation profile array directly — because SPLAT! reads a whole terrain
tile itself rather than accepting a profile like itmlogic does.

## Usage

```python
from ratplan_itwom import ElevationGrid, Site, predict_point_to_point

result = predict_point_to_point(
    tx=Site(lat=40.55, lon_deg_east=-105.55, height_m=2.0),
    rx=Site(lat=40.55, lon_deg_east=-105.45, height_m=1.5),
    frequency_mhz=433.0,
    terrain=ElevationGrid(
        min_lat=40.54, max_lat=40.56,
        min_lon_deg_east=-105.56, max_lon_deg_east=-105.44,
        values_m=[[1500.0, 1520.0, ...], ...],  # row=ascending lat, col=ascending lon
    ),
)
result.path_loss_db
```

`../../ratplan_terrain/primitives/terrain_profile.py`'s `elevation_grid_from_dtm()` builds an `ElevationGrid`
from a real DTM (a `ratplan_terrain.primitives.terrain.DtmSampler` over ratmap's height data) — see
`../../CLAUDE.md` for how `ratplan_terrain` gets that DTM (live ratmap API or a local snapshot file).

Requires Docker running and the `ratplan-itwom-service` image built (see
`../itwom/README.md`).

## Setup

```
python -m venv .venv
.venv/Scripts/python.exe -m pip install -e ".[dev]"
.venv/Scripts/python.exe -m pytest -m docker
```

Tests are marked `docker` (see `pyproject.toml`) since they need a running
Docker daemon and the built image — not run by a plain `pytest` with no
marker filter in an environment without Docker.

## Known gaps

Terrain comes from a coarse elevation grid (typically ~100x100 points covering just the tx/rx link, not
SPLAT!'s native 1200x1200-per-degree resolution — see `../itwom/README.md`). tx/rx must fall within one
1x1 degree tile. See `../../OPEN_ISSUES.md`.
