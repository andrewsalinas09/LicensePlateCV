"""Run the decoder on an external reference image (first: the oracle screenshot).

Usage:
  uv run python tools/decode_reference.py ExampleLicensePlateGenerator/RHB6I06/Generated.png \
      --truth RHB6I06 [--char-heights 5,6,7,8,10,12,16] [--out composite.png]

The channel config is the full default pipeline (every stage at its ParamSpec
default — what the inspector renders when no slider has been touched), with
char_height_px swept: render scale is the one nuisance a screenshot certainly
does not preserve, so it is estimated by registration quality (best
TM_SQDIFF_NORMED across the sweep). Everything else stays at defaults until a
config-recording mechanism exists (screenshots made before that carry no
settings sidecar).
"""

from __future__ import annotations

import argparse
import os
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from lrlpr.camera import build_full_pipeline  # noqa: E402
from lrlpr.decode import ScoringModel  # noqa: E402
from lrlpr.decode.reference import decode_reference, register, srgb_inverse  # noqa: E402
from lrlpr.plate_spec import SPECS  # noqa: E402

FONT = os.path.join(os.path.dirname(__file__), "..", "data", "fonts",
                    "GL-Nummernschild-Eng.ttf")
NEUTRAL = "XXX0X00"  # valid LLLDLDD string; carries no information about the answer


def load_linear(path: str) -> np.ndarray:
    bgr = cv2.imread(path, cv2.IMREAD_COLOR)
    if bgr is None:
        raise SystemExit(f"cannot read image: {path}")
    return srgb_inverse(bgr[..., ::-1].astype(np.float64) / 255.0)


def model_for(pipeline, char_height: float, spec_name: str) -> ScoringModel:
    ov = {
        "surface": {"font_path": os.path.abspath(FONT), "spec": spec_name},
        "project": {"char_height_px": char_height},
    }
    return ScoringModel(pipeline, ov, frozenset(), a=0.0, b=0.0)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("image")
    ap.add_argument("--truth", default=None, help="known plate string, for scoring the decode")
    ap.add_argument("--spec", default="mercosur_br_car")
    ap.add_argument("--char-heights", default="5,6,7,8,10,12,16,20",
                    help="native render scales (px) to try; best registration wins")
    ap.add_argument("--out", default=None, help="save pred|obs|residual composite PNG here")
    args = ap.parse_args()

    spec = SPECS[args.spec]
    ref = load_linear(args.image)
    pipeline = build_full_pipeline()

    print(f"reference {args.image}: {ref.shape[1]}x{ref.shape[0]} px")
    candidates = []
    for ch in (float(s) for s in args.char_heights.split(",")):
        m = model_for(pipeline, ch, args.spec)
        pred = m.predict(NEUTRAL)
        try:
            reg = register(ref, pred)
        except ValueError as e:
            print(f"  char_height {ch:5.1f}: skipped ({e})")
            continue
        candidates.append((reg.score, ch, m, reg))
        print(f"  char_height {ch:5.1f}: pred {pred.shape[1]}x{pred.shape[0]}, "
              f"zoom {reg.scale:5.2f}, ncc {reg.score:.4f}")
    if not candidates:
        raise SystemExit("no candidate registered")

    _, char_height, model, _ = max(candidates, key=lambda c: c[0])
    print(f"\nbest config: char_height_px = {char_height} (native render scale)")

    result = decode_reference(model, spec, ref, NEUTRAL, truth=args.truth)
    reg = result.registration
    print(f"registration: zoom {reg.scale:.3f}, offset ({reg.x}, {reg.y}), "
          f"ncc {reg.score:.4f}")
    print(f"noise floor b_hat = {result.b_hat:.6f} (sigma {np.sqrt(result.b_hat):.4f})")
    print(f"\ndecoded: {result.decoded}" + (f"   truth: {result.truth}" if result.truth else ""))
    if result.truth:
        ok = result.decoded == result.truth
        print(f"result: {'CORRECT' if ok else 'WRONG'}   "
              f"delta = {result.delta_nats:+.2f} nats (L(truth) - L(best wrong))")
    print("\nslot  argmax  truth  posterior  margin(nats)")
    for j, t in enumerate(result.tables):
        tr = result.truth[j] if result.truth else "-"
        mark = " " if (not result.truth or t.argmax() == tr) else " <-- WRONG"
        print(f"  {j}     {t.argmax()}       {tr}      {t.top1_posterior():6.3f}   "
              f"{t.margin():10.2f}{mark}")

    if args.out:
        pred = (result.scoring or model).predict(result.decoded)
        obs = result.observation
        resid = np.abs(obs - pred)
        resid_vis = np.clip(resid / max(resid.max(), 1e-9), 0, 1)
        strip = np.concatenate(
            [np.clip(pred, 0, 1), np.clip(obs, 0, 1), resid_vis], axis=1)
        out8 = (np.clip(strip, 0, 1) ** (1 / 2.2) * 255).astype(np.uint8)
        cv2.imwrite(args.out, out8[..., ::-1])
        print(f"\ncomposite (pred | observation | residual): {args.out}")


if __name__ == "__main__":
    main()
