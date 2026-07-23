"""Design-01 stage [3]: projective geometry — plate plane -> camera frame.

Phase-1 parameterization (demo-friendly; full intrinsics arrive with the camera
phase): the plate is placed at a distance implied by the requested character
height in output pixels, rotated by yaw/pitch/roll, and imaged by a pinhole
camera with the given focal length. Output stays SUPERSAMPLED (factor
``supersample``): sensor integration is stage [6]'s job, not ours.

Outputs: image (h, w, 3) linear radiance; homography (3, 3) plate-mm -> output px.

PROVISIONAL: cv2.warpPerspective with INTER_LINEAR sampling of the supersampled
plate render. At supersample >= 4 the interpolation error is far below relief/
shading effects; revisit if the leverage analysis disagrees. Lens distortion
deferred to the camera phase (design-01 [3] lists it under intrinsics).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import cv2
import numpy as np

from lrlpr.pipeline import ParamSpec, Stage
from lrlpr.plate_spec import SPECS


def plate_homography(
    spec_width: float, spec_height: float, char_height_mm: float,
    char_height_px: float, yaw_deg: float, pitch_deg: float, roll_deg: float,
    focal_mm: float, pixel_pitch_um: float, supersample: int,
) -> tuple[np.ndarray, tuple[int, int], float]:
    """Homography from plate mm-coords to supersampled output px.

    Pinhole model with real units: focal length in mm, sensor pixel pitch in
    µm, so focal_px = focal_mm / pitch. The camera distance is derived so a
    frontal plate's characters are ``char_height_px`` tall at sensor
    resolution — with realistic pitch this puts the camera tens of meters
    away, giving physically correct (weak) perspective. Returns the distance
    (mm) too, so the GUI can display it.
    """
    y, p, r = np.deg2rad([yaw_deg, pitch_deg, roll_deg])
    Ry = np.array([[np.cos(y), 0, np.sin(y)], [0, 1, 0], [-np.sin(y), 0, np.cos(y)]])
    Rx = np.array([[1, 0, 0], [0, np.cos(p), -np.sin(p)], [0, np.sin(p), np.cos(p)]])
    Rz = np.array([[np.cos(r), -np.sin(r), 0], [np.sin(r), np.cos(r), 0], [0, 0, 1]])
    R = Rz @ Rx @ Ry

    focal_px = focal_mm / (pixel_pitch_um * 1e-3) * supersample  # in supersampled px
    px_per_mm_out = char_height_px * supersample / char_height_mm
    distance = focal_px / px_per_mm_out  # mm; frontal scale = focal_px/Z
    center = np.array([spec_width / 2, spec_height / 2, 0.0])

    def project(uv: np.ndarray) -> np.ndarray:
        X = R @ (np.array([uv[0], uv[1], 0.0]) - center) + np.array([0, 0, distance])
        return focal_px * X[:2] / X[2]

    corners_mm = np.array(
        [[0, 0], [spec_width, 0], [spec_width, spec_height], [0, spec_height]],
        dtype=np.float64,
    )
    corners_px = np.array([project(c) for c in corners_mm])
    corners_px -= corners_px.min(axis=0)
    margin = 4.0 * supersample
    corners_px += margin
    out_w = int(np.ceil(corners_px[:, 0].max() + margin))
    out_h = int(np.ceil(corners_px[:, 1].max() + margin))
    Hmat = cv2.getPerspectiveTransform(
        corners_mm.astype(np.float32), corners_px.astype(np.float32)
    )
    return Hmat.astype(np.float64), (out_h, out_w), distance


def _project(state: Mapping[str, Any], params: Mapping[str, Any]) -> dict[str, Any]:
    spec = SPECS[state["spec_name"]]
    Hmat, (out_h, out_w), distance_mm = plate_homography(
        spec.width, spec.height, spec.char_height,
        params["char_height_px"], params["yaw_deg"], params["pitch_deg"],
        params["roll_deg"], params["focal_mm"], params["pixel_pitch_um"],
        int(params["supersample"]),
    )
    # Compose with mm -> source-px scaling of the rendered plate maps.
    src_scale = np.diag([state["mm_per_px"], state["mm_per_px"], 1.0])
    warp = Hmat @ src_scale
    if params["grid_warp"] is not None:
        # Render onto an externally-fitted grid (decoder geometry fitting, G1+):
        # grid_warp maps NATIVE default-projection px -> native target-grid px;
        # composing it here means all resampling happens inside the renderer at
        # supersampled resolution — the observation itself is never resampled.
        ss = int(params["supersample"])
        S = np.diag([float(ss), float(ss), 1.0])
        gw = np.asarray(params["grid_warp"], dtype=np.float64).reshape(3, 3)
        warp = S @ gw @ np.linalg.inv(S) @ warp
        gh, gw_px = params["grid_shape"]
        out_h, out_w = int(gh) * ss, int(gw_px) * ss
        Hmat = S @ gw @ np.linalg.inv(S) @ Hmat
    image = cv2.warpPerspective(
        state["radiance"], warp, (out_w, out_h),
        flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT,
        borderValue=tuple(params["backdrop"] for _ in range(3)),
    )
    focal_px_super = params["focal_mm"] / (params["pixel_pitch_um"] * 1e-3) * int(
        params["supersample"]
    )
    return {
        "image": image,
        "current": image,  # the working image consumed by downstream camera stages
        "homography": Hmat,
        "supersample": int(params["supersample"]),
        "camera_distance_m": distance_mm / 1000.0,
        "focal_px_super": focal_px_super,
    }


PROJECT_STAGE = Stage(
    name="project",
    fn=_project,
    params=(
        ParamSpec("char_height_px", 12.0, lo=2.0, hi=80.0, step=0.5, units="px",
                  doc="character height at SENSOR resolution (pre-supersample)"),
        ParamSpec("yaw_deg", 0.0, lo=-75.0, hi=75.0, step=0.5, units="deg"),
        ParamSpec("pitch_deg", 0.0, lo=-60.0, hi=60.0, step=0.5, units="deg"),
        ParamSpec("roll_deg", 0.0, lo=-30.0, hi=30.0, step=0.5, units="deg"),
        ParamSpec("focal_mm", 25.0, lo=2.0, hi=200.0, step=1.0, units="mm",
                  doc="pinhole focal length"),
        ParamSpec("pixel_pitch_um", 3.0, lo=0.8, hi=10.0, step=0.1, units="um",
                  doc="sensor pixel pitch (with focal, sets true perspective)"),
        ParamSpec("supersample", 8, lo=1, hi=16, step=1,
                  doc="working-grid oversampling vs sensor pixels"),
        ParamSpec("backdrop", 0.35, lo=0.0, hi=1.0, step=0.05,
                  doc="constant radiance behind the plate (placeholder scene)"),
        ParamSpec("grid_warp", None, hidden=True,
                  doc="3x3 homography, native default-projection px -> native "
                      "target-grid px; render onto a fitted observation grid"),
        ParamSpec("grid_shape", None, hidden=True,
                  doc="(h, w) native target-grid size, required with grid_warp"),
    ),
    provides=("image", "homography", "supersample"),
    doc="design-01 [3]: pinhole projection of the shaded plate",
)
