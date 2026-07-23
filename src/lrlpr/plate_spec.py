"""Plate geometry specifications (design-01 [1]).

All dimensions in millimeters on the plate plane. Origin: top-left corner of the
plate; u to the right, v downward (image convention).

PROVISIONAL: the numeric values below are placeholders from general references,
pending the official CONTRAN/Mercosur specification research (agent in flight,
2026-07-22). Every number here must be replaced by a sourced value or measured
from real HR imagery before the renderer is trusted (design-01 validation gate).
"""

from __future__ import annotations

import re
from dataclasses import dataclass


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
    band_rgb: tuple[float, float, float] = (0.0, 0.2, 0.6)
    border_width: float = 0.0  # printed/raised border line width (mm)
    border_margin: float = 0.0  # distance from plate edge to border line (mm)
    relief_height: float = 1.2  # emboss height (mm) — PROVISIONAL typical value
    die_radius: float = 1.0  # stamping shoulder radius (mm) — PROVISIONAL

    def validate_string(self, s: str) -> str:
        s = s.upper()
        if not re.fullmatch(self.pattern, s):
            raise ValueError(f"{s!r} does not match {self.name} pattern {self.pattern}")
        return s


def _evenly_spaced_slots(kinds: str, width: float, margin: float) -> tuple[CharSlot, ...]:
    """PROVISIONAL layout: n slots with centers evenly spaced between margins.

    Real plates have specified group gaps; replace with sourced positions.
    """
    n = len(kinds)
    usable = width - 2 * margin
    pitch = usable / n
    return tuple(
        CharSlot(cx=margin + pitch * (i + 0.5), kind=k) for i, k in enumerate(kinds)
    )


# Brazilian Mercosur car plate (post-2018). Pattern LLL D L DD ("AAA9A99").
MERCOSUR_BR_CAR = PlateSpec(
    name="mercosur_br_car",
    width=400.0,
    height=130.0,
    char_height=63.0,  # PROVISIONAL
    char_baseline_v=110.0,  # PROVISIONAL: band on top, glyphs in lower region
    slots=_evenly_spaced_slots("LLLDLDD", 400.0, margin=28.0),  # PROVISIONAL
    pattern=r"[A-Z]{3}[0-9][A-Z][0-9]{2}",
    background_rgb=(0.90, 0.90, 0.90),  # white paint, linear albedo PROVISIONAL
    char_rgb=(0.04, 0.04, 0.04),  # black paint PROVISIONAL
    band_height=30.0,  # PROVISIONAL
    band_rgb=(0.02, 0.09, 0.30),  # Mercosur blue PROVISIONAL
    border_width=4.0,  # PROVISIONAL
    border_margin=6.0,  # PROVISIONAL
)

# Old Brazilian gray plate (pre-2018). Pattern LLL-DDDD; hyphen not a slot.
BRAZIL_OLD_CAR = PlateSpec(
    name="brazil_old_car",
    width=400.0,
    height=130.0,
    char_height=63.0,  # PROVISIONAL
    char_baseline_v=100.0,  # PROVISIONAL
    slots=_evenly_spaced_slots("LLLDDDD", 400.0, margin=30.0),  # PROVISIONAL
    pattern=r"[A-Z]{3}[0-9]{4}",
    background_rgb=(0.55, 0.55, 0.55),  # gray PROVISIONAL
    char_rgb=(0.04, 0.04, 0.04),
    border_width=0.0,
    relief_height=1.2,
)

SPECS = {s.name: s for s in (MERCOSUR_BR_CAR, BRAZIL_OLD_CAR)}
