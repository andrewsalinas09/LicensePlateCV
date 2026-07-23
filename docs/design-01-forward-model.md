# Design 01 — The Forward Model: Renderer + Camera Simulation

**Status: DRAFT for discussion — nothing here is implemented. Items marked PROVISIONAL are
choices we expect to revisit with experiments. Per project protocol, no code until this is
signed off.**

The forward model is the deterministic-plus-stochastic function that turns a hypothesis
(plate string `s`) into a predicted probability distribution over observed pixels. It has two
halves: the **renderer** (what the plate looks like in the world) and the **camera** (what the
acquisition pipeline does to it). Every stage below is a physical claim; every stage gets an
on/off toggle so its leverage on the decision can be measured (∂LLR/∂θ analysis, memo §4.4).

Pipeline overview (causal order):

```
s (string) ─► [1] plate surface (2.5D relief + materials)
           ─► [2] illumination & shading
           ─► [3] projective geometry (intrinsics + extrinsics)
           ─► [4] motion + rolling shutter
           ─► [5] optics PSF
           ─► [6] sensor sampling (pixel aperture + Bayer mosaic)
           ─► [7] sensor noise (shot + read)
           ─► [8] demosaic
           ─► [9] ISP (WB, tone curve, sharpening)
           ─► [10] resampling / digital downscale
           ─► [11] codec (JPEG / H.264)
           ═► y (observed frame)
```

## [1] Plate surface — NOT flat (agreed 2026-07-22)

Plates are stamped aluminum: characters raised ~1.0–1.5 mm with rounded die edges, painted
faces, on retroreflective sheeting. Model as 2.5D:

- **Heightmap** h(u,v): glyph outlines (FE-Schrift vector paths) extruded to relief height
  `h_char`, with a die-radius rounding profile at edges (parameter `r_die`). Both are physical
  constants per plate spec — look up or measure once, then fixed.
- **Albedo map** a(u,v): character paint color on raised faces, sheeting color elsewhere
  (Mercosur: black on white; band colors per class).
- **Material/BRDF**: daylight ≈ Lambertian diffuse + weak retroreflective lobe. Night/flash:
  retro lobe dominates (bright plate, inverted contrast possible). PROVISIONAL: start diffuse +
  retro-lobe scalar; no specular clearcoat, no interreflection.

Why it matters: at ~5 px character height, an illumination-dependent shadow/highlight rim on
glyph edges shifts apparent edge positions at the sub-pixel level, which changes the aliased
pattern after downsampling — and aliased patterns are the evidence we decode from. A flat
renderer systematically biases every character likelihood under directional light.

## [2] Illumination & shading

- Parameterization: sun/dominant direction **l** (2 angles), direct intensity E_d, ambient/sky
  E_a. Shading: `I(u,v) = a(u,v) · [E_a + E_d · max(0, n(u,v)·l)] + retro term`.
- Cast shadows from relief: horizon test on the heightmap (cheap at render scale).
- **Sharing:** within a track (~1 s), θ_light is SHARED across frames (see design-02 §5).
- PROVISIONAL: no spatially varying illumination across the plate (it is 40 cm wide; sky
  gradients negligible at that scale), revisit for headlight/shadow-boundary cases.

## [3] Projective geometry

- **Extrinsics**: plate pose (rotation R, translation t) per frame → with intrinsics defines
  the homography H from plate plane to sensor plane (plate is planar; relief handled in [1]-[2]
  as shading, not parallax — PROVISIONAL, valid because relief ≪ distance).
- **Intrinsics** K: focal length, principal point; **lens distortion**: radial k1, k2
  (Brown model). For LRLPR-26 unknown → estimable from scene structure / marginalized.
- Rendering is done **supersampled** (integer factor S× the sensor grid, S≈8) so all
  sub-pixel geometry survives until sensor integration in [6].

## [4] Motion + rolling shutter (matters a lot — agreed 2026-07-22)

- **Motion blur**: plate moves with image-plane velocity v during exposure T_exp; blur kernel =
  line integral along the (possibly curved, but PROVISIONAL: straight) trajectory. Length
  ‖v‖·T_exp px, direction v/‖v‖.
- **Rolling shutter**: sensor rows are read sequentially, row r exposed at t₀ + r·t_row.
  Moving plate → per-row displacement → shear/wobble: `Δx(r) = v_x · t_row · r` (and Δy).
  Parameter t_row (line time) is a camera constant — estimable once per camera from any
  fast-moving object, then known. Implemented by evaluating the geometry of [3] at the
  row-dependent time, not as a post-warp. Interacts with [5]: each row has its own effective
  motion kernel phase.
- Track kinematics (from the 5-frame sequence) constrain v strongly — velocity is nearly
  shared/smooth across a track (design-02 §5: slowly-varying nuisance).

## [5] Optics PSF

- Parametric family: defocus disk (radius ρ_d) ⊗ isotropic Gaussian (σ_o, lumping diffraction
  + aberrations + AA filter) ⊗ motion kernel from [4]. PROVISIONAL: this 2-3 parameter family
  vs. measured MTF; plate borders/character stems act as slanted-edge targets for in-situ PSF
  estimation (memo §4.3).
- Applied at supersample resolution, before sensor integration.

## [6] Sensor sampling: pixel aperture + Bayer

- **Pixel aperture**: integrate the supersampled irradiance over each pixel's footprint
  (box filter ≈ fill-factor; PROVISIONAL: 100% fill factor box).
- **Bayer mosaic (RGGB)**: each site retains ONE color channel. The sensor never measured 2/3
  of the color data — demosaic [8] will invent it, with structured artifacts on high-contrast
  glyph edges (zippering, false color). Modeling this is why we simulate mosaic+demosaic
  instead of pretending the camera captured RGB.
- **CRITICALITY NOTE (Andrew, 2026-07-22): at our SNR, [6]+[8] are among the most important
  stages to get exactly right.** We operate at the pixel level; some of the bits of
  information per frame are literally mosaic structure leaking through into the final image
  (channel-dependent sampling phase on glyph edges survives demosaic and even downstream
  resampling as a colored micro-pattern). Getting the mosaic layout, phase, and demosaic
  arithmetic bit-faithful is not optional polish — it is evidence.
- **Color: plates are NOT all black/white.** NY (older) plates are yellow-on-blue/yellow
  fields; Mercosur bands are colored; commercial classes vary. Albedo is per-channel RGB from
  the start, and WB/CCM in [9] carry real leverage for colored plates. PROVISIONAL: still skip
  full spectral (wavelength-resolved) simulation — linear-RGB albedo with per-channel gains —
  revisit only if a colored-plate validation fails.

## [7] Sensor noise (inserted at the RAW mosaic domain)

- Heteroscedastic Gaussian approximation of Poisson shot + Gaussian read:
  `σ²(I) = a·I + b` with gain a and read floor b — the standard photon-transfer model, both
  estimable from flat patches in real footage.
- Clipping at black level and saturation (hard nonlinearity — matters for night/flash).
- User note (2026-07-22): allow noise injection points BEFORE AND AFTER other stages too —
  we don't know a priori how much each matters; the leverage analysis decides. Architecture:
  every stage boundary accepts an optional noise term; defaults off except [7].

## [8] Demosaic

- The camera's algorithm is unknown. Options: bilinear, Malvar-He-Cutler (OpenCV default),
  edge-directed (AHD-like). Treat the **choice as a small discrete nuisance** (3-4 candidates,
  marginalize or select by residual fit), each deterministic given the mosaic.
- Known consequence: correlated residuals across neighboring pixels (violates iid — handled by
  the covariance model in design-02 §3).

## [9] ISP

- Black level subtract → white balance gains (2 params) → color matrix (PROVISIONAL: identity)
  → tone curve (sRGB gamma with optional contrast S-curve, 1-2 params) → **sharpening**
  (unsharp mask: amount, radius — creates halos at glyph edges that a model without it would
  misread as evidence) → optional in-camera denoise (PROVISIONAL: off; revisit for night).
- All estimable/marginalized; mostly shared per camera or per track.

## [10] Resampling

- Digital downscale by the surveillance stack or dataset creation. Kernel matters (bilinear vs
  bicubic vs area) — for FANVID this stage is EXACTLY KNOWN: `cv2.resize INTER_CUBIC` to
  1280×720 then to 320×180 (we have the script; A=-0.75 Keys kernel). For other data:
  small discrete kernel family + scale factor, estimable.

## [11] Codec

- **JPEG**: 8×8 block DCT, per-coefficient uniform quantization with steps from the quant
  table (READ FROM THE FILE HEADER — known exactly when we have the file). Likelihood
  evaluated natively in this domain (design-02 §2).
- **H.264 / H.265 video** (H.265/HEVC is common in modern surveillance — first-class support,
  not an afterthought): intra frames ≈ JPEG-like (4×4–32×32 transforms; H.265 has larger CTUs
  and stronger in-loop filtering incl. SAO); inter frames predicted from neighbors + quantized
  residual + deblocking. Consequences: (a) within-frame correlated artifacts, (b) ACROSS-FRAME
  correlated noise → the ρ/N_eff machinery of design-02 §4; GOP structure (which frames are
  I/P/B) is readable from the stream when we have it.
- **Multi-generation encoding (Andrew, 2026-07-22)**: real evidence is often screenshots of
  screenshots — e.g. FANVID is a YouTube re-encode of whatever upload pipeline the source went
  through, possibly with screen capture in between. Model the codec stage as a CASCADE of
  1..k encode/decode generations, each with its own codec/params (+ possible intermediate
  resampling). Generation count and per-generation params = discrete/continuous nuisances.
  Each generation re-quantizes on its own block grid; misaligned grids compound into
  characteristic artifact patterns (useful: they also fingerprint the processing history).

## Identifiability table (memo §4.4 discipline)

| Parameter | Status |
|---|---|
| Glyph geometry, plate dims, relief height/die radius | Known (spec/measure once) |
| FANVID resize kernels | Known exactly (their script) |
| JPEG quant tables, GOP structure | Known when file available (headers) |
| Homography/pose per frame | Estimate (corners, borders; per-frame) |
| Velocity, rolling-shutter line time | Estimate (track kinematics; t_row per camera) |
| PSF params (σ_o, ρ_d) | Estimate (slanted-edge on borders/stems) |
| Noise a, b | Estimate (photon transfer on flats) |
| Illumination direction/ratio | Estimate or marginalize; SHARED per track |
| Demosaic choice, resample kernel (non-FANVID) | Small discrete nuisance; marginalize/select |
| Sharpening, tone curve, WB | Estimate; shared per camera |
| Dirt, frames/screws, sheeting wear | Marginalize (low-dim perturbation prior) or absorb |

## Implementation requirements (for later phases; listed so design constrains code)

1. Every stage toggleable and parameterized; a "channel config" object fully describes a model.
   Stages are pure functions `(image, params) -> image` with a declared parameter schema
   (name, range, units, log/linear scale) — this single architecture serves the library, the
   ablation toggles, AND the inspection GUI (design-03) which auto-generates its sliders from
   the same schema.
2. Supersampled compositional rendering: glyph g in slot j rendered once per (frame nuisance
   set), composed per hypothesis — this is what makes trellis unary/pairwise tables cheap.
3. Bit-exact replication of known stages (cv2 cubic for FANVID; libjpeg quantization).
4. Validation before use: renders vs. real HR crops (LRLPR-26 Scenario A has corner GT);
   slanted-edge MTF sanity; photon-transfer noise fit. The renderer is WRONG until proven
   otherwise against real images.
