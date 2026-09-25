# simulation_tool — visual test tool for Scan + GP correction

A visual frontend over the *real* `connectivity_module/ratplan_connectivity` pipeline: terrain
hillshade + road network on MapLibre (same base as `mapviz/`), plus:

1. **Place a relay** — click "Place relay", then click the map. Runs the real `ItmGridScan` against
   real terrain and shows its `CoverageRaster` as a colored heatmap (red = poor link margin, green =
   good).
2. **Add an observation** — enter an RSSI value (dBm) in the toolbar, click "Add observation", then
   click the map. Runs the real `GpCorrector.observe()` + `.corrected_raster()` and the heatmap
   updates to reflect the Bayesian correction.

**Single active relay at a time.** Placing a new relay discards the previous relay, its
`GpCorrector`, and every observation placed against it — this isn't a multi-relay mission simulator
yet, just a way to exercise Scan/GP interactively. RSSI values are typed in by hand rather than
auto-computed: injecting a hypothetical reading and watching the raster reshape is the point.

See `architecture.md` §8/§9 for how this relates to `mapviz/` (stays scoped to terrain+roads
sanity-checking, not wired to Scan) and to `rattfallan-demo` (a UI-pattern reference only — its own
backend calls are stale against this repo).

## Setup

Needs the real backend packages installed alongside this tool's own dependencies (see repo root
`CLAUDE.md`'s setup section for the equivalent pattern used by `ratplan_planner`/
`connectivity_module`):

```
cd simulation_tool
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt
.venv/Scripts/pip install -e ".." -e "../connectivity_module" -e "../connectivity_module/ITWOM/itm" -e "../connectivity_module/ITWOM/itwom_client"
```

No Docker/network needed — the ITM scan + GP observe flow used here never touches the separate
ITWOM/SPLAT! service.

## Data

Needs a `ratmap` snapshot's `data/` dir, containing `height.tif` and `roads.geojson`. Defaults to
`../ratmap/snapshots/real_map_scenario_north/data` (same convention `mapviz`/`rattfallan-demo` use);
point it elsewhere with:

```
set RATPLAN_SIMULATION_TOOL_DATA_DIR=path\to\snapshot\data
```

If `height.tif` is missing, the map still loads (terrain/roads layers just skip, same as `mapviz`)
but relay placement is disabled (503) — there's no meaningful Scan without real terrain. If
`roads.geojson` is missing, only the roads layer is skipped.

Startup pays the same one-time ~30-40s hillshade decimated-read cost `mapviz/README.md` documents
(against `real_map_scenario_north`'s ~4GB `height.tif`) — a one-time process-start cost, not
per-relay-placement.

## Performance

`ItmGridScan`'s own library defaults (`target_cell_size_m=25.0`, `max_extent_m=1500.0`) run a
120x120 grid — 14,400 individual ITM calls, too slow to feel interactive on a click. This tool
defaults to a coarser interactive grid instead (`target_cell_size_m=50.0`, `max_extent_m=800.0` —
32x32, ~1,000 calls), overridable via:

```
set SIMULATION_TOOL_CELL_SIZE_M=50.0
set SIMULATION_TOOL_MAX_EXTENT_M=800.0
```

No performance budget for `Scan()` has ever been derived (`architecture.md` §9) — these are a
heuristic starting point, not a validated number. Tune them down further if relay placement still
isn't comfortably interactive on your machine, or up for higher-fidelity rasters if you can afford
the wait.

## GP kernel lengthscales

`ArdKernel`'s lengthscales decide how far one observation's correction spreads. Its defaults are
uncalibrated placeholders (`kernel.py`), and they're tight: one observation mostly affects cells within
~100–200 m, because the elevation (20 m) and LOS-obstruction-count (1) terms stop correlating cells
whenever the terrain changes. Override any of them per env var. An unset var keeps `ArdKernel`'s own
default:

| Env var | `ArdKernel` field | Default |
|---|---|---|
| `SIMULATION_TOOL_LS_POSITION_M` | `lengthscale_position` | 150 |
| `SIMULATION_TOOL_LS_ELEVATION_M` | `lengthscale_elevation` | 20 |
| `SIMULATION_TOOL_LS_DISTANCE_M` | `lengthscale_distance` | 150 |
| `SIMULATION_TOOL_LS_BEARING` | `lengthscale_bearing` | 0.5 |
| `SIMULATION_TOOL_LS_LOS_COUNT` | `lengthscale_los_count` | 1 |

```
set SIMULATION_TOOL_LS_POSITION_M=500
set SIMULATION_TOOL_LS_ELEVATION_M=60
```

Radio link-budget constants (`RadioParams`) and the kernel's `alpha`/`sigma2` still use fixed library
defaults. Edit their construction in `server.py` directly if you need different values.

## Run

```
simulation_tool/.venv/Scripts/uvicorn simulation_tool.server:app --reload
```

from `RATPLAN/`, then open `http://127.0.0.1:8000`.
