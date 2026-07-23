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
