"""Per-slot hypothesis tables with the format prior (design-02 §3).

For slot j we score only the LEGAL characters (letters or digits per the layout
spec — the non-adversarial format prior, the ARK5I56 lesson): cross-class
confusions (1/I, 0/O, 5/S…) are removed by construction; only within-class
ambiguity survives.

A slot table is the CONDITIONAL score of varying character j while the other
slots hold a reference string. At E0/E1 (no coupling) the reference is
irrelevant — slots are independent and the per-slot argmax is the exact MAP.
At E2+ this becomes an iterated-conditional / trellis message; the reference is
the current best estimate. (True joint decoding via Viterbi enters when the
measured coupling bandwidth demands it — later rung.)
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from lrlpr.decode.likelihood import ScoringModel
from lrlpr.plate_spec import PlateSpec

LETTERS = tuple(chr(c) for c in range(ord("A"), ord("Z") + 1))
DIGITS = tuple(str(d) for d in range(10))


def alphabet_for_slot(spec: PlateSpec, j: int) -> tuple[str, ...]:
    return LETTERS if spec.slots[j].kind == "L" else DIGITS


@dataclass
class SlotTable:
    """Scores for one slot: character -> log-likelihood (conditional on ref)."""

    slot: int
    scores: dict[str, float]

    def posterior(self) -> dict[str, float]:
        chars = list(self.scores)
        ll = np.array([self.scores[c] for c in chars])
        p = np.exp(ll - ll.max())
        p /= p.sum()
        return dict(zip(chars, p, strict=True))

    def argmax(self) -> str:
        return max(self.scores, key=self.scores.get)

    def margin(self) -> float:
        """Top-1 minus top-2 log-likelihood (nats) — the per-slot evidence gap."""
        vals = sorted(self.scores.values(), reverse=True)
        return vals[0] - vals[1] if len(vals) > 1 else float("inf")

    def top1_posterior(self) -> float:
        return max(self.posterior().values())


def slot_tables(
    scoring: ScoringModel, y: np.ndarray, spec: PlateSpec, ref_string: str
) -> list[SlotTable]:
    """One SlotTable per position, each scoring its legal alphabet."""
    ref = spec.validate_string(ref_string)
    tables = []
    for j in range(len(spec.slots)):
        scores = {}
        for ch in alphabet_for_slot(spec, j):
            cand = ref[:j] + ch + ref[j + 1 :]
            scores[ch] = scoring.score(y, cand)
        tables.append(SlotTable(slot=j, scores=scores))
    return tables


def decode_independent(
    scoring: ScoringModel, y: np.ndarray, spec: PlateSpec, ref_string: str
) -> tuple[str, list[SlotTable]]:
    """Per-slot argmax decode (exact MAP when slots don't couple; E0/E1)."""
    tables = slot_tables(scoring, y, spec, ref_string)
    return "".join(t.argmax() for t in tables), tables
