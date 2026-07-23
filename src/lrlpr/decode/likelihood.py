"""Single-frame likelihood scoring (design-02 §1-§2, noise model (a) only).

The forward model predicts a DISTRIBUTION over images, not an image (the seed
lesson, 2026-07-22). Scoring a hypothesis s means: render s through the KNOWN
channel with noise OFF to get the predicted mean ŷ(s), then evaluate how
probable the observed pixels y are under the noise distribution centered on ŷ.

Noise model (a), heteroscedastic Gaussian at the output domain:
    σ²(ŷ) = a·ŷ + b            (shot slope a, read floor b, per design-01 [7])
    log p(y|s) = -½ Σᵢ [ (yᵢ-ŷᵢ)²/σᵢ² + log 2πσᵢ² ]

This is EXACT when the observation's noise lives in the scoring domain (E1: no
codec/mosaic after noise) and is the deliberate CONTROL model once a codec
intervenes (E3 races it against the DCT-domain likelihood, design-02 §2b).

The predicted means are seed-INDEPENDENT, so ScoringModel caches them per
string: N candidate renders once, then any number of observations scored by
cheap array math.
"""

from __future__ import annotations

import copy
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from lrlpr.pipeline import Pipeline

_VAR_FLOOR = 1e-8  # guards log/÷ when a=b=0 (E0); far below any real noise level


def gaussian_loglik(
    y: np.ndarray, pred: np.ndarray, a: float, b: float
) -> tuple[float, np.ndarray]:
    """Total log-likelihood and its per-pixel map under σ²=a·pred+b."""
    var = np.maximum(a * np.clip(pred, 0.0, None) + b, _VAR_FLOOR)
    per_px = -0.5 * ((y - pred) ** 2 / var + np.log(2 * np.pi * var))
    return float(per_px.sum()), per_px


def sse(y: np.ndarray, pred: np.ndarray) -> float:
    """Sum of squared error — the noise-free residual (E0's exact-zero check)."""
    return float(((y - pred) ** 2).sum())


@dataclass
class ScoringModel:
    """Scores plate-string hypotheses against an observation under known nuisances.

    base_overrides / disabled fully specify the channel (the "oracle" nuisances).
    a, b are the noise-model constants used for the Gaussian likelihood. The
    string is injected at ``string_stage.string_param``.
    """

    pipeline: Pipeline
    base_overrides: Mapping[str, Mapping[str, Any]]
    disabled: frozenset[str] = frozenset()
    a: float = 0.0
    b: float = 0.0
    string_stage: str = "surface"
    string_param: str = "plate_string"
    _pred_cache: dict[str, np.ndarray] = field(default_factory=dict, repr=False)

    def _overrides_for(self, string: str) -> dict[str, dict[str, Any]]:
        ov = copy.deepcopy({k: dict(v) for k, v in self.base_overrides.items()})
        ov.setdefault(self.string_stage, {})[self.string_param] = string
        return ov

    def predict(self, string: str) -> np.ndarray:
        """Noise-free predicted mean image for ``string`` (cached)."""
        if string not in self._pred_cache:
            # Disabling the noise stage yields the deterministic mean.
            disabled = set(self.disabled) | {"sensor_noise"}
            state = self.pipeline.run(self._overrides_for(string), disabled=disabled)
            self._pred_cache[string] = np.ascontiguousarray(state["current"])
        return self._pred_cache[string]

    def observe(self, string: str, seed: int) -> np.ndarray:
        """Generate one noisy observation of ``string`` (the noise stage active)."""
        ov = self._overrides_for(string)
        ov.setdefault("sensor_noise", {})
        ov["sensor_noise"].update({"shot_gain": self.a, "read_var": self.b, "seed": seed})
        state = self.pipeline.run(ov, disabled=set(self.disabled))
        return np.ascontiguousarray(state["current"])

    def score(self, y: np.ndarray, string: str) -> float:
        """log p(y | string) under the Gaussian noise model."""
        total, _ = gaussian_loglik(y, self.predict(string), self.a, self.b)
        return total

    def score_map(self, y: np.ndarray, string: str) -> np.ndarray:
        return gaussian_loglik(y, self.predict(string), self.a, self.b)[1]
