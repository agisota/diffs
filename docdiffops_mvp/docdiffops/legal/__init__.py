"""Russian legal layer for DocDiffOps (Sprint 3).

Public surface:
- ``terms``  — regex patterns and abbreviations
- ``refs``   — ``parse_refs`` extracts inline legal references
                (e.g. "ст. 5, ч. 2 ФЗ № 109-ФЗ")
- ``chunker`` — ``chunk_text`` returns a list of ``Chunk`` for the doc_type
                emitted by ``source_registry.classify``
"""

from .chunker import Chunk, chunk_text
from .refs import LegalRef, parse_refs

__all__ = ["Chunk", "chunk_text", "LegalRef", "parse_refs"]
