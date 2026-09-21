# ratplan-itwom-service (GPL-2.0)

**License: GPL-2.0 (see `LICENSE`). This folder is third-party code (unmodified
upstream [SPLAT!](https://github.com/jmcmellen/splat), which bundles
`itwom3.0.cpp`), not RATPLAN's own code.** RATPLAN's own code never imports,
links, or vendors anything from here — see `../itwom_client` for the only
way RATPLAN talks to this. Background and the full licensing reasoning:
[`../../architecture.md`](../../architecture.md) §3.1/§4.2.

## What this is

A Docker image that builds SPLAT! from source (unmodified — `Dockerfile`
just clones upstream and runs its own `./build splat`) and wraps it with a
minimal JSON-over-stdio CLI (`wrapper/itwom_cli.py`) so it can be called as
a subprocess: JSON in, JSON out, nothing shared but pipes. That's what keeps
this GPL-2.0 component from pulling RATPLAN's own code into GPL scope — see
the FSF GPL FAQ text quoted in architecture.md §3.1 on "arm's length"
program separation.

SPLAT! runs ITWOM by default; pass `"use_itwom": false` in the request to
get classic Longley-Rice ITM instead (`-olditm`), for comparison.

## Terrain: real DTM data, via a coarse elevation grid

The wrapper fills its own SPLAT! `.sdf` terrain tile by bilinear-interpolating from a coarse regular
elevation grid supplied in the request (`terrain.elevation_grid`) — real DTM data sampled from ratmap
by the caller (`ratplan_terrain.primitives.terrain_profile.elevation_grid_from_dtm`), not a formula. The grid
only needs to cover the tx/rx link itself (plus a margin): out-of-grid `.sdf` cells clamp to the grid's
own edges, since SPLAT!'s diffraction calculation only cares about cells between tx and rx anyway.

The `.sdf` index math in `write_sdf()` was reverse-engineered directly from
upstream `splat.cpp` (`GetElevation`'s lat/lon→array-index formula and
`LoadSDF_SDF`'s read-order loop), not from `srtm2sdf.c`'s original
HGT-reading logic — untouched by the real-terrain wiring, which only
changed `elevation_m()`'s data source. See the docstring for the
derivation if this ever needs revisiting.

## Request/response format

```json
// stdin
{
  "frequency_mhz": 433.0,
  "tx": {"lat": 40.55, "lon_deg_east": -105.55, "height_m": 2.0},
  "rx": {"lat": 40.55, "lon_deg_east": -105.45, "height_m": 1.5},
  "terrain": {"elevation_grid": {
    "min_lat": 40.54, "max_lat": 40.56,
    "min_lon_deg_east": -105.56, "max_lon_deg_east": -105.44,
    "values_m": [[1500.0, 1520.0], [1510.0, 1530.0]]
  }},
  "ground": {"relative_permittivity": 15.0, "conductivity_s_per_m": 0.005},
  "climate": 5, "polarization": 0,
  "fraction_of_situations": 0.5, "fraction_of_time": 0.5,
  "erp_watts": 0, "use_itwom": true
}
```
```json
// stdout
{"ok": true, "model": "ITWOM Version 3.0", "path_loss_db": 164.15, "free_space_loss_db": 103.73, "stdout": "..."}
```

tx/rx must fall within the same 1x1 degree tile (the generator only writes
one tile) — fine for short relay hops, not for long-range links.

## Build & run

```
docker build -t ratplan-itwom-service .
docker run --rm -i ratplan-itwom-service < request.json
```

Use `../itwom_client` (RATPLAN's own MIT/proprietary Python code) rather
than shelling out to `docker run` directly — it's the arm's-length client
wrapper, structurally parallel to `ITWOM/itm/`'s `ratplan_itm` package.
