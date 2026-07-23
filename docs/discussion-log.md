# Discussion Log

Append-only record of design discussions, insights, and decisions — including thinking that
doesn't rise to a design doc. Purpose (per Andrew, 2026-07-22): a future model/reader should be
able to distill everything important from `docs/` alone.

---

## 2026-07-22 — Phase 0 research + FANVID + core design discussion

**Landscape (from two research passes, see phase0-*.md):** ICPR 2026 LRLPR benchmark open at
82.13%; no analysis-by-synthesis competitor exists; Confidence Gap named an open problem by
organizers (winner 6.67%, best 14.86%) — natural headline metric for a likelihood method.
Dataset access: LRLPR-26 et al. require university-email license; Andrew (solo, no affiliation)
emailed Laroca an honest request; awaiting reply. Not on the critical path (Paper B is
synthetic-first).

**FANVID demoted after joint audit.** Andrew: "kind of garbage — way harder and not real
optical low res." Verified: LR is digitally manufactured (source YouTube → cv2 INTER_CUBIC
1280×720 → 320×180; we have the script, so the operator is exactly known); median plate
13.8×4.8 px, >half of clips ≤5 px plate height; ~half effectively static (62/175 clips <3 px
total motion — no phase diversity, so frames are near-copies); regions mixed (Indian, NYC taxi
e.g. 5N53B, various) so no single font prior; some annotation boxes corrupt (negative heights).
Retained roles: (1) controlled decoder testbed on the moving subset (known operator!), (2)
calibration showcase — quantify what fraction of the benchmark is information-theoretically
undecodable (turns "garbage" into a publishable statement).

**The "waving" text Andrew observed in FANVID clips** = sub-pixel phase aliasing: bicubic
decimation folds above-Nyquist glyph energy differently as the plate moves fractions of an LR
pixel. It is the exploitable information (dither/drizzle mechanism), and per-frame sub-pixel
registration is therefore a critical nuisance parameter.

**Process rule (standing):** nothing technical gets implemented without Andrew understanding
it 1000%. Design doc → discussion → sign-off → code with tests against the agreed math.
Provisional choices marked PROVISIONAL. All discussions logged here.

**Renderer must model the stamp (Andrew).** Plates are embossed; raised glyphs cast
illumination-dependent sub-pixel shadow/highlight rims that change which aliased pattern the
downsampler produces. Renderer = 2.5D heightmap + normals + shading; illumination is a shared
per-track nuisance. → design-01 [1]-[2].

**Channel must literally simulate a camera (Andrew):** blur → rolling shutter (matters a lot)
→ Bayer mosaic → noise (insertion points before/after every stage; leverage measured, not
assumed) → demosaic → ISP → resample → codec; intrinsics + extrinsics. → design-01 [3]-[11].

**Evidence accumulation ("the magic", Andrew's 1-pixel × 1M-frames intuition):** confirmed
mechanism — per-frame expected score gap between truth and competitor = KL divergence (may be
millibits); gaps ADD across frames; error decays exponentially (Chernoff). No reconstruction
anywhere; no per-frame decisions ever (argmax/voting discards exactly the millibits that are
all the information at low SNR). → design-02 §3.

**Two correlations resolved (Andrew's sun question):**
- Noise correlation between frames: tunable ρ∈[0,1]; N_eff = N/(1+(N−1)ρ); never adds
  information, but modelable correlation partially cancels (fixed-pattern noise removable
  exactly because ρ=1). Unmodeled ρ ⇒ overconfident garbage; so ρ is estimated, never assumed.
- Condition (nuisance) correlation: shared sun = pooling gain (nuisance tax paid once) but
  frozen blind spots (aliasing collisions unbreakable within the track); varying conditions =
  diversity insurance (different projections; limit case photometric stereo). Nature's split in
  a 1-s track is favorable: photometrics static, geometry varying. Static-plate + single-encode
  clips have both knobs at worst — the formal reason the degenerate FANVID clips are hopeless.
  → design-02 §4-§5.

**Open questions flagged:** EM bootstrap under weak evidence (self-confirming-decode risk;
consistency test as tripwire); Gaussian-pixel vs DCT-quantization likelihood (both built,
experiments decide); spatial residual correlation model; how much relief shading matters at
heavy compression (leverage test).

---

## 2026-07-22 (later) — design-01 review feedback + inspection app requirement

Andrew signed off on design-01 direction ("looks very good") with additions, all incorporated:

- **Inspection GUI is a first-class deliverable** (new design-03): PySide6 app, real-time
  sliders for every stage parameter, per-stage image taps (incl. RAW mosaic view), A/B
  compare, scenario presets, track playback. Rationale: vibe-testing the physics by playing
  with it / trying to break it is how Andrew finds the best stuff; also debugging + shareable
  walkthrough. Architecture consequence: stages must be pure schema-described functions
  (library-side), GUI is a thin reflective viewer — no separate "demo physics."
- **GPU vs CPU question resolved**: for our analytic raster workload it's speed, not quality —
  Blender's CPU/GPU differences are implementation/feature-parity issues, not inherent physics.
  Realism lives in sampling density, kernel exactness, model completeness. Plan: CPU NumPy
  reference (gold standard, unit-tested) → GPU port validated against it in CI; real encoder
  libraries for all codec stages (never hand-rolled approximations). Mitsuba 3 noted as
  optional offline ground truth if BRDF-level validation is ever needed.
- **Bayer/demosaic elevated to critical** (Andrew): at this SNR, part of the per-frame
  information is literally mosaic structure leaking through — bit-faithful mosaic phase and
  demosaic arithmetic is evidence, not polish. → design-01 [6] criticality note.
- **Colored plates**: not all plates are black/white (NY yellow, Mercosur bands) — per-channel
  RGB albedo from the start; WB/CCM carry real leverage on colored plates. Full spectral
  simulation still deferred (PROVISIONAL).
- **Multi-generation encoding**: real evidence is screenshots-of-screenshots (FANVID = YouTube
  re-encode chain). Codec stage becomes a cascade of 1..k generations, each with own params;
  generation count is a nuisance; misaligned block grids compound + fingerprint the history.
- **H.265 first-class** alongside H.264 (common in surveillance).

---

## 2026-07-22 (later still) — metric clarifications and an early go/no-go quantity

Notes from further discussion. All of this is speculative — none of it is validated, and the
approach may well not work in practice; recorded only so the reasoning isn't lost.

- **Terminology care: the competition's Confidence Gap is not calibration.** It is
  E[conf | correct] − E[conf | incorrect]. It does not test whether predictions at confidence
  q are correct with frequency q; two badly miscalibrated systems can share the same gap.
  When we write about confidence we should keep the two concepts separate and be precise
  about which one any number refers to.
- **A Bayesian posterior is calibrated by construction only under its own generating model.**
  On synthetic data drawn from our own channel, calibration is guaranteed (and therefore
  uninteresting as evidence). The only interesting question is calibration under a
  *misspecified/estimated* channel on real data — entirely open, and the known failure mode
  (confidently wrong under model mismatch, memo §5) cuts exactly against it.
- **Paired LR/HR tracks as channel-calibration data.** If access to real paired data is ever
  granted (LRLPR-26 / UFPR-SR-Plates style: LR and HR of the same plate), the pairs could be
  used to estimate the acquisition channel empirically (registration, blur kernels,
  photometrics, residual covariance) rather than hand-guessing a camera simulation. A
  hand-built generic simulator and a data-calibrated channel are very different objects; the
  latter is the one that might describe real data. This adds a channel-estimation work item
  to the plan (fits design-01's identifiability table as an additional estimation source).
- **The earliest meaningful empirical quantity we can measure** on any real paired track:
  Δ = log p(y | s_true) − log p(y | s_best-wrong) under our fitted channel. If Δ is not
  reliably positive on real validation tracks, the model is not describing reality and
  everything downstream is moot. This should be a named milestone experiment (added to
  design-02 §8) — a cheap, honest kill-test long before any leaderboard thoughts.
