"""Decode an EXTERNAL reference image (screenshot / crop) against the forward model.

PROVISIONAL instrumentation for the oracle-screenshot rung (discussion log
2026-07-22 "reference images"): the observation did not come from our pipeline
run but from a file — display gamma, 8-bit quantization, PNG, unknown view
rescaling. Registration here is NOT design-02 §7's EM loop; it is the
string-independent bootstrap that §7 calls for:

  - The template is the forward model's prediction for a NEUTRAL string (not
    the truth, not a hypothesis under test) so no character information leaks
    into registration. What localizes the plate is the structure outside the
    characters — band, retroreflective field, backdrop — Andrew's "the colors
    on the outside are giving a ton of info" observation, made operational.
  - Search is over (uniform scale, translation) via zero-mean normalized
    cross-correlation (TM_CCOEFF_NORMED), coarse geometric sweep then local
    refine. NOT least-squares (TM_SQDIFF_NORMED): normalized SSD is degenerate
    under scale search — a tiny flat template region matched to any flat patch
    scores near zero, so small scales always win (observed on the first
    RHB6I06 run: it matched a 21x10 dark corner). Zero-mean correlation
    scores flat-on-flat as ~0 and is comparable across template sizes. A
    minimum-coverage constraint (template must span >= min_cover of the
    reference in one dimension) additionally bounds the scale search to
    "the snip is mostly the plate view".

Domain note: with the ISP's srgb_gamma on (default), the pipeline's final
"current" is display-referred; the app's screenshot channel applies a further
1/2.2 display gamma. sRGB-inverting the file (≈ ^2.2) therefore lands the
reference approximately back in the pipeline-output domain. Approximately —
the piecewise-sRGB vs pure-2.2 mismatch is a deliberate, known residual of
this rung.

Noise model for scoring: a=0, b estimated robustly from the registered
residual against the neutral-string prediction (median of squared residuals
scaled by 1/0.4549, the χ²₁ median) — character-cell mismatches are outliers
the median ignores. This absorbs the render's realized sensor noise draw,
quantization, and resampling error into one honest scalar floor.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import cv2
import numpy as np

from lrlpr.decode.likelihood import ScoringModel
from lrlpr.decode.slots import SlotTable, decode_icm
from lrlpr.plate_spec import PlateSpec

# Median of chi^2_1: E[median((r/sigma)^2)] = 0.4549 -> robust variance scale.
_CHI2_MEDIAN = 0.4549


def srgb_inverse(x01: np.ndarray) -> np.ndarray:
    """Display-referred [0,1] -> linear (IEC 61966-2-1 inverse), vectorized."""
    x = np.clip(np.asarray(x01, dtype=np.float64), 0.0, 1.0)
    return np.where(x <= 0.04045, x / 12.92, ((x + 0.055) / 1.055) ** 2.4)


@dataclass
class Registration:
    scale: float  # template (prediction) pixels -> reference pixels
    x: int  # top-left of the matched region in the reference
    y: int
    score: float  # match quality: NCC (G0) or ECC rho (G1); higher = better, max 1
    warp: np.ndarray | None = None  # G1: 3x3 homography, template px -> reference px
    method: str = "ncc"  # "ncc" (G0 similarity) | "ecc" (G1 sub-pixel homography)


def _match_at_scale(ref32: np.ndarray, tmpl: np.ndarray, s: float):
    th, tw = round(tmpl.shape[0] * s), round(tmpl.shape[1] * s)
    if th < 8 or tw < 8 or th > ref32.shape[0] or tw > ref32.shape[1]:
        return None
    t = cv2.resize(tmpl, (tw, th), interpolation=cv2.INTER_LINEAR).astype(np.float32)
    res = cv2.matchTemplate(ref32, t, cv2.TM_CCOEFF_NORMED)
    res = np.nan_to_num(res, nan=-np.inf, posinf=-np.inf, neginf=-np.inf)
    _, maxv, _, maxloc = cv2.minMaxLoc(res)
    return float(maxv), maxloc


def register(ref_linear: np.ndarray, template: np.ndarray,
             n_coarse: int = 25, n_fine: int = 13,
             min_cover: float = 0.2, overhang: float = 0.25) -> Registration:
    """Find (scale, translation) of the template inside the reference image.

    min_cover: the scaled template must span at least this fraction of the
    reference in width or height. Deliberately PERMISSIVE (0.2): its only job
    is to kill degenerate tiny-flat-patch locks; the zero-mean NCC does the
    real discrimination. At 0.5 it FORBADE the true zoom on a roomy snip
    (render occupying 38% of the capture -> forced 32%-too-large template ->
    all-slots-garbage decode, 2026-07-23). A snip may legitimately contain
    far more surround than render.
    overhang: the reference is replicate-padded by this fraction of its size
    before matching, so a hand snip cropped tighter than the template's
    backdrop margin can still register (the template may hang past the snip
    edge). Without this, a tight snip forces the scale search low and the
    decode collapses (observed: char-7 tight snip -> zoom 3.8 vs true 7 ->
    garbage). Returned x/y are in ORIGINAL reference coordinates and may be
    negative when the template overhangs.
    """
    ref32 = np.ascontiguousarray(ref_linear, dtype=np.float32)
    tmpl = np.ascontiguousarray(template, dtype=np.float32)
    m = round(overhang * min(ref32.shape[:2]))
    refp = cv2.copyMakeBorder(ref32, m, m, m, m, cv2.BORDER_REPLICATE)
    s_max = min(refp.shape[0] / tmpl.shape[0], refp.shape[1] / tmpl.shape[1])
    s_min = min_cover * max(ref32.shape[0] / tmpl.shape[0],
                            ref32.shape[1] / tmpl.shape[1])
    s_min = min(s_min, s_max)  # keep a non-empty range
    best: tuple[float, float, tuple[int, int]] | None = None
    for s in np.geomspace(s_min, s_max, n_coarse):
        found = _match_at_scale(refp, tmpl, float(s))
        if found and (best is None or found[0] > best[0]):
            best = (found[0], float(s), found[1])
    if best is None:
        raise ValueError("registration failed: no valid scale in "
                         f"[{s_min:.2f}, {s_max:.2f}]")
    for s in np.linspace(max(best[1] * 0.9, s_min), min(best[1] * 1.1, s_max), n_fine):
        found = _match_at_scale(refp, tmpl, float(s))
        if found and found[0] > best[0]:
            best = (found[0], float(s), found[1])
    score, s, (x, y) = best
    return Registration(scale=s, x=int(x) - m, y=int(y) - m, score=score)


def _gray32(img: np.ndarray) -> np.ndarray:
    g = img.mean(axis=2) if img.ndim == 3 else img
    return np.ascontiguousarray(g, dtype=np.float32)


def structure_fit_mask(pred_a: np.ndarray, pred_b: np.ndarray,
                       char_dilate: int = 1) -> np.ndarray:
    """String-independent fit mask in template coords: plate region MINUS
    character cells, derived purely from two different-string predictions.

    Character pixels = where the two predictions differ (union of both glyph
    sets, dilated). Plate region = where the prediction departs from the
    border-estimated backdrop. Geometry fitting restricted to this mask uses
    the band/outline/background only — the outside-colors structure — so no
    character information can steer the alignment.
    """
    ga, gb = _gray32(pred_a), _gray32(pred_b)
    chars = (np.abs(ga - gb) > 0.02).astype(np.uint8)
    k = np.ones((2 * char_dilate + 1,) * 2, np.uint8)
    chars = cv2.dilate(chars, k)
    border = np.concatenate([ga[0], ga[-1], ga[:, 0], ga[:, -1]])
    plate = (np.abs(ga - np.median(border)) > 0.04).astype(np.uint8)
    plate = cv2.morphologyEx(plate, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    plate = cv2.dilate(plate, np.ones((5, 5), np.uint8))
    mask = plate & (1 - chars)
    if mask.sum() < 50:  # degenerate (tiny render) -> fall back to plate region
        mask = plate
    return (mask * 255).astype(np.uint8)


def _scale_warp(warp: np.ndarray, s: float) -> np.ndarray:
    scale_m = np.diag([s, s, 1.0])
    return (scale_m @ warp @ np.linalg.inv(scale_m)).astype(np.float32)


def _ecc_run(ref_g, tmpl_g, warp0, fit_mask, levels, iters):
    warp = warp0.copy()
    rho = -1.0
    for level_scale in levels:
        rg = cv2.resize(ref_g, None, fx=level_scale, fy=level_scale,
                        interpolation=cv2.INTER_AREA) if level_scale != 1.0 else ref_g
        wl = _scale_warp(warp, level_scale)
        mask_ref = None
        if fit_mask is not None:
            mask_ref = cv2.warpPerspective(fit_mask, wl, (rg.shape[1], rg.shape[0]))
        criteria = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, iters, 1e-7)
        try:
            rho, wl = cv2.findTransformECC(tmpl_g, rg, wl, cv2.MOTION_HOMOGRAPHY,
                                           criteria, mask_ref, 5)
        except cv2.error:
            return None
        warp = _scale_warp(wl, 1.0 / level_scale)
    return float(rho), warp


def refine_homography(ref_linear: np.ndarray, template: np.ndarray,
                      reg: Registration, fit_mask: np.ndarray | None = None,
                      iters: int = 300) -> Registration | None:
    """G1: sub-pixel homography refinement (ECC) from the G0 similarity lock.

    Attempt ladder: (1) full-res with the character-masked fit (the clean,
    string-independent version), (2) full-res unmasked (tiny renders can leave
    the mask too thin for ECC to converge — the neutral-string glyphs then
    contribute a small alignment bias, accepted and logged), (3) half-res
    pyramid rescue for large initial misalignment. Returns None if all
    diverge — callers fall back to the G0 similarity.
    """
    ref_g, tmpl_g = _gray32(ref_linear), _gray32(template)
    warp0 = np.array([[reg.scale, 0, reg.x], [0, reg.scale, reg.y], [0, 0, 1]],
                     np.float32)
    attempts = (
        ((1.0,), fit_mask),
        ((1.0,), None),
        ((0.5, 1.0), None),
    )
    for levels, mask in attempts:
        out = _ecc_run(ref_g, tmpl_g, warp0, mask, levels, iters)
        if out is not None:
            rho, warp = out
            return Registration(scale=reg.scale, x=reg.x, y=reg.y, score=rho,
                                warp=warp.astype(np.float64), method="ecc")
    return None


def extract_observation(ref_linear: np.ndarray, pred_shape: tuple[int, ...],
                        reg: Registration) -> np.ndarray:
    """Resample the registered region onto the prediction's native grid.

    G1 (reg.warp set): anti-alias blur matched to the zoom factor, then a
    single perspective warp — sub-pixel, pose-absorbing.
    G0 fallback: axis-aligned crop + area resize; handles out-of-bounds crops
    (template overhanging the snip edge) by replicate-padding, mirroring
    register()'s overhang allowance.
    """
    h, w = pred_shape[:2]
    if reg.warp is not None:
        # No anti-alias pre-blur: screenshot refs are nearest-zoomed constant
        # blocks, so point-sampling block centers recovers native values
        # EXACTLY — a pre-blur would inject blur the prediction doesn't have
        # (measured: it alone flipped B->D at char 10). For photographic refs
        # the un-averaged sampling noise lands in the robust b_hat instead.
        return cv2.warpPerspective(
            ref_linear, reg.warp.astype(np.float64), (w, h),
            flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP,
            borderMode=cv2.BORDER_REPLICATE,
        ).astype(np.float64)
    th, tw = round(h * reg.scale), round(w * reg.scale)
    top, left = max(0, -reg.y), max(0, -reg.x)
    bottom = max(0, reg.y + th - ref_linear.shape[0])
    right = max(0, reg.x + tw - ref_linear.shape[1])
    if any((top, left, bottom, right)):
        ref_linear = cv2.copyMakeBorder(ref_linear, top, bottom, left, right,
                                        cv2.BORDER_REPLICATE)
    y0, x0 = reg.y + top, reg.x + left
    crop = ref_linear[y0 : y0 + th, x0 : x0 + tw]
    return cv2.resize(crop, (w, h), interpolation=cv2.INTER_AREA).astype(np.float64)


def robust_read_var(residual: np.ndarray) -> float:
    """Robust per-pixel variance from a residual map (median-of-squares)."""
    return float(np.median(residual**2) / _CHI2_MEDIAN)


@dataclass
class ReferenceDecode:
    registration: Registration
    observation: np.ndarray  # y on the scoring grid (obs-native when refined)
    b_hat: float  # estimated noise floor used as read_var
    tables: list[SlotTable] = field(default_factory=list)
    decoded: str = ""
    truth: str | None = None
    delta_nats: float | None = None  # design-02 §8.6: L(truth) - L(best wrong)
    scoring: ScoringModel | None = None  # the model actually used (grid-composed when refined)


def _complement_string(spec: PlateSpec, neutral: str) -> str:
    out = [
        "8" if s.kind == "D" else ("W" if c != "W" else "M")
        for c, s in zip(neutral, spec.slots)
    ]
    return spec.validate_string("".join(out))


def decode_reference(
    scoring: ScoringModel,
    spec: PlateSpec,
    ref_linear: np.ndarray,
    neutral_string: str,
    truth: str | None = None,
    passes: int = 2,
    refine: bool = True,
) -> ReferenceDecode:
    """Register, extract, estimate noise, and slot-decode a reference image.

    ``neutral_string`` seeds registration and the first conditional pass; it
    must be a valid plate string but carries no information about the answer.
    ``passes`` > 1 re-runs the slot tables conditioned on the previous decode
    (iterated conditional; matters once blur/codec couple neighboring slots).
    ``refine`` runs the G1 sub-pixel homography (character cells masked out of
    the fit), then decodes under two candidate channels — (a) crop+area
    extraction with the caller's model (correct inverse of a pure screenshot
    zoom) and (b) the fitted pose residual rendered into the candidates via
    project grid_warp (the observation is never perspective-resampled;
    measured 2026-07-24: even the exactly-true warp applied to the observation
    flips characters — sampling is not a homography of the sampled image) —
    and keeps whichever final prediction best reproduces the observation
    (posterior predictive correlation; truth never consulted). On ECC
    divergence the G0 similarity + crop extraction is used alone.
    """
    neutral = spec.validate_string(neutral_string)
    pred_neutral = scoring.predict(neutral)
    reg0 = register(ref_linear, pred_neutral)
    reg = reg0
    refined = None
    if refine:
        fit_mask = structure_fit_mask(
            pred_neutral, scoring.predict(_complement_string(spec, neutral)))
        refined = refine_homography(ref_linear, pred_neutral, reg0, fit_mask)
        if refined is not None:
            reg = refined

    # ONE observation: the G0 crop+area extraction — the correct inverse of a
    # pure screenshot zoom, at the NCC-peak scale (the ECC scale wanders in a
    # flat basin on blocky content and must not drive the crop). TWO candidate
    # channel models explain it: (a) the caller's model as-is; (b) the model
    # with the ECC residual homography (relative to the G0 crop map) rendered
    # into the candidates via project grid_warp — genuine pose differences
    # live there, and the observation is never perspective-resampled
    # (measured: even the exactly-true warp applied to the observation flips
    # characters). No geometric statistic separates ECC basin-wander from real
    # pose (corner deviation, interior displacement, median-b, structure/flat
    # RMS all fail), so the selector is generative: decode under both models
    # and keep the one whose final prediction best reproduces the observation
    # (posterior predictive correlation; the truth is never consulted).
    h, w = pred_neutral.shape[:2]
    y = extract_observation(ref_linear, (h, w), reg0)
    candidates: list[ScoringModel] = [scoring]
    if refined is not None:
        W = refined.warp / refined.warp[2, 2]
        cw0, ch0 = max(8, round(w * reg0.scale)), max(8, round(h * reg0.scale))
        E0 = np.array([[cw0 / w, 0, reg0.x], [0, ch0 / h, reg0.y],
                       [0, 0, 1.0]])
        grid_warp = np.linalg.inv(E0) @ W  # residual vs the G0 crop map
        ov = {k: dict(v) for k, v in scoring.base_overrides.items()}
        ov.setdefault("project", {}).update(
            {"grid_warp": grid_warp, "grid_shape": (h, w)})
        candidates.append(ScoringModel(
            scoring.pipeline, ov, scoring.disabled, scoring.a, scoring.b,
            var_scale=scoring.var_scale, string_stage=scoring.string_stage,
            string_param=scoring.string_param))

    best = None
    for model_c in candidates:
        model_c.a = 0.0
        model_c.b = max(robust_read_var(y - model_c.predict(neutral)), 1e-6)
        model_c.var_scale = 1.0  # b_hat is already in the scoring domain
        decoded_c, tables_c = decode_icm(model_c, y, spec, neutral,
                                         passes=passes)
        pred_dec = model_c.predict(decoded_c)
        corr = float(np.corrcoef(_gray32(y).ravel(),
                                 _gray32(pred_dec).ravel())[0, 1])
        if best is None or corr > best[0]:
            best = (corr, model_c, decoded_c, tables_c)

    _, active, decoded, tables = best

    out = ReferenceDecode(registration=reg, observation=y, b_hat=active.b,
                          tables=tables, decoded=decoded, truth=truth,
                          scoring=active)
    if truth is not None:
        out.truth = spec.validate_string(truth)
        out.delta_nats = _delta_vs_truth(tables, out.truth)
    return out


def _delta_vs_truth(tables: list[SlotTable], truth: str) -> float:
    """L(truth) - L(best wrong string), from per-slot tables (design-02 §8.6).

    Under (conditional) slot additivity the best wrong string differs from the
    best string in exactly one slot when the decode is correct; if any slot's
    argmax already disagrees with truth, delta is negative.
    """
    total_best = sum(max(t.scores.values()) for t in tables)
    total_truth = sum(t.scores[truth[j]] for j, t in enumerate(tables))
    if total_truth < total_best:  # decode disagrees with truth somewhere
        return total_truth - total_best
    # decode == truth: margin to the nearest single-slot flip
    return min(
        t.scores[truth[j]] - max(v for c, v in t.scores.items() if c != truth[j])
        for j, t in enumerate(tables)
    )
