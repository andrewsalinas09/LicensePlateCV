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

## 2026-07-22 — Phase 1 first cut landed (renderer [1]-[3] + inspector app)

Design-01 approved by Andrew; design-02 under study (no likelihood code until signed off).
Implemented per design: Stage/ParamSpec/Pipeline with prefix caching; surface stage
(EDT-based emboss shoulder, per-cell glyph centering); shading stage (Lambertian + heightfield
cast shadows, documented light convention); pinhole projection with real units. PySide6
inspector auto-generates controls from schemas. 16 physics tests.

Tests caught two real bugs before any human saw a render: (1) shadow-march direction derived
from a zero vector at elevation 90°; (2) focal-mm/focal-px conflation put the camera 13 cm
from the plate — fixed by adding sensor pixel_pitch_um, camera now lands at physically
sensible distances (~44 m for 12 px chars with a 25 mm lens). Recorded as evidence the
test-against-agreed-math protocol earns its keep.

Official CONTRAN spec extracted (Res. 780/2019 / 969/2022 — see plate-spec-sources.md):
notable corrections vs assumptions — chars 65 mm (not 63), fixed 46 mm cell pitch with
per-cell centering (font advances must NOT be used), NO border on Mercosur plates, band
390×30 mm Pantone 286. Relief height is not publicly specified anywhere (1.2 mm industry
assumption, PROVISIONAL). GL-Nummernschild-Eng (Gutenberg Labo FE-Engschrift digitization,
free license) adopted as the glyph source. Remaining renderer gaps before HR validation:
band contents (emblem/BRASIL/flag), QR, "BR" mark, corner rounding, retroreflective lobe.

---

## 2026-07-22 — Camera stages [4]-[11] landed (design-01 chain complete, first pass)

Andrew approved [1]-[3] ("looks decent, some things I may want to tweak") and asked for the
rest of design-01. Implemented: motion+rolling shutter (row-dependent time via remap,
midpoint-rule exposure integral, velocity in real units from speed/distance/focal), optics PSF
(defocus disk ⊗ Gaussian at supersample res), sensor (exact box aperture + Bayer with phase
choice), heteroscedastic noise at RAW (σ²=aI+b, seeded), demosaic (real cv2 bilinear/VNG/EA;
pattern-name→cv2-code mapping verified by constant-color round-trip test), ISP (WB, sRGB gamma,
S-curve, unsharp), delivery resample (kernel = discrete nuisance), codec (REAL libjpeg,
multi-generation with block-grid misalignment shift). 46 tests total; test-writing caught two
sign-convention slips in the motion smear direction — conventions now documented in the tests.

Deferred, explicitly: H.264/H.265 via ffmpeg (arrives with the multi-frame track phase;
per-frame JPEG is the flagged intra-only stand-in), retroreflective lobe, black-level offset,
lens distortion. GUI now reflects all 11 stages with 15 dynamic image taps.

Visual verification at LRLPR-26-like scale (9 px chars, 40 km/h, 10 ms exposure, q25 ×2
generations): 15 px motion smear (matches v·T), visible Bayer checkerboard in RAW,
chroma-blotch demosaic noise, JPEG block grid — qualitatively indistinguishable from real
degraded surveillance crops. Camera stages await Andrew's vibe pass in the inspector.

---

## 2026-07-22 — Distance-knob clarification + first eyeball match against real data

Question resolved: distance = `project.char_height_px` (camera distance derived from it, shown
live); `supersample` is computation accuracy only — verified invariant (S=4 vs S=8: ~0.006 mean
diff). What co-varies with distance automatically: motion blur px and RS shear (∝1/d, derived).
What deliberately doesn't: optics PSF in sensor px, per-pixel noise, codec quality (camera
properties, not distance properties — the information loss from distance is purely scale).

First smoke test exposed an unrealistic default: 8 ms exposure at 25 m gave a physically
correct 18 px smear that real daylight footage doesn't show — daylight surveillance exposures
are 1–4 ms. Recipe updated (2 ms, 15 km/h).

**Milestone (kept humble):** Andrew ran the HR→LR test himself in the inspector — tuned the
render to match a real LRLPR-26 HR example, then moved ONLY the distance knob — and found the
result "very close" to the corresponding real LR appearance (pose hand-estimated, so not
exact). This is an eyeball-level validation only: it says the forward model produces the right
CHARACTER of degradation, not that it's likelihood-grade accurate. The real bar remains the Δ
kill-test (design-02 §8.6). Noted connection: hand-tuning pose until the render matches IS one
manual iteration of the design-02 nuisance-estimation loop — the decoder automates exactly
this, scored by likelihood instead of eyeball, jointly over all candidate strings.

Known eyeball-visible gaps to close before HR validation: plate frame/screws, band artwork
(emblem/BRASIL/flag), WB color cast, H.264 (JPEG stand-in until multi-frame phase).

---

## 2026-07-22 — Andrew observes seed-dominance at LR scale; ensemble view added

Andrew, sweeping `sensor_noise.seed` at ~8 px chars: the LR image changes drastically per seed
— from closely resembling the real tracks.png LR examples to not resembling them at all.
Interpretation agreed: at this SNR the noise draw is comparable to the surviving glyph signal,
so the forward model's prediction is a WIDE DISTRIBUTION over images; each seed is one draw,
and the real frame is itself one draw. Consequences: (1) never expect any single seed to match
a specific real frame — the pass criterion is that the real frame looks like it belongs in the
ensemble; a real frame resembling NO seed would indicate model mismatch; (2) the seed is NOT a
model parameter — the likelihood integrates over the noise distribution analytically; fitting a
noise realization would be fitting noise (exception, later: structured/fixed-pattern components
with ρ→1, which are estimable); (3) this is the visual form of why single frames carry
millibits of evidence and fusion does the work — the observation distributions of competing
strings overlap heavily at this scale, and that overlap is what the ideal-observer bound will
quantify.

Tool added: inspector "seed ensemble 3×3" checkbox — tiles nine seed draws of the current tap
so the distribution (not one draw) is what the eye calibrates against.

---

## 2026-07-22 — Same-string hand recreation of a real LR example (ARK5156)

Andrew hand-tuned the full pipeline to recreate the real ARK5156 LR example from the LRLPR-26
README figure — same string, hand-estimated pose — and the per-character blob structure matches
closely (which pixels darken, how each glyph dissolves, band position, grouping rhythm). Pair
committed in `ExampleLicensePlateGenerator/` (real from the public README figure; generated).

Honest quantitative residual (matched-scale comparison): real has ~2× plate-region contrast
(std 0.252 vs 0.117) and ~3× gradient energy, plus a warm color cast (red car body + WB) and a
car-body surround our flat backdrop lacks. Interpretation: the remaining mismatch is
PHOTOMETRIC (lighting scale, WB, tone, surround), not structural — and photometrics are
exactly what the planned nuisance-estimation loop fits automatically. Kept humble: this is one
hand-picked example, matched by the person who chose the parameters; it demonstrates
feasibility of manual channel matching, nothing more. The rigorous version remains the Δ
kill-test on real paired tracks with fitted (not hand-tuned) nuisances.

Next tooling step agreed as valuable: A/B compare in the inspector (load a real crop, flicker
against the render, difference metrics at native resolution).

Follow-on observation (Andrew): the recreated plate is ARK5I56, not ARK5156 — the Mercosur
pattern (LLL-D-L-DD) forces position 5 to be a LETTER, so the glyph everyone reads as "1" is
provably "I". The format prior disambiguated a character without better pixels (and the
renderer's pattern validator enforced it during recreation). Generalized: plate systems are
"designed non-adversarial" — (1) class-locked slots eliminate ALL cross-class confusions
(1/I, 0/O, 5/S, 8/B, 2/Z, 6/G, 7/T never compete in any Mercosur slot; only within-class
ambiguity survives: E/F, C/G, O/Q; 3/8, 6/8, 5/6), worth far more than the raw 7.4-bit space
reduction (36⁷→26⁴·10³); (2) FE-Schrift is literally a forgery-impeding design — maximizing
glyph-pair distinguishability is its design objective, which is the same quantity (pairwise
KL) our decoder's error rates run on. Consequence for design-02 §8.5: the collision census
only needs within-class pairs per slot. Consequence for the earlier ARK5156 mentions in this
log/commits: string corrected to ARK5I56.

Second recreation pair added (Andrew): RHB6I06 (again a position-5 "1"→I correction via the
format pattern), this time with the HR reference screenshot — a same-plate HR/LR/generated
triple in `ExampleLicensePlateGenerator/RHB6I06/`. Glyph-blob morphology visibly closer than
the first pair. Key finding: the quantitative residual has the SAME signature as pair 1 —
generated is flatter (contrast 0.139 vs 0.229) and cooler than real (both real examples: dark
red car surrounds; part of the gradient gap is a resolution confound in the saved PNG). A
systematic residual across independent hand-matches indicates an uncalibrated global channel
parameter (lighting scale / tone / dataset sharpening / surround), not random mismatch —
exactly what channel calibration from a small set of pairs would fix once. Still eyeball-tier
evidence; Δ with fitted nuisances remains the bar.

Design-02 discussion opened (Andrew): how to account for some nuisances being fixed while
others vary — e.g. PSF/MTF. Resolved as the **nuisance hierarchy** (design-02 §5b added):
every nuisance declares a scope (camera-fixed / track / frame / realization); scope = how many
observations constrain it = pooling strength; treatment follows scope (calibrate-and-plug-in /
marginalize / EM-search / integrate analytically). Key worked example: "the PSF" decomposes
across THREE scopes (base MTF camera-fixed, defocus track-derived from distance, motion blur
frame-directional with kinematic smoothness) — high-dimensional nuisances de-fang by scope
decomposition. Major consequence: HR frames calibrate camera-fixed parameters that transfer
directly to LR likelihoods — paired datasets are calibration channels. Frame/band-artwork
renderer work discussed then deferred by Andrew (band artwork is flat printed film — albedo
only; frame/screws = 3D via shared-heightmap shadows + two-plane homography parallax — design
sketched in conversation, not yet in design-01).

Decoder test plan agreed in principle (Andrew: "generate the image, then find the text from
it — forget the dataset; pure data first; lots of instrumentation; be intelligent about which
chars blur together"). Formalized as the **oracle ladder**: E0 plumbing proof (zero noise, all
nuisances known, truth must win with zero residual) → E1 noise-only (Gaussian likelihood exact
by construction; per-slot argmax IS exact MAP since no coupling; validates machinery against
theory) → E2 blur/downsample (coupling appears; ink gap ≈ 0.17×char height → at 8 px chars
neighbors couple beyond ~0.7 px blur radius; horizontal motion blur is the coupling amplifier
reaching 2-3 cells; coupling bandwidth MEASURED from the forward model per config, feeds
trellis order k; deliverable = factorization gap vs exact enumeration) → E3 full chain known
nuisances (race pixel-Gaussian vs DCT likelihood, first calibration curves) → E4 remove
knowledge one nuisance at a time (measured cost per unknown) → E5 multi-frame (Chernoff, ρ).
Then real HR, then real LR. Instrumentation: decoder tab in inspector — live per-slot
likelihood heatmaps, posterior bars, margins, truth marker, reacting to degradation sliders.
First build = E0+E1 + decoder tab, pending Andrew's go (design-02 gate).

BUILT (Andrew: "let's go for it"): `lrlpr/decode/` — likelihood.py (Gaussian noise model (a),
prediction caching since means are seed-independent), slots.py (per-slot format-prior tables:
only legal chars per slot, conditional-on-reference scoring), rungs.py (E0-E3 oracle configs).
Tests test_decode_e0_e1.py (8, green): E0 truth has exactly-zero residual + wins every slot +
reference-independence without coupling; E1 recovery, seed-reproducibility, margins shrink with
noise, and **calibration under genuine ambiguity**. Decoder tab added to inspector: per-slot
posterior heatmap (truth=green, wrong-argmax=red, brightness=posterior), predicted string, mean
margin, weakest-slot confidence.

**Leakage audit (Andrew was suspicious E1 was "too easy / degenerate"):** ran adversarial
checks. (1) predict() is seed-independent (byte-identical across calls) — no seed leakage.
(2) 20 random plates decoded with CORRECT vs FIXED-WRONG reference string: 20/20 both — no
reference leakage; the decoder recovers whatever is in the pixels. (3) pure-noise image decodes
to garbage (TTT3I33), NOT the truth — no answer-peeking. Resolution of "how is there no
information yet it's not degenerate": a 7 px CHAR-HEIGHT observation is ~3,400 px (~150-480
px/char), per-pixel SNR ~4.8 → per-char SNR ~100. 7 px is information-RICH; recovery is
inevitable, not suspicious. Degradation kicks in at real LR scale (2-3 px/char): measured 5px
98%, 4px 80%, 3px 60% — it IS degenerate there, we just hadn't aimed at that scale. Deeper: E1
is easy BY DESIGN because the observation comes from the exact same forward model (no glyph/pose/
blur mismatch) — a pure matched-filter problem; E1 validates machinery only, never realism.
Caveat found: margin-in-nats is ~13 even on pure noise (scales with pixel count) → poor
standalone confidence metric; use the normalized posterior (which the calibration test already
does). Instrumentation TODO: replace/augment margin-in-nats display with posterior.

**First scientific finding (E1):** pure sensor noise barely degrades recognition — even 7 px
chars recover at 100% under max noise. Recognition only breaks below ~4 px (80% per-slot acc) /
3 px (60%). And calibration holds tightly there: mean confidence 0.799 vs accuracy 0.802 at
4 px, 0.584 vs 0.600 at 3 px. Confirms the machinery is calibrated by construction under the
true model (validates code, not realism) AND that the real degradation driver is coupling/blur,
not noise — motivating E2 as the next and more important rung.

Second realization (Andrew): "I don't even need the dataset to test the model — I mean I do,
but I don't." Formalized: dataset-free = everything where we control ground truth (decoder
development, ideal-observer bound sweeps, factorization gap, fusion ablations — the method
computes rather than learns, so no training data enters its construction). Dataset-required =
validating that the channel describes reality (Δ test, real-data calibration) — but that role
needs a small number of paired real examples to fit/check a camera model, not a large training
corpus. The dataset's role shrinks from prerequisite to validation instrument. (Caveat kept in
view: synthetic data from our own model can never validate the model — the small real set is
irreplaceable for that, and none of today's eyeball evidence substitutes for it.)

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
