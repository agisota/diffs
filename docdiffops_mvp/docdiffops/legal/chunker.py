"""Structural chunkers for Russian legal/policy documents.

Given raw extracted text, produce a flat list of ``Chunk`` objects
preserving the hierarchy via ``parent_id`` references. The chunk graph
is what ``legal_structural_diff`` aligns across LHS/RHS of a pair —
two NPAs that share article numbers can be diffed at the article level
even when surrounding paragraphs have shifted.

Dispatcher: ``chunk_text(doc_type, text)`` picks the right strategy
based on the doc_type from ``source_registry.classify``.
"""
from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from typing import Iterable

from .terms import (
    ARTICLE_RE,
    BRACKETED_NUM_RE,
    CHAPTER_RE,
    CYRILLIC_LETTER_RE,
    NUMBERED_POINT_RE,
    PART_HEADER_RE,
    PREAMBLE_END,
    SECTION_RE,
    normalize_ws,
)


@dataclass
class Chunk:
    """A structural unit inside a legal/policy document.

    ``kind`` ∈ ``{section, chapter, article, part, point, subpoint, paragraph,
    measure, claim, preamble}``. ``number`` is the numeric/letter
    identifier ("5", "II", "а"). ``parent_id`` points to the surrounding
    chunk; a top-level chunk has ``parent_id=None``. ``text`` is the
    chunk body (excluding the header line itself for headed kinds).
    """

    chunk_id: str
    kind: str
    number: str | None
    title: str
    text: str
    parent_id: str | None = None
    line_start: int = 0
    line_end: int = 0
    extras: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _cid(*parts: str) -> str:
    """Deterministic 12-char chunk_id from a tuple."""
    h = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
    return "ch_" + h[:12]


def _split_lines(text: str) -> list[str]:
    return [l.rstrip() for l in (text or "").splitlines()]


# ---------------------------------------------------------------------------
# NPA chunker — статья → часть → пункт → подпункт → абзац
# ---------------------------------------------------------------------------


def chunk_npa(text: str, doc_id: str = "doc") -> list[Chunk]:
    """Chunk a federal-law-style text. Top-level units are Articles.

    Inside each Article, numbered "1." lines become Parts; "1) ..." lines
    become Points; "а) ..." lines become Subpoints. Lines that don't
    match any header pattern are appended to the current open chunk's
    body — this preserves prose under articles intact.
    """
    lines = _split_lines(text)
    chunks: list[Chunk] = []
    current_article: Chunk | None = None
    current_part: Chunk | None = None
    current_point: Chunk | None = None
    current_subpoint: Chunk | None = None
    buffer: list[str] = []

    def _flush_buffer_into(c: Chunk | None) -> None:
        if c is None or not buffer:
            buffer.clear()
            return
        c.text = (c.text + ("\n" if c.text else "") + "\n".join(buffer)).strip()
        buffer.clear()

    def _open_chunk(kind: str, num: str | None, title: str, parent: Chunk | None, line_no: int) -> Chunk:
        cid = _cid(doc_id, kind, num or "", title or "", str(line_no))
        return Chunk(
            chunk_id=cid,
            kind=kind,
            number=num,
            title=normalize_ws(title or ""),
            text="",
            parent_id=parent.chunk_id if parent else None,
            line_start=line_no,
            line_end=line_no,
        )

    for i, raw_line in enumerate(lines):
        line = raw_line.strip()
        if not line:
            buffer.append("")
            continue

        if PREAMBLE_END.match(line):
            # Stop NPA-style chunking; remaining lines become a single
            # "appendix" chunk to preserve traceability.
            _flush_buffer_into(current_subpoint or current_point or current_part or current_article)
            tail = "\n".join(lines[i:]).strip()
            if tail:
                appendix = _open_chunk("appendix", None, line, None, i)
                appendix.text = tail
                appendix.line_end = len(lines) - 1
                chunks.append(appendix)
            return chunks

        m = ARTICLE_RE.match(line)
        if m:
            # Flush pending text into the most-specific OPEN chunk; if none
            # is open yet (we're still in the preamble), flush into the
            # preamble chunk (creating it if necessary).
            target = current_subpoint or current_point or current_part or current_article
            if target is None and buffer:
                pre = next((c for c in chunks if c.kind == "preamble"), None)
                if pre is None:
                    pre = _open_chunk("preamble", None, "", None, 0)
                    chunks.insert(0, pre)
                target = pre
            _flush_buffer_into(target)
            current_article = _open_chunk("article", m.group("num"), m.group("title"), None, i)
            chunks.append(current_article)
            current_part = current_point = current_subpoint = None
            continue

        m = SECTION_RE.match(line)
        if m:
            _flush_buffer_into(current_subpoint or current_point or current_part or current_article)
            section = _open_chunk("section", m.group("num"), m.group("title"), None, i)
            chunks.append(section)
            current_article = section  # later articles attach under this section
            current_part = current_point = current_subpoint = None
            continue

        m = CHAPTER_RE.match(line)
        if m:
            _flush_buffer_into(current_subpoint or current_point or current_part or current_article)
            chap = _open_chunk("chapter", m.group("num"), m.group("title"), current_article, i)
            chunks.append(chap)
            continue

        m = PART_HEADER_RE.match(line)
        if m and current_article is not None:
            _flush_buffer_into(current_subpoint or current_point or current_part)
            current_part = _open_chunk("part", m.group("num"), m.group("title"), current_article, i)
            chunks.append(current_part)
            current_point = current_subpoint = None
            continue

        m = NUMBERED_POINT_RE.match(line)
        if m and current_article is not None:
            _flush_buffer_into(current_subpoint or current_point or current_part)
            # Numbered "1." lines under an Article are PARTS (siblings of
            # each other, all parented to the Article — not nested deeper).
            current_part = _open_chunk("part", m.group("num"), "", current_article, i)
            current_part.text = m.group("text")
            chunks.append(current_part)
            current_point = current_subpoint = None
            continue

        m = BRACKETED_NUM_RE.match(line)
        if m and current_article is not None:
            _flush_buffer_into(current_subpoint or current_point)
            parent = current_part or current_article
            current_point = _open_chunk("point", m.group("num"), "", parent, i)
            current_point.text = m.group("text")
            chunks.append(current_point)
            current_subpoint = None
            continue

        m = CYRILLIC_LETTER_RE.match(line)
        if m and current_article is not None:
            _flush_buffer_into(current_subpoint)
            parent = current_point or current_part or current_article
            current_subpoint = _open_chunk("subpoint", m.group("letter"), "", parent, i)
            current_subpoint.text = m.group("text")
            chunks.append(current_subpoint)
            continue

        # Plain prose — append to the most-specific open chunk.
        target = current_subpoint or current_point or current_part or current_article
        if target is None:
            # Pre-Article preamble.
            if not chunks or chunks[-1].kind != "preamble":
                pre = _open_chunk("preamble", None, "", None, i)
                chunks.append(pre)
            buffer.append(line)
        else:
            buffer.append(line)
            target.line_end = i

    _flush_buffer_into(current_subpoint or current_point or current_part or current_article or (chunks[-1] if chunks else None))
    return chunks


# ---------------------------------------------------------------------------
# Concept chunker — раздел → пункт → подпункт → абзац
# ---------------------------------------------------------------------------


def chunk_concept(text: str, doc_id: str = "doc") -> list[Chunk]:
    """Migration policy concepts and similar policy docs.

    Top level is Section; numbered points (1., 2., …) become Points
    rather than Parts (semantically equivalent at this layer). Otherwise
    behaves like the NPA chunker.
    """
    lines = _split_lines(text)
    chunks: list[Chunk] = []
    current_section: Chunk | None = None
    current_point: Chunk | None = None
    current_subpoint: Chunk | None = None
    buffer: list[str] = []

    def _flush(c: Chunk | None) -> None:
        if c is None or not buffer:
            buffer.clear()
            return
        c.text = (c.text + ("\n" if c.text else "") + "\n".join(buffer)).strip()
        buffer.clear()

    for i, raw_line in enumerate(lines):
        line = raw_line.strip()
        if not line:
            buffer.append("")
            continue
        if PREAMBLE_END.match(line):
            _flush(current_subpoint or current_point or current_section)
            break

        m = SECTION_RE.match(line)
        if m:
            _flush(current_subpoint or current_point or current_section)
            current_section = Chunk(
                chunk_id=_cid(doc_id, "section", m.group("num"), str(i)),
                kind="section",
                number=m.group("num"),
                title=normalize_ws(m.group("title")),
                text="",
                line_start=i, line_end=i,
            )
            chunks.append(current_section)
            current_point = current_subpoint = None
            continue

        m = NUMBERED_POINT_RE.match(line)
        if m and current_section is not None:
            _flush(current_subpoint or current_point)
            current_point = Chunk(
                chunk_id=_cid(doc_id, "point", m.group("num"), str(i)),
                kind="point",
                number=m.group("num"),
                title="",
                text=m.group("text"),
                parent_id=current_section.chunk_id,
                line_start=i, line_end=i,
            )
            chunks.append(current_point)
            current_subpoint = None
            continue

        m = CYRILLIC_LETTER_RE.match(line)
        if m and current_point is not None:
            _flush(current_subpoint)
            current_subpoint = Chunk(
                chunk_id=_cid(doc_id, "subpoint", m.group("letter"), str(i)),
                kind="subpoint",
                number=m.group("letter"),
                title="",
                text=m.group("text"),
                parent_id=current_point.chunk_id,
                line_start=i, line_end=i,
            )
            chunks.append(current_subpoint)
            continue

        target = current_subpoint or current_point or current_section
        if target is None:
            if not chunks or chunks[-1].kind != "preamble":
                chunks.append(Chunk(
                    chunk_id=_cid(doc_id, "preamble", str(i)),
                    kind="preamble", number=None, title="", text="",
                    line_start=i, line_end=i,
                ))
            buffer.append(line)
        else:
            buffer.append(line)
            target.line_end = i

    _flush(current_subpoint or current_point or current_section)
    return chunks


# ---------------------------------------------------------------------------
# Government plan chunker — мероприятие → срок → ответственный → результат
# ---------------------------------------------------------------------------


def chunk_gov_plan(text: str, doc_id: str = "doc") -> list[Chunk]:
    """Government action plans (Распоряжение Правительства).

    Real plans are typically tables, but extracted text can still be
    chunked by enumerated measures. We treat each top-level numbered
    item as a "measure" chunk and look inside for срок/ответственный/
    результат hints which we attach to ``extras``.
    """
    lines = _split_lines(text)
    chunks: list[Chunk] = []
    current_measure: Chunk | None = None
    buffer: list[str] = []

    deadline_kw = ("срок", "период")
    responsible_kw = ("ответствен",)
    outcome_kw = ("ожидаемый", "результат")

    def _flush() -> None:
        nonlocal current_measure
        if current_measure is None:
            buffer.clear()
            return
        body = "\n".join(buffer).strip()
        current_measure.text = (current_measure.text + ("\n" if current_measure.text else "") + body).strip()
        # Mine extras from the body (very heuristic).
        low = current_measure.text.lower()
        for kw in deadline_kw:
            if kw in low:
                current_measure.extras.setdefault("has_deadline", True)
        for kw in responsible_kw:
            if kw in low:
                current_measure.extras.setdefault("has_responsible", True)
        for kw in outcome_kw:
            if kw in low:
                current_measure.extras.setdefault("has_outcome", True)
        buffer.clear()

    for i, raw_line in enumerate(lines):
        line = raw_line.strip()
        if not line:
            buffer.append("")
            continue

        m = NUMBERED_POINT_RE.match(line)
        if m:
            _flush()
            current_measure = Chunk(
                chunk_id=_cid(doc_id, "measure", m.group("num"), str(i)),
                kind="measure",
                number=m.group("num"),
                title=normalize_ws(m.group("text")[:120]),
                text=m.group("text"),
                line_start=i, line_end=i,
            )
            chunks.append(current_measure)
            continue

        if current_measure is not None:
            buffer.append(line)
            current_measure.line_end = i

    _flush()
    return chunks


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------


def chunk_text(doc_type: str | None, text: str, doc_id: str = "doc") -> list[Chunk]:
    """Pick the right chunker based on ``doc_type`` from source_registry.

    Falls back to ``chunk_npa`` when doc_type is unknown — it's the most
    permissive of the three and produces useful output even on prose
    that never matches an Article header (becomes one big preamble).
    """
    dt = (doc_type or "").upper()
    if dt == "LEGAL_NPA":
        return chunk_npa(text, doc_id=doc_id)
    if dt == "LEGAL_CONCEPT":
        return chunk_concept(text, doc_id=doc_id)
    if dt == "GOV_PLAN":
        return chunk_gov_plan(text, doc_id=doc_id)
    # Default: try NPA chunker. Cheap and graceful.
    return chunk_npa(text, doc_id=doc_id)


def to_dicts(chunks: Iterable[Chunk]) -> list[dict]:
    return [c.to_dict() for c in chunks]
