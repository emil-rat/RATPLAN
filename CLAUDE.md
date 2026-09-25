# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project status

**Restart, connectivity module working end-to-end against real terrain, mission-planner library only a
minimal seed so far.** This is a fresh `RATPLAN/` (the predecessor project, `rattfallan`, is archived at
`../arkiv/RATPLAN - gammal/` and a diverged sibling snapshot `../arkiv/rattfallan/` — read from for
provenance, never edited). **2026-09-22: per Emil's explicit instruction, the archived project is no longer
to be used as a source for this restart at all** — a carryover audit found real problems in what had been
inherited from it (not just unvalidated stubs), documented in `OPEN_ISSUES.md`'s "Archive carryover audit"
entry. `pseudocode-v2.md` and `architecture.md` §§5–6 are marked non-authoritative in-place as a result (kept
on disk for historical context only); the DP is being re-derived from scratch against `KONTEXT.md` and the
real `ITWOM`/`ratplan_terrain` primitives, starting with `ratplan_planner/` (below). **2026-09-23:**
everything that computes RF connectivity — the ITWOM/ITM engines and the concrete `Scan`/GP implementation
that consumes them — was pulled out of `ratplan_planner/` into its own `connectivity_module/`, so the
planner package now holds only the DP/mission-planning code. What exists today:

- **`connectivity_module/`** — everything that computes RF connectivity, in two subfolders:
  - **`connectivity_module/ITWOM/`** — the two physics-prior implementations, both working end-to-end
    against real Lantmäteriet terrain (via `ratplan_terrain/`, below):
    - `ITWOM/itm/` (`ratplan_itm`) — ITM (Longley-Rice) via `itmlogic`, in-process, MIT-licensed. Own
      `pyproject.toml`/`.venv`. Takes a plain `TerrainProfile`, decoupled from any GIS stack.
    - `ITWOM/itwom/` — ITWOM v3.0 via unmodified upstream SPLAT!, GPL-2.0, runs as its own Docker
      container — **third-party code, not RATPLAN's own; don't edit it as if it were.** Fills its own
      SPLAT!-native terrain tile from a real elevation grid supplied in the request (`elevation_m()`), not
      the old synthetic base+ridge formula.
    - `ITWOM/itwom_client/` (`ratplan_itwom`) — RATPLAN's own arm's-length client for the above, talks to
      the container over stdin/stdout JSON. Own `pyproject.toml`/`.venv`.
    - See `connectivity_module/ITWOM/README.md` and `architecture.md` §§3–4 for why the ITWOM half is a
      separate service rather than an in-process library (GPL-2.0 licensing boundary) — that distinction
      matters, don't collapse it.
  - **`connectivity_module/ratplan_connectivity/`** (own `pyproject.toml`/`.venv`, depends on
    `ratplan_terrain`/`ratplan_itm`/`ratplan_itwom_client`) — the concrete `Scan(position) -> CoverageRaster`
    implementation, landed 2026-09-22 (`43c35fe` "GP implementation, first try"; Emil owns this code, don't
    build on it unprompted): `models/coverage.py` (`CoverageRaster` — a real lat/lon covered-cell grid with a
    reachable-cell-boundary eligibility filter, re-derived from model.md §5 to replace the archive's
    isotropic-circle `near_edge` formula, which didn't hold for a real DTM-LOS-shaped raster), and
    `primitives/`: `scan.py` (`ItmGridScan` — the physics-prior grid scan, always pure ITM, never touches
    observations/GP state), `gp_correction.py` (`GpCorrector` — the fixed-grid recursive Bayesian/GP
    correction folding live RSSI into the ITM prior at flat per-observation cost; not wired into any live
    RSSI ingestion pipeline yet), and `kernel.py`/`features.py` (the GP's ARD covariance kernel and augmented
    feature vector, `model.md` §3.5). See `CLAUDE_SESSIONS.md`'s 2026-09-22 entry for the full design
    rationale and what's still out of scope.
- **`ratplan_terrain/`** — real-terrain plumbing, a fresh package (own `pyproject.toml`/`.venv`), structurally
  parallel to `ratplan_itm`/`ratplan_itwom` rather than part of the future mission-planner package (whatever
  that ends up being named — `architecture.md` §6's `rattfallan/` target layout predates this and is not
  settled): `primitives/terrain.py::DtmSampler` (bilinear DTM sampling), `io/{ratmap_client.py,dtm_loader.py}`
  (pulls a DTM clip from a live ratmap or a pre-baked snapshot's `height.tif`), and
  `primitives/terrain_profile.py` (bridges a sampled DTM into each of `ratplan_itm`'s and `ratplan_itwom`'s
  own terrain inputs).
- **`mapviz/`** — a scoped-down visual sanity-check tool (terrain hillshade + road network on MapLibre), not
  wired to `Scan` yet. See `mapviz/README.md`.
- **`simulation_tool/`** — 2026-09-25: a second, separate visual tool wired to the real Scan/GP pipeline —
  click to place a relay and see its `ItmGridScan`-derived `CoverageRaster`, then click to place
  manually-entered-RSSI observations and see `GpCorrector.observe()`/`.corrected_raster()` reshape it live.
  Single active relay at a time (placing a new one replaces the previous relay, its corrector, and its
  observations) — the seed of an eventual broader simulation tool, not multi-relay yet. See
  `simulation_tool/README.md` and `architecture.md` §8/§9 for how it relates to `mapviz/` (stays
  terrain+roads-only) and `rattfallan-demo` (UI-pattern reference only, backend calls stale).
- **`ratplan_planner/`** — the mission-planner package (own `pyproject.toml`/`.venv`, depends on
  `ratplan_terrain` and `ratplan_connectivity`), started fresh 2026-09-22 without reference to the archive,
  and now holding only the planning algorithm itself. So far: `models/` (`RouteLeg`; `MissionInput` fields
  taken directly from `KONTEXT.md`'s "Indata", not `pseudocode-v2.md`; `CandidateResult`/`PlanResult` from
  `KONTEXT.md`'s "Utdata", each candidate holding its own private
  `ratplan_connectivity.models.coverage.CoverageRaster`) and `primitives/protocols.py` (the five
  swappable-primitive `Protocol`s: `Scan`/`Evaluate`/`BatteryModel`/`Samband`/`Router`, unimplemented here —
  `Scan`'s concrete implementation lives in `connectivity_module/ratplan_connectivity/`, not in this
  package). **Not yet built**: the road-graph candidate generator, `planner/dp.py` itself, the local
  `Router` (needs re-justifying the symmetric-cost assumption per the carryover audit, not silently
  re-porting it), and `Evaluate`/`BatteryModel`/`Samband` (still no math — `model.md` §§6–7).

Two documents split "what RATPLAN computes" from "how it's built":

- **[`architecture.md`](./architecture.md)** — the system/backend design: module boundaries, service
  boundaries (why ITWOM runs as its own Docker service), package layout, testing strategy, `mapviz`.
- **[`model.md`](./model.md)** — the mathematical model: the GP/kriging connectivity-correction math (mean
  function, covariance, parameter estimation, online update, open modeling questions), and the DP mission
  planner's value function/recurrence. `pseudocode-v2.md` is **not** authoritative for the DP's control flow
  or candidate-generation details as of 2026-09-22 (see "Project status" above) — `model.md` §5 is the
  current source for the value function/recurrence/eligibility filter, itself partly re-derived from the
  archive-free redesign, not just a restatement.

When the two disagree on *what* a component computes, `model.md` wins; on *where/how it runs*,
`architecture.md` wins.

Setup, per component (`connectivity_module/ITWOM/itm` and `connectivity_module/ITWOM/itwom_client` are still independently installable with their
own `.venv`; `ratplan_terrain` is a separate root-level package with its own `pyproject.toml`, not yet folded
into any of the others):

```
cd connectivity_module/ITWOM/itm && python -m venv .venv && .venv/Scripts/pip install -e ".[dev]" && .venv/Scripts/pytest
cd connectivity_module/ITWOM/itwom_client && python -m venv .venv && .venv/Scripts/pip install -e ".[dev]" && .venv/Scripts/pytest -m docker

# ratplan_terrain (real-terrain plumbing) -- from RATPLAN/
python -m venv .venv && .venv/Scripts/pip install -e ".[dev]" && .venv/Scripts/pytest

# ratplan_connectivity (Scan/GP implementation) -- from RATPLAN/connectivity_module/; needs Python >=3.11,
# ratplan_terrain, ratplan_itm, and ratplan_itwom_client (ratplan_terrain.primitives.terrain_profile imports
# it unconditionally even though scan.py only ever uses the ITM half) installed alongside it
cd connectivity_module && python -m venv .venv && .venv/Scripts/pip install -e ".[dev]" -e ".." -e "./ITWOM/itm" -e "./ITWOM/itwom_client" && .venv/Scripts/pytest

# ratplan_planner (mission planner) -- from RATPLAN/ratplan_planner/; needs Python >=3.11, ratplan_terrain,
# and ratplan_connectivity installed alongside it. ratplan_connectivity declares ratplan_itm/
# ratplan_itwom_client as name-only deps (no PyPI package exists for either), so they need installing from
# their local paths here too, even though ratplan_planner itself never imports them directly.
cd ratplan_planner && python -m venv .venv && .venv/Scripts/pip install -e ".[dev]" -e ".." -e "../connectivity_module" -e "../connectivity_module/ITWOM/itm" -e "../connectivity_module/ITWOM/itwom_client" && .venv/Scripts/pytest
```

`ratplan_terrain`'s own tests that call into `ratplan_itm`/`ratplan_itwom` (`tests/primitives/
test_terrain_profile.py`, `connectivity_module/ITWOM/itwom_client/tests/test_client.py`'s real-terrain
cases) need those packages installed in the same environment as `ratplan_terrain` too —
`pip install -e connectivity_module/ITWOM/itm -e connectivity_module/ITWOM/itwom_client` alongside `-e .`.

`connectivity_module/ITWOM/itwom_client`'s tests need Docker running and the `ratplan-itwom-service` image built (see
`connectivity_module/ITWOM/itwom/README.md`) — marked `docker`, skipped without that marker.

A root `tests/` tree exists (`tests/conftest.py`, `tests/README.md`, config folded into the root
`pyproject.toml`'s `[tool.pytest.ini_options]`) — today it covers `ratplan_terrain/` (`tests/models/`,
`tests/primitives/`, `tests/integration/`), and will grow to cover the DP mission-planner package once that
exists. `pytest` from `RATPLAN/` runs it (excludes `-m integration` by default).

No lint/format tooling configured yet, anywhere in this repo.

- `KONTEXT.md` — original human-written project brief (Swedish). Source of truth for terminology and
  mission inputs/outputs; don't let other docs drift from it.
- `Goal.md` — one-paragraph statement of mission intent, including the "ITWOM as prior + Bayesian
  kriging correction" idea `model.md` §§2–3 formalizes.
- `pseudocode.md` — superseded v1 sketch, kept for reference only.
- `pseudocode-v2.md` — **non-authoritative as of 2026-09-22** (see "Project status" above); historical
  reference only, kept on disk with an in-place banner explaining why.
- `OPEN_ISSUES.md` — running log of upstream issues, known gaps, and unresolved implementation decisions
  discovered while building `ITWOM/`. Separate from `research/ReadingNotes.md` (Emil's own notes, don't
  edit) and from `architecture.md`/`model.md` (the designs, not a punch list).
- `research/reading_list.md` — the GP/kriging/kriging-vs-anisotropy literature `model.md` §§2–4 is built on,
  with full citations and confidence ratings per source.
- `CLAUDE_SESSIONS.md` — running log of what Claude Code sessions did, one entry per session, tied to the
  git commit(s) each one produced. Separate from `OPEN_ISSUES.md` (issues/gaps, not session history).

## What Råttfällan/RATPLAN is

A **mission planner** for a UGV ("Råtta"/rat) team. Given a mission (target location, battery requirement at
target, time limit), it proposes multiple candidate routes/starting positions for the operator crew, each
with an evaluation of how good that option is. It's a planning aid for the befäl (commander) / gruppledare
(group leader), not a control system.

### Terminology (Swedish)

- **Puck** — relay transmitter, extends radio range from the rat
- **Råtta** — small UGV ("the rat")
- **Operatör** — drives the rat, watches the camera feed
- **Navigatör** — plans routes during an active operation, supports the operator, syncs with C2 systems like ATAK

### Sibling projects

RATPLAN is one part of a larger system and is meant to live alongside these sibling repos in the same parent directory:

- **ratak-ai** (`../ratak-ai`) — the server architecture that actually drives/controls the rats (operator + navigator views, image detection, UGV control).
- **ratmap** (`../ratmap`) — offline map service (terrain/satellite/road data) with live pathfinding. This is where `Scan`/route data comes from. It exposes a route-query API and a mutable in-process road graph — **must run with a single worker**, since the graph lives in process memory. See its own README/CLAUDE.md for setup (requires Lantmäteriet credentials for terrain/vector data).
- **rattfallan-demo** (`../rattfallan-demo`) — a standalone local web app (FastAPI + MapLibre, ATAK-inspired dark tactical UI) for manually placing target/start/puck positions and seeing live, real terrain-based RF coverage and real shortest-path road routing. Not `plan_mission()`'s search — a hand-driven demo/animation tool built for screen-recorded presentations. Currently depends on primitives from the archived `rattfallan` package that no longer exist after this restart, so it can't run against this repo as-is (`architecture.md` §8).
- **rattfallan-maps** (`../rattfallan-maps`) — real 10x10km and 20x35km snapshots (roads, land cover, orthophoto tiles, DTM) pulled once from a locally running `ratmap`, used to run `plan_mission()` against real road topology without a live `ratmap` needed afterward.

`../arkiv/RATPLAN - gammal` is the archived predecessor (`rattfallan`) — read from for provenance
(`pseudocode-v2.md`, the package-layout shape, `implementation.md`), never edited.

RATPLAN's algorithm is a *consumer* of ratmap's map data (terrain, land-cover, road graph) — it takes one
snapshot of the specified mission area per planning run and runs its own routing/coverage computation
locally against that snapshot from then on, rather than reimplementing map data collection itself.

## Algorithm — see `pseudocode-v2.md` (control flow) and `model.md` §5 (math)

Core primitives (`architecture.md` §5 diagram, `model.md` §§6–7 for the two that have no math yet):

- `Scan(position) -> CoverageRaster` — RF/line-of-sight coverage grid around a position, out to sender max
  range. Only ever called for the target and for relay-sender positions already chosen — never for every raw
  candidate. Every result is theoretical: a puck is only ever *really* placed once the UGV has physically
  driven there and dropped it, during mission execution — never during planning. Implementation target:
  ITM/ITWOM physics prior (`architecture.md` §§2–3, working) plus a GP/kriging Bayesian correction from live
  RSSI (`model.md` §3) — both implemented in `connectivity_module/ratplan_connectivity/`.
- `Evaluate(position, raster) -> (score, description)` — quantitative 0–1 `score` (exposure/cover via DTM +
  land-cover, with enemy-standoff distance as a soft penalty, combined with an assistance score: path time
  to the supply unit) used for ranking, plus a qualitative LLM-generated `description` carried through to
  output but never used for ranking. Combination rule not yet specified — `model.md` §6.
- `BatteryModel(leg) -> wh_consumed` — energy-consumption model per route leg, independent of `Evaluate`. No
  model yet — `model.md` §7.
- `Samband(road_ids, covered_raster) -> probability` — stub; probability of maintaining comms the whole
  route. No model yet — `model.md` §7.

Structured as a **dynamic program over road positions**, expanding relay-by-relay (0 relays, then 1, up to
`relay_count_max`) — value function, recurrence, and the "eligibility vs. ranking are different functions"
distinction are in `model.md` §5; short version:

- **State**: a road position. **Value** (`best[pos]`): cheapest known path from `pos` back to `target` in
  both time and energy; the ordered puck-drop positions along the way; and `covered_raster`, private to
  that one path — never pooled or merged across candidates, since only one candidate's relays will ever
  really be placed.
- A placed relay's best path to target is computed once, memoized when kept into the frontier — later
  candidates near it only need a short local route plus the relay's memoized cost.
- Each relay level: candidates must be near the *edge* of the new relay's coverage (a hard eligibility
  filter — a point comfortably inside doesn't need this hop's puck), then the top `K` are kept by **pure
  reach**, not `Evaluate` score. Every survivor still gets `Evaluate`, `Samband`, and its own retreat/resupply
  routes computed regardless of whether it also becomes a relay one level deeper.
- Stops when a relay level produces no new frontier, or `relay_count_max` is reached. **This is a beam
  search with no optimality guarantee** — see `model.md` §5's note on beam width `K`.

Output: all candidate starting positions across relay levels 0..R, each with its road path to target, time
and battery cost, relay drop points in drive order, that candidate's own private coverage raster, `Evaluate`
score + description, a `Samband` probability, and retreat/resupply routes — ranked by `Evaluate` score across
all levels combined.

## Key inputs/outputs (from `KONTEXT.md`)

**Mission input**: target location, required battery remaining at target, time limit.
**Operator input**: number of available pucks, minimum standoff distance from known enemy positions.
**From C2/ratmap**: last known enemy positions, friendly unit positions, other rats and their planned routes, user-drawn routes, mined/closed roads. (Not all of these are wired into `pseudocode-v2.md` yet — see its "Inputs" section for what's deferred.)

**Output per candidate**: samband (probability of maintaining comms the whole way), type of overhead cover (buildings, trees), mission duration, area coverage (connectivity to the rat), free withdrawal routes, resupply/maintenance feasibility, and a description of the route (protection, trafficability).
