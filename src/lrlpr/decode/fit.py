"""In-model nuisance search (G2 / design-02 §7): match by RENDERING, always.

Andrew's directive (2026-07-24): "It is imperative that everything is searching
and matching through the model's parameters. It was designed to be a camera
taking a photo at a simulator." No image-space geometry surrogates: pose, scale,
position, sub-pixel phase, and photometrics are MODEL parameters; every
hypothesis is evaluated by rendering it and comparing to the observation. If a
real image cannot be matched, that indicts the simulator (a missing nuisance
dimension), never a registration heuristic.

Search ladder (coarse -> fine, all string-independent):
  A. Color-structure init: the blue band + white field located by color
     statistics (the "outside colors" bootstrap) -> initial char_height (from
     plate width), roll (band axis), rough position. Robust to lighting and
     surround, unlike template correlation (which failed on real_HR).
  B. Coarse pose grid around the init: each (char_height, yaw, pitch, roll)
     hypothesis is RENDERED (neutral string) and slid over the observation via
     zero-mean NCC — invariant to photometric gain/offset, so lighting cannot
     block localization.
  C. Nelder-Mead refinement of (char_height, yaw, pitch, roll, tx, ty) — tx/ty
     are the sub-pixel sensor phase, applied INSIDE the renderer via the
     project stage's grid warp (the observation is never resampled). The
     photometric pair (gain, offset) is solved analytically per render on the
     character-masked region. Objective: robust (median) masked squared
     residual.
  D. Decode with the existing slot machinery at the fitted parameters.

PROVISIONAL: scalar gain/offset photometrics (design-02 measured photometric
errors cheap vs geometric ones); character cells masked via the render's own
plate homography; screenshots at display zoom are absorbed into char_height
(the camera moves closer) — nearest-zoom blockiness is an unmodeled display
artifact the robust noise floor must eat.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import cv2
import numpy as np
from scipy.optimize import minimize

from lrlpr.decode.likelihood import ScoringModel
from lrlpr.decode.reference import robust_read_var
from lrlpr.decode.slots import SlotTable, decode_icm
from lrlpr.plate_spec import PlateSpec

NEUTRAL_DEFAULT = "XXX0X00"


def _gray(img: np.ndarray) -> np.ndarray:
    return img.mean(axis=2) if img.ndim == 3 else img


# --------------------------------------------------------------- stage A


def color_init(y_linear: np.ndarray) -> dict[str, float] | None:
    """Locate the plate from color structure alone: blue band + white field.

    Returns initial char_height_px, roll_deg, and band center, or None if no
    band-like region exists (caller falls back to a wider grid).
    """
    r, g, b = y_linear[..., 0], y_linear[..., 1], y_linear[..., 2]
    blue = (b > 1.4 * r) & (b > 1.15 * g) & (b > 0.015)
    if blue.sum() < 20:
        return None
    ys, xs = np.nonzero(blue)
    pts = np.stack([xs.astype(float), ys.astype(float)])
    center = pts.mean(axis=1)
    cov = np.cov(pts)
    evals, evecs = np.linalg.eigh(cov)
    major = evecs[:, np.argmax(evals)]
    roll = float(np.degrees(np.arctan2(major[1], major[0])))
    if roll > 90:
        roll -= 180
    if roll < -90:
        roll += 180
    proj = (pts[0] - center[0]) * major[0] + (pts[1] - center[1]) * major[1]
    band_len = float(np.percentile(proj, 98) - np.percentile(proj, 2))
    plate_w = band_len * 400.0 / 390.0  # band is 390 of 400 mm
    char_height = 0.1625 * plate_w  # 65 / 400
    if char_height < 3:
        return None
    return {"char_height_px": char_height, "roll_deg": float(np.clip(roll, -25, 25)),
            "cx": float(center[0]), "cy": float(center[1])}


# --------------------------------------------------------------- rendering


def _project_overrides(base: dict[str, dict[str, Any]], **proj) -> dict:
    ov = {k: dict(v) for k, v in base.items()}
    ov.setdefault("project", {}).update(proj)
    return ov


def _render(pipeline, ov, disabled, string_stage="surface",
            string_param="plate_string", string=NEUTRAL_DEFAULT):
    ov = {k: dict(v) for k, v in ov.items()}
    ov.setdefault(string_stage, {})[string_param] = string
    state = pipeline.run(ov, disabled=set(disabled) | {"sensor_noise"})
    return state


def char_cell_mask(state, spec: PlateSpec, shape) -> np.ndarray:
    """True where character cells project — from the render's own homography.

    String-independent by construction (uses slot GEOMETRY, not glyphs).
    """
    ss = state["supersample"]
    H = state["homography"] / ss
    mask = np.zeros(shape[:2], np.uint8)
    half_w = 0.55 * spec.slots[1].cx - 0.55 * spec.slots[0].cx  # ~half pitch
    top = spec.char_baseline_v - spec.char_height * 1.15
    bot = spec.char_baseline_v + spec.char_height * 0.15
    for slot in spec.slots:
        quad_mm = np.array([[slot.cx - half_w, top], [slot.cx + half_w, top],
                            [slot.cx + half_w, bot], [slot.cx - half_w, bot]])
        q = cv2.perspectiveTransform(quad_mm.reshape(1, -1, 2), H)[0]
        cv2.fillPoly(mask, [np.round(q).astype(np.int32)], 1)
    return mask.astype(bool)


# --------------------------------------------------------------- fitting


@dataclass
class FitResult:
    params: dict[str, float]  # fitted project-stage parameters
    window: tuple[int, int]  # top-left of the matched window in the reference
    shape: tuple[int, int]  # window size (= render size)
    gain: float
    offset: float
    score: float  # final NCC of the fitted render at the window
    n_renders: int = 0


def _slide(y_gray32: np.ndarray, tmpl_gray32: np.ndarray):
    """Best gain/offset-invariant placement of the render inside the ref."""
    th, tw = tmpl_gray32.shape
    H, W = y_gray32.shape
    pad_y = max(0, th - H + 4) // 2 + 4
    pad_x = max(0, tw - W + 4) // 2 + 4
    yp = cv2.copyMakeBorder(y_gray32, pad_y, pad_y, pad_x, pad_x,
                            cv2.BORDER_REPLICATE)
    res = cv2.matchTemplate(yp, tmpl_gray32, cv2.TM_CCOEFF_NORMED)
    res = np.nan_to_num(res, nan=-1.0)
    _, maxv, _, (mx, my) = cv2.minMaxLoc(res)
    return float(maxv), (mx - pad_x, my - pad_y)


def _gain_offset(y_win: np.ndarray, pred: np.ndarray, mask: np.ndarray):
    """Least-squares photometric map pred -> y on the non-character mask."""
    p = _gray(pred)[mask]
    o = _gray(y_win)[mask]
    var = p.var()
    if var < 1e-12:
        return 1.0, float(o.mean() - p.mean())
    g = float(((p - p.mean()) * (o - o.mean())).mean() / var)
    g = float(np.clip(g, 0.05, 20.0))
    return g, float(o.mean() - g * p.mean())


def _extract_window(ref: np.ndarray, xy, shape):
    x, y = xy
    h, w = shape
    top, left = max(0, -y), max(0, -x)
    bot = max(0, y + h - ref.shape[0])
    right = max(0, x + w - ref.shape[1])
    if any((top, left, bot, right)):
        ref = cv2.copyMakeBorder(ref, top, bot, left, right, cv2.BORDER_REPLICATE)
    return ref[y + top: y + top + h, x + left: x + left + w]


def fit_nuisances(
    pipeline,
    base_overrides: dict,
    disabled,
    spec: PlateSpec,
    ref_linear: np.ndarray,
    neutral: str = NEUTRAL_DEFAULT,
    yaw_grid=(-15.0, 0.0, 15.0),
    pitch_grid=(-10.0, 0.0, 10.0),
    roll_span=(-6.0, 0.0, 6.0),
    ch_span=(0.75, 0.9, 1.0, 1.15, 1.3),
    refine_iters: int = 120,
) -> FitResult:
    """Stages A-C: search the model's own parameters to explain ref_linear."""
    counter = {"n": 0}

    def render(**proj):
        counter["n"] += 1
        return _render(pipeline, _project_overrides(base_overrides, **proj),
                       disabled, string=neutral)

    init = color_init(ref_linear)
    if init is not None:
        ch0, roll0 = init["char_height_px"], init["roll_deg"]
    else:  # fall back: guess from reference height, wider sweep
        ch0, roll0 = max(6.0, 0.28 * ref_linear.shape[0]), 0.0
        ch_span = (0.4, 0.6, 0.85, 1.2, 1.7)
    ch0 = float(np.clip(ch0, 3.0, 78.0))

    y_g = np.ascontiguousarray(_gray(ref_linear), np.float32)
    best = None  # (ncc, params, xy, shape)
    for f in ch_span:
        ch = float(np.clip(ch0 * f, 2.5, 79.0))
        for yaw in yaw_grid:
            for pitch in pitch_grid:
                for dr in roll_span:
                    roll = float(np.clip(roll0 + dr, -29.0, 29.0))
                    st = render(char_height_px=ch, yaw_deg=yaw,
                                pitch_deg=pitch, roll_deg=roll)
                    tmpl = np.ascontiguousarray(_gray(st["current"]), np.float32)
                    if (tmpl.shape[0] > 3 * y_g.shape[0]
                            or tmpl.shape[1] > 3 * y_g.shape[1]):
                        continue
                    ncc, xy = _slide(y_g, tmpl)
                    p = {"char_height_px": ch, "yaw_deg": yaw,
                         "pitch_deg": pitch, "roll_deg": roll}
                    if best is None or ncc > best[0]:
                        best = (ncc, p, xy, tmpl.shape)
    if best is None:
        raise ValueError("no pose hypothesis produced a comparable render")
    _, p0, xy0, shape0 = best

    # Stage C: continuous refinement; window FIXED at the stage-B lock, render
    # forced onto the window grid (grid_shape) with sub-pixel phase tx/ty.
    y_win = _extract_window(ref_linear, xy0, shape0)

    def objective(v):
        ch, yaw, pitch, roll, tx, ty = v
        if not (2.5 <= ch <= 79 and abs(yaw) < 60 and abs(pitch) < 45
                and abs(roll) < 29 and abs(tx) < 4 and abs(ty) < 4):
            return 1e6
        gw = np.array([[1.0, 0, tx], [0, 1.0, ty], [0, 0, 1.0]])
        st = render(char_height_px=float(ch), yaw_deg=float(yaw),
                    pitch_deg=float(pitch), roll_deg=float(roll),
                    grid_warp=gw, grid_shape=shape0)
        pred = st["current"]
        mask = ~char_cell_mask(st, spec, pred.shape)
        g, o = _gain_offset(y_win, pred, mask)
        r = _gray(y_win) - (g * _gray(pred) + o)
        return float(np.median(r[mask] ** 2))

    v0 = np.array([p0["char_height_px"], p0["yaw_deg"], p0["pitch_deg"],
                   p0["roll_deg"], 0.0, 0.0])
    # Explicit initial simplex: scipy's default uses 5%-of-value steps, which
    # DEGENERATES to 0.00025 for zero-valued components — yaw/pitch/tx/ty
    # would never be explored (observed: fit pinned at yaw=pitch=0, left-side
    # slots flipping from the uncorrected foreshortening).
    steps = np.array([2.0, 5.0, 4.0, 2.0, 0.6, 0.6])
    simplex = np.vstack([v0] + [v0 + steps[i] * np.eye(6)[i] for i in range(6)])
    res = minimize(objective, v0, method="Nelder-Mead",
                   options={"maxiter": refine_iters, "xatol": 0.02,
                            "fatol": 1e-8, "initial_simplex": simplex})
    ch, yaw, pitch, roll, tx, ty = res.x
    params = {"char_height_px": float(ch), "yaw_deg": float(yaw),
              "pitch_deg": float(pitch), "roll_deg": float(roll),
              "grid_warp": np.array([[1.0, 0, tx], [0, 1.0, ty], [0, 0, 1.0]]),
              "grid_shape": shape0}
    st = _render(pipeline, _project_overrides(base_overrides, **params),
                 disabled, string=neutral)
    pred = st["current"]
    mask = ~char_cell_mask(st, spec, pred.shape)
    g, o = _gain_offset(y_win, pred, mask)
    pg, yg = _gray(pred)[mask], _gray(y_win)[mask]
    ncc = float(np.corrcoef(pg, yg)[0, 1])
    return FitResult(params=params, window=xy0, shape=tuple(shape0), gain=g,
                     offset=o, score=ncc, n_renders=counter["n"])


# --------------------------------------------------------------- decoding


@dataclass
class FitDecode:
    fit: FitResult
    observation: np.ndarray
    b_hat: float
    tables: list[SlotTable] = field(default_factory=list)
    decoded: str = ""
    truth: str | None = None
    delta_nats: float | None = None


def decode_with_fit(
    pipeline,
    base_overrides: dict,
    disabled,
    spec: PlateSpec,
    ref_linear: np.ndarray,
    truth: str | None = None,
    neutral: str = NEUTRAL_DEFAULT,
    passes: int = 2,
    **fit_kw,
) -> FitDecode:
    """Stage D: fit nuisances in-model, then slot-decode at the fit.

    The photometric map is inverted on the OBSERVATION side as (y - offset) /
    gain — a scalar relabeling of intensities (exactly invertible), not a
    spatial resampling, so the never-resample rule is respected.
    """
    fit = fit_nuisances(pipeline, base_overrides, disabled, spec, ref_linear,
                        neutral=neutral, **fit_kw)
    ov = _project_overrides(base_overrides, **fit.params)
    model = ScoringModel(pipeline, ov, frozenset(disabled), 0.0, 0.0)
    y_win = _extract_window(ref_linear, fit.window, fit.shape)
    y = (y_win - fit.offset) / max(fit.gain, 1e-6)

    model.b = max(robust_read_var(y - model.predict(neutral)), 1e-6)
    decoded, tables = decode_icm(model, y, spec, neutral, passes=passes)

    out = FitDecode(fit=fit, observation=y, b_hat=model.b, tables=tables,
                    decoded=decoded, truth=truth)
    if truth is not None:
        out.truth = spec.validate_string(truth)
        from lrlpr.decode.reference import _delta_vs_truth
        out.delta_nats = _delta_vs_truth(tables, out.truth)
    return out
