"""Design-01 stages [10] resampling and [11] codec.

[10] Digital downscale by the surveillance/delivery stack. Kernel is a
discrete nuisance (bilinear/bicubic/area/lanczos — FANVID's known tail is
cubic). Scale < 1 shrinks; 1.0 = pass-through.

[11] Codec: REAL encoder only (agreed 2026-07-22 — the artifacts ARE the
noise model). Single-image path implemented now with libjpeg via
cv2.imencode; supports MULTI-GENERATION cascades (screenshots-of-screenshots):
each generation re-encodes, optionally with a small inter-generation shift
that misaligns the 8x8 block grids (compounding artifacts, fingerprinting the
history). H.264/H.265 via ffmpeg arrives with the multi-frame track phase —
per-frame JPEG is the intra-frame approximation until then (flagged, not
silent).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import cv2
import numpy as np

from lrlpr.pipeline import ParamSpec, Stage

_KERNELS = {
    "area": cv2.INTER_AREA,
    "bilinear": cv2.INTER_LINEAR,
    "bicubic": cv2.INTER_CUBIC,
    "lanczos": cv2.INTER_LANCZOS4,
}


def _resample(state: Mapping[str, Any], params: Mapping[str, Any]) -> dict[str, Any]:
    img = state["current"]
    scale = params["scale"]
    if abs(scale - 1.0) < 1e-9:
        return {"current": img, "delivered": img}
    h, w = img.shape[:2]
    out = cv2.resize(img, (max(1, round(w * scale)), max(1, round(h * scale))),
                     interpolation=_KERNELS[params["kernel"]])
    return {"current": out, "delivered": out}


RESAMPLE_STAGE = Stage(
    name="resample",
    fn=_resample,
    params=(
        ParamSpec("scale", 1.0, lo=0.05, hi=1.0, step=0.05,
                  doc="delivery downscale factor (1 = none)"),
        ParamSpec("kernel", "bicubic", choices=tuple(_KERNELS),
                  doc="resampling kernel — discrete nuisance (FANVID tail = bicubic)"),
    ),
    provides=("delivered",),
    optional=True,
    doc="design-01 [10]: delivery resampling",
)


def jpeg_roundtrip(img01: np.ndarray, quality: int) -> np.ndarray:
    """Encode/decode through real libjpeg. Input/output float RGB [0,1]."""
    bgr8 = np.clip(img01[..., ::-1] * 255.0 + 0.5, 0, 255).astype(np.uint8)
    ok, buf = cv2.imencode(".jpg", bgr8, [cv2.IMWRITE_JPEG_QUALITY, int(quality)])
    if not ok:
        raise RuntimeError("JPEG encode failed")
    dec = cv2.imdecode(buf, cv2.IMREAD_COLOR)
    return dec[..., ::-1].astype(np.float64) / 255.0


def _codec(state: Mapping[str, Any], params: Mapping[str, Any]) -> dict[str, Any]:
    img = state["current"]
    if img.ndim == 2:  # never encode RAW; codec sees the ISP/delivered image
        raise ValueError("codec stage requires an RGB image (run demosaic/ISP first)")
    shift = int(params["gen_shift_px"])
    for _ in range(int(params["generations"])):
        img = jpeg_roundtrip(img, params["quality"])
        if shift:
            img = np.roll(img, (shift, shift), axis=(0, 1))  # misalign next block grid
    if shift:  # undo net translation so geometry is preserved
        n = int(params["generations"]) * shift
        img = np.roll(img, (-n, -n), axis=(0, 1))
    return {"current": img, "decoded": img}


CODEC_STAGE = Stage(
    name="codec",
    fn=_codec,
    params=(
        ParamSpec("quality", 60, lo=5, hi=100, step=1, doc="libjpeg quality"),
        ParamSpec("generations", 1, lo=1, hi=6, step=1,
                  doc="encode/decode generations (screenshots-of-screenshots)"),
        ParamSpec("gen_shift_px", 0, lo=0, hi=4, step=1, units="px",
                  doc="inter-generation shift misaligning 8x8 block grids"),
    ),
    provides=("decoded",),
    optional=True,
    doc="design-01 [11]: JPEG codec, multi-generation (real libjpeg)",
)
