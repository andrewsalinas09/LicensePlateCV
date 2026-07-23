"""Oracle-ladder rung configurations (docs/discussion-log.md).

Each rung returns (base_overrides, disabled) fully specifying a channel, so a
ScoringModel built from it is in ORACLE mode (all nuisances known — the regime
whose synthetic accuracy IS the ideal-observer bound, design-02 §8).

E0  zero noise, no blur/mosaic/codec — plumbing proof
E1  + sensor noise only (Gaussian likelihood exact; no character coupling)
E2  + optics blur + delivery downscale (coupling appears)
E3  + full chain (Bayer, demosaic, ISP, JPEG) — codec breaks Gaussian on purpose
"""

from __future__ import annotations

from typing import Any

# Stages that can be switched off (must be optional=True in their definition).
_ALL_OPTIONAL = {"motion_rs", "optics", "sensor_noise", "isp", "resample", "codec"}


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
) -> tuple[dict[str, dict[str, Any]], set[str], float, float]:
    """Return (base_overrides, disabled, a, b) for a rung.

    Bayer is OFF for E0-E2 (keeps noise Gaussian in the output domain, so the
    pixel likelihood is exact); E3 turns the full chain on.
    """
    ov: dict[str, dict[str, Any]] = {
        "surface": {"font_path": font_path, "plate_string": plate_string},
        "project": {"char_height_px": char_height_px, "supersample": supersample},
        "sensor": {"bayer": False},
    }
    disabled = set(_ALL_OPTIONAL)

    if rung in ("E1", "E2", "E3"):
        disabled.discard("sensor_noise")
        ov["sensor_noise"] = {"shot_gain": a, "read_var": b}
    if rung in ("E2", "E3"):
        disabled.discard("optics")
        ov["optics"] = {"defocus_radius_px": 0.0, "gaussian_sigma_px": blur_sigma_px}
        if downscale < 1.0:
            disabled.discard("resample")
            ov["resample"] = {"scale": downscale, "kernel": "area"}
    if rung == "E3":
        ov["sensor"] = {"bayer": True}
        for s in ("isp", "codec"):
            disabled.discard(s)
        ov["codec"] = {"quality": jpeg_quality, "generations": 1}

    return ov, disabled, a, b
