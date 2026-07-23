"""In-model nuisance search (fit.py): everything through the model's parameters.

The G2 milestone: a posed, display-zoomed, snipped observation decoded by a
model that starts BLIND to pose, scale, position, and photometrics — all of
them searched in the renderer's own parameterization (Andrew's directive
2026-07-24: no image-space geometry surrogates; the simulator IS the
hypothesis space). The display zoom must be absorbed into char_height
("camera closer"), the pose recovered, and the decode exact.
"""

import os

import cv2
import numpy as np
import pytest

from lrlpr.camera import build_full_pipeline
from lrlpr.decode.fit import decode_with_fit
from lrlpr.decode.reference import srgb_inverse
from lrlpr.plate_spec import SPECS

FONT = next((p for p in (r"data\fonts\GL-Nummernschild-Eng.ttf",
                        r"C:\Windows\Fonts\arialbd.ttf") if os.path.exists(p)), None)
pytestmark = pytest.mark.skipif(FONT is None, reason="no font available")

SPEC = SPECS["mercosur_br_car"]
TRUTH = "RHB6I06"
ZOOM = 4.3
DIS = {"optics", "isp", "resample", "codec", "motion_rs"}


def test_in_model_search_decodes_posed_zoomed_snip():
    pipeline = build_full_pipeline()
    obs_ov = {"surface": {"font_path": os.path.abspath(FONT),
                          "plate_string": TRUTH},
              "project": {"char_height_px": 10.0, "supersample": 4,
                          "yaw_deg": 6.0, "pitch_deg": 3.0, "roll_deg": 4.0},
              "sensor": {"bayer": False},
              "sensor_noise": {"shot_gain": 5e-4, "read_var": 5e-5}}
    cur = np.clip(pipeline.run(obs_ov, disabled=set(DIS))["current"], 0, 1)
    disp8 = (cur ** (1 / 2.2) * 255).astype(np.uint8)
    big = cv2.resize(disp8, None, fx=ZOOM, fy=ZOOM,
                     interpolation=cv2.INTER_NEAREST)
    pad = 25
    canvas = np.full((big.shape[0] + 2 * pad, big.shape[1] + 2 * pad, 3), 30,
                     np.uint8)
    canvas[pad:-pad, pad:-pad] = big
    ref = srgb_inverse(canvas.astype(np.float64) / 255.0)

    base = {"surface": {"font_path": os.path.abspath(FONT)},
            "project": {"supersample": 4},
            "sensor": {"bayer": False},
            "sensor_noise": {"shot_gain": 5e-4, "read_var": 5e-5}}

    res = decode_with_fit(pipeline, base, DIS, SPEC, ref, truth=TRUTH)

    assert res.decoded == TRUTH
    assert res.delta_nats is not None and res.delta_nats > 0
    p = res.fit.params
    # display zoom absorbed into scale: 10 px at 4.3x view -> ~43 px
    assert abs(p["char_height_px"] - 10.0 * ZOOM) / (10.0 * ZOOM) < 0.10
    assert abs(p["roll_deg"] - 4.0) < 2.0  # pose actually recovered
