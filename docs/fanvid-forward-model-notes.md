# FANVID Forward-Model & Decoder Design Notes (2026-07-22)

Triggered by user observation: FANVID "LR" is not optical low resolution — it is digitally
manufactured, and scrolling the clips shows a *waving* pattern in the plate text.

## 1. The degradation operator is exactly known

FANVID LR frames are produced by the authors' own script (we have it,
`data/FANVID_repo/assets/download_script_lp.py`):

```
source YouTube video frame
  → cv2.resize(frame, (1280, 720), INTER_CUBIC)     # HR
  → cv2.resize(HR,    (320, 180),  INTER_CUBIC)     # LR  (some clips 270-wide)
```

That's the whole "camera" for the LR set: deterministic bicubic decimation, byte-exact
reproducible with OpenCV. Consequences:

- For analysis-by-synthesis on FANVID, the *digital tail* of the forward model needs zero
  estimation — no PSF fitting for the resize stage, no sensor noise model. We apply the literal
  same `cv2.resize` calls to rendered hypotheses.
- All remaining unknowns live upstream, in the HR/source image: original camera optics + motion
  blur, exposure, and **YouTube H.264/VP9 compression at source resolution** (block artifacts,
  in-loop deblocking, quantization — the dominant noise process).
- 4:1 (or larger) decimation is aggressive: bicubic folds above-Nyquist glyph energy into the LR
  band as **aliasing**, it does not destroy it. Aliased energy is signal to a decoder that models
  the operator, and noise to everyone else.

## 2. The "waving" text = sub-pixel phase diversity (it is the information)

As the plate translates by fractions of an LR pixel between frames, the bicubic sampling grid
hits the glyphs at a different phase; the folded (aliased) low-frequency pattern reorganizes.
Visually: text appears to undulate. Confirmed on MH02BQ8778 clip 0 (279 frames, plate ~20×7 px,
~2 px/char): consecutive crops show the same blob rearranging its internal pixel pattern.

This is exactly the dither/drizzle mechanism from memo §4.5: each frame is a *different linear
projection of the same above-Nyquist content*. A hypothesis decoder exploits it by rendering the
candidate plate, applying the **per-frame sub-pixel homography**, then the exact decimation, and
scoring — frames with different phases then discriminate hypotheses that any single frame cannot.

Corollary: **per-frame sub-pixel registration becomes the critical nuisance parameter** for
FANVID. Registration enters the EM loop (memo §4.3) as a per-frame continuous nuisance g_i;
errors degrade gracefully (a misregistered frame contributes a flat likelihood, not corruption).

## 3. Decoder implication: never decide per frame (user's point, sharpened)

At ~2 px/char the single-frame posterior over the plate space is nearly flat — a per-frame
"best match" list would contain an enormous number of near-ties, and voting over per-frame
argmaxes collapses. This does not threaten the architecture, because the trellis decoder never
enumerates per-frame candidates:

- Per frame i and character slot j we compute a small **likelihood table** φ_ij(c) (|A| entries,
  plus pairwise terms) by scoring glyph renders through the frame's forward model.
- Multi-frame fusion = **elementwise addition of log-tables across frames** (memo §4.5),
  Σᵢ φ_ij(c). No decisions, no candidate lists, no combinatorics in the frame dimension.
- One Viterbi/forward-backward pass on the *fused* trellis at the end.

Cost is linear in frames; 279-frame clips are fine. Weak evidence (fractions of a bit per
character per frame) accumulates — Chernoff scaling says LLR grows ~linearly in effective
frame count. This handles both regimes the user named (few frames × high info, many frames ×
low info) with the same machinery: the tables just get their mass from different places.

## 4. Caveats specific to FANVID

- **Frames are not independent.** All frames come from one YouTube encode; inter-frame
  prediction correlates compression artifacts across frames (memo §11 Q5). The effective number
  of independent frames is < N. Mitigations: estimate temporal correlation of residuals and
  down-weight the log-likelihood sum (effective-N correction), or whiten in the residual domain.
  Must quantify before trusting Chernoff-style confidence out of 279 "frames".
- **Fonts/layout are NOT government-uniform** (Indian plates: HSRP vs painted variants, varying
  spacing, some two-line). The "known renderer" assumption weakens to a *font-family
  marginalization* — render under a small set of plausible Indian plate fonts and marginalize.
  FANVID is the messy-font stress test; Mercosur stays the clean physics story.
- **Annotation boxes are loose** (crops include background/other signage); plate localization +
  homography estimation is part of the FANVID-specific nuisance stack.
- Our rebuilt LR should match the authors' byte-for-byte *only if* YouTube serves the same
  encode; format selection differences could produce small deltas. If we ever compare against
  their published baseline numbers, verify checksums on a few clips or regenerate consistently.

## 5. Open design question (flagged, not solved)

How to schedule EM over (string s, per-frame registrations {g_i}, photometrics) when per-frame
evidence is this weak: registration needs a decent current hypothesis, and the hypothesis needs
registration. Likely answer: bootstrap registration from the *plate border/blob* (structure
independent of the string, memo §4.3), coarse-to-fine over frame subsets, anneal. Needs
experiments in Phase 3.
