"""G1: sub-pixel homography registration (discussion log 2026-07-24 proposal).

The decisive test: the OBSERVATION is rendered with a pose the scoring model
does NOT know (its sliders say zero pose). Because shading precedes projection
and the plate is planar, the pose difference is exactly a homography — G1 must
fit it from string-independent structure (character cells masked out) and the
decode must then succeed. Without G1 this scenario is the measured 1-px ≈
100k-nats failure regime.
"""

import os

import cv2
import numpy as np
import pytest

from lrlpr.camera import build_full_pipeline
from lrlpr.decode import ScoringModel
from lrlpr.decode.reference import decode_reference, srgb_inverse
from lrlpr.plate_spec import SPECS

FONT = next((p for p in (r"data\fonts\GL-Nummernschild-Eng.ttf",
                        r"C:\Windows\Fonts\arialbd.ttf") if os.path.exists(p)), None)
pytestmark = pytest.mark.skipif(FONT is None, reason="no font available")

SPEC = SPECS["mercosur_br_car"]
TRUTH = "RHB6I06"
NEUTRAL = "XXX0X00"
ZOOM = 4.3  # deliberately non-integer (nearest-zoom jitter included)

BASE = {
    "surface": {"font_path": os.path.abspath(FONT) if FONT else "",
                "plate_string": TRUTH},
    "project": {"char_height_px": 10.0, "supersample": 4},
}

# G1's claim is GEOMETRY under a linear chain. A post-projection codec is
# deliberately excluded: JPEG blocks live in the observation's posed frame, so
# warping the image back cannot re-align them with the prediction's block grid
# — codec-under-unknown-pose requires G2 (render at the fitted pose) + E3.
LINEAR_CHAIN = {"sensor": {"bayer": False},
                "sensor_noise": {"shot_gain": 5e-4, "read_var": 5e-5}}
DISABLED = frozenset({"optics", "isp", "resample", "codec", "motion_rs"})


def _snip(current: np.ndarray) -> np.ndarray:
    disp8 = (np.clip(current, 0, 1) ** (1 / 2.2) * 255).astype(np.uint8)
    big = cv2.resize(disp8, None, fx=ZOOM, fy=ZOOM, interpolation=cv2.INTER_NEAREST)
    pad = 25
    canvas = np.full((big.shape[0] + 2 * pad, big.shape[1] + 2 * pad, 3), 30, np.uint8)
    canvas[pad:-pad, pad:-pad] = big
    return srgb_inverse(canvas.astype(np.float64) / 255.0)


def test_g1_decodes_under_unknown_pose():
    """Observation posed (yaw 6, pitch 3, roll 4); model sliders say zero pose."""
    pipeline = build_full_pipeline()
    posed = {**BASE, **LINEAR_CHAIN,
             "project": {**BASE["project"],
                         "yaw_deg": 6.0, "pitch_deg": 3.0, "roll_deg": 4.0}}
    ref = _snip(pipeline.run(posed, disabled=set(DISABLED))["current"])

    model = ScoringModel(pipeline, {**BASE, **LINEAR_CHAIN}, DISABLED, 0.0, 0.0)
    res = decode_reference(model, SPEC, ref, NEUTRAL, truth=TRUTH)

    assert res.registration.method == "ecc", "G1 refinement did not run/converge"
    assert res.decoded == TRUTH
    assert res.delta_nats is not None and res.delta_nats > 0


def test_g1_no_harm_on_zero_pose():
    """The easy case must stay easy with refinement enabled."""
    pipeline = build_full_pipeline()
    ref = _snip(pipeline.run(BASE)["current"])
    model = ScoringModel(pipeline, BASE, frozenset(), 0.0, 0.0)
    res = decode_reference(model, SPEC, ref, NEUTRAL, truth=TRUTH)
    assert res.decoded == TRUTH
    assert res.delta_nats is not None and res.delta_nats > 0
