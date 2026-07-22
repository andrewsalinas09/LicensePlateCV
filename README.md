# LRLPR — Generative Trellis Decoding for Low-Resolution License Plate Recognition

Analysis-by-synthesis decoding of severely degraded license plates: render candidate
plate strings through a physical camera forward model (optics → sensor → ISP → codec),
score hypotheses by likelihood against the observed pixels, decode exactly via a
character-position trellis, and fuse video frames by log-likelihood summation.

Primary scientific goal: the **ideal-observer performance bound** for the task —
Bayes-optimal recognition rate as a function of degradation — and statistical-efficiency
analysis of existing recognizers against it.

See `generative-plate-decoding-research-memo.md` for the full research memo (v2).

## Setup

Requires [uv](https://docs.astral.sh/uv/).

```sh
uv sync
```

## Layout

- `src/lrlpr/` — library code (renderer, forward model, trellis decoder, fusion)
- `tests/` — pytest suite
- `docs/` — research notes and phase write-ups
- `data/` — datasets (gitignored; see docs for access instructions)
