"""Oracle-ladder rung E2: blur + delivery downscale — coupling appears.

Three claims under test (design-02 §3 + the 2026-07-22 audit):
1. The var_scale correction is REAL: after an integer-factor area downscale of
   the noise, empirical residual variance matches (a·ŷ+b)·scale², not (a·ŷ+b).
2. Blur creates slot coupling: a slot's table now depends on what the other
   slots' reference says (it provably does not at E0).
3. Iterated conditional decoding still recovers truth at moderate blur — the
   regime where per-slot conditioning is a good approximation.
"""

import os

import numpy as np
import pytest

from lrlpr.camera import build_full_pipeline
from lrlpr.decode import ScoringModel, decode_icm, slot_tables
from lrlpr.decode.rungs import rung_config
from lrlpr.plate_spec import SPECS

FONT = next((p for p in (r"data\fonts\GL-Nummernschild-Eng.ttf",
                        r"C:\Windows\Fonts\arialbd.ttf") if os.path.exists(p)), None)
pytestmark = pytest.mark.skipif(FONT is None, reason="no font available")

SPEC = SPECS["mercosur_br_car"]
TRUTH = "ABC1D23"


def _model(rung, **kw):
    rc = rung_config(rung, FONT, plate_string=TRUTH, **kw)
    return ScoringModel(build_full_pipeline(), rc.overrides, frozenset(rc.disabled),
                        rc.a, rc.b, var_scale=rc.var_scale)


def test_e2_downscale_variance_correction_matches_reality():
    """Noise through a 2x2 area downscale: var_out ≈ (a·ŷ+b)/4, not (a·ŷ+b)."""
    m = _model("E2", a=1e-3, b=1e-4, char_height_px=16.0, downscale=0.5)
    assert m.var_scale == pytest.approx(0.25)
    pred = m.predict(TRUTH)
    res = np.stack([m.observe(TRUTH, seed) - pred for seed in range(40)])
    emp = res.var(axis=0).mean()
    modeled = (m.a * np.clip(pred, 0, None) + m.b).mean()
    ratio = emp / modeled
    assert 0.18 < ratio < 0.32, f"uncorrected-variance ratio {ratio:.3f} not ~0.25"
    assert 0.7 < ratio / m.var_scale < 1.3  # corrected model matches empirics


def test_e2_blur_couples_neighboring_slots():
    """With blur, slot-3's WITHIN-SLOT score shape depends on the other slots'
    reference. Without blur the other cells only add a constant offset to every
    candidate (disjoint support), which centering removes exactly."""
    def ref_sensitivity(blur):
        m = _model("E2", a=0.0, b=1e-4, char_height_px=8.0, blur_sigma_px=blur)
        y = m.predict(TRUTH)
        t_true = slot_tables(m, y, SPEC, ref_string=TRUTH)[3]
        t_other = slot_tables(m, y, SPEC, ref_string="XYZ9Z99")[3]

        def centered(t):
            mean = np.mean(list(t.scores.values()))
            return {c: v - mean for c, v in t.scores.items()}

        c_true, c_other = centered(t_true), centered(t_other)
        return max(abs(c_true[c] - c_other[c]) for c in c_true)

    weak, strong = ref_sensitivity(0.0), ref_sensitivity(2.0)
    assert strong > 10 * max(weak, 1e-9), (weak, strong)


def test_e2_icm_recovers_truth_at_moderate_blur():
    m = _model("E2", a=5e-4, b=5e-5, char_height_px=12.0,
               blur_sigma_px=1.0, downscale=0.5)
    y = m.observe(TRUTH, seed=3)
    decoded, tables = decode_icm(m, y, SPEC, ref_string="XXX0X00", passes=3)
    assert decoded == TRUTH
    assert all(t.margin() > 0 for t in tables)
