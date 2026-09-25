# RATPLAN — Claude Code session log

A running log of what Claude Code sessions did in this repo, one entry per session, newest first. Each
entry ties to the git commit(s) that captured its work, so "what changed and why" can be found without
digging through commit messages or chat history. Separate from `OPEN_ISSUES.md` (upstream/design issues
discovered along the way, not session-by-session) and `research/ReadingNotes.md` (Emil's own reading notes,
not to be edited).

This log starts 2026-09-22 — earlier work (the ITM/ITWOM implementations, real-terrain wiring, the
`ratplan_planner` scaffolding) predates it and isn't backfilled; see `OPEN_ISSUES.md`'s own changelog and
`CLAUDE.md`'s "Project status" section for that history, and `git log` for the commits themselves.

---

## 2026-09-22 — Scan implemented: ITM physics prior + fixed-grid Bayesian/GP correction

**Commit:** `43c35fe` "GP implementation, first try"

Implemented `Scan(position) -> CoverageRaster` end to end — the last unimplemented primitive blocking a
real `ratplan_planner` (`CLAUDE.md`'s "Not yet built" list). Two parts, per Emil's explicit split:

1. **`ItmGridScan`** (`ratplan_planner/primitives/scan.py`) — the physics-prior grid scan. Always pure
   ITM, never touches observations or GP state ("Scan will always be the ITWOM/ITM prior distribution.
   Should never care about the update" — Emil). Uses ITM at reliability 90%/confidence 50% (a conservative
   point estimate). `CoverageRaster` (`models/coverage.py`) gained `mean_db`/`variance_db` fields alongside
   the existing boolean `covered`, plus `covered_from_margin()` deriving coverage from the link-margin/Φ
   threshold (model.md §4).

2. **`GpCorrector`** (`ratplan_planner/primitives/gp_correction.py`) — the Bayesian correction layer,
   updating the coverage belief from live RSSI as the UGV drives. Landed on a **fixed-grid recursive
   Bayesian filter**: a Subset-of-Regressors/Deterministic-Training-Conditional sparse-GP construction
   (Csató & Opper, 2002 lineage) with inducing points fixed at the raster's own cells — one `O(N³)`
   Cholesky factorization at construction, then `O(N²)` per `.observe()` call regardless of how many
   observations accumulate over a mission. Chosen after working through the alternatives with Emil (exact
   recursive Cholesky updates, NNGP/local truncation, sparse inducing-point streaming GPs, sliding windows)
   given the UGV streams continuously while driving, not "tens of points once." Uses an ARD kernel
   (`kernel.py`) over an augmented feature vector (`features.py`: position, elevation, bearing sin/cos,
   line-of-sight obstruction count) per model.md §3.5 option 3 — Emil's own idea, formalizing "correlate on
   similar points, not just close ones."

**A real design bug found via the plan's own verification step, not anticipated going in:** benchmarking
`ItmGridScan` against real terrain (`../ratmap/snapshots/real_map_scenario_north`) showed under 1% coverage
at the originally-planned grid sizing (cell count derived from a closed-form free-space link-budget
formula). Root cause: at a 2m antenna height, real ITM path loss on this terrain already exceeds a typical
link budget within several hundred meters to ~1km, while free-space math alone suggested tens of km — a
>10x overestimate from real terrain/ground-effect loss at low antenna height (the exact "ITWOM/ITM alone
isn't good enough for our terrain and scale" problem `Goal.md` motivates the whole GP-correction layer
with). Fixed by decoupling resolution from extent: `target_cell_size_m` is now a fixed resolution target,
and grid extent is `min(radio.max_range_m(), max_extent_m)` — the link budget still shrinks the grid for a
genuinely short-range radio, but a hard cap stops an optimistic free-space number from wrecking resolution
for a realistic one. Re-verified: ~98% near-sender coverage with a real, visible boundary, 0.5-2.8s per
scan depending on cap/resolution.

**Also fixed:** `ratplan_planner/pyproject.toml` was missing `ratplan-itm`, `ratplan-itwom-client` (needed
transitively via `ratplan_terrain.primitives.terrain_profile`'s unconditional import), and `scipy` as
declared dependencies despite needing all three now — added, and updated `CLAUDE.md`'s setup command to
match.

**Tests:** 33 new/updated, all passing offline against synthetic in-memory DTMs (no live ratmap/Docker
needed) — `tests/test_coverage.py`, `tests/primitives/{test_features,test_kernel,test_scan,test_gp_correction}.py`.
Key invariants checked: zero observations → posterior exactly equals the prior (model.md §3.1's
graceful-degradation claim); posterior variance never increases after an observation (GPML Ex. 4).

**Not done / explicitly out of scope this session:**
- No live RSSI ingestion pipeline exists anywhere in this repo — `GpCorrector` is a tested, reusable
  component, not wired into a mission-execution loop (that's `ratak-ai`'s territory, or a future
  mission-runner).
- Parameter estimation (`α`, `β`, per-dimension lengthscales) are placeholder constants — no Nordic-forest
  field data exists yet to calibrate them (model.md §3.6).
- ITWOM (vs. ITM) not used as the mean surface — deferred per architecture.md §3.1's own "decided
  empirically once both are available" framing; `ItmGridScan` is ITM-only for now.
- The DP itself (`planner/dp.py`) is still unbuilt; `Scan` is only one of its five primitives.

**Asana:** logged against `C1. Batch GP-posterior implementerad` and `C3. Online-uppdatering implementerad`
(under "RATPLAN: patentansökan sambandsmodul") — both left open, since the implemented method (fixed-grid
SoR/DTC) differs from what each ticket's note specifically names (C1: plain batch Cholesky; C3: Fink &
Kumar / Quattrini Li / arXiv:2607.17954) and that gap should be checked against the patent strategy before
either closes.

---

## 2026-09-23 — Restructure: `connectivity_module/` extracted from `ratplan_planner`/`ITWOM`

**Commit:** `1788d48` "Extract connectivity_module/ from ratplan_planner and ITWOM" (committed
2026-09-25; the commit also carries the GP kernel's `distance_m` feature/`lengthscale_distance`, which
landed in the moved files after this session and before the commit)

Per Emil: `ratplan_planner` should hold only the DP/mission-planning algorithm, not the concrete
`Scan`/GP connectivity implementation. Pulled everything that computes RF connectivity into one new
top-level `connectivity_module/` folder:

- `ITWOM/` moved wholesale to `connectivity_module/ITWOM/` — internal structure (`itm/`, `itwom/`,
  `itwom_client/`, each's own `pyproject.toml`/`.venv`) untouched; their relative cross-references to each
  other (`../itwom/Dockerfile` etc.) still resolve correctly since only the parent folder relocated.
- `ratplan_planner`'s former `models/coverage.py` and `primitives/{scan,gp_correction,kernel,features}.py`
  moved to a new sibling package, `connectivity_module/ratplan_connectivity/` (own `pyproject.toml`, name
  `ratplan-connectivity`) — mirrors how the repo root today *is* `ratplan_terrain`'s own package. Internal
  imports renamed from `ratplan_planner.{models,primitives}...` to `ratplan_connectivity.{models,primitives}...`
  throughout the four moved files and their five moved test files.
- `ratplan_planner` now only imports `CoverageRaster` from the new `ratplan_connectivity` package
  (`primitives/protocols.py`, `models/results.py`); its `pyproject.toml` dropped `ratplan-itm`/
  `ratplan-itwom-client`/`scipy` (nothing left in the package needs them) and added `ratplan-connectivity`.
- Updated every current (non-historical) `ITWOM/...` path reference in `CLAUDE.md`, `architecture.md`,
  `OPEN_ISSUES.md`, and `model.md` to `connectivity_module/ITWOM/...`; left each doc's own dated
  changelog/session-log entries and `architecture.md` §§5–6 (already flagged non-authoritative/historical)
  untouched, adding new dated entries instead where a changelog convention exists.
- Deleted the now-stale gitignored `.venv`/`*.egg-info` directories under the old `ratplan_planner/` and
  `ITWOM/itm/`, `ITWOM/itwom_client/` locations — regenerate per `CLAUDE.md`'s updated setup commands.

**Not done this session:** no code review/audit of the moved files' actual logic — this was a pure
structural move plus import/doc updates, verified only by re-running each affected package's test suite
(see plan's Verification section for the exact commands).

---

## 2026-09-24/25 — `simulation_tool/`: visual frontend over the real Scan + GP correction

**Commit:** `07d9fca` "Add simulation_tool: visual frontend over real Scan + GP correction"

Per Emil: a new, separate `simulation_tool/` (not an addition to `mapviz/`, which stays terrain+roads
only) that's a thin visual frontend over the real `ratplan_connectivity` functions, as the seed of a
broader simulation tool. Built 2026-09-24 from plan `add-the-possibility-to-floating-moore.md`, then
verified and extended 2026-09-25:

- `server.py` (FastAPI): `POST /api/relay` runs the real `ItmGridScan` and builds a fresh `GpCorrector`;
  `POST /api/observe` folds a manually-typed RSSI reading in via `GpCorrector.observe()`;
  `/api/reset`, `/api/state` (restores the page after a browser refresh), `/api/hillshade`, `/api/roads`.
  **Single active relay:** placing a new one discards the old corrector and its observations. No
  scan/GP math is reimplemented here. `CoverageRaster` is flipped north-up server-side (`np.flipud`) and
  `margin_db` is exposed as a display value.
- Frontend (MapLibre, Gremlin design-system chrome): one-shot click modes for relay/observation, a
  `margin_db` heatmap using `rattfallan-demo`'s colour ramp.
- Doc updates: `architecture.md` §8/§9 superseded-notes (the coverage layer went here, not into
  `mapviz`) and a `CLAUDE.md` "Project status" bullet. These are in `1788d48`, since those files also
  carried the restructure edits.

**Verified 2026-09-25** against `real_map_scenario_north`, by calling the endpoints directly (not a
browser click-through, which Emil did himself): all endpoints behave as planned, a −110 dBm reading
lowers nearby margin by up to ~32 dB, and refresh-restore and reset work.

**Found while verifying:**
- **Scan cost.** At the tool's default 800 m extent / 50 m cells (32×32), a scan takes ~0.7 s, but every
  cell comes out covered (the 130 dB default link budget reaches far beyond 800 m), so there's no visible
  coverage edge. At 3000 m (120×120) the edge shows, but a scan takes ~42 s: about 57× the time for 14×
  the cells, so cost per cell grows with extent. Not investigated further. Still no derived performance
  budget (`architecture.md` §9).
- **GP reach is very local with `ArdKernel`'s defaults.** One observation mostly affects cells within
  ~100–200 m (31 cells >1 dB), because the summed-exponent kernel's tight `lengthscale_elevation` (20 m)
  and `lengthscale_los_count` (1) terms stop correlating cells wherever the terrain changes. These are
  documented placeholders (`kernel.py`), not a bug. Added env-var overrides for all five lengthscales
  in `server.py` (`SIMULATION_TOOL_LS_*`; an unset var keeps `ArdKernel`'s own default, and `kernel.py`
  itself is untouched). With position/distance 500, elevation 60, LOS count 3, one reading changes 250
  cells >1 dB over ~1 × 1 km. Calibrating these properly still needs field data (`model.md` §3.6).
