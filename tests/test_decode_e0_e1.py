"""Oracle-ladder rungs E0 (plumbing) and E1 (noise-only) — decoder proofs.

E0: zero noise, all nuisances known -> truth scores best with EXACTLY zero
    residual; any wrong string has positive residual. Proves renderer +
    likelihood + hypothesis loop are mutually consistent.
E1: known Gaussian noise, no character coupling -> per-slot argmax is the exact
    MAP; machinery is calibrated by construction (validates the CODE against
    theory, per design-02 §6 — NOT evidence the model fits reality).
"""

import os

import numpy as np
import pytest

from lrlpr.camera import build_full_pipeline
from lrlpr.decode import ScoringModel, decode_independent, slot_tables, sse
from lrlpr.decode.rungs import rung_config
from lrlpr.plate_spec import SPECS

FONT = next((p for p in (r"data\fonts\GL-Nummernschild-Eng.ttf",
                        r"C:\Windows\Fonts\arialbd.ttf") if os.path.exists(p)), None)
pytestmark = pytest.mark.skipif(FONT is None, reason="no font available")

SPEC = SPECS["mercosur_br_car"]
TRUTH = "ABC1D23"


def _model(rung, **kw):
    rc = rung_config(rung, FONT, plate_string=TRUTH, **kw)
    model = ScoringModel(build_full_pipeline(), rc.overrides, frozenset(rc.disabled),
                         rc.a, rc.b, var_scale=rc.var_scale)
    return model, rc


# --------------------------------------------------------------------- E0

def test_e0_truth_has_zero_residual():
    m, _ = _model("E0")
    y = m.predict(TRUTH)  # zero-noise observation == the mean itself
    assert sse(y, m.predict(TRUTH)) == 0.0


def test_e0_wrong_string_has_positive_residual_and_lower_score():
    m, _ = _model("E0")
    y = m.predict(TRUTH)
    wrong = "ABC1D24"  # last digit differs
    assert sse(y, m.predict(wrong)) > 0.0
    assert m.score(y, TRUTH) > m.score(y, wrong)


def test_e0_every_slot_recovers_truth_by_argmax():
    m, _ = _model("E0")
    y = m.predict(TRUTH)
    decoded, tables = decode_independent(m, y, SPEC, ref_string=TRUTH)
    assert decoded == TRUTH
    for t in tables:
        assert t.margin() > 0.0  # strict winner in every slot


def test_e0_reference_string_does_not_matter_without_coupling():
    """No blur -> slot j score is independent of the other slots' reference."""
    m, _ = _model("E0")
    y = m.predict(TRUTH)
    t_ref_truth = slot_tables(m, y, SPEC, ref_string=TRUTH)[3]
    t_ref_other = slot_tables(m, y, SPEC, ref_string="XYZ9Z99")[3]
    # Slot 3 is a digit; its argmax must be truth's digit regardless of ref.
    assert t_ref_truth.argmax() == t_ref_other.argmax() == TRUTH[3]


# --------------------------------------------------------------------- E1

def test_e1_low_noise_recovers_all_slots():
    m, _ = _model("E1", a=2e-4, b=2e-5, char_height_px=24.0)
    y = m.observe(TRUTH, seed=1)
    decoded, _ = decode_independent(m, y, SPEC, ref_string=TRUTH)
    assert decoded == TRUTH


def test_e1_noise_is_seed_reproducible():
    m, _ = _model("E1", a=1e-3, b=1e-4)
    assert np.array_equal(m.observe(TRUTH, 5), m.observe(TRUTH, 5))
    assert not np.array_equal(m.observe(TRUTH, 5), m.observe(TRUTH, 6))


def test_e1_margins_shrink_as_noise_grows():
    """Higher noise variance -> smaller per-slot evidence gap (LLR ∝ 1/σ²)."""
    def mean_margin(a, b):
        m, _ = _model("E1", a=a, b=b)
        y = m.predict(TRUTH)  # score the clean mean; margin reflects 1/σ² scaling
        tables = slot_tables(m, y, SPEC, ref_string=TRUTH)
        return np.mean([t.margin() for t in tables])

    assert mean_margin(2e-4, 2e-5) > mean_margin(4e-3, 4e-4)


def test_e1_machinery_is_calibrated():
    """Under the true generating model, assigned confidence ≈ empirical accuracy.

    Tautological (E1's likelihood IS the generator) — this validates the CODE,
    not the model's realism. Predictions are seed-independent and cached, so
    only observations regenerate per seed.
    """
    # Operating point with GENUINE ambiguity: 4 px chars at max noise gives
    # ~80% per-slot accuracy (verified), so this exercises calibration under
    # real uncertainty rather than the trivial all-correct regime.
    m, _ = _model("E1", a=0.05, b=0.01, char_height_px=4.0, supersample=2)
    m.predict(TRUTH)  # warm cache

    n_seeds = 60
    conf, correct = [], []
    for seed in range(n_seeds):
        y = m.observe(TRUTH, seed=seed)
        for j, t in enumerate(slot_tables(m, y, SPEC, ref_string=TRUTH)):
            conf.append(t.top1_posterior())
            correct.append(t.argmax() == TRUTH[j])
    mean_conf, acc = float(np.mean(conf)), float(np.mean(correct))
    assert 0.6 < acc < 0.95, f"need an ambiguous regime, got acc={acc:.3f}"
    # Calibration: mean assigned confidence tracks realized accuracy.
    assert abs(mean_conf - acc) < 0.08, f"conf={mean_conf:.3f} acc={acc:.3f}"
