"""Design-01 stage [4]: motion blur + rolling shutter.

Physical model: during the exposure the plate translates in the image plane
with velocity derived from vehicle speed and viewing geometry:

    v_px/s = focal_px * (speed_m/s) / (distance_m)      (transverse motion)

Rolling shutter: sensor row r is exposed at t = r * line_time; we evaluate the
scene at the row-dependent time (design-01: geometry evaluated per row, NOT a
post-warp of the finished frame — implemented as a row-dependent displacement
in the remap, which is equivalent for image-plane translation).

Motion blur: line integral over the exposure window, approximated by averaging
``n_blur_samples`` time samples (midpoint rule over [0, exposure]).

PROVISIONAL:
  - Image-plane translation is uniform across the frame (true for transverse
    motion at distance >> plate size; revisit for strong perspective/turning).
  - Trajectory is straight within one exposure.
  - motion_direction_deg gives the image-plane direction (0 = rightward,
    90 = downward) rather than a full 3D trajectory.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import cv2
import numpy as np

from lrlpr.pipeline import ParamSpec, Stage


def velocity_px_per_s(
    speed_kmh: float, direction_deg: float, focal_px: float, distance_m: float
) -> np.ndarray:
    speed = speed_kmh / 3.6  # m/s
    mag = focal_px * speed / max(distance_m, 1e-6)
    th = np.deg2rad(direction_deg)
    return np.array([mag * np.cos(th), mag * np.sin(th)])  # x right, y down


def apply_motion_rs(
    image: np.ndarray,
    v_px_s: np.ndarray,
    exposure_s: float,
    line_time_s_per_row: float,
    n_samples: int,
) -> np.ndarray:
    """Average of row-time-shifted samples: rolling shutter + motion blur."""
    h, w = image.shape[:2]
    xs = np.arange(w, dtype=np.float32)[None, :].repeat(h, axis=0)
    ys = np.arange(h, dtype=np.float32)[:, None].repeat(w, axis=1)
    row_t = ys * line_time_s_per_row  # rolling-shutter time offset per row

    acc = np.zeros_like(image)
    # Midpoint samples over the exposure window.
    taus = (np.arange(n_samples) + 0.5) / n_samples * exposure_s
    for tau in taus:
        t = row_t + tau
        # Scene at time t is the t=0 scene translated by v*t: sample source at p - v*t.
        map_x = xs - np.float32(v_px_s[0]) * t.astype(np.float32)
        map_y = ys - np.float32(v_px_s[1]) * t.astype(np.float32)
        acc += cv2.remap(
            image, map_x, map_y, interpolation=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_REPLICATE,
        )
    return acc / n_samples


def _motion(state: Mapping[str, Any], params: Mapping[str, Any]) -> dict[str, Any]:
    img = state["current"]
    S = state["supersample"]
    v = velocity_px_per_s(
        params["speed_kmh"], params["motion_direction_deg"],
        state["focal_px_super"], state["camera_distance_m"],
    )
    # line_time is per SENSOR row; supersampled rows advance S x faster.
    line_time_super = params["line_time_us"] * 1e-6 / S
    out = apply_motion_rs(
        img, v, params["exposure_ms"] * 1e-3, line_time_super,
        int(params["n_blur_samples"]),
    )
    return {"current": out, "image_motion": out}


MOTION_STAGE = Stage(
    name="motion_rs",
    fn=_motion,
    params=(
        ParamSpec("speed_kmh", 0.0, lo=0.0, hi=200.0, step=1.0, units="km/h",
                  doc="vehicle transverse speed"),
        ParamSpec("motion_direction_deg", 0.0, lo=0.0, hi=360.0, step=5.0, units="deg",
                  doc="image-plane motion direction: 0=right, 90=down"),
        ParamSpec("exposure_ms", 8.0, lo=0.1, hi=40.0, step=0.1, units="ms"),
        ParamSpec("line_time_us", 30.0, lo=0.0, hi=120.0, step=1.0, units="us",
                  doc="rolling-shutter line readout time per sensor row (0 = global)"),
        ParamSpec("n_blur_samples", 16, lo=1, hi=64, step=1,
                  doc="time samples approximating the exposure line integral"),
    ),
    provides=("image_motion",),
    optional=True,
    doc="design-01 [4]: motion blur + rolling shutter (row-dependent time)",
)
