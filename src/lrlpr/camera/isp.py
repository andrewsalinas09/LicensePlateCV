"""Design-01 stage [9]: ISP — white balance, tone curve, sharpening.

Order (design-01): WB gains -> tone curve (sRGB gamma + optional contrast
S-curve) -> unsharp-mask sharpening (the halo generator). Color matrix is
identity (PROVISIONAL per design-01), in-camera denoise off (PROVISIONAL).

Output is display-referred in [0,1] — the image a JPEG would encode.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import cv2
import numpy as np

from lrlpr.pipeline import ParamSpec, Stage


def srgb_encode(linear: np.ndarray) -> np.ndarray:
    l = np.clip(linear, 0.0, 1.0)
    return np.where(l <= 0.0031308, 12.92 * l, 1.055 * np.power(l, 1 / 2.4) - 0.055)


def s_curve(x: np.ndarray, strength: float) -> np.ndarray:
    """Contrast S-curve around mid-gray; strength 0 = identity."""
    if strength <= 1e-6:
        return x
    y = 0.5 + (1 + strength) * (x - 0.5) / (1 + strength * np.abs(2 * x - 1))
    return np.clip(y, 0.0, 1.0)


def unsharp(img: np.ndarray, amount: float, radius_px: float) -> np.ndarray:
    if amount <= 1e-6 or radius_px <= 1e-3:
        return img
    blurred = cv2.GaussianBlur(img, (0, 0), radius_px)
    return np.clip(img + amount * (img - blurred), 0.0, 1.0)


def _isp(state: Mapping[str, Any], params: Mapping[str, Any]) -> dict[str, Any]:
    img = state["current"].astype(np.float64)
    img = img * np.array([params["wb_r"], 1.0, params["wb_b"]])
    img = srgb_encode(img) if params["srgb_gamma"] else np.clip(img, 0.0, 1.0)
    img = s_curve(img, params["contrast"])
    img = unsharp(img, params["sharpen_amount"], params["sharpen_radius_px"])
    return {"current": img, "isp_image": img}


ISP_STAGE = Stage(
    name="isp",
    fn=_isp,
    params=(
        ParamSpec("wb_r", 1.0, lo=0.5, hi=2.0, step=0.01, doc="white-balance red gain"),
        ParamSpec("wb_b", 1.0, lo=0.5, hi=2.0, step=0.01, doc="white-balance blue gain"),
        ParamSpec("srgb_gamma", True, doc="sRGB opto-electronic transfer (off = linear out)"),
        ParamSpec("contrast", 0.0, lo=0.0, hi=1.5, step=0.05, doc="S-curve strength"),
        ParamSpec("sharpen_amount", 0.0, lo=0.0, hi=3.0, step=0.05,
                  doc="unsharp-mask amount (halo generator)"),
        ParamSpec("sharpen_radius_px", 1.0, lo=0.2, hi=5.0, step=0.1, units="px"),
    ),
    provides=("isp_image",),
    optional=True,
    doc="design-01 [9]: WB, tone curve, sharpening",
)
