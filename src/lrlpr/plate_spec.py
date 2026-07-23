"""Plate geometry specifications (design-01 [1]).

All dimensions in millimeters on the plate plane. Origin: top-left corner of the
plate; u to the right, v downward (image convention).

Mercosur numbers are sourced from CONTRAN Resolução 780/2019 Anexo I (geometry
retained by the in-force Res. 969/2022) — see docs/plate-spec-sources.md for
the full citation trail. Items still not officially specified are marked
PROVISIONAL with the assumption used.

Key sourced facts (cars):
  - Plate 400×130 ±2 mm; aluminum 1 ±0.2 mm; NO printed/raised border (the
    white retroreflective film runs to the plate edge — unlike old BR plates).
  - Characters: FE-Engschrift, cap height 65 mm, "alto relevo" (relief height
    itself is NOT specified anywhere public — industry ~1-1.5 mm, PROVISIONAL).
  - Layout: 7 equidistant cells of 46 mm pitch (322 mm field), character block
    ending ~38 mm from the right plate edge; glyphs are CENTERED PER CELL, not
    typeset with the font's natural tracking (Brazilian deviation from German
    usage — do not use font advances).
  - Blue band: 30 mm tall, 390 mm long, Pantone 286 (#0032A0 sRGB equivalent).
  - Corner radius: undocumented; drawings suggest ~10 mm (PROVISIONAL).
Not yet rendered (TODO, matters for HR validation): band contents (MERCOSUL
emblem 32×22, white "BRASIL" text, flag 28×20), QR code, "BR" mark 20 mm,
micro-lettering, film watermarks, fixing slots.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


def srgb_to_linear(rgb8: tuple[int, int, int]) -> tuple[float, float, float]:
    """sRGB 0-255 -> linear reflectance (IEC 61966-2-1)."""
    out = []
    for c in rgb8:
        x = c / 255.0
        out.append(x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4)
    return tuple(out)


@dataclass(frozen=True)
class CharSlot:
    """One character position: center-x (mm), and whether it's a letter or digit."""

    cx: float
    kind: str  # "L" letter | "D" digit


@dataclass(frozen=True)
class PlateSpec:
    name: str
    width: float  # mm
    height: float  # mm
    char_height: float  # mm (glyph cap height on the plate)
    char_baseline_v: float  # mm from plate top to glyph baseline
    slots: tuple[CharSlot, ...]
    pattern: str  # regex the plate string must match
    background_rgb: tuple[float, float, float]  # linear RGB albedo
    char_rgb: tuple[float, float, float]
    band_height: float = 0.0  # Mercosur blue band (0 = none)
    band_length: float = 0.0  # band length (mm), horizontally centered
    band_top: float = 0.0  # mm from plate top edge to band top
    band_rgb: tuple[float, float, float] = (0.0, 0.2, 0.6)
    border_width: float = 0.0  # raised painted border line width (0 = none)
    border_margin: float = 0.0  # distance from plate edge to border line (mm)
    relief_height: float = 1.2  # emboss height (mm) — PROVISIONAL (unspecified)
    die_radius: float = 1.0  # stamping shoulder radius (mm) — PROVISIONAL

    def validate_string(self, s: str) -> str:
        s = s.upper()
        if not re.fullmatch(self.pattern, s):
            raise ValueError(f"{s!r} does not match {self.name} pattern {self.pattern}")
        return s


def _pitched_slots(kinds: str, first_center: float, pitch: float) -> tuple[CharSlot, ...]:
    return tuple(
        CharSlot(cx=first_center + pitch * i, kind=k) for i, k in enumerate(kinds)
    )


# ---------------------------------------------------------------------------
# Brazilian Mercosur car plate (CONTRAN Res. 780/2019 Anexo I; Res. 969/2022).
# Character field: 7 cells x 46 mm = 322 mm, ending 38 mm from the right edge
# -> field spans [40, 362] mm; first cell center at 40 + 23 = 63 mm.
# Vertical: band region ends ~34 mm from top; chars (65 mm) approximately
# centered in the remaining 96 mm field -> top at 34 + 15.5 = 49.5, baseline
# (caps/digits have no descenders) at 114.5 mm. PROVISIONAL pending px-level
# validation against real HR crops.
# ---------------------------------------------------------------------------
MERCOSUR_BR_CAR = PlateSpec(
    name="mercosur_br_car",
    width=400.0,
    height=130.0,
    char_height=65.0,  # Res.780 item 2.4.1.2
    char_baseline_v=114.5,  # derived, PROVISIONAL (see above)
    slots=_pitched_slots("LLLDLDD", first_center=63.0, pitch=46.0),  # Fig. II
    pattern=r"[A-Z]{3}[0-9][A-Z][0-9]{2}",
    background_rgb=(0.92, 0.92, 0.92),  # white retroreflective, PROVISIONAL albedo
    char_rgb=(0.02, 0.02, 0.02),  # black hot-stamp film, PROVISIONAL albedo
    band_height=30.0,  # Tabela II
    band_length=390.0,  # Tabela II
    band_top=4.0,  # Fig. II: 34 mm band region = 4 mm offset + 30 mm band
    band_rgb=srgb_to_linear((0x00, 0x32, 0xA0)),  # Pantone 286
    border_width=0.0,  # NO border on Mercosur plates (film to edge)
    relief_height=1.2,  # PROVISIONAL — not in any public spec
    die_radius=1.0,  # PROVISIONAL
)

# Commercial (Aluguel) variant: red characters, Pantone 186C.
MERCOSUR_BR_CAR_COMMERCIAL = PlateSpec(
    name="mercosur_br_car_commercial",
    width=400.0, height=130.0, char_height=65.0, char_baseline_v=114.5,
    slots=MERCOSUR_BR_CAR.slots, pattern=MERCOSUR_BR_CAR.pattern,
    background_rgb=MERCOSUR_BR_CAR.background_rgb,
    char_rgb=srgb_to_linear((0xC8, 0x10, 0x2E)),  # Pantone 186C
    band_height=30.0, band_length=390.0, band_top=4.0,
    band_rgb=MERCOSUR_BR_CAR.band_rgb,
)

# ---------------------------------------------------------------------------
# Old Brazilian gray plate, pre-2018 (CONTRAN Res. 231/2007): 400x130 mm,
# char height 63 mm, stroke 10 mm, font "Mandatory"; raised painted border.
# Slot positions PROVISIONAL (Res. 231 layout figures not yet extracted).
# ---------------------------------------------------------------------------
BRAZIL_OLD_CAR = PlateSpec(
    name="brazil_old_car",
    width=400.0,
    height=130.0,
    char_height=63.0,  # Res. 231/2007
    char_baseline_v=100.0,  # PROVISIONAL
    slots=_pitched_slots("LLLDDDD", first_center=55.0, pitch=48.0),  # PROVISIONAL
    pattern=r"[A-Z]{3}[0-9]{4}",
    background_rgb=(0.55, 0.55, 0.55),  # gray, PROVISIONAL albedo
    char_rgb=(0.02, 0.02, 0.02),
    border_width=4.0,  # raised painted border exists on old plates; PROVISIONAL width
    border_margin=6.0,  # PROVISIONAL
    relief_height=1.2,
)

SPECS = {
    s.name: s
    for s in (MERCOSUR_BR_CAR, MERCOSUR_BR_CAR_COMMERCIAL, BRAZIL_OLD_CAR)
}
