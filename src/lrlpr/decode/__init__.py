"""Decoding: likelihood scoring and per-slot hypothesis evaluation.

Implements the oracle-ladder machinery (docs/discussion-log.md). E0-E2 only —
the pixel-domain Gaussian likelihood and per-slot tables. Frame fusion, DCT
likelihood, correlation, and EM arrive with later rungs (design-02, ungated).
"""

from lrlpr.decode.likelihood import ScoringModel, gaussian_loglik, sse
from lrlpr.decode.slots import (
    SlotTable,
    alphabet_for_slot,
    decode_independent,
    slot_tables,
)

__all__ = [
    "ScoringModel",
    "gaussian_loglik",
    "sse",
    "SlotTable",
    "alphabet_for_slot",
    "decode_independent",
    "slot_tables",
]
