"""Russian legal layer for DocDiffOps (Sprint 3).

Public surface:
- ``terms``  — regex patterns and abbreviations
- ``refs``   — ``parse_refs`` extracts inline legal references
                (e.g. "ст. 5, ч. 2 ФЗ № 109-ФЗ")
- ``chunker`` — ``chunk_text`` returns a list of ``Chunk`` for the doc_type
                emitted by ``source_registry.classify``
"""

from .chunker import Chunk, chunk_text
from .claims import Claim, claim_validation_events, extract_claims, validate_claim
from .rank_gate import apply_rank_gate
from .refs import LegalRef, parse_refs
from .structural_diff import legal_structural_diff

__all__ = [
    "Chunk",
    "chunk_text",
    "Claim",
    "claim_validation_events",
    "extract_claims",
    "validate_claim",
    "LegalRef",
    "parse_refs",
    "legal_structural_diff",
    "apply_rank_gate",
]
