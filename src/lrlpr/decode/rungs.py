"""Oracle-ladder rung configurations (docs/discussion-log.md).

Each rung yields a RungConfig fully specifying a channel, so a ScoringModel
built from it is in ORACLE mode (all nuisances known — the regime whose
synthetic accuracy IS the ideal-observer bound, design-02 §8).

E0  zero noise, no blur/mosaic/codec — plumbing proof
E1  + sensor noise only (Gaussian likelihood exact; no character coupling)
E2  + optics blur + delivery downscale (coupling appears). Blur precedes the
    noise stage (mean-only, likelihood untouched). The area downscale FOLLOWS
    noise, so the likelihood is kept exact by var_scale = scale²: an integer-
    factor box average of k² independent samples has var (a·ŷ+b)/k², outputs
    independent (exact for integer 1/scale; approximate otherwise).
E3  + full chain (Bayer, demosaic, ISP, JPEG) — the nonlinear chain breaks the
    pixel Gaussian ON PURPOSE (it is the control model; measured 2026-07-23:
    at 7 px chars it flips within-class neighbors, e.g. R→B). var_scale stays 1
    — no scalar correction can fix a nonlinear-chain misspecification.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Stages that can be switched off (must be optional=True in their definition).
_ALL_OPTIONAL = {"motion_rs", "optics", "sensor_noise", "isp", "resample", "codec"}


@dataclass(frozen=True)
class RungConfig:
    overrides: dict[str, dict[str, Any]]
    disabled: set[str] = field(default_factory=set)
    a: float = 0.0  # noise-stage shot gain (raw stage parameter)
    b: float = 0.0  # noise-stage read variance (raw stage parameter)
    var_scale: float = 1.0  # likelihood variance factor for post-noise linear stages


def rung_config(
    rung: str,
    font_path: str,
    plate_string: str = "ABC1D23",
    char_height_px: float = 24.0,
    supersample: int = 4,
    a: float = 0.0,
    b: float = 0.0,
    blur_sigma_px: float = 0.0,
    downscale: float = 1.0,
    jpeg_quality: int = 60,
) -> RungConfig:
    """Build the channel configuration for a rung.

    Bayer is OFF for E0-E2 (keeps the post-noise chain linear, so the pixel
    likelihood is exact given var_scale); E3 turns the full chain on.
    """
    ov: dict[str, dict[str, Any]] = {
        "surface": {"font_path": font_path, "plate_string": plate_string},
        "project": {"char_height_px": char_height_px, "supersample": supersample},
        "sensor": {"bayer": False},
    }
    disabled = set(_ALL_OPTIONAL)
    var_scale = 1.0

    if rung in ("E1", "E2", "E3"):
        disabled.discard("sensor_noise")
        ov["sensor_noise"] = {"shot_gain": a, "read_var": b}
    if rung in ("E2", "E3"):
        disabled.discard("optics")
        ov["optics"] = {"defocus_radius_px": 0.0, "gaussian_sigma_px": blur_sigma_px}
        if downscale < 1.0:
            disabled.discard("resample")
            ov["resample"] = {"scale": downscale, "kernel": "area"}
            if rung == "E2":
                var_scale = downscale**2  # exact for integer 1/scale box average
    if rung == "E3":
        ov["sensor"] = {"bayer": True}
        for s in ("isp", "codec"):
            disabled.discard(s)
        ov["codec"] = {"quality": jpeg_quality, "generations": 1}

    return RungConfig(overrides=ov, disabled=disabled, a=a, b=b, var_scale=var_scale)
