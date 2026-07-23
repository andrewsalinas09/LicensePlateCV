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

---

## 2026-07-22 (reference images) — screenshot-of-oracle as the first external input; outside colors carry heavy information

Andrew's observation on the RHB6I06 pair: the colors OUTSIDE the characters — blue band, white
retroreflective field vs the dark surround — are "giving a ton of info." They are the largest,
most color-distinct structures in a LR crop, so they anchor localization/registration and
photometrics (white balance, exposure) *string-independently* — exactly the bootstrap
structure design-02 §7 wants for initializing registration before any character evidence
exists. Worth exploiting deliberately rather than incidentally.

Agreed first step toward real inputs (Andrew): **screenshot the oracle** — capture the
renderer's own output through a display/screenshot channel (display gamma, 8-bit quantization,
PNG, possibly view rescaling). Same image, but NOT literally identical to the pipeline's linear
array: the gentlest possible model mismatch, with ground truth still known. Ladder of external
inputs: oracle screenshot → hand-matched recreation screenshots → real crops (Real.png).
`ExampleLicensePlateGenerator/RHB6I06/Generated.png` (a screenshot of the render) is the first
instance.

BUILT (inspector): (1) **Save view PNG** button — saves the displayed (gamma 1/2.2, 8-bit)
image, making "screenshot the oracle" a one-click reproducible step instead of a manual snip;
(2) **Reference tab** — load an external image from disk or paste a screenshot from the
clipboard (Win+Shift+S → Ctrl+V), preloads the RHB6I06 Generated.png, pixel inspector shows
raw u8 and sRGB-linearized values; the image is stored both display-referred and linearized
(IEC 61966-2-1 inverse) for future scoring use. NOTE the linearization is approximate for our
own screenshots (app displays with pure 1/2.2, sRGB inverse is piecewise) — that residual
mismatch is part of what the oracle-screenshot rung is for. Not yet built (next, "go from
there"): registering/scoring the loaded reference against the forward model.

---

## 2026-07-23 — First external decode: the screenshot channel is nearly free; unknown nuisances are everything

BUILT: `lrlpr/decode/reference.py` (+ CLI `tools/decode_reference.py`, GUI "Decode reference"
button, test test_decode_reference.py). Registration = string-independent template match over
(scale, translation): the template is the forward model's prediction for a NEUTRAL string
(XXX0X00), so no truth leaks into registration — the "outside colors" doing the localizing.
Two lessons baked in: (1) normalized SSD (TM_SQDIFF_NORMED) is DEGENERATE under scale search
(a tiny flat template patch matches any flat region with ~zero error; first run locked onto a
21×10 dark corner) — zero-mean NCC (TM_CCOEFF_NORMED) + a minimum-coverage constraint fixes
it; (2) noise floor for scoring is estimated robustly from the registered residual
(median-of-squares / 0.4549, χ²₁ median) so character-cell mismatch doesn't inflate it.
Domain note: with ISP srgb_gamma on, pipeline output is display-referred, so sRGB-inverting a
screenshot lands ≈ back in the prediction's domain (piecewise-vs-2.2 residual, deliberate).

**Result, controlled rung (settings KNOWN — render at defaults, char 8 px, full chain incl.
JPEG, noise seed 0; screenshot channel = display gamma → 8-bit → nearest zoom 7.8× → border →
PNG → sRGB-inverse):** registration recovers the view transform almost exactly (zoom 7.767 vs
true 7.8; offset 19 vs true 18; NCC 0.928, and the char_height sweep's NCC peaks at the true
8 px), decode is 7/7 slots, Δ = +148 nats. The screenshot channel costs ~nothing when the
channel is known — machinery validated through a genuinely external image path.

**Result, uncontrolled rung (RHB6I06/Generated.png — Andrew's hand-tuned render, settings NOT
recorded):** registration still locks (NCC 0.821, char_height ≈ 8 px, zoom 7.83) but decode is
3/7 (RMB8A86 vs RHB6I06) with high posteriors — CONFIDENTLY WRONG, exactly the design-02 §6
misspecification failure mode, on the mildest possible real input. Residual shows the
prediction's chars thinner/sharper than the observation's (lighting/blur/relief hand-tuning
we didn't reproduce). Δ swings +148 → −126 nats between known and unknown nuisances: first
direct measurement of the "cost of unknown nuisances" (E4's question) — and it dwarfs the
screenshot-channel cost. Wrong slots are all within-class neighbors (H→M, 6→8, I→A, 0→8),
format prior still holding the class structure.

Consequences: (1) settings sidecars — a saved oracle screenshot is only a controlled
experiment if the config is recorded; Save-view should eventually write the overrides JSON
next to the PNG (TODO); (2) the GUI loop is now: load reference → tune sliders → Decode
reference (current settings as channel) → watch Δ; recovering RHB6I06 by re-tuning is the
natural next exercise, followed by Real.png — where nuisance ESTIMATION (design-02 §7),
not hand-tuning, is the real answer.

---

## 2026-07-23 — E3 arrived early: the pixel-Gaussian breaks under the full chain at 7 px (Andrew's R→B)

Andrew ran the GUI reference decode on his own snip (RMN6X08, char 7) and got BMN6X08 —
one slot wrong, R→B, high confidence. Ablation chase (channel stages toggled one at a time,
then registration removed entirely):

| variant | chain | screenshot channel | registration | result |
|---|---|---|---|---|
| loose/tight snips, any zoom/gamma | full | yes | yes | B...... (tight snips: garbage) |
| E: pipeline output scored directly | full | none | none | **BH.....** |
| F: E + gamma/8-bit round-trip | full | quantization only | none | B...... |
| G: E1 chain (no Bayer/ISP/JPEG) | reduced | none | none | **....... perfect** |

So the flip is NOT the screenshot, NOT the snip, NOT registration: it is the ORACLE decode
failing at char 7 under Bayer+demosaic+ISP+JPEG — the design-02 §2 prediction landing
exactly ("pixel-domain Gaussian is provably wrong after compression"). Mechanism: the model
scores y against JPEG(clean mean) with additive Gaussian noise, but the chain is nonlinear —
JPEG(mean + noise) ≠ JPEG(mean) + noise, demosaic correlates the noise, quantization
manufactures/deletes evidence below bin width. The residual around truth is structured, and
at 7 px a neighbor hypothesis (B, more ink) systematically beats truth (R). At 8 px the same
chain decodes 7/7 — the failure has a scale threshold, as E3 was designed to measure.
Registration precision is exonerated (E fails with no registration; G succeeds at the same
7 px). Corollary confirmed at the same time: noise model (a) is fine as long as noise enters
LAST (E1/G) — consistent with the E2 resample-variance caveat from the design-02 accuracy
audit (variance must be pushed through any linear stage after noise; nonlinear stages break
Gaussianity outright).

Consequences: (1) the codec-aware DCT likelihood (§2b) is promoted from "planned comparison"
to "needed for any full-chain decode below ~8 px" — E3 should be built next in earnest, with
the demosaic correlation term in scope; (2) multi-frame fusion does NOT rescue a misspecified
likelihood — scores add, so bias adds too: more frames = exponentially more confident in the
same wrong answer; fix the per-frame likelihood before fusing (answers Andrew's "5 images
help exponentially" hope: yes for independent frames under a correct model — copies of one
frame are ρ=1/N_eff=1 and add nothing; under a wrong model more frames make it worse);
(3) tight hand-snips additionally break registration (template can't overhang the reference
edge → scale forced low → garbage) — fix by padding the reference before matching (TODO,
instrumentation).

Side observation (Andrew, curiosity poke — real data stays deferred): reference-decoding the
real HR photo (RHB6I06/real_HR.png) fails outright BUT with visibly low confidence — "at
least it knows it's bad." Recorded as an observation only: a weak posterior on an unmodeled
input is the §6 "flat = insufficient information" behavior, but honesty under misspecification
is NOT yet a claimable property (the same day produced confidently-wrong cases at 7 px).
Decision: no real-data chasing until the ladder reaches it; development continues in order.

---

## 2026-07-23 (later) — E2 built: variance correction verified, coupling measured, ICM decoding

BUILT (continuing the agreed ladder): (1) `ScoringModel.var_scale` — the audit fix made real:
post-noise linear stages transform the noise variance; for integer-factor area downscale k,
var_out = (a·ŷ+b)/k² with outputs independent, so the pixel likelihood stays EXACT at E2 with
var_scale = scale². Verified empirically in tests: measured residual-variance ratio ≈ 0.25 at
scale 0.5 vs the uncorrected model (would be a ~5× evidence overcount). rung_config now
returns a RungConfig dataclass carrying it; E3 keeps var_scale = 1 deliberately (no scalar
fixes a nonlinear chain — it is the control). (2) `decode_icm` promoted into slots.py
(iterated conditional decode, fixed-point early stop); reference.py now uses it. (3) Coupling
measured the right way after a wrong first attempt worth recording: comparing a slot's RAW
scores across reference strings is confounded (other cells' residuals differ by a constant
per candidate); the clean signal is the WITHIN-SLOT CENTERED table difference, which is
exactly zero without blur (disjoint support) and large with σ=2 px blur at 8 px chars — the
first direct measurement of design-02 §3's coupling term. (4) Instrumentation: registration
now replicate-pads the reference (default 25%) so a tight hand-snip whose crop cuts into the
backdrop margin still registers (template may overhang the snip edge; regression test locks
zoom recovery + exact decode on a tight crop); Save-view PNG now writes a settings-sidecar
JSON (overrides + tap) — a screenshot without its config can never be a controlled experiment
again. Tests: 59 green.

Next in queue (unchanged): E2 factorization-gap experiment (ICM/trellis-k vs exact enumeration
on reduced alphabets, coupling bandwidth vs blur/motion), then E3 in earnest = the §2b
DCT-domain codec-aware likelihood (design pass first — core math).

UX correctness fix after Andrew was misled by the decoder tab: the reference decode's "truth"
was silently taken from the plate_string SLIDER (render content), so decoding Generated.png
while the slider still said RMN6X08 displayed RMN6X08 as truth with green cells — reading as
"it guessed RMN6X08". Truth is now an explicit optional field on the Reference tab; blank =
unknown → no green/red grading, argmax outlined white, no Δ. Principle: ground truth about an
external image is an input the user asserts, never inferred from unrelated render state.
(Clarified in the same exchange: reference decode fits ONLY zoom/position/noise-floor;
pose/lighting/blur/char-height come from the sliders — §7 remains the missing fitting loop,
and registration/extraction is measurably the healthy part on this very image.)

---

## 2026-07-24 — The nuisance-cost asymmetry (measured) and the geometric-fit design proposal (G-ladder)

**Measurement that drives the design** (known channel, char 8, E1 chain, same observation):
exact channel Δ = +2,261 nats (truth wins, 7/7); the SAME image shifted ONE pixel Δ =
−102,674 (garbage decode); 5% gamma error Δ = +2,072 (still 7/7); shift+gamma ≈ shift.
Total character evidence ≈ 2.3k nats; one pixel of unmodeled geometry ≈ 100k nats of
structured error — 45× the entire string. Photometric error of similar "size" is ~free.
Consequences: (1) answers "the HR image is human-legible, why doesn't truth win?" — the
likelihood has no invariances; on a real photo EVERY hypothesis including truth sits ~100k
nats away and the argmax is decided by junk between equally-terrible fits, with high
posterior because posteriors are RELATIVE (softmax) — absolute misfit (σ̂, §6 chi-squared
self-audit) is the only "this is garbage" signal; (2) §7's geometric fit must be SUB-PIXEL
while photometrics can be fit loosely (scalar gain/offset first); (3) human "trivial reading"
= instinctive nuisance fitting before shape comparison — the eye also uses the characters to
align, which the decoder must NOT (registration stays string-independent by design).

**Proposal (pending Andrew's go): pull geometric fitting forward, ahead of E3.** G-ladder:
- G0 (built): coarse scale+translation via zero-mean NCC on a neutral-string template.
- G1: sub-pixel refinement, similarity → full HOMOGRAPHY (exact geometric family for a
  planar plate; relief/frame parallax negligible at this rung), ECC/Lucas-Kanade style
  gradient refinement initialized from G0, fitted on string-independent structure ONLY
  (character-cell rectangles masked out — slot geometry is known). Decode path: warp the
  observation once onto the render grid (resampling caveat carried, same as today's extract).
- G2 (true §7 entry): decompose the fitted homography into project-stage pose params
  (yaw/pitch/roll/char_height/offsets), then refine IN-MODEL by maximizing the
  neutral-string likelihood over pose + scalar photometric gain/offset (Nelder-Mead; each
  iterate re-renders). Candidates then decode with NO observation resampling, and pose
  uncertainty lives in the model's own parameterization (design-02 §5b frame scope).
- Validation rungs: synthetic pose perturbations (known yaw/pitch/roll, fit, measure
  sub-pixel accuracy + Δ recovery) → own screenshots (sidecar-controlled) → real_HR.png
  with truth RHB6I06 (the visceral target: decoder reads a legible photo because it fitted
  the pose itself) → Real.png (kill-test preview, §8.6).
Known risks, stated: ECC divergence on low-texture/JPEG-blocked inputs (G0 init + masks
mitigate); README-figure compression on real_HR is an unmodeled codec; character-masked
fitting leaves less texture at extreme LR (band/edges must suffice — the outside-colors bet,
now load-bearing). E3 (DCT likelihood) queued right after — G-ladder does not replace it.

**G1 BUILT and validated (2026-07-24, "let's test it!").** The milestone test passes: an
observation rendered at pose (yaw 6, pitch 3, roll 4), snipped through a non-integer 4.3×
nearest zoom, decoded by a POSE-BLIND model (sliders say zero pose) — 7/7 with Δ > 0
(test_geometry_g1). All previous scenarios stay green (62 tests). The build surfaced three
design-level findings, each measured, that reshaped the implementation:

1. **Never resample the observation — render into its frame instead.** Even with the
   EXACTLY-TRUE warp, perspective-resampling the observation onto the model grid flips
   characters at small char heights: pixel sampling is not a homography of the sampled
   image (posed-camera pixel footprints ≠ warped pose-0 footprints; codec blocks live in
   the posed frame). Implemented as `project.grid_warp/grid_shape` (hidden ParamSpecs): the
   fitted residual homography composes INTO the renderer at supersampled resolution, and
   the observation is only ever integer-cropped + area-downscaled. This is G2's principle
   arriving early, forced by measurement.
2. **The frame origin is part of the channel.** Rendering candidates on a grid spanning the
   whole snip (origin shifted vs the template frame) misaligned Bayer phase and JPEG block
   grids and flipped slots; the scoring grid must coincide with the template frame.
3. **ECC on blocky screenshot content wanders in a flat basin** — rho 0.98 with px-scale
   spurious anisotropy/perspective; harmless to extraction, poison to the render path. No
   string-independent geometric or residual statistic separates basin-wander from real pose
   (tried and measured: corner deviation, interior displacement, robust-median b,
   structure/flat RMS ratio — all fail). Resolution: ONE observation (G0 NCC-peak crop),
   TWO candidate channel models (plain, and ECC-residual grid-rendered), decode under both,
   select by POSTERIOR PREDICTIVE CORRELATION between final prediction and observation
   (dimensionless → per-path smoothing biases cancel; truth never consulted). ~2× decode
   cost, no thresholds.

**real_HR.png (the milestone target): fails UPSTREAM of G1 — coarse registration never
locks** (NCC 0.35, template partially off-image, σ̂ 0.59 ≈ scoring noise vs noise; the GUI's
unreliable-registration warning fires correctly). The neutral-template NCC does not survive
real-photo appearance: dark red car surround vs gray backdrop, white plate FRAME absent from
the render, real lighting. So the frontier moved from "decode given geometry" (now works,
synthetically, pose-blind) to "coarse localization under real photometrics" — exactly
Andrew's outside-colors observation as an algorithm: find the blue band + white field by
COLOR STRUCTURE, not template correlation; plus a photometric gain/offset fit before/within
registration (G2's other half). Next session: color-cue G0 for real images, then re-run
real_HR.

**G2 BUILT — in-model nuisance search (Andrew's directive: "everything is searching and
matching through the model's parameters. It was designed to be a camera taking a photo at a
simulator").** `lrlpr/decode/fit.py`: color-structure init (blue band + white field located by
color statistics — the outside-colors bootstrap, robust where template NCC failed) → coarse
pose grid, every hypothesis RENDERED and slid via gain/offset-invariant NCC → Nelder-Mead over
(char_height, yaw, pitch, roll, sub-pixel phase tx/ty via the project grid warp) with the
photometric gain/offset solved analytically per render on the character-masked region (mask
from the render's own homography — slot geometry, not glyphs) → existing slot decoder. ECC and
all image-space geometry surrogates are OFF the primary path (reference.py retained as the
screenshot-rung instrument). Results: the G1 milestone scenario (posed 6/3/4, display-zoomed
4.3×, pose-blind model) decodes 7/7 with Δ=+464 THROUGH PURE PARAMETER SEARCH — pose recovered
(yaw 5.2, roll 3.8), display zoom correctly absorbed into char_height (42.4 ≈ 10·4.3, "camera
closer") — ~300 renders, 13 s (test_fit_g2 pins it; 63 tests green). **real_HR.png: first
partial real-photo read — TKR6I06, right four slots (6I06) correct**, sane localization,
gain 0.55/offset −0.08 fitted. The remaining failure is the three LEFT slots, systematic —
per the "simulator needs improvement" principle this residual now indicts a specific missing
nuisance dimension (left-side lighting/shading gradient or the white plate frame, both absent
from the render), not the machinery. Bug worth recording: scipy Nelder-Mead's default initial
simplex uses 5%-of-value steps → ZERO-initialized dims (yaw/pitch/tx/ty) got 0.00025 steps and
were never explored (symptom: fit pinned at yaw=pitch=0, left-half slots flipping from
uncorrected foreshortening); fixed with an explicit initial simplex.

**GPU go-decision (Andrew, 2026-07-24) + profile.** Design-03's position stands (speed not
quality; CPU stays the gold standard). Measured before porting: pose-eval was 21 ms of which
~14 ms was motion_rs running its 16-sample blur AT SPEED 0 — now a true no-op (identity,
byte-exact; pose-eval 6.7 ms, fit 6.3→2.0 s). String-eval 63 ms (glyph raster + shading
dominate), decode ~16 s. Hardware: RTX 4070 Ti SUPER 16 GB; torch 2.11 cu128 added as `gpu`
dependency group. Microbenchmark (batched grid_sample+avg_pool+eltwise vs cv2 loop, B=256):
warm GPU 8× on the kernel, CPU↔GPU max diff 1.7e-5 — far under the 8-bit floor, confirming
"same math". The REAL win needs the whole hypothesis loop batched (B,C,H,W tensors end-to-end)
so per-stage Python overhead amortizes: target decode 16 s → <0.5 s and sweep throughput for
E2/E3/bound Monte Carlo. Port plan: batch surface via per-slot glyph sprites (= compositional
rendering, design-01 impl req 2 — same restructuring the trellis tables need, do together);
shading/ISP elementwise; project = batched grid_sample; sensor = avg_pool + mosaic mask;
demosaic = conv; JPEG stays REAL libjpeg on CPU at the batch boundary (design-03 §3 —
artifacts ARE the noise model); standing CI test asserts GPU matches CPU reference within
tolerance per stage. CPU baseline should be committed before the port starts.

**Andrew's deliberate stress-tests, both failures root-caused same day:** (1) ~6-7 px snip
decoded 5/7 (A→D, 3→1) — third independent confirmation of the E3 codec-regime finding
(full chain + pixel Gaussian breaks below ~8 px); not the snip channel (forensics: nearest
non-integer 11.16× zoom, photometrics ~free). (2) 9 px rolled-plate snip decoded to TOTAL
garbage (HTR0B00) — qualitatively different signature (all slots wrong, no within-class
structure) = registration lock-on failure, and the cause was OUR OWN GUARDRAIL: min_cover=0.5
assumed the snip is mostly plate; his roomy snip (render = 38% of capture, true zoom 5.73×)
had the true zoom FORBIDDEN → forced 13.5× at ncc 0.27 → scored the wrong pixels. Fix:
min_cover 0.2 (permissive; zero-mean NCC does the real discrimination) + GUI warns
"REGISTRATION UNRELIABLE" when ncc < 0.5 (the 0.27-vs-0.90 gap was the visible tell all
along). Verified: the exact stress scenario (char 9, roll 18°, FULL chain incl. JPEG,
non-integer 5.73× snip) now decodes 7/7 with Δ = +613 nats — 9 px is comfortably inside the
working envelope; the codec regime (~≤7 px) remains the real boundary until §2b. Failure
taxonomy now established for triage: within-class near-misses = likelihood misspecification;
all-slot garbage = registration; confidently-wrong with good ncc = channel/nuisance mismatch.
Tests 60 green (roomy-snip regression added).
