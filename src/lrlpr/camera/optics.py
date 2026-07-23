"""Design-01 stage [5]: optics PSF — defocus disk ⊗ Gaussian.

Parametric family per design-01: defocus modeled as a uniform disk of radius
rho_d, everything else isotropic (diffraction + aberrations + AA filter) lumped
into a Gaussian sigma_o. Motion blur is NOT here — stage [4] handles it
temporally (equivalent to the motion component of the PSF line integral).

Parameters are in SENSOR pixels (the physically meaningful unit); converted to
supersampled pixels internally. Applied at supersample resolution, before
sensor integration ([6]), as the design requires.

PROVISIONAL: kernel truncation at 4 sigma; disk rasterized with antialiased
edge (subpixel-area approximation).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import cv2
import numpy as np

from lrlpr.pipeline import ParamSpec, Stage


def disk_kernel(radius_px: float) -> np.ndarray:
    """Uniform disk kernel, antialiased edge, normalized to sum 1."""
    if radius_px < 0.5:
        return np.ones((1, 1))
    r = int(np.ceil(radius_px)) + 1
    yy, xx = np.mgrid[-r : r + 1, -r : r + 1]
    dist = np.hypot(xx, yy)
    k = np.clip(radius_px + 0.5 - dist, 0.0, 1.0)  # ~pixel-area coverage
    return k / k.sum()


def apply_psf(image: np.ndarray, defocus_radius: float, sigma: float) -> np.ndarray:
    out = image
    if defocus_radius >= 0.5:
        out = cv2.filter2D(out, -1, disk_kernel(defocus_radius),
                           borderType=cv2.BORDER_REPLICATE)
    if sigma > 1e-3:
        out = cv2.GaussianBlur(out, (0, 0), sigmaX=sigma, sigmaY=sigma,
                               borderType=cv2.BORDER_REPLICATE)
    return out


def _optics(state: Mapping[str, Any], params: Mapping[str, Any]) -> dict[str, Any]:
    S = state["supersample"]
    out = apply_psf(
        state["current"],
        params["defocus_radius_px"] * S,
        params["gaussian_sigma_px"] * S,
    )
    return {"current": out, "image_optics": out}


OPTICS_STAGE = Stage(
    name="optics",
    fn=_optics,
    params=(
        ParamSpec("defocus_radius_px", 0.0, lo=0.0, hi=6.0, step=0.1, units="sensor px",
                  doc="defocus disk radius"),
        ParamSpec("gaussian_sigma_px", 0.5, lo=0.0, hi=4.0, step=0.05, units="sensor px",
                  doc="lumped diffraction/aberration/AA Gaussian sigma"),
    ),
    provides=("image_optics",),
    optional=True,
    doc="design-01 [5]: optics PSF (defocus disk x Gaussian)",
)
