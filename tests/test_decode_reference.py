"""Oracle-screenshot rung: decode an image that left and re-entered the system.

The observation is NOT a pipeline array but a simulated screenshot of one:
display gamma (1/2.2), 8-bit quantization, nearest-neighbor view zoom, app
border, then sRGB-inverse linearization on load (piecewise != pure 2.2 — the
deliberate residual mismatch of this rung). With the channel settings KNOWN,
registration must recover the view transform and the decode must be exact.
(Verified live 2026-07-23 on the RHB6I06 files: known settings -> 7/7 slots,
delta +148 nats; unknown hand-tuned settings -> confidently wrong. The gap is
the cost of unknown nuisances, not of the screenshot channel.)
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
ZOOM = 3.5
OVERRIDES = {
    "surface": {"font_path": os.path.abspath(FONT) if FONT else "",
                "plate_string": TRUTH},
    "project": {"char_height_px": 8.0, "supersample": 4},
}


def _screenshot(current: np.ndarray) -> np.ndarray:
    """Display gamma -> 8-bit -> nearest zoom -> dark border, as the app shows it."""
    disp8 = (np.clip(current, 0, 1) ** (1 / 2.2) * 255).astype(np.uint8)
    big = cv2.resize(disp8, None, fx=ZOOM, fy=ZOOM, interpolation=cv2.INTER_NEAREST)
    pad = 9
    canvas = np.full((big.shape[0] + 2 * pad, big.shape[1] + 2 * pad, 3), 30, np.uint8)
    canvas[pad:-pad, pad:-pad] = big
    return canvas


def test_oracle_screenshot_roundtrip_decodes_exactly():
    pipeline = build_full_pipeline()
    shot = _screenshot(pipeline.run(OVERRIDES)["current"])  # noise on, seed 0
    ref_linear = srgb_inverse(shot.astype(np.float64) / 255.0)

    model = ScoringModel(pipeline, OVERRIDES, frozenset(), 0.0, 0.0)
    res = decode_reference(model, SPEC, ref_linear, NEUTRAL, truth=TRUTH)

    assert abs(res.registration.scale - ZOOM) / ZOOM < 0.05  # view zoom recovered
    assert res.decoded == TRUTH
    assert res.delta_nats is not None and res.delta_nats > 0  # design-02 §8.6 margin


def test_roomy_snip_registers_despite_large_surround():
    """A snip where the render is only ~38% of the capture must still find the
    true zoom (pre-fix: min_cover=0.5 FORBADE it -> forced 13.5x vs true 5.7x
    -> all-slots garbage, Andrew's HTR0B00, 2026-07-23)."""
    pipeline = build_full_pipeline()
    shot = _screenshot(pipeline.run(OVERRIDES)["current"])
    bh, bw = shot.shape[:2]
    canvas = np.full((int(bh / 0.38), int(bw / 0.38), 3), 30, np.uint8)
    y0, x0 = (canvas.shape[0] - bh) // 2, (canvas.shape[1] - bw) // 2
    canvas[y0:y0 + bh, x0:x0 + bw] = shot
    ref_linear = srgb_inverse(canvas.astype(np.float64) / 255.0)

    model = ScoringModel(pipeline, OVERRIDES, frozenset(), 0.0, 0.0)
    res = decode_reference(model, SPEC, ref_linear, NEUTRAL, truth=TRUTH)

    assert abs(res.registration.scale - ZOOM) / ZOOM < 0.05
    assert res.decoded == TRUTH


def test_tight_snip_still_registers_via_overhang():
    """A hand snip cropped inside the render's backdrop margin must not force
    the scale search low (pre-fix failure: zoom 3.8 vs true 7 -> garbage)."""
    pipeline = build_full_pipeline()
    shot = _screenshot(pipeline.run(OVERRIDES)["current"])
    cut_v, cut_h = round(2.2 * ZOOM), round(3.5 * ZOOM)  # into the backdrop margin
    tight = shot[cut_v:-cut_v, cut_h:-cut_h]
    ref_linear = srgb_inverse(tight.astype(np.float64) / 255.0)

    model = ScoringModel(pipeline, OVERRIDES, frozenset(), 0.0, 0.0)
    res = decode_reference(model, SPEC, ref_linear, NEUTRAL, truth=TRUTH)

    assert abs(res.registration.scale - ZOOM) / ZOOM < 0.05
    assert res.decoded == TRUTH
