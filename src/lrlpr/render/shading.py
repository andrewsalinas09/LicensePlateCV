"""Design-01 stage [2]: illumination & shading of the relief surface.

Coordinate convention (documented; tests depend on it):
  x right, y DOWN (image convention), z toward the viewer (out of the plate).
  Light direction l = unit vector pointing FROM the surface TOWARD the light.
  azimuth_deg: 0 = light from the right edge, 90 = from the top of the image,
  180 = from the left, 270 = from below. elevation_deg: 90 = frontal.

Model (design-01 [2]):
  radiance = albedo * (E_ambient + E_direct * max(0, n·l) * shadow_visibility)

Cast shadows: heightfield horizon test — a point is shadowed if any point along
the ray toward the light rises above the ray of elevation ``elevation_deg``.
Hard shadows, optionally softened by a small Gaussian (penumbra proxy —
PROVISIONAL; a physical penumbra model needs the sun's angular size).

PROVISIONAL: Lambertian only — no retroreflective lobe yet (daylight regime);
no interreflection. Retro lobe is required before any night/flash scenario.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import numpy as np
from scipy.ndimage import gaussian_filter

from lrlpr.pipeline import ParamSpec, Stage


def surface_normals(height_mm: np.ndarray, mm_per_px: float) -> np.ndarray:
    """Unit normals of the heightfield z = h(x, y). Shape (H, W, 3)."""
    dh_dv, dh_du = np.gradient(height_mm, mm_per_px)  # rows = y(v), cols = x(u)
    n = np.dstack([-dh_du, -dh_dv, np.ones_like(height_mm)])
    return n / np.linalg.norm(n, axis=2, keepdims=True)


def light_vector(azimuth_deg: float, elevation_deg: float) -> np.ndarray:
    az, el = np.deg2rad(azimuth_deg), np.deg2rad(elevation_deg)
    # y negated: azimuth 90° means light from the TOP of the image (y down).
    return np.array([np.cos(az) * np.cos(el), -np.sin(az) * np.cos(el), np.sin(el)])


def cast_shadow_mask(
    height_mm: np.ndarray, mm_per_px: float, azimuth_deg: float, elevation_deg: float
) -> np.ndarray:
    """1.0 where lit, 0.0 where occluded by the relief (hard shadows).

    Marching implementation: shift the heightfield along the light's horizontal
    direction in 1-px steps; occluded if shifted height exceeds the local ray
    height. Ray length bounded by max relief / tan(elevation) — cheap, since
    relief is ~1 mm.
    """
    el = np.deg2rad(max(elevation_deg, 1e-3))
    az = np.deg2rad(azimuth_deg)
    d = np.array([np.cos(az), -np.sin(az)])  # horizontal unit dir toward light (y down)
    max_len_mm = float(height_mm.max()) / np.tan(el)
    n_steps = int(np.ceil(max_len_mm / mm_per_px))
    if n_steps == 0:
        return np.ones_like(height_mm)

    H, W = height_mm.shape
    rows = np.arange(H)[:, None]
    cols = np.arange(W)[None, :]
    lit = np.ones_like(height_mm, dtype=bool)
    for t in range(1, n_steps + 1):
        # Sample the surface at p + t*d (toward the light), nearest-neighbor.
        rr = np.clip(np.round(rows - t * d[1]).astype(int), 0, H - 1)  # y down
        cc = np.clip(np.round(cols + t * d[0]).astype(int), 0, W - 1)
        ray_height = height_mm + t * mm_per_px * np.tan(el)
        lit &= height_mm[rr, cc] <= ray_height + 1e-9
    return lit.astype(np.float64)


def _shade(state: Mapping[str, Any], params: Mapping[str, Any]) -> dict[str, Any]:
    height = state["height_mm"]
    mm_per_px = state["mm_per_px"]
    normals = surface_normals(height, mm_per_px)
    light = light_vector(params["azimuth_deg"], params["elevation_deg"])

    ndotl = np.clip(normals @ light, 0.0, None)
    if params["cast_shadows"]:
        vis = cast_shadow_mask(height, mm_per_px, params["azimuth_deg"],
                               params["elevation_deg"])
        if params["shadow_soften_px"] > 0:
            vis = gaussian_filter(vis, params["shadow_soften_px"])
        ndotl = ndotl * vis

    shading = params["ambient"] + params["direct"] * ndotl
    return {"radiance": state["albedo"] * shading[..., None], "shading": shading}


SHADING_STAGE = Stage(
    name="shading",
    fn=_shade,
    params=(
        ParamSpec("azimuth_deg", 90.0, lo=0.0, hi=360.0, step=1.0, units="deg",
                  doc="light azimuth: 0=right, 90=top, 180=left, 270=bottom"),
        ParamSpec("elevation_deg", 45.0, lo=1.0, hi=90.0, step=1.0, units="deg",
                  doc="light elevation: 90 = frontal"),
        ParamSpec("direct", 0.85, lo=0.0, hi=2.0, step=0.05, doc="direct irradiance"),
        ParamSpec("ambient", 0.15, lo=0.0, hi=1.0, step=0.05, doc="ambient irradiance"),
        ParamSpec("cast_shadows", True, doc="heightfield cast shadows"),
        ParamSpec("shadow_soften_px", 1.0, lo=0.0, hi=10.0, step=0.5, units="px",
                  doc="penumbra proxy blur (PROVISIONAL)"),
    ),
    provides=("radiance", "shading"),
    optional=False,
    doc="design-01 [2]: Lambertian shading + relief cast shadows",
)
