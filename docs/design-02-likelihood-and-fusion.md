# Design 02 — Likelihood, Evidence Accumulation, and Multi-Frame Fusion

**Status: DRAFT for discussion — nothing implemented. This is the mathematical heart ("the
magic", per discussion 2026-07-22): how evidence about the string accumulates in hypothesis
space without any reconstruction step.**

## 1. Single-frame likelihood — what "scoring a hypothesis" means

For hypothesis `s`, frame `y`, nuisances (θ = channel params, g = geometry): the forward model
(design-01) produces a **predicted mean image** ŷ(s, θ, g) and a **noise distribution** around
it. The score is

    L(s) = log p(y | s, θ, g)

"How surprising are these exact observed pixels if the truth were s." The predicted image is
scaffolding — never compared by eye, never thresholded, never reconstructed from. Only the
scalar log-probability leaves the frame.

## 2. The noise model (what p(y | ŷ) actually is)

Baseline and refinement, both to be implemented, compared by experiment:

- **(a) Heteroscedastic Gaussian, pixel domain** (baseline): residual r = y − ŷ,
  `log p = −½ Σᵢ [ rᵢ²/σᵢ² + log 2πσᵢ² ]` with σᵢ² = a·ŷᵢ + b + σ_q² (shot + read +
  quantization floor). Simple, fast, provably wrong after compression — kept as the control.
- **(b) Codec-aware, DCT domain** (for JPEG/intra frames): the decoder knows each DCT
  coefficient was quantized with step Δₖ (from the file header). Observed coefficient cₖ means
  the pre-quantization value was in the bin [cₖ−Δₖ/2, cₖ+Δₖ/2). With the forward model
  predicting pre-codec coefficient mean μₖ and variance σₖ²:

      log p(y|s) = Σₖ log [ Φ((cₖ+Δₖ/2 − μₖ)/σₖ) − Φ((cₖ−Δₖ/2 − μₖ)/σₖ) ]

  Key property: a residual smaller than the quantization bin contributes ~zero evidence —
  pixel-domain Gaussian scoring gets exactly this wrong (it manufactures evidence from
  quantization noise). Degenerates to (a) when Δ→0. This is the principled version of
  "compression-informed" (cf. Moussa et al.).
- **Spatial correlation**: demosaic and deblocking correlate neighboring residuals → model
  residual covariance (PROVISIONAL: stationary AR/block structure estimated from real
  residuals; whitening transform before scoring). Ignoring it overcounts evidence within a
  frame, same disease as frame correlation, smaller dose.

## 3. Accumulation in hypothesis space (the 1-pixel × 1M-frames principle)

Agreed intuition (user, 2026-07-22): one pixel per frame × enough frames = perfect recovery,
with no image ever formed. Mechanism:

- Per frame, the expected score gap between truth s* and any competitor s′ is
  `E[L(s*) − L(s′)] = KL( p(y|s*) ‖ p(y|s′) ) ≥ 0` — possibly a millibit per frame.
- Scores ADD across (conditionally independent) frames ⇒ the gap grows ~linearly in frame
  count while fluctuations grow ~√N ⇒ posterior concentrates on s*; error probability decays
  exponentially with rate = the Chernoff information (the standard bound).
- Nothing per-frame is ever decided. Per-frame argmax/voting throws away the millibit
  contributions, which are ALL the information in the low-SNR regime. This is the formal
  version of "the reconstruction can't be best-match-per-frame-then-combine."

Practical form: per frame we don't score 10⁸ strings; we compute per-slot **log-likelihood
tables** φ_j(c) (36 entries per slot) + pairwise ψ_j(c,c′) via compositional rendering
(design-01 impl. req. 2). Fusion = elementwise summation of tables across frames. One
Viterbi/forward-backward on the fused trellis at the end. Coupling order k is a TUNABLE
decoder parameter (k=1 pairwise … k=∞ exact enumeration); accuracy-vs-k IS the measured
factorization gap (memo §4.2).

## 4. Noise correlation across frames — the ρ knob (agreed 2026-07-22)

Frames from one video encode (inter prediction), shared fixed-pattern noise, persistent
atmospheric shimmer ⇒ frame noises are NOT independent. Model, not patch:

- Joint likelihood over the track with cross-frame residual covariance. Simplest structure:
  equicorrelation ρ ∈ [0,1] between frames ⇒ information of N frames equals

      N_eff = N / (1 + (N−1)·ρ)

  independent frames (ρ=0 → N; ρ=1 → 1: the 151-identical-frames clip). Chernoff decay runs
  on N_eff. Emerges from GLS/whitening of the joint covariance, not bolted on.
- ρ is ESTIMABLE: correlation of residuals across frames after fitting the current hypothesis;
  or structured from the GOP (I-frames ~independent; P/B correlated with references).
  PROVISIONAL: equicorrelation vs AR(1)-in-time vs GOP-structured — start equicorrelated,
  upgrade if residual diagnostics demand.
- **Correlation you can model is partially recoverable**: perfectly correlated noise of known
  structure cancels (frame differences are noise-free; fixed-pattern noise is estimable and
  removable exactly BECAUSE ρ=1). Unmodeled correlation = pure evidence overcounting ⇒
  overconfident garbage. Hence: measure ρ, never assume 0.

## 5. Condition correlation (nuisances) — the sun question (agreed 2026-07-22)

Distinct from §4 and behaves oppositely. Per nuisance, declare temporal sharing:

| Nuisance | Sharing within a track |
|---|---|
| Illumination (sun) | SHARED (static over ~1 s) |
| Codec state, camera ISP, PSF magnitude | SHARED / slowly varying |
| Velocity | Slowly varying (smooth kinematics) |
| Registration / sub-pixel phase | PER-FRAME (this is the waving) |
| Motion-blur direction | PER-FRAME (follows velocity) |

Two opposing effects:
- **Pooling gain**: shared nuisances are estimated once from all N frames — the nuisance tax
  (posterior width spent on calibration) is paid once, split N ways.
- **Diversity insurance**: varying conditions provide different projections of the plate.
  A single fixed condition can have ALIASING COLLISIONS — hypothesis pairs (E vs F) whose
  predictions coincide under that exact phase/lighting; no amount of noise averaging breaks
  the tie, only a different condition does. Diversity bounds the asymptote of what is
  identifiable; noise independence (§4) bounds the rate. (Limit case: sun sweeping across
  frames = photometric stereo on the relief.)
- Nature's split in a 1-s track is favorable: expensive-to-estimate photometrics stay fixed
  (pool them); the diversity-generating condition (sub-pixel geometry) is the one that varies.
- Degenerate case, now formalized: static plate + single encode = no phase diversity AND high
  ρ — both knobs at their worst (the "garbage" FANVID clips).

## 5b. Nuisance hierarchy — scopes (extension, discussed 2026-07-22)

§5's shared/per-frame split generalizes to a declared SCOPE per nuisance:

| Scope | Examples | Constrained by | Treatment |
|---|---|---|---|
| Camera-fixed | intrinsics, base optical MTF, noise a/b, ISP, codec config, Bayer phase | every frame the camera produced (incl. plate-free footage; slanted edges anywhere measure the lens) | calibrate once → plug-in point estimate (residual uncertainty sub-threshold by the §4.4 criterion) |
| Track | illumination, distance regime (→ defocus), speed magnitude, WB state | the track's N frames | marginalize (small grid / Laplace) or EM-estimate with uncertainty propagated |
| Frame | pose/sub-pixel phase, motion direction, codec block phase | one frame + hierarchical priors (kinematic smoothness ties frames) | the EM loop's real search space |
| Realization | the noise draw | never estimated | integrated analytically (structured ρ→1 components excepted, §4) |

Worked example (the question that prompted this): "the PSF" is not one nuisance —
base MTF is CAMERA-FIXED (slanted-edge calibratable, once), defocus is TRACK-derived
(function of distance, which geometry estimates anyway, plus one camera-fixed focus
setting), motion blur is FRAME-level in direction but kinematically smooth in magnitude.
A naively-free per-frame 2D kernel collapses into: a calibrated constant ⊗ a derived
quantity ⊗ a smoothness-tied sequence. Scope decomposition is the general de-fanging
move for high-dimensional nuisances.

Consequences: (1) **HR frames calibrate the camera for LR decoding** — same camera, so
camera-fixed parameters fitted on sharp HR transfer directly into the LR likelihood
(the paired datasets are calibration channels, not just SR training data); (2) with an
unknown camera (single wild image) the camera level has no pooling and everything
degrades gracefully to per-image marginalization with honestly wider posteriors.
Deferred refinements: field-dependent PSF (camera-fixed function of image position);
slow drift of "fixed" parameters (temporal prior if residual diagnostics demand).

## 6. Confidence, calibration, self-audit

- Posterior over strings from forward-backward on the fused trellis (marginals, top-k).
- Precision about metrics: the ICPR "Confidence Gap" (E[conf|correct] − E[conf|incorrect]) is
  NOT calibration — it doesn't test whether confidence-q predictions are right q of the time.
  A Bayes posterior is exactly calibrated *only under its own generating model* (tautological
  on our synthetic data; guaranteed by construction). Whether calibration survives channel
  misspecification on real data is an OPEN question — the §7/memo-§5 failure mode
  (confidently wrong under mismatch) argues it may not. Claim nothing until measured.
- Flat posterior = proof of insufficient information (distinct from peaked-but-wrong).
- Cross-frame consistency test (memo §4.5): per-frame posteriors must scatter consistently
  with their widths (chi-squared); excess disagreement flags forward-model mismatch on the
  very track being decoded — runtime self-audit, no ground truth needed.
- All confidence claims must use N_eff, not N (§4) — otherwise calibration silently breaks
  exactly on correlated tracks.

## 7. Nuisance estimation schedule (OPEN — flagged, not solved)

EM with Viterbi/forward-backward E-step (memo §4.3). The weak-evidence bootstrap problem:
registration needs a hypothesis, the hypothesis needs registration. Current plan (to be
tested, Phase 3): initialize registration from string-independent structure (plate border,
blob centroid, track kinematics smoothness); coarse-to-fine over frame subsets; anneal the
noise scale. Failure mode to watch: EM locking onto a wrong string that "explains" the
registrations it induced (self-confirming). The §6 consistency test is the tripwire.

## 8. What gets measured before we trust any of this

1. Noise-model comparison (a) vs (b) on synthetic JPEG sweeps: calibration curves.
2. ρ estimation accuracy on synthetic correlated tracks; N_eff vs realized error rate.
3. Factorization gap vs k on reduced alphabets (exact enumeration as gold standard).
4. Chernoff scaling check: log(error) vs N_eff linear?
5. Collision census: which (character, phase, lighting) pairs actually collide at 2-5 px —
   informs how much diversity a track needs, feeds the ideal-observer bound story.
6. **Milestone kill-test (first thing to run on any real paired data):** per-track margin
   Δ = log p(y | s_true) − log p(y | s_best-wrong) under the fitted channel. If Δ is not
   reliably positive on real validation tracks, the channel model is not describing reality
   and the approach fails there — find out as early and cheaply as possible. (Paired LR/HR
   tracks, where available, double as channel-calibration data: registration, empirical blur,
   photometrics, residual covariance estimated from pairs instead of hand-guessed.)
