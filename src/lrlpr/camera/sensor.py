"""Design-01 stages [6] sensor sampling (pixel aperture + Bayer) and [7] noise.

[6] Pixel aperture: integrate the supersampled irradiance over each sensor
pixel's footprint — exact box filter for integer supersample factors
(cv2.INTER_AREA). Then exposure scaling to full-well fraction, then the Bayer
mosaic: each site keeps ONE channel (RGGB with a selectable phase — the phase
matters: it is part of the mosaic structure that leaks into the evidence).

[7] Noise at the RAW mosaic domain (design-01: heteroscedastic Gaussian
approximation of Poisson shot + Gaussian read):  sigma^2(I) = a*I + b, then
clipping to [0, 1] (black level/saturation hard nonlinearity).

PROVISIONAL:
  - 100% fill factor (box aperture).
  - Albedo->RGB direct (no spectral simulation), per design-01 [6] color note.
  - Simple [0,1] clip; explicit black-level offset deferred.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import cv2
import numpy as np

from lrlpr.pipeline import ParamSpec, Stage

# 2x2 Bayer patterns: channel index (0=R,1=G,2=B) at [row%2][col%2].
BAYER_PATTERNS = {
    "RGGB": ((0, 1), (1, 2)),
    "BGGR": ((2, 1), (1, 0)),
    "GRBG": ((1, 0), (2, 1)),
    "GBRG": ((1, 2), (0, 1)),
}


def pixel_aperture(image: np.ndarray, supersample: int) -> np.ndarray:
    """Integer-factor box integration to the sensor grid (exact box filter)."""
    h, w = image.shape[:2]
    hs, ws = h // supersample, w // supersample
    img = image[: hs * supersample, : ws * supersample]
    return cv2.resize(img, (ws, hs), interpolation=cv2.INTER_AREA)


def mosaic(rgb: np.ndarray, pattern: str) -> np.ndarray:
    """Sample one channel per site -> single-channel RAW image."""
    pat = BAYER_PATTERNS[pattern]
    h, w = rgb.shape[:2]
    raw = np.empty((h, w), dtype=rgb.dtype)
    for dr in (0, 1):
        for dc in (0, 1):
            raw[dr::2, dc::2] = rgb[dr::2, dc::2, pat[dr][dc]]
    return raw


def _sensor(state: Mapping[str, Any], params: Mapping[str, Any]) -> dict[str, Any]:
    rgb = pixel_aperture(state["current"], state["supersample"]) * params["exposure_scale"]
    out: dict[str, Any] = {"sensor_rgb": rgb, "bayer_pattern": params["pattern"]}
    if params["bayer"]:
        raw = mosaic(rgb, params["pattern"])
        out["raw_mosaic"] = raw
        out["current"] = raw
    else:
        out["current"] = rgb
        out["raw_mosaic"] = None
    return out


SENSOR_STAGE = Stage(
    name="sensor",
    fn=_sensor,
    params=(
        ParamSpec("exposure_scale", 0.8, lo=0.05, hi=2.0, step=0.05,
                  doc="scene radiance 1.0 -> this fraction of full well"),
        ParamSpec("bayer", True, doc="sample through the Bayer mosaic (off = ideal RGB sensor)"),
        ParamSpec("pattern", "RGGB", choices=tuple(BAYER_PATTERNS),
                  doc="Bayer layout/phase — part of the evidence structure"),
    ),
    provides=("sensor_rgb", "raw_mosaic"),
    doc="design-01 [6]: pixel-aperture integration + Bayer mosaic",
)


def _noise(state: Mapping[str, Any], params: Mapping[str, Any]) -> dict[str, Any]:
    img = state["current"]
    rng = np.random.default_rng(int(params["seed"]))
    var = params["shot_gain"] * np.clip(img, 0.0, None) + params["read_var"]
    noisy = img + rng.standard_normal(img.shape) * np.sqrt(var)
    noisy = np.clip(noisy, 0.0, 1.0)  # black level / saturation (PROVISIONAL simple clip)
    return {"current": noisy, "raw_noisy": noisy}


NOISE_STAGE = Stage(
    name="sensor_noise",
    fn=_noise,
    params=(
        ParamSpec("shot_gain", 0.001, lo=0.0, hi=0.05, step=0.0005,
                  doc="shot-noise gain a in sigma^2 = a*I + b (photon-transfer slope)"),
        ParamSpec("read_var", 0.00005, lo=0.0, hi=0.01, step=0.00005,
                  doc="read-noise variance b (photon-transfer floor)"),
        ParamSpec("seed", 0, lo=0, hi=100000, step=1, doc="RNG seed (reproducibility)"),
    ),
    provides=("raw_noisy",),
    optional=True,
    doc="design-01 [7]: shot + read noise at the RAW domain, clipped",
)
