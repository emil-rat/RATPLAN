# RATPLAN — open issues & concerns log

Ändringslogg:
2026-09-19 - Skapad av Claude — first entries from implementing `ITWOM/itm/` (architecture.md §3, open item 1).
2026-09-19 - Claude — `itm/` moved to `ITWOM/itm/`, added `ITWOM/itwom/` (SPLAT!/ITWOM as a Docker service, GPL-2.0) and `ITWOM/itwom_client/` (RATPLAN's own arm's-length client), at Emil's request to co-locate both prior-mean implementations. New entries below under "ITWOM/itwom service".
2026-09-21 - Claude — real Lantmäteriet terrain wired into both ITM and ITWOM via a new minimal `ratplan_terrain/` package; synthetic ITWOM terrain (`Terrain`/base+ridge) removed outright, not kept as a fallback. See "Real terrain wired into both ITM and ITWOM" under Resolved/superseded.
2026-09-22 - Claude — carryover audit of `pseudocode-v2.md`/`architecture.md` §§5–6/`model.md` §5 against the archived `rattfallan` project found real, not just aspirational, problems; `pseudocode-v2.md` and `architecture.md` §§5–6 marked non-authoritative at Emil's request, DP being re-derived from scratch without the archive. See "Archive carryover audit" under DP/mission-planner design.

Running log of upstream issues, known gaps, and unresolved decisions discovered while building RATPLAN, kept separate from `research/ReadingNotes.md` (which is Emil's own reading notes, not to be edited) and from `architecture.md` (which is the design, not a punch list). Newest entries at the top of each section.

---

## Upstream dependency issues

### itmlogic #64 — "Interpreting 'reliability'"
[github.com/edwardoughton/itmlogic/issues/64](https://github.com/edwardoughton/itmlogic/issues/64) — open.

Reported ambiguity in how itmlogic's `reliability` output parameter should be interpreted. Relevant to `ITWOM/itm/` directly: `predict_point_to_point()` returns one `PathLossEstimate` per (reliability%, confidence%) pair, and RATPLAN will need to pick a specific quantile to convert path loss into a connectivity probability for the coverage map (architecture.md §2). If the semantics of that parameter are ambiguous upstream, RATPLAN's choice of quantile inherits that ambiguity. **Action before relying on a specific reliability value for a real decision: read the full issue thread and cross-check the interpretation against the original NTIA ITM documentation (not just itmlogic's docstrings).**

### itmlogic maintenance status — correction from earlier session estimate
Earlier in this session I described itmlogic as showing "no sign of very recent activity." That was based on an incomplete fetch. Correction, checked directly against PyPI: latest release is **1.2, published March 2025** — so it's more actively maintained than first estimated, not a dormant 2020-only project. Still modest (74 stars, 24 forks, 7 open issues, 4 open PRs as of this session), but not stale.

### itmlogic ships no packaged point-to-point entry point
`itmlogic_p2p()`, the documented point-to-point orchestration function, lives only in the upstream repo's `scripts/p2p.py` — it is **not** part of the installed `itmlogic` PyPI package (confirmed: its imports include a local `terrain_module` that isn't shipped, and the function itself isn't under `itmlogic/`). `ratplan_itm.point_to_point.predict_point_to_point` is therefore our own orchestration, adapted from that upstream example, calling itmlogic's actual public subroutines (`qerfi`, `qlrpfl`, `avar`) unmodified — see the docstring in `ITWOM/itm/ratplan_itm/point_to_point.py`. Not a blocker, just means "itmlogic as-is" in practice meant "itmlogic's subroutines as-is, our glue code around them," not "an official p2p API used unmodified." Worth re-reading if itmlogic ever does package an official entry point, to see if it's worth switching to.

## ITWOM/itwom service

### Single-tile limitation
The request/response contract requires tx and rx to fall within the same 1x1 degree SDF tile (`itwom_cli.py` only ever writes one tile). Fine for short relay hops (Råttan's actual use case), not for long-range links. Not fixed — just documented as a constraint, since it matches the expected use case.

### Not validated against a real published reference case
Unlike `ITWOM/itm/`'s test (which reproduces itmlogic's own documented worked example with known expected loss values), `ITWOM/itwom_client/tests/test_client.py` now runs against real terrain (a ratmap snapshot's `height.tif`, via `ratplan_terrain`) but only asserts relative/physical-sanity properties (path loss exceeds free-space loss; real terrain relief changes the result vs. a flattened version of the same grid) — not against any independent published ITWOM result with known expected dB values. A tighter validation (matching a documented SPLAT!/ITWOM worked example, if one exists with known expected output, the way the Crystal Palace/Mursley case anchors `ITWOM/itm/`) is still open.

### `write_sdf()`'s index mapping was reverse-engineered, not copied from upstream
The `.sdf` file format and its (x,y)→(lat,lon) index mapping were derived by reading `splat.cpp`'s `GetElevation()` (write target) and `LoadSDF_SDF()` (read order) directly — not by reusing `srtm2sdf.c`'s own array-fill logic, since that logic is for converting real SRTM `.hgt` files, which isn't what we're doing. The derivation is documented in `write_sdf()`'s docstring. It was verified empirically (the flat-terrain sanity test and the ridge-obstruction test both produce physically sane, differently-shaped results), not against a second independent implementation — worth a closer look if terrain-dependent results ever look wrong in a way that's hard to explain physically.

### Docker dependency
The service requires Docker Desktop running locally (or wherever this gets deployed) — no native-compiler fallback was built this session (Emil chose Docker over MSYS2/WSL when asked). `ITWOM/itwom_client`'s tests are marked `docker` and skipped by default without a marker filter, so a plain `pytest` run elsewhere in the workspace won't fail for lack of Docker — but anyone actually running RATPLAN's connectivity module against ITWOM needs Docker available at runtime, not just at test time.

### SPLAT! pinned to a specific commit
`ITWOM/itwom/Dockerfile` builds from `jmcmellen/splat` pinned to commit `08f06f5` (2026-09-19), not floating on `main` — deliberate, since this is GPL-2.0 third-party source and silent upstream changes shouldn't silently change RATPLAN's propagation results. Update the pin deliberately if upstream fixes something relevant, not automatically.

## Validation gaps

### `ITWOM/itm/` validated against itmlogic, not against NTIA's own reference implementation
`ITWOM/itm/tests/test_point_to_point.py` reproduces itmlogic's own documented worked example (Crystal Palace → Mursley, 41.5 MHz) and pins the resulting output as a regression baseline. This confirms the wrapper is wired correctly against itmlogic's subroutines. It does **not** independently confirm itmlogic's own numbers match NTIA's C++ reference (`NTIA/itm`) output for the same inputs — that cross-check was flagged as a possible spike in the prior session turn and was not done (Emil chose to implement itmlogic as-is instead of spiking the comparison first). Worth doing before trusting absolute dB values for a real siting decision, not before continuing architecture/integration work.

### Ground constants and climate are uncalibrated defaults
`GroundConstants` defaults (relative permittivity 15, conductivity 0.005 S/m) and `Climate.CONTINENTAL_TEMPERATE` in `ITWOM/itm/ratplan_itm/environment.py` are itmlogic's own example values, not chosen for Swedish/Nordic terrain. Same category of gap as `research/reading_list.md`'s flagged Nordic-β and vegetation-attenuation gaps — a field-calibration problem, not a code problem. Exposed as overridable parameters so calibration can happen without touching this module's code.

---

## DP / mission-planner design

### Archive carryover audit (2026-09-22) — pseudocode-v2.md / architecture.md §§5–6 / model.md §5 not to be trusted as spec
Emil asked that the archived predecessor (`../arkiv/RATPLAN - gammal/`, and a diverged sibling snapshot
`../arkiv/rattfallan/` the current repo hadn't previously consulted) not be used as a source for this restart
at all, after a review turned up real problems, not just unvalidated stubs:

- `pseudocode-v2.md` was restored and labeled "the authoritative spec, verbatim," but the archive's own final
  `planner/dp.py`/`primitives/evaluate.py` had already diverged from it (a separate puck-placement vs.
  starting-position `Evaluate` split, folding the rat's own onboard antenna into reported coverage via
  `covered_raster | start_scan(c)`, a relay-position eval cache) — none of that is reflected in the pseudocode.
- `model.md` §5's candidate-eligibility (`near_edge`) formula restates the archive's `GridCoverageRaster.near_edge`
  as clean math, dropping that method's own docstring admission that it's a straight-line/isotropic-circle
  heuristic that's *wrong* once the coverage raster has a real DTM-LOS shape — exactly what `Scan` now
  produces via ITM/ITWOM. Don't port this formula; eligibility needs re-deriving against the real raster shape.
- The archive's local routing layer (`routing/router.py`) hand-duplicates `ratmap`'s `speed_based_weight`
  under an unstated assumption that road cost is symmetric — the archive's own `requirements-ratmap.md`
  flagged this as conditionally-true-today, not invariant, and a drift risk if `ratmap`'s weight function
  ever changes. Prefer querying `ratmap` for route cost over re-deriving its weight function locally.
- Archive's `Evaluate`/`Scan` defaults were literally `random.random()` and a flat circle per the archive's
  own `CLAUDE.md` — confirms nothing about their scoring logic should be ported (already moot: `Scan` is real
  physics now, `Evaluate`'s combination rule is already flagged as unspecified in `model.md` §6).

Action taken: `pseudocode-v2.md` and `architecture.md` §§5–6 marked non-authoritative in-place (banners at
each doc's top), kept on disk for historical context only. `model.md` §5 not yet marked — same caveat applies
(the `near_edge` formula above lives there) but hasn't been annotated yet. The DP (state/value definition,
recurrence, eligibility, routing) is being re-derived from scratch against `KONTEXT.md` and the real
`ITWOM`/`ratplan_terrain` primitives, not from the archive.

## Resolved / superseded

### Real terrain wired into both ITM and ITWOM
Both "itmlogic's own terrain/DEM tooling not used" and "Terrain is synthetic, not real DEM data" (below) are resolved: a minimal `ratplan_terrain/` package now exists (`ratplan_terrain/primitives/terrain.py::DtmSampler`, `ratplan_terrain/io/{ratmap_client.py,dtm_loader.py}`) that samples real elevation from ratmap's downloaded Lantmäteriet DTM — either via a live `GET /api/snapshot/height` call or a pre-baked snapshot's `height.tif` read straight off disk (the same file `mapviz/server.py` reads). `ratplan_terrain/primitives/terrain_profile.py` bridges that into each backend: `terrain_profile_from_dtm()` produces `ratplan_itm.TerrainProfile` directly (a real elevation profile, matching `ITWOM/itm/`'s existing decoupled-from-GIS contract exactly); `elevation_grid_from_dtm()` produces `ratplan_itwom.ElevationGrid`, a coarse (~100x100) regular grid over the tx/rx link's bounding box that `ITWOM/itwom/wrapper/itwom_cli.py`'s `elevation_m()` now bilinear-interpolates into its SPLAT! `.sdf` tile, replacing the old base+ridge formula outright (no synthetic-terrain code path kept). The `.sdf` file format/index-mapping code in `write_sdf()` itself is untouched — only its elevation *source* changed.

Deliberate tradeoff for ITWOM: the grid is coarser than SPLAT!'s native 1200-points-per-degree `.sdf`
resolution, sized to just the link's bounding box (plus a margin) rather than a whole 1x1-degree tile, to
keep the JSON request payload small. Revisit if a real obstructed-path validation ever shows this
resolution is too coarse to reproduce a known terrain feature correctly.

*(older resolved entries, if any, go above this one)*
