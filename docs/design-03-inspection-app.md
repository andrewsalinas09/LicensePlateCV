# Design 03 — Interactive Pipeline Inspection App (PySide6)

**Status: DRAFT for discussion. Requirement from Andrew (2026-07-22): every pipeline step gets
a GUI for demo + inspection, with sliders configuring things in real time. Purpose: vibe-test
the physics in many situations/environments, try to break it, debug visually, and have a
shareable walkthrough. "It's how I find the best stuff."**

## Why this is load-bearing, not a toy

The forward model makes ~30 physical claims (design-01). Most bugs in physics simulation are
not crashes — they're images that are subtly wrong (shadow on the wrong side, blur applied
after gamma, mosaic phase off by one). The fastest detector for those is a human with sliders.
The GUI is also the enforcement mechanism for good architecture: it only works if every stage
is a pure, parameterized, schema-described function — exactly what the science needs anyway.

## Architecture

```
lrlpr (library)                      lrlpr-inspect (PySide6 app)
┌──────────────────────────┐         ┌────────────────────────────────┐
│ Stage: pure function     │ schema  │ auto-generated parameter panel │
│  (image, params)->image  ├────────►│  (sliders/combos/checkboxes)   │
│ + ParamSpec schema       │         │                                │
│  name,range,units,scale  │         │ stage-tap image viewer         │
│ Pipeline: [Stage,...]    │ images  │  (view AFTER any stage,        │
│  with per-stage caching  ├────────►│   zoom to pixel level, RAW     │
└──────────────────────────┘         │   mosaic view, A/B compare)    │
                                     └────────────────────────────────┘
```

- **Stages as pure functions with schemas.** The GUI reflects over the pipeline: each
  parameter's slider is generated from its declared range/scale; each stage gets an on/off
  toggle (the same toggle the ablation harness uses). Zero GUI-specific code inside the
  library — the app is a thin viewer over the real pipeline, so what you inspect IS what the
  decoder uses. No divergence possible between "demo physics" and "real physics."
- **Per-stage caching for real-time sliders.** Moving a slider on stage k recomputes only
  stages k..end (upstream outputs are cached). Preview runs at reduced supersampling for
  interactivity, with a "full quality" render button that recomputes at science settings —
  the quality knob is sampling density, never different math (see GPU/CPU below).
- **Stage taps.** A viewer showing the image after ANY stage: linear radiance, post-shading,
  post-PSF, RAW Bayer mosaic (as the actual one-channel-per-site grid, not interpolated),
  post-demosaic, post-ISP, post-resample, post-codec (+ residual vs. pre-codec). Pixel
  inspector (hover → exact values), zoom to single-pixel level.
- **A/B compare.** Any two configs side-by-side or flicker-toggle (e.g. relief on/off,
  demosaic algorithm A/B) — this is how "does this stage matter visually" gets vibe-tested
  before the leverage analysis quantifies it.
- **Scenario presets.** Named JSON channel configs (= design-01 config objects): "daylight
  highway", "night IR flash", "rainy dusk", "FANVID digital tail", "3-generation YouTube".
  Shareable; the fun-walkthrough mode is just a curated preset sequence with captions.
- **Scrubbable dimensions**: plate string, sun azimuth/elevation, distance (char height in
  px), velocity, exposure, JPEG Q / HEVC QP, generation count, seed. A time axis renders a
  short track (N frames with kinematics) and plays it — this is where waving/aliasing becomes
  directly visible and breakable.

## GPU vs CPU rendering (Andrew's question, answered)

**For our workload, GPU vs CPU is a speed decision, not a quality decision.** The Blender
folklore is Blender-specific: Cycles CPU/GPU kernels historically differed in *feature
support* (e.g. OSL shaders CPU-only) and memory limits — implementation differences, not
physics. GPUs and CPUs run the same IEEE-754 float math; results differ only in last-bit
rounding from different summation orders (~1e-7 relative for float32), far below every noise
floor in our channel (quantization alone is ~1e-2).

What actually controls realism for us: (1) **sampling density** — supersampling factor S,
PSF kernel support, per-row rolling-shutter evaluation; (2) **kernel exactness** — bit-faithful
cubic coefficients, correct mosaic phase, real libjpeg/libx265 for codecs; (3) **model
completeness** — the stages themselves. None of these care what device the arrays live on.
Note we are NOT path tracing: the renderer is analytic 2.5D shading + convolutions + warps —
deterministic array math, embarrassingly parallel.

**Plan:**
1. **CPU reference implementation first** (NumPy/SciPy, float64 where cheap): the gold
   standard, unit-tested against analytic cases. Slow is fine; it defines correctness.
2. **GPU port later** (PyTorch tensors, same operations) for the big sweeps (10⁸-hypothesis
   scoring, bound Monte Carlo) — with a standing CI test asserting GPU output matches CPU
   reference within tolerance on fixed test vectors. If they ever diverge beyond tolerance,
   the GPU port is wrong by definition.
3. **Codec stages always run the real encoders** (libjpeg, ffmpeg/libx264/libx265) — never a
   hand-rolled "JPEG-like" approximation; the artifacts ARE the noise model.
4. PROVISIONAL: if the shading model ever needs full global illumination / measured-BRDF
   validation (retroreflective sheeting at night), use Mitsuba 3 offline as a ground-truth
   renderer to validate the fast analytic renderer against — not in the interactive loop.

## Dependencies & placement

- App package `tools/inspect_app/` (PySide6 added as a dev/tools dependency group — the core
  library must not depend on Qt).
- Preview interactivity target: <100 ms per slider move at preview quality on CPU; if a stage
  can't hit that (codec cascade), it drops to debounced async recompute — never blocking the UI.

## Build order

The app grows a tab per phase, in step with the library: Phase 1 renderer tab (string, font,
relief, lighting, geometry sliders) → Phase 2 adds camera stages → Phase 3 adds a decoder tab
(live likelihood tables per slot, posterior bars, per-frame evidence contributions — watching
the posterior sharpen as frames accumulate is both the demo and the debugger).
