# RATPLAN tests — layout convention

One `tests/` tree, mirrored by module, plus a separate `tests/integration/`. Not per-module test
folders colocated inside each package. See `architecture.md` §8 for the reasoning (short version: the
DP in `planner/dp.py` and the `Primitives` DI bundle deliberately couple every module together, so tests
need fixtures from several packages at once — one shared `conftest.py` beats duplicating fixtures per
package, or forcing cross-package imports a colocated layout would need).

## Where a test goes

Mirror the future mission-planner package's own layout (`architecture.md` §7 — that package's name isn't
settled; §6's `rattfallan/` predates `ratplan_terrain/`, which already exists as its own separate package
and is not what this section's `models/`/`primitives/`/`io/` subfolders are named after). Today, `models/`
and `primitives/` cover `ratplan_terrain/` (`test_geometry.py`, `test_terrain.py`, `test_terrain_profile.py`)
— the rest of this layout is what the DP/planner package will grow into once it exists:

```
tests/
  conftest.py            shared fixtures (MissionInput, GraphSnapshot, small CoverageRaster, ...)
  models/                test_geometry.py, test_coverage.py, test_mission.py, test_route.py, test_results.py
  snapshot/               test_road_graph.py, test_mission_snapshot.py
  primitives/              test_scan.py, test_evaluate.py, test_battery.py, test_samband.py
  routing/                  test_router.py, test_candidates.py
  planner/                   test_dp.py, test_beam.py
  io/                          test_mission_input.py, test_ratmap_client.py (offline-fakeable parts)
  integration/                  anything that needs a live ratmap, or itm/'s real service boundary
```

Create a subfolder when its module exists, not before — `tests/integration/` is the one exception,
already created, since it's a structural split (network-dependent vs. offline) independent of which
modules exist yet.

## Running

`pytest` from `RATPLAN/` runs everything except `integration`-marked tests (config lives in the root
`pyproject.toml`'s `[tool.pytest.ini_options]`, not a separate `pytest.ini`). Run those explicitly with
`pytest -m integration` once there's something in `tests/integration/` that needs a live `ratmap` or
`itm/`'s service boundary up.
