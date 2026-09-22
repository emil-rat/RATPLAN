# RATPLAN Architecture — system/backend design

Ändringslogg:
2026-09-19 - Skapad av Claude (session with Emil J) — first architecture pass, scoped to the connectivity module and its ITM implementation, per Goal.md.
2026-09-19 - Extended by Claude (separate session with Emil J) — §§6–9 added to cover the rest of the program (package layout, testing strategy, visual test tooling), §5 renumbered to §10. §§1–4 (connectivity/ITM) are untouched — that module is being implemented live in `itm/` by another session this same day; do not edit §§1–4 or `itm/` without checking with that session first. Also restored [`pseudocode-v2.md`](./pseudocode-v2.md) (the DP mission-planner spec `KONTEXT.md` already pointed to, missing from this fresh restart) from the archived `rattfallan` implementation — see §7's note on provenance.
2026-09-19 - By the session referenced above (the one building the connectivity module) — moved `itm/` to `ITWOM/itm/` and started `ITWOM/itwom/` (SPLAT!/ITWOM as an arm's-length subprocess service, per §3.1) alongside it, at Emil's request to keep both prior-mean implementations under one parent folder. Updated every `itm/` path reference below (§3.3, §6–§10) accordingly — content/decisions in §§6–9 otherwise untouched.
2026-09-19 - Same session — `ITWOM/itwom/` (SPLAT!/ITWOM, GPL-2.0, Docker) and `ITWOM/itwom_client/` (RATPLAN's own arm's-length client) built and verified end-to-end: image builds, container runs, client calls it successfully, ITWOM vs. classic ITM diverge as expected on a synthetic obstructed path (§3.3 updated, §10's open item retired). Known gaps (synthetic terrain, single-tile limit, no independent reference validation) logged in `OPEN_ISSUES.md`.
2026-09-20 - Claude (session with Emil J) — split the math out of this file into [`model.md`](./model.md): former §2 ("Connectivity module internals," the GP/kriging/decomposition math) now lives there as §§2–4; the math-flavored items in the old §10 open-items list (joint-vs-independent GP, Nordic β/anisotropy) moved there too, as model.md §8. This file keeps everything about *where code runs and how it's organized* — the connectivity module's own service-boundary/licensing design (§§2–4 below, renumbered), package layout, testing, mapviz. Sections renumbered throughout (old §§6–10 → new §§5–9) since there's no longer a numbering gap to preserve. When architecture and model disagree on what a component computes, model.md wins; when they disagree on where/how it runs, this file wins.

Companion docs: [`model.md`](./model.md) (the mathematical model — GP/kriging connectivity correction, the DP's value function/recurrence, and everything else in the "what is being computed" category), [`Goal.md`](./Goal.md) (mission intent), [`KONTEXT.md`](./KONTEXT.md) (terms, algorithm sketch), [`pseudocode.md`](./pseudocode.md) (superseded v1 Scan/Evaluate sketch), [`pseudocode-v2.md`](./pseudocode-v2.md) (authoritative DP mission-planner spec), [`research/reading_list.md`](./research/reading_list.md) (GP/kriging math `model.md` leans on).

---

## 1. System shape

RATPLAN's output, per KONTEXT.md, is a ranked set of (start position, path, relay count) proposals for driving Råttan to a target. `pseudocode.md` already fixes the control loop: `Scan(sender, coordinates)` produces a coverage heatmap from a transmitter; `Evaluate(coordinates)` scores a candidate location using that heatmap plus other cost layers. Everything below is the internals of `Scan` — the connectivity/RF module — since that's this session's scope.

```
                 ┌──────────────────────────┐
                 │   ratmap (DEM, land      │
                 │   cover, roads, enemy    │
                 │   pos, other rat paths)  │
                 └───────────┬──────────────┘
                              │ terrain profile, clutter
                              ▼
                 ┌──────────────────────────┐
Live RSSI  ─────▶│   Connectivity module    │────▶ coverage posterior
from Råttan      │   (this doc)             │      mean + variance
                 └───────────┬──────────────┘
                              │ Scan() results
                              ▼
                 ┌──────────────────────────┐
                 │  Mission planner core     │
                 │  (road network search,    │
                 │  Evaluate(), relay        │
                 │  placement — pseudocode)  │
                 └──────────────────────────┘
```

## 2. Connectivity module — what it computes, and where that's designed

Per Goal.md, the design is **physics prior + online Bayesian correction**, not physics alone. The math for
both halves — the GP formulation, the shadowing-correlation model, parameter estimation, the online-update
approach, and the open modeling questions (joint-vs-independent GP per relay, terrain anisotropy, Nordic-β
calibration) — is `model.md` §§2–4, not repeated here. This section and §3 are about the two physics-prior
implementations that feed `model.md`'s `m(x)`: where they run, how data flows into them, and why they're
split across a licensing boundary.

`Scan(sender, coordinates)`'s output — posterior mean **and** variance per cell (`model.md` §3.1) — is what
`Evaluate()` and relay placement (pseudocode step 1) consume; variance is meant to eventually drive "where
should the next relay/measurement go" (`model.md` §3.1, §3.3's forward pointer to Tier 3 of the reading
list), though that consumer isn't built yet either.

## 3. ITM implementation

### 3.1 Decision: ITM in-process as the GP mean; ITWOM available via an arm's-length service if needed

**Why**, and the licensing research behind it — see §4. Short version, corrected after checking the actual GPL FAQ text (not just secondhand summary): calling a GPL-2.0 program as a genuinely separate process — subprocess/CLI/socket/HTTP, no shared internal data structures, no linking — does not make the calling program GPL. The FSF's own FAQ says so directly ("pipes, sockets and command-line arguments... the modules normally are separate programs"), and since GPL-2.0 (unlike AGPL) has no network clause, running SPLAT!/ITWOM as an internal service that RATPLAN's own code calls over an API means GPL's distribution trigger may never fire at all — and even if the whole stack ships on-prem to a customer, RATPLAN itself can stay proprietary as long as the two communicate at arm's length and SPLAT!'s own (already-open) source stays available.

So the plan:
- **Base ITM (NTIA reference / itmlogic, §3.3) runs in-process**, as the default `m(x)` mean surface for the GP layer (`model.md` §2–3). It's public-domain-equivalent — no reason to put it behind a service boundary; no license reason to avoid linking it directly.
- **ITWOM (via SPLAT!) runs as a separate service/subprocess**, called through a defined API (CLI invocation or a thin RPC/HTTP wrapper around `splat`/`itwom3.0.cpp`), *not* vendored into RATPLAN's own codebase or statically linked. This keeps RATPLAN's own code out of GPL scope while still getting ITWOM's obstruction/RTE accuracy where it matters (short-range, obstructed paths — the "terrain and scale" weakness Goal.md flags). Use it as an alternative/supplementary mean surface alongside or instead of ITM, decided empirically once both are available.
- Two implementation rules that keep the arm's-length argument solid: don't share complex internal data structures across the boundary (pass terrain profile + link parameters in, get path loss back — not shared memory/objects), and don't fork or vendor `itwom3.0.cpp` into RATPLAN's own repo/build — call an unmodified SPLAT! install as an external dependency, the way you'd call `ffmpeg` or a GPL database server.
- Residual, lower-severity caveat: `itwom3.0.cpp` itself carries no explicit copyright/license notice from Shumate (§4.2) — a chain-of-title question independent of GPL scope, not resolved by the API boundary. Low likelihood of actually mattering (the code was co-developed with SPLAT!'s maintainer and filed publicly with the FCC, not misappropriated), but worth a one-line disclosure if this ever goes through legal review before a defense-customer delivery.

### 3.2 Data flow into ITM

- **Terrain profile extraction**: for a (sender, receiver) pair, sample elevation along the great-circle path from `ratmap`'s DEM at ITM's required profile resolution.
- **Model parameters**: frequency (Råttan's relay radio band), antenna heights, ground constants (permittivity/conductivity — climate/terrain-class dependent, calibratable per `model.md` §3.6), polarization, variability mode (point-to-point, per KONTEXT's need for specific link predictions rather than area-statistical predictions).
- **Batching for `Scan()`**: one sender location needs path loss to every cell in the area of interest — batch profile extraction + ITM calls over the grid; this is the perf-sensitive path since it reruns per candidate relay location in the pseudocode's iterative relay-placement loop.
- **Output**: per-cell path loss → convert to link margin/probability-of-connectivity given Råttan's radio's sensitivity and TX power (`model.md` §4 has the proposed, not-yet-validated conversion) — this is the `m(x)` mean surface handed to the GP layer in `model.md` §3.

### 3.3 Implementation options

| Option | License | Notes |
|---|---|---|
| Port [NTIA/itm](https://github.com/NTIA/itm) (C++ reference) directly, wrap for our stack | Public-domain-equivalent (US govt work) | Most authoritative reference; matches FCC/NTIA validation. |
| Use [itmlogic](https://github.com/edwardoughton/itmlogic) (Python port of ITM only) | MIT (+ must retain NTIA's attribution text, per ITM's own terms) | **Implemented** as [`ITWOM/itm/`](./ITWOM/itm/), as-is. If the rest of RATPLAN's stack is Python, this avoids a C++ binding layer. Not yet cross-validated against the NTIA C++ reference — see `OPEN_ISSUES.md`. |
| SPLAT! (unmodified upstream install, e.g. [jmcmellen/splat](https://github.com/jmcmellen/splat)), for ITWOM specifically | GPL-2.0 (package-level) | **Implemented** as [`ITWOM/itwom/`](./ITWOM/itwom/) (the GPL-2.0 Docker service, unmodified upstream SPLAT! pinned to a specific commit) + [`ITWOM/itwom_client/`](./ITWOM/itwom_client/) (RATPLAN's own arm's-length caller). Verified end-to-end against a synthetic obstructed path; ITWOM vs. classic ITM (`-olditm`) diverge ~14 dB as expected. Terrain is synthetic, not real DEM data yet — see `OPEN_ISSUES.md`. |

ITM options are safe to embed directly in-process in a closed-source deliverable — no licensing reason to isolate them. The SPLAT!/ITWOM row is deliberately architected as an external service, not an in-process dependency; keep that distinction in the implementation (§3.1) rather than collapsing it back into a single "ITM library" choice. Decision on C++-wrapped-vs-native-Python for the ITM path is a stack/perf question, not a licensing one — worth a quick follow-up once RATPLAN's service language is settled (KONTEXT.md references a Python `pyproject.toml`/`requirements.txt` in the archived implementation, so itmlogic is the likely default).

## 4. Licensing research (ITWOM open libraries)

Question asked this session: are there open ITWOM libraries, and can they be used freely?

### 4.1 Base ITM (Longley-Rice) — clean

[`NTIA/itm`](https://github.com/NTIA/itm) is NTIA/ITS's own reference implementation. Its `LICENSE.md`, fetched directly:

> This software was developed by employees of [NTIA]... works of NTIA employees are not subject to copyright protection within the United States [per the US-government-work doctrine]... You may improve, modify, and create derivative works of the software... Please provide appropriate acknowledgments of NTIA's creation of the software in any copies or derivative works.

No copyleft, no field-of-use restriction, no commercial-use bar — just "AS IS," no warranty, and a request (not a hard requirement) for acknowledgment. **Safe to use straight up**, including in a closed-source deliverable, per §3.1's decision. [`itmlogic`](https://github.com/edwardoughton/itmlogic) (Python port, ITM only — does not include ITWOM) is MIT-licensed on top of that, same conclusion.

### 4.2 ITWOM v3.0 (Shumate's extension) — genuinely ambiguous, be careful

ITWOM adds the obstruction/RTE handling that's better for short-range, obstructed paths than plain ITM — exactly what Goal.md calls out. It is not separately, cleanly licensed:

- The canonical source (`itwom3.0.cpp`, e.g. in [jmcmellen/splat](https://github.com/jmcmellen/splat/blob/main/itwom3.0.cpp)) carries only a **provenance/history comment block** (traces lineage back to the public-domain ITM, lists the chain of contributors and dates) — fetched directly, confirmed **no copyright notice, license grant, or usage-restriction text anywhere in the file**.
- Sid Shumate published the ITWOM v3.0 source as part of a public comment filed with the FCC (Docket 10-152). John Magliacane then folded it into **SPLAT!**, which is licensed **GPL-2.0** as a whole project on GitHub. But that GPL declaration is SPLAT!'s (the integrator's), not a license grant made by Shumate for his own code specifically — there's no documented instance of Shumate himself licensing his ITWOM additions under GPL or anything else.

Practical read: **two separate risks, of very different severity.**
1. **Copyleft risk — real, but containable.** If you copy `itwom3.0.cpp` (or a wrapper like `pyitwom3`) directly into RATPLAN's own codebase/binary, or link it in-process, the combined work is arguably obligated to be GPL-2.0-compatible on distribution. But per the FSF's own GPL FAQ (checked directly, quoted in §3.1): a program that calls a GPL program as a genuinely separate process — pipes, sockets, CLI args, no shared internal data structures — stays separate under GPL, and GPL-2.0 has no network clause, so a privately-run service you call over an API never triggers distribution obligations on your own code at all. **This is the containment strategy adopted in §3.1** — ITWOM/SPLAT! runs as an isolated service RATPLAN calls at arm's length, not code merged into RATPLAN's own repo/binary.
2. **Chain-of-title risk**, independent of (1) and *not* fixed by the API boundary — because Shumate's own code carries no explicit license notice, it's not fully documented what rights SPLAT! holds to redistribute it. Low-severity in practice (publicly filed with the FCC, developed in cooperation with SPLAT!'s maintainer over years, not misappropriated code) but worth disclosing if this goes through a formal legal review before a defense-customer delivery.

**Conclusion: ITWOM is usable, not off the table — just not as code merged into RATPLAN itself.** §3.1 is the resulting design: ITM in-process (clean lineage, no reason to isolate it), ITWOM behind a service boundary (arm's-length call, unmodified upstream SPLAT! install, no vendoring).

---

## 5. Full program architecture

> **§§5–6 NON-AUTHORITATIVE — historical reference only, 2026-09-22.** The DP structure, package layout, and
> "carried forward unchanged" framing below were inherited from the archived `rattfallan` project. A carryover
> audit found the restated eligibility math doesn't hold for a real terrain-shaped coverage raster, the local
> routing layer hand-duplicates `ratmap`'s weight function under an unstated symmetric-cost assumption the
> archive's own docs flagged as conditional (not invariant), and `pseudocode-v2.md` (§5's other source) was
> itself already stale relative to the archive's own final code (see `OPEN_ISSUES.md`). Per Emil's 2026-09-22
> instruction, the archived project is not a source for this restart — §§5–6 are kept for historical context
> only. The DP (shape, value function, primitives, package layout) is being re-derived from scratch.

§§1–4 above are the internals of `Scan` — one primitive in a larger algorithm. This section places that module in the whole program, per `pseudocode-v2.md` (restored from the archived `rattfallan` implementation — see §6's provenance note) and the predecessor's `implementation.md`/`CLAUDE.md`, updated for this restart's connectivity design.

The predecessor project (archived at `arkiv/rattfallan`) already answered the shape question once, under one hard constraint carried forward here: **modularity** — every "hard" primitive (`Scan`, `Evaluate`, `BatteryModel`, `Samband`, local `route()`) is independently swappable, without the DP or any other primitive needing to change. This restart keeps that constraint; what's changed since the archived version is `Scan` itself, upgraded from a flat-circle stub to the physics-prior-plus-Bayesian-GP design in §2/`model.md` §§2–4.

```
MissionInput (target, battery/time budget, relay count, enemy locations, retreat/supply points)
        │
        ▼
┌───────────────────────────────────────────────────────────────────┐
│ planner.dp.plan_mission()  —  DP over road positions               │
│   expands relay levels 0..relay_count_max (pseudocode-v2.md,       │
│   value function/recurrence restated in model.md §5)               │
│                                                                     │
│   per candidate, calls out to the swappable primitives:            │
│     Scan(position)        → CoverageRaster   (§2/§3 — GP+ITM/ITWOM)│
│     Evaluate(pos, raster) → (score, description)                   │
│     BatteryModel(leg)     → wh_consumed                             │
│     Samband(road_ids, raster) → probability                        │
│     route()               → RouteLeg  (local road-graph routing)   │
└───────────────────────────────────────────────────────────────────┘
        │
        ▼
PlanResult — ranked candidates, each with route, relay chain, coverage,
             evaluation, samband, retreat/resupply routes
```

`Scan` is the one primitive under active development elsewhere right now (`ITWOM/itm/`, per §3); the rest of this section — package layout, DP structure, test strategy, visual tooling — is written so that work can land without anything here needing to change, per the modularity constraint above.

## 6. Package layout

Provenance note: `pseudocode-v2.md` and the package layout below are carried forward from the archived `rattfallan` implementation (`arkiv/rattfallan/implementation.md`, `arkiv/rattfallan/CLAUDE.md`) — this restart's fresh `RATPLAN/` had lost the file (`KONTEXT.md` §Algoritm already pointed to it; it was just missing on disk). The archived package's actual primitives (`CircleScan`, `RandomEvaluate`) are superseded by this doc's connectivity design and are not being ported as-is — only the shape (Protocol per primitive + a DI bundle) and the DP itself carry forward unchanged.

```
RATPLAN/
  pyproject.toml            # requires-python >=3.11; pytest config (§7)
  architecture.md            # this file
  model.md                    # the mathematical model (GP/kriging, DP value function, open questions)
  Goal.md, KONTEXT.md, pseudocode.md, pseudocode-v2.md
  research/                  # reading_list.md and supporting material

  ITWOM/itm/                       # connectivity module (§2/§3) — separate session, own pyproject.toml/.venv

  rattfallan/                 # the importable library + CLI (not yet created this restart)
    models/
      geometry.py             # Position (WGS84 canonical) + working-CRS transforms
      route.py                # RouteLeg
      coverage.py              # CoverageRaster protocol (.covers, .near_edge, __or__) + implementations
      mission.py               # MissionInput (pseudocode-v2.md §Inputs)
      results.py                # CandidateResult, PlanResult (pseudocode-v2.md §Output)
    snapshot/
      road_graph.py             # GraphSnapshot -> networkx graph, candidate sampling
      mission_snapshot.py        # bundles road graph + terrain/land-cover for one planning run
    primitives/
      scan.py                    # Scan protocol; real implementation calls ratplan_itm.predict_point_to_point (ITWOM/itm/, §3) once wired up
      evaluate.py                 # Evaluate protocol + implementation (cover/exposure + assistance score, model.md §6)
      battery.py                   # BatteryModel protocol + implementation (model.md §7)
      samband.py                    # Samband protocol + implementation (stub in pseudocode-v2.md / model.md §7, TBD)
      bundle.py                     # Primitives — one DI object the DP takes in
    routing/
      router.py                     # Router protocol + LocalGraphRouter
      candidates.py                  # generate_candidates(): on-road sampling, annulus filter, dedup
    io/
      mission_input.py               # loads/validates MissionInput from a mission file
      ratmap_client.py                # ratmap snapshot fetch (live or frozen)
    planner/
      dp.py                           # plan_mission() — pseudocode-v2.md's algorithm, verbatim (math in model.md §5)
      beam.py                          # top_k() reach-ranking helper
    cli.py

  mapviz/                     # visual test tool (§8) — terrain + roads, not the DP

  tests/                      # §7
```

`rattfallan/` itself isn't created by this session — building it is separate work once `ITWOM/itm/`'s `Scan` contract is settled (§5's dependency note). This section fixes the target layout so whoever writes it, and whoever writes `tests/` alongside it, agree on where each piece goes without re-deriving it from `pseudocode-v2.md` each time.

## 7. Testing strategy

**Decision: one `tests/` tree, mirrored by module, plus a separate `tests/integration/`.** Not per-module test folders inside each package.

Why: the archived `rattfallan` project already used this shape (`arkiv/rattfallan/tests/` — flat, one file roughly per module, one `conftest.py`, plus its own `tests/integration/` for the one test that needs a live `ratmap`) and `repo-map/tests/` uses the same convention workspace-wide for cross-repo contract tests. One tree means one `pytest` invocation runs everything, one `conftest.py` holds fixtures shared across modules (a `MissionInput` fixture, a small `GraphSnapshot` fixture, etc.) without duplicating them per package, and the module-mirrored subfolder still keeps "where's the test for `primitives/scan.py`" a one-line answer (`tests/primitives/test_scan.py`). Per-module colocated `tests/` folders were the alternative — rejected because this project's primitives are deliberately coupled through one DP (§5) and one `Primitives` DI bundle (`primitives/bundle.py`); tests for `planner/dp.py` need fixtures from `models/`, `snapshot/`, and every primitive at once, which a colocated-per-module layout would force into awkward cross-package imports or duplicated fixtures instead of one shared `conftest.py`.

```
RATPLAN/
  pytest.ini                 # or [tool.pytest.ini_options] in pyproject.toml, once one exists
  tests/
    README.md                 # this convention, kept next to the tests it describes
    conftest.py                # shared fixtures (MissionInput, GraphSnapshot, etc.)
    models/        test_geometry.py, test_coverage.py, test_mission.py, ...
    snapshot/      test_road_graph.py, ...
    primitives/    test_scan.py, test_evaluate.py, test_battery.py, test_samband.py
    routing/       test_router.py, test_candidates.py
    planner/       test_dp.py, test_beam.py
    io/            test_mission_input.py, test_ratmap_client.py (offline-fakeable parts only)
    integration/   test_ratmap_client.py (needs a live ratmap), anything that needs ITWOM/itm/'s real service boundary
```

Each subfolder is created alongside the module it tests, not pre-populated now — `tests/integration/` is the one exception, created now (§8 note: it's also where a real end-to-end check against `ITWOM/itm/`'s eventual service API belongs, once that boundary is stable) since it's a structural split independent of which modules exist yet. `integration` tests are marked (`@pytest.mark.integration`) and excluded by default (`addopts = -m "not integration"`, same as the archived project's `pyproject.toml`), run explicitly with `-m integration` — keeps the default `pytest` run offline and fast.

## 8. Visual test tooling (`mapviz/`)

A scoped-down visual sanity check, not a rebuild of `rattfallan-demo`'s presentation tool. `rattfallan-demo` (sibling repo) is a full hand-driven demo app (director window, screen recording, unit animation, MGRS grid, scenario save/load) built for screen-recorded presentations — most of that is decorative for the actual job here, which is eyeballing real terrain/road data while `rattfallan/` gets built, and it currently depends on a version of this package (`rattfallan.config`, `.primitives.scan.TerrainPathLossScan`, `.primitives.terrain.DtmSampler`, etc.) that no longer exists after this restart, so it can't run against this repo as-is anyway.

**Scope for this pass: terrain hillshade + road network only.** No marker placement, no routing, no coverage heatmap, no scenario save/load — those get added later, once `rattfallan/`'s own primitives exist to back them, rather than stubbed now and thrown away.

- Lives at `RATPLAN/mapviz/` (dev/test tool for the module being built here, not a separate product — §5's location decision).
- `server.py` (FastAPI): `GET /api/hillshade` reads a ratmap snapshot's `height.tif` (decimated read via `rasterio`'s `out_shape`, since a snapshot's DTM can be several GB — never loads full resolution), computes a standard surface-normal hillshade (same formula/defaults `gdaldem hillshade` and `rattfallan-demo/scenario_builder/server.py`'s `_compute_hillshade` use, so it looks identical to that tool's own terrain layer), and returns `{n_rows, n_cols, intensity, corners}`. `GET /api/roads` serves the snapshot's already-derived `roads.geojson` (produced by `ratmap`'s own `prepare_visual_data.py`) as-is — no processing needed, it already carries per-category `color`.
- Data source: a ratmap snapshot's `data/` dir (`height.tif` + `roads.geojson`), same convention as `rattfallan-demo` — defaults to `../ratmap/snapshots/real_map_scenario_north/data`, overridable via `RATPLAN_MAPVIZ_DATA_DIR`.
- Frontend: MapLibre GL (vendored, not CDN — same offline-by-default convention every other map tool in this workspace follows), hillshade rendered as an `image` source (client paints the intensity grid to a canvas and hands MapLibre a data URL, exactly `rattfallan-demo/app.js`'s `buildHillshadeDataUrl` pattern), roads as a `geojson` source with a casing+centerline line-layer pair (`layers.js`'s convention, simplified — no viewport-bboxed live refetching, since a snapshot's road set is small enough to load once).
- Deliberately **not** wired to `ITWOM/itm/` or any `Scan` implementation yet — once `rattfallan/primitives/scan.py` exists and calls into `ITWOM/itm/`'s real service boundary (§3.1), `mapviz` is where a coverage-heatmap layer gets added back, reusing this same hillshade/roads base rather than starting a new map tool.

---

## 9. Open items for next session

- ~~Confirm itmlogic supports point-to-point mode~~ — done. Implemented as [`ITWOM/itm/`](./ITWOM/itm/) (self-contained module, own `pyproject.toml`/`.venv`, itmlogic as a normal dependency, wrapped rather than forked). See [`ITWOM/itm/README.md`](./ITWOM/itm/README.md) for usage/scope and [`OPEN_ISSUES.md`](./OPEN_ISSUES.md) for what's still unresolved about it (itmlogic issue #64, uncalidated-against-NTIA gap, uncalibrated ground constants).
- ~~Build the ITWOM service~~ — done. Implemented as [`ITWOM/itwom/`](./ITWOM/itwom/) (GPL-2.0 Docker service, unmodified upstream SPLAT! pinned to commit `08f06f5`) + [`ITWOM/itwom_client/`](./ITWOM/itwom_client/) (RATPLAN's own arm's-length client). See both READMEs and `OPEN_ISSUES.md`'s "ITWOM/itwom service" section for what's still open (synthetic terrain, single-tile limit, no independent reference validation).
- No performance budget set yet for `Scan()`'s grid-batched ITM calls — needed once relay-placement iteration counts (pseudocode.md step 1) are estimated.
- `rattfallan/` package (§6) doesn't exist yet this restart — needs building once `ITWOM/itm/`'s `Scan` contract (§3.1) is stable enough for `primitives/scan.py` to call into it. The GP/kriging correction layer (`model.md` §3) isn't implemented at all yet — `ITWOM/itm/`/`ITWOM/itwom/` only produce the physics-prior mean; `primitives/scan.py` will need to decide where that layer lives (inside `rattfallan/` itself, or its own module alongside `ITWOM/`) when it's built.
- `mapviz/` (§8) ships with no coverage layer by design (scope decision this session) — revisit once there's a `Scan` implementation to visualize.
- Modeling questions that block calibration/implementation of the GP/kriging layer, not the architecture outline itself, are tracked in `model.md` §8 (joint-vs-independent GP per relay, terrain anisotropy, Nordic-forest `β`, the path-loss-to-connectivity-probability conversion, `Evaluate`/`BatteryModel`/`Samband`'s missing math) — not duplicated here.
