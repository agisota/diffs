"""Inline legal reference parser.

Recognizes patterns like:

    ст. 5
    ст. 5, ч. 2
    статья 7 части 3 пункт 1 подпункта а
    п. 4 ст. 109 ФЗ № 109-ФЗ
    раздела II Концепции
    Указ Президента № 622 от 31.10.2018

Returns a list of ``LegalRef`` objects with the fields it could resolve.
This is heuristic, not a full parser — designed for evidence-matrix
hyperlinking and for the legal_structural_diff comparator to align
chunks across documents that cite the same provision.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .terms import ABBR, DATE_RE, NPA_DOC_RE


@dataclass
class LegalRef:
    """A resolved reference to a structural unit, optionally inside a doc.

    ``parts`` keeps the explicit hierarchy (e.g. ``{"article": "5",
    "part": "2"}``). ``doc_kind`` and ``doc_num`` identify the host
    NPA when present. ``span`` is the (start, end) slice of the input
    string the reference was parsed from.
    """

    raw: str
    parts: dict[str, str] = field(default_factory=dict)
    doc_kind: str | None = None
    doc_num: str | None = None
    doc_date: str | None = None
    span: tuple[int, int] = (0, 0)

    def key(self) -> str:
        """Stable dotted key for indexing: ``article=5/part=2/point=3``."""
        order = ["section", "chapter", "article", "part", "point", "subpoint", "paragraph"]
        return "/".join(f"{k}={self.parts[k]}" for k in order if k in self.parts)


# Build a single regex matching any abbreviation form followed by a number.
# We split the abbreviations by length descending so longer forms ("статья")
# match before shorter ("ст") to avoid swallowing the longer label.
_ABBR_FORMS = sorted(ABBR.keys(), key=len, reverse=True)
_ABBR_ALT = "|".join(re.escape(a) for a in _ABBR_FORMS)

_REF_TOKEN_RE = re.compile(
    rf"(?P<abbr>{_ABBR_ALT})\s+(?P<num>\d+(?:\.\d+)*|[а-яё]|[IVXLCDM]+)",
    re.IGNORECASE,
)

# A "chain" is a sequence of refs separated by commas/spaces with no
# intervening sentence. We extend a chain greedily by looking for adjacent
# ref tokens within a small window.
_CHAIN_GAP = re.compile(r"^[\s,;.]*$")


def parse_refs(text: str) -> list[LegalRef]:
    """Return all legal refs found in ``text``.

    Each ref combines as many hierarchical parts as appear in a single
    chain (e.g. ``ст. 5, ч. 2, п. 3`` collapses to one ref with three
    parts). When a chain ends and an NPA identifier follows ("ФЗ №
    109-ФЗ от 18.07.2006"), it's attached to that ref.
    """
    if not text:
        return []
    out: list[LegalRef] = []
    pos = 0
    while pos < len(text):
        m = _REF_TOKEN_RE.search(text, pos)
        if m is None:
            break
        chain_start = m.start()
        parts: dict[str, str] = {}
        last_end = m.end()

        # Eat the first token + any consecutive ref tokens.
        cur = m
        while cur is not None:
            kind = ABBR[cur.group("abbr").lower()]
            if kind not in parts:
                parts[kind] = cur.group("num")
            last_end = cur.end()
            # Look for an adjacent ref token within the next ~20 chars,
            # bridged only by whitespace/punctuation.
            tail_start = cur.end()
            nxt = _REF_TOKEN_RE.search(text, tail_start, tail_start + 32)
            if nxt is None:
                break
            gap = text[tail_start:nxt.start()]
            if not _CHAIN_GAP.match(gap):
                break
            cur = nxt

        # Attempt to attach an NPA identifier after the chain.
        doc_kind = doc_num = doc_date = None
        tail = text[last_end : last_end + 200]
        npa = NPA_DOC_RE.search(tail)
        if npa is not None:
            doc_kind = (npa.group("kind") or "").strip()
            doc_num = (npa.group("num") or None)
            d = DATE_RE.search(tail[npa.start() :])
            if d is not None:
                if d.group(1):
                    doc_date = f"{int(d.group(1)):02d}.{int(d.group(2)):02d}.{d.group(3)}"
                else:
                    doc_date = f"{d.group(4)} {d.group(5)} {d.group(6)}"

        ref = LegalRef(
            raw=text[chain_start:last_end].strip(),
            parts=parts,
            doc_kind=doc_kind,
            doc_num=doc_num,
            doc_date=doc_date,
            span=(chain_start, last_end),
        )
        out.append(ref)
        pos = last_end

    return out
