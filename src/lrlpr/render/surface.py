"""Design-01 stage [1]: plate surface — albedo + relief heightmap.

Works entirely on the plate plane in mm; rasterized at ``px_per_mm`` resolution
(the supersampled working grid — sensor integration happens much later, [6]).

Outputs into state:
  albedo    (H, W, 3) float64, linear RGB reflectance in [0, 1]
  height_mm (H, W)    float64, emboss relief height above plate face
  char_mask (H, W)    float64, antialiased glyph ink coverage in [0, 1]
  mm_per_px float

PROVISIONAL choices (flagged per protocol):
  - Glyphs centered by ink bounding box at slot centers (real spec may position
    by cell/advance; replace when official layout numbers arrive).
  - Emboss shoulder = raised-cosine profile over die_radius (real stamped
    profile unknown; smooth ramp with zero slope at both ends).
  - Paint covers relief above ``paint_coverage`` fraction of full height
    (models paint applied to the raised face, bare shoulder flanks).
"""

from __future__ import annotations

from collections.abc import Mapping
from functools import lru_cache
from typing import Any

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy.ndimage import distance_transform_edt

from lrlpr.pipeline import ParamSpec, Stage
from lrlpr.plate_spec import SPECS, PlateSpec


@lru_cache(maxsize=8)
def _calibrated_font(font_path: str, cap_height_px: int) -> ImageFont.FreeTypeFont:
    """Font sized so the capital-letter height equals ``cap_height_px`` pixels.

    Font nominal size != cap height, so calibrate by measuring 'H'.
    """
    probe_size = max(cap_height_px, 8)
    for _ in range(4):
        font = ImageFont.truetype(font_path, probe_size)
        left, top, right, bottom = font.getbbox("H")
        measured = bottom - top
        if measured == cap_height_px:
            break
        probe_size = max(8, round(probe_size * cap_height_px / max(measured, 1)))
    return ImageFont.truetype(font_path, probe_size)


def _raster_glyph(font: ImageFont.FreeTypeFont, ch: str) -> np.ndarray:
    """Antialiased ink mask of a single glyph, tightly cropped, float in [0,1]."""
    left, top, right, bottom = font.getbbox(ch)
    w, h = right - left, bottom - top
    img = Image.new("L", (w + 4, h + 4), 0)
    ImageDraw.Draw(img).text((2 - left, 2 - top), ch, fill=255, font=font)
    arr = np.asarray(img, dtype=np.float64) / 255.0
    ys, xs = np.nonzero(arr > 0)
    if len(ys) == 0:
        raise ValueError(f"glyph {ch!r} rendered empty")
    return arr[ys.min() : ys.max() + 1, xs.min() : xs.max() + 1]


def _shoulder_profile(distance_px: np.ndarray, die_radius_px: float) -> np.ndarray:
    """Relief fraction from inside-distance: raised-cosine ramp (PROVISIONAL)."""
    t = np.clip(distance_px / max(die_radius_px, 1e-9), 0.0, 1.0)
    return 0.5 * (1.0 - np.cos(np.pi * t))


def _build_surface(state: Mapping[str, Any], params: Mapping[str, Any]) -> dict[str, Any]:
    spec: PlateSpec = SPECS[params["spec"]]
    plate = spec.validate_string(params["plate_string"])
    ppm = params["px_per_mm"]
    mm_per_px = 1.0 / ppm

    H, W = round(spec.height * ppm), round(spec.width * ppm)
    char_mask = np.zeros((H, W), dtype=np.float64)

    font = _calibrated_font(params["font_path"], round(spec.char_height * ppm))
    for ch, slot in zip(plate, spec.slots, strict=True):
        glyph = _raster_glyph(font, ch)
        gh, gw = glyph.shape
        # PROVISIONAL: ink-bbox centered at slot center, bottom at baseline.
        r0 = round(spec.char_baseline_v * ppm) - gh
        c0 = round(slot.cx * ppm - gw / 2)
        r1, c1 = r0 + gh, c0 + gw
        if r0 < 0 or c0 < 0 or r1 > H or c1 > W:
            raise ValueError(f"glyph {ch!r} exceeds plate bounds — check spec/layout")
        np.maximum(char_mask[r0:r1, c0:c1], glyph, out=char_mask[r0:r1, c0:c1])

    # Raised regions: glyphs, plus the border ridge if the spec has one.
    raised = char_mask.copy()
    border_mask = np.zeros_like(char_mask)
    if spec.border_width > 0 and params["border"]:
        m0 = round(spec.border_margin * ppm)
        m1 = m0 + max(round(spec.border_width * ppm), 1)
        border_mask[m0:-m0 or None, m0:-m0 or None] = 1.0
        border_mask[m1:-m1 or None, m1:-m1 or None] = 0.0
        np.maximum(raised, border_mask, out=raised)

    # Relief: distance transform inside the raised region -> shoulder profile.
    inside = raised > 0.5
    dist_in = distance_transform_edt(inside)
    height_mm = params["relief_height_mm"] * _shoulder_profile(
        dist_in, params["die_radius_mm"] * ppm
    )
    height_mm[~inside] = 0.0

    # Albedo: background, band, then paint on sufficiently-raised glyph/border area.
    albedo = np.empty((H, W, 3), dtype=np.float64)
    albedo[:] = spec.background_rgb
    if spec.band_height > 0 and params["band"]:
        albedo[: round(spec.band_height * ppm), :] = spec.band_rgb
    painted = height_mm >= params["paint_coverage"] * params["relief_height_mm"]
    paint_w = np.where(painted, np.maximum(char_mask, border_mask), 0.0)[..., None]
    albedo = albedo * (1 - paint_w) + np.asarray(spec.char_rgb) * paint_w

    return {
        "albedo": albedo,
        "height_mm": height_mm,
        "char_mask": char_mask,
        "mm_per_px": mm_per_px,
        "plate_string": plate,
        "spec_name": spec.name,
    }


SURFACE_STAGE = Stage(
    name="surface",
    fn=_build_surface,
    params=(
        ParamSpec("plate_string", "ABC1D23", doc="7-char plate text (layout-validated)"),
        ParamSpec("spec", "mercosur_br_car", choices=tuple(SPECS), doc="plate layout spec"),
        ParamSpec("font_path", "data/fonts/FE-Engschrift.ttf", doc="TTF for glyphs"),
        ParamSpec("px_per_mm", 2.0, lo=0.5, hi=8.0, step=0.5, units="px/mm",
                  doc="supersampled working resolution on the plate plane"),
        ParamSpec("relief_height_mm", 1.2, lo=0.0, hi=3.0, step=0.05, units="mm",
                  doc="emboss height (0 = flat plate ablation)"),
        ParamSpec("die_radius_mm", 1.0, lo=0.1, hi=5.0, step=0.1, units="mm",
                  doc="stamping shoulder radius"),
        ParamSpec("paint_coverage", 0.8, lo=0.0, hi=1.0, step=0.05,
                  doc="fraction of relief height above which paint covers"),
        ParamSpec("band", True, doc="render Mercosur band"),
        ParamSpec("border", True, doc="render raised border ridge"),
    ),
    provides=("albedo", "height_mm", "char_mask", "mm_per_px"),
    doc="design-01 [1]: plate surface (albedo + stamped relief)",
)
