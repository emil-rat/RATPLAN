"""Calls the ITWOM service (../itwom) as a subprocess via `docker run -i`.

This is the arm's-length boundary architecture.md §3.1 requires: this
process and the service container communicate only via JSON over
stdin/stdout — no shared memory, no linking, no imported GPL code. See
../itwom/README.md for the service side and the license-scope reasoning.
"""

import json
import subprocess

from .types import ElevationGrid, GroundConstants, ItwomResult, Site

DEFAULT_IMAGE = "ratplan-itwom-service"


class ItwomServiceError(RuntimeError):
    pass


def predict_point_to_point(
    tx: Site,
    rx: Site,
    frequency_mhz: float,
    *,
    terrain: ElevationGrid,
    ground: GroundConstants = GroundConstants(),
    climate: int = 5,
    polarization: int = 0,
    fraction_of_situations: float = 0.5,
    fraction_of_time: float = 0.5,
    erp_watts: float = 0.0,
    use_itwom: bool = True,
    image: str = DEFAULT_IMAGE,
    timeout_s: float = 60.0,
) -> ItwomResult:
    """Predict point-to-point path loss via the ITWOM (or, with
    use_itwom=False, classic ITM) service, against real terrain.

    `terrain` must cover both tx and rx (see
    ratplan_terrain.primitives.terrain_profile.elevation_grid_from_dtm to build one from ratmap's DTM). tx/rx
    must also fall within the same 1x1 degree tile the service's own .sdf writer generates (see
    ../itwom/wrapper/itwom_cli.py) — SPLAT!'s own single-tile limitation, not this client's.
    """
    request = {
        "frequency_mhz": frequency_mhz,
        "tx": {"lat": tx.lat, "lon_deg_east": tx.lon_deg_east, "height_m": tx.height_m},
        "rx": {"lat": rx.lat, "lon_deg_east": rx.lon_deg_east, "height_m": rx.height_m},
        "terrain": {
            "elevation_grid": {
                "min_lat": terrain.min_lat,
                "max_lat": terrain.max_lat,
                "min_lon_deg_east": terrain.min_lon_deg_east,
                "max_lon_deg_east": terrain.max_lon_deg_east,
                "values_m": terrain.values_m,
            },
        },
        "ground": {
            "relative_permittivity": ground.relative_permittivity,
            "conductivity_s_per_m": ground.conductivity_s_per_m,
        },
        "climate": climate,
        "polarization": polarization,
        "fraction_of_situations": fraction_of_situations,
        "fraction_of_time": fraction_of_time,
        "erp_watts": erp_watts,
        "use_itwom": use_itwom,
    }

    try:
        result = subprocess.run(
            ["docker", "run", "--rm", "-i", image],
            input=json.dumps(request),
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
    except FileNotFoundError as exc:
        raise ItwomServiceError(
            "docker executable not found — the ITWOM service requires Docker"
        ) from exc

    if result.returncode != 0:
        raise ItwomServiceError(
            f"ITWOM service exited {result.returncode}\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )

    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ItwomServiceError(f"non-JSON output from ITWOM service: {result.stdout}") from exc

    if not payload.get("ok"):
        raise ItwomServiceError(f"ITWOM service reported an error: {payload}")

    return ItwomResult(
        model=payload["model"],
        path_loss_db=payload["path_loss_db"],
        free_space_loss_db=payload.get("free_space_loss_db"),
    )
