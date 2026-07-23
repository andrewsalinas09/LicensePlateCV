"""Physics checks for camera stages [4]-[11] against the design-01 math."""

import numpy as np
import pytest

from lrlpr.camera.delivery import jpeg_roundtrip
from lrlpr.camera.demosaic import demosaic
from lrlpr.camera.motion import apply_motion_rs, velocity_px_per_s
from lrlpr.camera.optics import apply_psf, disk_kernel
from lrlpr.camera.sensor import BAYER_PATTERNS, mosaic, pixel_aperture

rng = np.random.default_rng(7)


# ---------------------------------------------------------------- [4] motion/RS

def test_velocity_units():
    """60 km/h at 40 m with focal 8333 px -> 16.67 m/s * 8333/40 = 3472 px/s."""
    v = velocity_px_per_s(60.0, 0.0, focal_px=8333.0, distance_m=40.0)
    assert np.allclose(v, [3472.1, 0.0], atol=0.1)


def test_zero_speed_is_identity():
    img = rng.random((32, 32, 3))
    out = apply_motion_rs(img, np.zeros(2), 0.008, 30e-6, 8)
    assert np.allclose(out, img, atol=1e-6)


def test_motion_blur_length():
    """Point source smeared over ~v*T_exp pixels along the motion direction."""
    img = np.zeros((21, 101, 3))
    img[10, 30] = 1.0
    v = np.array([1000.0, 0.0])  # px/s
    out = apply_motion_rs(img, v, exposure_s=0.02, line_time_s_per_row=0.0, n_samples=40)
    hit = np.nonzero(out[10, :, 0] > 1e-4)[0]
    # Content position x(t) = x0 + v*t (sampled at p - v*t): the point smears
    # v*T = 20 px to the RIGHT of x=30.
    assert 15 <= hit.max() - hit.min() <= 22
    assert hit.min() >= 29 and hit.max() <= 52
    assert np.isclose(out.sum(), img.sum(), rtol=0.05)  # energy preserved


def test_rolling_shutter_shears_rows():
    """Vertical bar + horizontal motion + line time: row displacement grows with row."""
    img = np.zeros((100, 60, 3))
    img[:, 30] = 1.0
    v = np.array([500.0, 0.0])
    out = apply_motion_rs(img, v, exposure_s=1e-6, line_time_s_per_row=1e-4, n_samples=1)
    def bar_pos(row):
        return np.argmax(out[row, :, 0])
    # Row r is exposed at t = r*1e-4 s; content has moved +v*t by then, so the
    # bar appears at 30 + 0.05*r — shear grows RIGHTWARD down the frame.
    assert bar_pos(0) == 30
    assert bar_pos(80) == 34  # 30 + 0.05*80
    assert bar_pos(10) < bar_pos(40) < bar_pos(80)


# ---------------------------------------------------------------- [5] optics

def test_disk_kernel_radius_and_norm():
    k = disk_kernel(3.0)
    assert np.isclose(k.sum(), 1.0)
    yy, xx = np.mgrid[: k.shape[0], : k.shape[1]]
    c = (k.shape[0] - 1) / 2
    support = np.hypot(yy - c, xx - c)[k > 1e-12]
    assert support.max() <= 3.6  # radius + AA edge

def test_psf_preserves_energy():
    img = rng.random((40, 40, 3))
    out = apply_psf(img, defocus_radius=2.0, sigma=1.0)
    assert np.isclose(out.mean(), img.mean(), rtol=0.02)  # replicate border ~preserves


# ---------------------------------------------------------------- [6] sensor

def test_pixel_aperture_is_exact_box_mean():
    img = rng.random((16, 16, 3))
    out = pixel_aperture(img, 4)
    manual = img.reshape(4, 4, 4, 4, 3).mean(axis=(1, 3))
    assert np.allclose(out, manual, atol=1e-12)


@pytest.mark.parametrize("pattern", list(BAYER_PATTERNS))
def test_mosaic_samples_correct_channels(pattern):
    rgb = np.zeros((4, 4, 3))
    rgb[..., 0], rgb[..., 1], rgb[..., 2] = 0.1, 0.5, 0.9
    raw = mosaic(rgb, pattern)
    pat = BAYER_PATTERNS[pattern]
    vals = {0: 0.1, 1: 0.5, 2: 0.9}
    for dr in (0, 1):
        for dc in (0, 1):
            assert np.allclose(raw[dr::2, dc::2], vals[pat[dr][dc]])


# ---------------------------------------------------------------- [8] demosaic

@pytest.mark.parametrize("algo", ["bilinear", "vng", "ea"])
@pytest.mark.parametrize("pattern", list(BAYER_PATTERNS))
def test_demosaic_restores_constant_color(pattern, algo):
    """Constant-color scene must survive mosaic->demosaic (validates the
    pattern-name mapping to cv2 codes)."""
    rgb = np.empty((16, 16, 3))
    rgb[..., 0], rgb[..., 1], rgb[..., 2] = 0.6, 0.3, 0.8
    rec = demosaic(mosaic(rgb, pattern), pattern, algo)
    interior = rec[4:-4, 4:-4]
    assert np.allclose(interior[..., 0], 0.6, atol=0.02)
    assert np.allclose(interior[..., 1], 0.3, atol=0.02)
    assert np.allclose(interior[..., 2], 0.8, atol=0.02)


# ---------------------------------------------------------------- [7] noise

def test_noise_photon_transfer():
    """Flat patches: measured variance tracks a*I + b."""
    from lrlpr.camera.sensor import NOISE_STAGE
    a, b = 0.004, 0.0002
    for level in (0.2, 0.8):
        state = {"current": np.full((200, 200), level)}
        out = NOISE_STAGE.run(state, {"shot_gain": a, "read_var": b, "seed": 3})
        measured = out["raw_noisy"].var()
        assert np.isclose(measured, a * level + b, rtol=0.06)


def test_noise_reproducible_by_seed():
    from lrlpr.camera.sensor import NOISE_STAGE
    state = {"current": np.full((32, 32), 0.5)}
    o1 = NOISE_STAGE.run(state, {"seed": 11})["raw_noisy"]
    o2 = NOISE_STAGE.run(state, {"seed": 11})["raw_noisy"]
    o3 = NOISE_STAGE.run(state, {"seed": 12})["raw_noisy"]
    assert np.array_equal(o1, o2) and not np.array_equal(o1, o3)


# ---------------------------------------------------------------- [9] ISP

def test_isp_identity_when_neutral():
    from lrlpr.camera.isp import ISP_STAGE
    img = rng.random((8, 8, 3))
    out = ISP_STAGE.run({"current": img}, {"srgb_gamma": False})["isp_image"]
    assert np.allclose(out, img, atol=1e-12)


def test_sharpening_overshoots_edges():
    from lrlpr.camera.isp import unsharp
    img = np.zeros((8, 32, 3))
    img[:, 16:] = 0.6
    soft = np.stack([np.convolve(img[0, :, 0], np.ones(3) / 3, mode="same")] * 8)
    soft = np.dstack([soft] * 3)
    sharp = unsharp(soft, amount=1.5, radius_px=1.5)
    assert sharp.max() > soft.max() + 0.01  # halo overshoot exists


# ---------------------------------------------------------------- [11] codec

def test_jpeg_error_grows_as_quality_drops():
    # Structured (compressible) test image — white noise would be worst-case
    # at every quality and mask the quality dependence.
    yy, xx = np.mgrid[:64, :64] / 64.0
    img = 0.5 + 0.3 * np.sin(2 * np.pi * 3 * xx) * np.cos(2 * np.pi * 2 * yy)
    img = np.dstack([img, 0.8 * img, 1.0 - 0.5 * img])
    e95 = np.abs(jpeg_roundtrip(img, 95) - img).mean()
    e10 = np.abs(jpeg_roundtrip(img, 10) - img).mean()
    assert e10 > 3 * e95


def test_multi_generation_compounds():
    from lrlpr.camera.delivery import CODEC_STAGE
    img = np.clip(rng.random((64, 64, 3)), 0, 1)
    g1 = CODEC_STAGE.run({"current": img}, {"quality": 40, "generations": 1})["decoded"]
    g4 = CODEC_STAGE.run(
        {"current": img}, {"quality": 40, "generations": 4, "gen_shift_px": 2}
    )["decoded"]
    assert np.abs(g4 - img).mean() > np.abs(g1 - img).mean()


# ------------------------------------------------------- full-chain smoke test

def test_full_pipeline_end_to_end():
    import os
    from lrlpr.camera import build_full_pipeline
    font = next((p for p in (r"data\fonts\GL-Nummernschild-Eng.ttf",
                             r"C:\Windows\Fonts\arialbd.ttf") if os.path.exists(p)), None)
    if font is None:
        pytest.skip("no font")
    p = build_full_pipeline()
    out = p.run({
        "surface": {"font_path": font},
        "project": {"char_height_px": 8.0, "supersample": 4},
        "motion_rs": {"speed_kmh": 40.0},
        "codec": {"quality": 30},
    })
    dec = out["decoded"]
    assert dec.ndim == 3 and dec.shape[2] == 3
    assert 0.0 <= dec.min() and dec.max() <= 1.0
    # sensor-resolution image: supersampling fully integrated away
    assert dec.shape[0] < out["image"].shape[0] / 3
