"""Physics checks for renderer stages [1]-[3] against the design-01 math.

Uses a Windows system font as a stand-in until the FE-Schrift TTF lands —
these tests check physics (relief bounds, shading identities, shadow
direction, projection scale), not glyph shapes.
"""

import os

import numpy as np
import pytest

from lrlpr.plate_spec import MERCOSUR_BR_CAR
from lrlpr.render import build_render_pipeline
from lrlpr.render.shading import cast_shadow_mask, light_vector, surface_normals

FONT = next(
    (p for p in (r"C:\Windows\Fonts\arialbd.ttf", r"C:\Windows\Fonts\arial.ttf")
     if os.path.exists(p)),
    None,
)
pytestmark = pytest.mark.skipif(FONT is None, reason="no system font available")

SURF = {"font_path": FONT, "px_per_mm": 2.0}


@pytest.fixture(scope="module")
def surface_state():
    return build_render_pipeline().run({"surface": SURF}, upto="surface")


def test_surface_shapes_and_ranges(surface_state):
    s = surface_state
    H, W = s["height_mm"].shape
    assert (H, W) == (260, 800)  # 130x400 mm at 2 px/mm
    assert s["albedo"].shape == (H, W, 3)
    assert 0.0 <= s["albedo"].min() and s["albedo"].max() <= 1.0
    # Relief bounded by the configured emboss height; wide strokes reach it.
    assert s["height_mm"].min() == 0.0
    assert np.isclose(s["height_mm"].max(), 1.2, atol=1e-9)
    assert s["char_mask"].sum() > 0


def test_invalid_plate_string_rejected():
    p = build_render_pipeline()
    with pytest.raises(ValueError):
        p.run({"surface": {**SURF, "plate_string": "1234567"}}, upto="surface")


def test_flat_plate_ablation_gives_zero_relief():
    p = build_render_pipeline()
    s = p.run({"surface": {**SURF, "relief_height_mm": 0.0}}, upto="surface")
    assert s["height_mm"].max() == 0.0


def test_normals_flat_regions_point_at_viewer(surface_state):
    n = surface_normals(surface_state["height_mm"], surface_state["mm_per_px"])
    assert np.allclose(n[0, 0], [0, 0, 1])  # corner: flat background


def test_frontal_light_shading_identity(surface_state):
    """elevation=90: n.l = n_z <= 1, exactly 1 on flat; no cast shadows possible."""
    p = build_render_pipeline()
    out = p.run(
        {"surface": SURF,
         "shading": {"elevation_deg": 90.0, "ambient": 0.0, "direct": 1.0}},
        upto="shading",
    )
    flat = surface_state["height_mm"] == 0.0
    # Erode 2px so heightmap gradient support doesn't touch the flat sample.
    from scipy.ndimage import binary_erosion
    flat = binary_erosion(flat, iterations=2)
    assert np.allclose(out["shading"][flat], 1.0, atol=1e-9)
    assert out["shading"].max() <= 1.0 + 1e-9


def test_light_vector_convention():
    assert np.allclose(light_vector(0, 0), [1, 0, 0])       # from the right
    assert np.allclose(light_vector(90, 0), [0, -1, 0])     # from the top (y down)
    assert np.allclose(light_vector(0, 90), [0, 0, 1])      # frontal


def test_cast_shadow_falls_away_from_light():
    """A single raised ridge under low light from the right: shadow on its left."""
    h = np.zeros((11, 41))
    h[:, 20] = 1.0  # 1mm wall
    lit = cast_shadow_mask(h, mm_per_px=0.5, azimuth_deg=0.0, elevation_deg=30.0)
    # shadow length = 1mm/tan(30deg) = 1.73mm = ~3.5px to the LEFT of the wall
    assert lit[5, 18] == 0.0 and lit[5, 17] == 0.0
    assert lit[5, 22] == 1.0 and lit[5, 25] == 1.0  # right side fully lit
    lit_rev = cast_shadow_mask(h, mm_per_px=0.5, azimuth_deg=180.0, elevation_deg=30.0)
    assert lit_rev[5, 22] == 0.0 and lit_rev[5, 18] == 1.0  # mirrored


GLYPHS_ONLY = {**SURF, "band": False, "border": False}  # so dark px = glyphs


def test_projection_char_height_matches_request():
    """Frontal projection: rendered char height ~= requested px * supersample."""
    p = build_render_pipeline()
    out = p.run(
        {"surface": GLYPHS_ONLY, "project": {"char_height_px": 10.0, "supersample": 4}}
    )
    img = out["image"]
    dark = img[..., 0] < 0.25  # glyph paint only (band/border disabled)
    rows = np.nonzero(dark.any(axis=1))[0]
    measured = rows.max() - rows.min() + 1
    expected = 10.0 * 4
    assert abs(measured - expected) / expected < 0.12  # PROVISIONAL tolerance


def test_projection_distance_is_physical():
    """25mm lens, 3um pitch, 12px chars -> camera tens of meters away."""
    p = build_render_pipeline()
    out = p.run({"surface": SURF})
    assert 20.0 < out["camera_distance_m"] < 100.0


def test_projection_yaw_compresses_width():
    """At realistic distance, yaw=60deg foreshortens width by ~cos(60)=0.5."""
    p = build_render_pipeline()
    frontal = p.run({"surface": SURF, "project": {"supersample": 2}})
    yawed = p.run({"surface": SURF, "project": {"supersample": 2, "yaw_deg": 60.0}})
    def plate_width(img):
        non_backdrop = np.abs(img[..., 2] - img[..., 0]) > 1e-6  # band is blue
        cols = np.nonzero(non_backdrop.any(axis=0))[0]
        return cols.max() - cols.min()
    ratio = plate_width(yawed["image"]) / plate_width(frontal["image"])
    assert abs(ratio - 0.5) < 0.06
