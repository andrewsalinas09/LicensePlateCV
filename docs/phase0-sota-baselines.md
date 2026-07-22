# Phase 0 — SOTA & Baseline Landscape (2026-07-22)

Compiled via deep web research. Condensed version in project memory (`lrlpr-sota-baselines`).

## ICPR 2026 LRLPR competition (arXiv:2604.22506)

- 269 teams registered, 99 valid entries; top-10 within 3.13 pp. Residual error 17.87% — far from solved.
- Metrics: exact-match track Recognition Rate; Confidence Gap (mean conf on correct − incorrect) as tiebreak.
  Official scoring script: raysonlaroca.github.io/supp/lrlpr26/

| Rank | Team | RR | Conf.Gap | Method |
|---|---|---|---|---|
| 1 | DLmath | 82.13% | 6.67% | teacher–student SR (HAT-FIR + MambaIRv2) + GP-LPR/Transformer OCR; **sum of logits over 5 LR frames before decoding**; 3-model logit-avg ensemble; external data (OpenALPR-BR, RodoSol, UFPR-ALPR) |
| 2 | AIO_JiangnamCoffee | 81.73% | 3.75% | STN + SE-ResNet + Transformer + CTC; CNN attention estimates per-frame quality, fuses 5 frames; 4-model ensemble; synthetic degradation of HR |
| 3 | OpenOCR (Fudan) | 80.17% | 2.38% | **no SR** — SVTRv2-AR direct STR; 4 models × 5 frames = 20 predictions, character-level majority voting |
| 4 | CAP2 | 80.10% | **14.86%** | MF-LPR²-style geometric preprocessing + U-Net text masks; dual-stream (ConvNeXtV2/DINOv2+DETR-lite; MAERec-B); position-wise character ensemble (Optuna-tuned); no external data |
| 5 | UIT-MeoBeo | 79.83% | 5.93% | PE-Core-L frame encoder + temporal Transformer; **fixed 7-slot decoding with position-wise letter/digit + layout masks**; quality-weighted fusion |

No team released code. #3 is reproducible from public components (Topdu/OpenOCR, Apache-2.0).

Strategic reading:
- Winner's logit summation across frames = crude version of our log-likelihood fusion.
- 5th place's fixed-slot layout-masked decoding = crude version of our trellis constraints.
- Nobody combined these with an explicit camera forward model. **No analysis-by-synthesis /
  likelihood-decoding LPR work found anywhere in 2025–26** — the niche is still open.
- **No post-competition result beats 82.13%** as of 2026-07-22 (only one unrelated citing paper).
- Confidence Gap is explicitly named an open problem (winner only 6.67%; best 14.86%) —
  calibrated likelihoods are our natural differentiator.

## Published methods with code (2023–26)

| Method | Venue | Result | Code |
|---|---|---|---|
| GP_LPR (Liu et al.) | MMM 2024 | OCR used by winner + Laroca SR benchmarks | github.com/MMM2024/GP_LPR (sparse docs) |
| Nascimento LPSR line | SIBGRAPI'24, JBCS'25 | UFPR-SR-Plates: LR 1.7–2.2% → 1 SR frame 29.9% → 5 frames + MVCP 42.3–44.7% | valfride/lpsr-lacd, lpr-rsr-ext |
| MF-LPR² (Na et al.) | CVIU 2025 | 86.44% on private RLPR (dashcam) | **no code** |
| LP-Diff (Gong et al.) | CVPR 2025 | multi-frame diffusion restoration; MDLP dataset (11k groups) | haoyGONG/LP-Diff |
| LP-LLM (Gong & Liu) | arXiv 2601.09116 | Qwen3-VL+LoRA, 89.4% on own Real-Blur-LP | **no code** |
| Moussa compression-informed transformer | ICIP 2022 | +8.9pp at severe degradation | d-moussa/forensic-license-plate-transformer (pretrained) |
| Schirrmacher probabilistic LPR | T-ITS 2023 | uncertainty flags wrong predictions | franziska-schirrmacher/LPR-uncertainty (TF) |
| CharDiff-LP | arXiv 2510.17330 | char-guided diffusion, −28.3% rel. CER | no code |

Negative data point (supports our thesis): WINK 2026 engineering note — SR pre-filters
(Real-ESRGAN etc.) gave 0.0% exact match on <100px crops; SR hallucinates characters;
LR-native training + multi-crop voting wins.

## STR models transferable to plates

- PARSeq (ECCV'22): 23.8M params, torch.hub one-liner, Apache-2.0; ships ABINet/TRBA/CRNN too.
- SVTRv2 (ICCV'25): ~20M, in Topdu/OpenOCR — competition #3 backbone.
- MAERec (ICCV'23, Union14M): strong on low-quality text.
- CLIP4STR: SOTA on 13 STR benchmarks; B fine-tunes on 24GB.

All feasible on a single RTX-class GPU except full DLmath ensemble reproduction (multi-week).

## Chosen comparison baselines (ranked)

1. **SVTRv2 via OpenOCR** — competition-grade (80.17% recipe), fully open, ~20M params.
2. **GP_LPR + SR + MVCP** (Laroca-group pipeline; winner's OCR component) — the
   restoration-then-recognition strawman, reproducible against UFPR-SR-Plates published numbers.
3. **PARSeq fine-tuned + per-frame logit summation** — AR model gives exact sequence
   log-probs; natural discriminative counterpart for likelihood-fusion ablations.

Honorable mentions: LP-Diff (open-code generative-restoration competitor),
Moussa transformer (forensic side-information baseline). MF-LPR² and LP-LLM:
reported-number comparisons only (no code, private benchmarks).
