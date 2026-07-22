# Phase 0 — Dataset Landscape (2026-07-22)

Compiled via deep web research. Condensed decision-relevant version in project memory
(`lrlpr-datasets`); this file is the full reference.

## 1. LRLPR-26 (primary benchmark)

- Paper: arXiv:2604.22506 · Site: icpr26lrlpr.github.io · Codabench 12259 ·
  Repo: github.com/raysonlaroca/lrlpr-26-dataset
- Competition concluded March 2026; dataset **now released post-competition** via
  email license agreement. Must be requested **from a university email account**
  (.edu/.ac etc.) to rayson@ppgia.pucpr.br (Rayson Laroca, PUCPR). ~5 business days.
  Non-commercial academic use; no manual annotation of the test set.
- Training: 20,000 tracks × (5 LR + 5 HR) = 200,000 images.
  - Scenario A (10k tracks): from UFPR-SR-Plates, daylight; full annotations (text, layout, corners).
  - Scenario B (10k tracks): new captures incl. rain/night; text + layout only.
- Test: 3,000 tracks × 5 LR = 15,000 images (600 Brazilian AAA-9999, 2,400 Mercosur AAA9A99);
  text + layout GT included in post-competition release; no HR, no corners.
- Source: 1920×1080 rolling-shutter camera, Curitiba, Brazil.
- Metric: exact-match track recognition rate; tiebreak = Confidence Gap.
- Leaderboard: blind phase closed; whether the public-test phase still scores
  post-hoc submissions is unconfirmed — ask icpr26lrlpr@gmail.com.
- Top-5 (of 99 valid submissions):
  1. DLmath (Korea Univ.) — 82.13% — teacher–student SR (HATFIR, MambaIRv2) + OCR
  2. AIO_JiangnamCoffee — 81.73% — STN → SE-ResNet → Transformer → CTC
  3. OpenOCR (Fudan) — 80.17% — direct OCR (SVTRv2-AR) + character-level voting, **no SR**
  4. CAP2 — 80.10% — MF-LPR² preprocessing, dual-stream, position-wise ensemble
  5. UIT-MeoBeo — 79.83% — multi-frame ViT, layout-aware decoding, quality-weighted fusion

## 2. FANVID (fully open, start immediately)

- arXiv:2506.07304 · huggingface.co/datasets/kv1388/FANVID (ungated)
- Ships annotation CSVs + scripts that download source videos from YouTube —
  **run extraction soon before sources rot**.
- License ambiguity: HF card says CC BY 4.0, paper says CC-BY-NC — treat as NC until clarified.
- ~1,203 LR clips at 320×180, 20–60 FPS. LP track: 360 unique plates (mostly US),
  ~47.8k train + ~18.3k test annotated frames; plate text GT in CSVs.
  LR is downsampled so single frames are indecipherable (temporal-integration premise).
- Baseline: TextRecBox 0.42 (RCDM SR + EasyOCR), 0.15 without SR. Weak → big headroom.

## 3. Brazilian family (all: signed agreement from university email, academic-only)

| Dataset | Size | Notes | Contact |
|---|---|---|---|
| UFPR-ALPR | 4,500 imgs = 150 tracks × 30 frames, 1080p | video-derived, full char boxes | rblsantos@inf.ufpr.br |
| RodoSol-ALPR | 20,000 single imgs, 720p | 4 classes: car/moto × BR/Mercosur; corners | first author |
| RodoSol-SR | LR/HR crops, LR 48×16, synthetic degradation to SSIM<0.1 | code: github.com/valfride/lpsr-lacd | rblsantos@inf.ufpr.br |
| UFPR-SR-Plates | 10,000 tracks × (5 LR + 5 HR) = 100k imgs, **real pairs** | ancestor of LRLPR-26 Scenario A; arXiv:2505.06393; SR lifts single-frame recognition 2.2%→29.9% | menotti@inf.ufpr.br |
| LPLC/v2 | 12,687 plates, 4 legibility classes + occlusion | arXiv:2508.18425, 2604.08741; good "illegible" triage set | lmlwojcik@inf.ufpr.br |

Efficient path: request LRLPR-26 + UFPR-SR-Plates + RodoSol + UFPR-ALPR together —
same PUCPR/UFPR research circle.

## 4. Chinese datasets

- **CCPD** (github.com/detectRecog/CCPD): open download, ~300k imgs 720×1160 CCPD2019 +
  CCPD2020 green plates. Annotations in filenames. No true LR/HR pairs; -challenge/-fn
  subsets have blur/distance. LPSRGAN (Neurocomputing 2024) defines a reusable n-stage
  random-combination degradation recipe over CCPD.
- CLPD: 1,200 test-only imgs, BaiduYun-only download (friction). PKUData: detection
  boxes only, no text — skip.

## 5. Rendering resources (Phase 1 inputs)

- **Mercosur/Brazilian post-2018 font = FE-Schrift (FE-Engschrift)** — free TTFs
  (fontasy.de, FontSpace). Layout AAA9A99, white bg, blue band.
- Pre-2018 Brazilian gray plates: "Mandatory" font (Keith Bates) is the usual digital
  stand-in — **verify glyphs against UFPR-ALPR crops before trusting**.
- US: per-state fonts; canonical catalog = Leeward Productions specimen series;
  California ≈ Penitentiary Gothic; many states = Zurich Extra Condensed (3M system).
- Generator repos: vinihcampos/plates-generator (Mercosur), fernandorovai/BRLicensePlateGen,
  niklaswa/license-plate-generator (EU/DE), ebadi/LicensePlateGenerator, etc.
- Ready-made synthetic Mercosur dataset: Mendeley Data nx9xbs4rgx/2 (open).

## Action items

1. Now (open): FANVID pull + CCPD download + FE-Schrift TTF + Mendeley synthetic Mercosur.
2. Email requests (need university address — user's is gmail, needs resolving):
   LRLPR-26, UFPR-SR-Plates, RodoSol(-SR), UFPR-ALPR.
3. Confirm with icpr26lrlpr@gmail.com whether public-test Codabench phase still scores submissions.
