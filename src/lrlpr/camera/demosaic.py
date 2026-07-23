"""Design-01 stage [8]: demosaic — the camera's invented 2/3 of the color data.

The real camera's algorithm is unknown -> the CHOICE is a small discrete
nuisance (design-01 [8]). Implemented via OpenCV's real demosaicers:
  bilinear  cv2.demosaicing(..., COLOR_Bayer*2BGR)
  vng       variable-number-of-gradients (edge-directed)
  ea        edge-aware

Passes through untouched when the sensor stage ran with bayer=False.

Note on OpenCV Bayer naming: cv2's COLOR_Bayer<XY>2BGR names the pattern by
the 2x2 tile STARTING AT PIXEL (1,1) of the sensor, not (0,0) — verified by
round-trip test (constant-color restoration) in tests/test_camera.py.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import cv2
import numpy as np

from lrlpr.pipeline import ParamSpec, Stage

# Our pattern name (tile at (0,0)) -> cv2 code (tile at (1,1) => diagonal swap).
_CV2_BASE = {
    "RGGB": "BG",
    "BGGR": "RG",
    "GRBG": "GB",
    "GBRG": "GR",
}
_ALGOS = {
    "bilinear": "",
    "vng": "_VNG",
    "ea": "_EA",
}


def demosaic(raw: np.ndarray, pattern: str, algo: str) -> np.ndarray:
    code = getattr(cv2, f"COLOR_Bayer{_CV2_BASE[pattern]}2BGR{_ALGOS[algo]}")
    raw16 = np.clip(raw * 65535.0, 0, 65535).astype(np.uint16)
    if algo == "vng":  # cv2 VNG requires 8-bit input
        raw8 = np.clip(raw * 255.0, 0, 255).astype(np.uint8)
        bgr = cv2.demosaicing(raw8, code).astype(np.float64) / 255.0
    else:
        bgr = cv2.demosaicing(raw16, code).astype(np.float64) / 65535.0
    return bgr[..., ::-1].copy()  # BGR -> RGB


def _demosaic(state: Mapping[str, Any], params: Mapping[str, Any]) -> dict[str, Any]:
    if state.get("raw_mosaic") is None:  # sensor ran with bayer off
        return {"demosaiced": state["current"], "current": state["current"]}
    rgb = demosaic(state["current"], state["bayer_pattern"], params["algo"])
    return {"current": rgb, "demosaiced": rgb}


DEMOSAIC_STAGE = Stage(
    name="demosaic",
    fn=_demosaic,
    params=(
        ParamSpec("algo", "bilinear", choices=tuple(_ALGOS),
                  doc="demosaic algorithm — discrete nuisance (real camera unknown)"),
    ),
    provides=("demosaiced",),
    doc="design-01 [8]: demosaic (bilinear/VNG/edge-aware)",
)
