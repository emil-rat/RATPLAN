#!/usr/bin/env python3
"""RATPLAN ITWOM service entrypoint — GPL-2.0, see ../LICENSE.

Reads a JSON request from stdin, synthesizes a terrain tile + SPLAT! site
files, invokes the unmodified upstream `splat` binary (built in this image's
Dockerfile) via subprocess, parses its point-to-point report, and writes a
JSON result to stdout. This is the only interface RATPLAN's own code talks
to — see ../../itwom_client, which calls this container via `docker run -i`
and never touches anything below this line.

Terrain comes from the request's `elevation_grid` — a coarse regular grid of real elevations sampled from
ratmap's DTM by the caller (ratplan_terrain.primitives.terrain_profile.elevation_grid_from_dtm), bilinear-
interpolated here to fill this service's own SPLAT!-native terrain tile. See OPEN_ISSUES.md.
"""

import json
import math
import re
import subprocess
import sys
import tempfile
from pathlib import Path

IPPD = 1200  # points per degree, standard (3 arc-second) resolution — must
             # match std-parms.h's HD_MODE=0 default baked into this image.
MPI = IPPD - 1


def elevation_m(lat: float, lon_east: float, elevation_grid: dict) -> float:
    """Bilinear lookup into the request's real-elevation grid (see module docstring). Queries outside
    the grid clamp to its own edges rather than raising -- the grid is built to cover the tx/rx link
    itself, so out-of-grid .sdf cells are expected and don't affect the diffraction calculation anyway."""
    min_lat, max_lat = elevation_grid["min_lat"], elevation_grid["max_lat"]
    min_lon, max_lon = elevation_grid["min_lon_deg_east"], elevation_grid["max_lon_deg_east"]
    values = elevation_grid["values_m"]
    n_lat, n_lon = len(values), len(values[0])

    lat_frac = 0.0 if max_lat == min_lat else (lat - min_lat) / (max_lat - min_lat)
    lon_frac = 0.0 if max_lon == min_lon else (lon_east - min_lon) / (max_lon - min_lon)
    lat_frac = min(max(lat_frac, 0.0), 1.0)
    lon_frac = min(max(lon_frac, 0.0), 1.0)

    row, col = lat_frac * (n_lat - 1), lon_frac * (n_lon - 1)
    row0, col0 = int(row), int(col)
    row1, col1 = min(row0 + 1, n_lat - 1), min(col0 + 1, n_lon - 1)
    fr, fc = row - row0, col - col0

    v00, v01 = values[row0][col0], values[row0][col1]
    v10, v11 = values[row1][col0], values[row1][col1]
    return v00 * (1 - fc) * (1 - fr) + v01 * fc * (1 - fr) + v10 * (1 - fc) * fr + v11 * fc * fr


def write_sdf(
    path: Path, min_north: int, max_north: int, min_west: int, max_west: int, elevation_grid: dict
) -> None:
    """Write a SPLAT! .sdf terrain tile.

    Format and index mapping reverse-engineered directly from upstream
    splat.cpp (LoadSDF_SDF's read loop and GetElevation's lat/lon->index
    formula), not from srtm2sdf.c's HGT-reading logic — we're synthesizing
    values to satisfy the *reader*, not reproducing the *writer*'s original
    SRTM-derived array layout. See ITWOM/itwom/README.md for the derivation.

    GetElevation(lat, lon) reads data[x][y] where:
        x = round(ippd * (lat - min_north))
        y = mpi - round(ippd * (max_west - lon_west))
    and LoadSDF_SDF fills data[x][y] by reading values in order x=0..mpi,
    inner y=0..mpi — so writing, for x in 0..mpi: for y in 0..mpi, the
    elevation at lat = min_north + x/ippd, lon_west = max_west - (mpi-y)/ippd
    reproduces exactly the file layout the reader expects.
    """
    lines = [str(max_west), str(min_north), str(min_west), str(max_north)]
    for x in range(IPPD):
        lat = min_north + x / IPPD
        for y in range(IPPD):
            lon_west = max_west - (MPI - y) / IPPD
            lon_east = -lon_west
            lines.append(str(round(elevation_m(lat, lon_east, elevation_grid))))
    path.write_text("\n".join(lines) + "\n")


def write_qth(path: Path, name: str, lat: float, lon_east: float, height_m: float) -> None:
    lon_west = -lon_east
    path.write_text(f"{name}\n{lat}\n{lon_west}\n{height_m} meters\n")


def write_lrp(path: Path, req: dict) -> None:
    ground = req.get("ground", {})
    path.write_text(
        "\n".join(
            [
                f"{ground.get('relative_permittivity', 15.0)}\t; Earth Dielectric Constant",
                f"{ground.get('conductivity_s_per_m', 0.005)}\t; Earth Conductivity",
                "301.000\t; Atmospheric Bending Constant",
                f"{req['frequency_mhz']}\t; Frequency in MHz",
                f"{req.get('climate', 5)}\t; Radio Climate",
                f"{req.get('polarization', 0)}\t; Polarization",
                f"{req.get('fraction_of_situations', 0.5)}\t; Fraction of situations",
                f"{req.get('fraction_of_time', 0.5)}\t; Fraction of time",
                f"{req.get('erp_watts', 0.0)}\t; ERP in watts",
                "",
            ]
        )
    )


REPORT_LOSS_RE = re.compile(
    r"(ITWOM Version [\d.]+|Longley-Rice) path loss: ([\d.]+) dB"
)
FREE_SPACE_RE = re.compile(r"Free space path loss: ([\d.]+) dB")


def parse_report(text: str) -> dict:
    loss_match = REPORT_LOSS_RE.search(text)
    fs_match = FREE_SPACE_RE.search(text)
    if not loss_match:
        raise ValueError(f"could not find a path loss line in SPLAT! report:\n{text}")
    return {
        "model": loss_match.group(1),
        "path_loss_db": float(loss_match.group(2)),
        "free_space_loss_db": float(fs_match.group(1)) if fs_match else None,
    }


def main() -> int:
    req = json.load(sys.stdin)

    tx = req["tx"]
    rx = req["rx"]
    elevation_grid = req["terrain"]["elevation_grid"]
    use_itwom = req.get("use_itwom", True)

    lats = [tx["lat"], rx["lat"]]
    lons_west = [-tx["lon_deg_east"], -rx["lon_deg_east"]]
    min_north, max_north = math.floor(min(lats)), math.floor(min(lats)) + 1
    min_west, max_west = math.floor(min(lons_west)), math.floor(min(lons_west)) + 1

    if not (min_north <= min(lats) and max(lats) < max_north):
        raise ValueError("tx/rx latitudes must fall within the same 1x1 degree tile")
    if not (min_west <= min(lons_west) and max(lons_west) < max_west):
        raise ValueError("tx/rx longitudes must fall within the same 1x1 degree tile")

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        sdf_dir = tmp_path / "sdf"
        sdf_dir.mkdir()
        sdf_file = sdf_dir / f"{min_north}:{max_north}:{min_west}:{max_west}.sdf"
        write_sdf(sdf_file, min_north, max_north, min_west, max_west, elevation_grid)

        write_qth(tmp_path / "TX.qth", "TX", tx["lat"], tx["lon_deg_east"], tx["height_m"])
        write_qth(tmp_path / "RX.qth", "RX", rx["lat"], rx["lon_deg_east"], rx["height_m"])
        write_lrp(tmp_path / "splat.lrp", req)

        cmd = ["splat", "-t", "TX", "-r", "RX", "-d", f"{sdf_dir}/", "-metric"]
        if not use_itwom:
            cmd.append("-olditm")

        result = subprocess.run(
            cmd, cwd=tmp_path, capture_output=True, text=True, timeout=120
        )

        report_file = tmp_path / "TX-to-RX.txt"
        if not report_file.exists():
            print(
                json.dumps(
                    {
                        "error": "SPLAT! did not produce a report file",
                        "returncode": result.returncode,
                        "stdout": result.stdout,
                        "stderr": result.stderr,
                    }
                )
            )
            return 1

        parsed = parse_report(report_file.read_text(encoding="latin-1"))

    print(json.dumps({"ok": True, **parsed, "stdout": result.stdout}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
