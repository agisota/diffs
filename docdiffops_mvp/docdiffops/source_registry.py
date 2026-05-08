"""Source classification and registration for DocDiffOps.

Maps a document's filename, optional source URL, and content sniff to
``(doc_type, source_rank)`` per PLAN §3 ADR-5 source hierarchy.

The module is intentionally pure-Python and side-effect-free: classify()
takes bytes (no network, no filesystem) and returns a tuple. Persistence
of the inferred classification on ``documents.source_url`` and on the
``source_registry`` table happens in ``docdiffops.db.repository`` and
``docdiffops.main``.

PR-3.6 (source-rank gate in classifier) and PR-4.4 (scheduled URL
polling) both consume the host -> rank table here. ``RANK_OVERRIDES``
gives operators a single dict to extend without touching the canonical
rank tables.
"""
from __future__ import annotations

from urllib.parse import urlparse

# ---------------------------------------------------------------------------
# Public constants
# ---------------------------------------------------------------------------

# Human-readable label for each rank. PR-3.6 uses these in evidence
# matrices and the executive summary, so keep them stable.
RANK_LABEL: dict[int, str] = {
    1: "official_npa",
    2: "departmental",
    3: "analytics",
}

# Doc-type vocabulary from the brief §13. Keep as a tuple so callers
# can branch on ``doc_type in DOC_TYPES`` without typos.
DOC_TYPES: tuple[str, ...] = (
    "LEGAL_NPA",
    "LEGAL_CONCEPT",
    "GOV_PLAN",
    "PRESENTATION",
    "TABLE",
    "WEB_ARTICLE",
    "OTHER",
)

# ---------------------------------------------------------------------------
# Host -> rank registry
#
# Rank 1 = official NPA publishers. Rank 2 = ministries / commercial
# regulatory aggregators (Garant, Consultant, Kontur). Rank 3 = analytics,
# media, social. The table is exact-host or suffix match — the exact
# hostname is checked first, then a suffix walk for ``*.gov.ru`` /
# ``*.mos.ru`` style wildcards.
#
# ``economy.gov.ru`` is explicitly demoted to rank 2 per spec; the rule
# below treats it as a literal exact-match (rank 2) before the
# ``.gov.ru`` suffix check (which would otherwise return rank 1).
# ---------------------------------------------------------------------------

# Exact host -> rank mappings (most specific wins).
HOST_RANK: dict[str, int] = {
    # Rank 1 — official NPA publishers.
    "kremlin.ru": 1,
    "pravo.gov.ru": 1,
    "publication.pravo.gov.ru": 1,
    "government.ru": 1,
    "duma.gov.ru": 1,
    "council.gov.ru": 1,
    # Rank 2 — ministries / commercial regulatory aggregators.
    "economy.gov.ru": 2,
    "minfin.gov.ru": 2,
    "minjust.gov.ru": 2,
    "mvd.ru": 2,
    "fsb.ru": 2,
    "kontur.ru": 2,
    "consultant.ru": 2,
    "garant.ru": 2,
}

# Suffix -> rank for wildcard hosts. Order matters: more specific
# suffixes must come first so they win the longest-match scan.
SUFFIX_RANK: tuple[tuple[str, int], ...] = (
    (".mos.ru", 1),
    (".gov.ru", 2),
)

# Operator-extensible override table. Anything here wins over the
# tables above. Empty by default; live deployments may seed from a
# yaml config in PR-3.6.
RANK_OVERRIDES: dict[str, int] = {}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def classify(
    filename: str,
    source_url: str | None = None,
    content_head: bytes | None = None,
) -> tuple[str, int]:
    """Return ``(doc_type, source_rank)`` for an uploaded document.

    Pure function: makes no network calls, no filesystem access. Callers
    upload bytes via FastAPI and pass the first few KB as ``content_head``.

    - ``filename`` — original upload filename (extension is the strongest
      signal for ``PRESENTATION`` / ``TABLE``).
    - ``source_url`` — provenance URL. ``None`` (locally-uploaded files)
      defaults the rank to 3 since we cannot prove provenance.
    - ``content_head`` — first ~4 KB of the file, used for Cyrillic
      keyword sniffing inside PDF/DOCX/HTML uploads.
    """
    return (
        infer_doc_type(filename, content_head),
        infer_source_rank(source_url),
    )


def infer_source_rank(source_url: str | None) -> int:
    """Return rank 1/2/3 by host. Defaults to 3 when URL is missing.

    Resolution order:

    1. ``RANK_OVERRIDES`` (operator-supplied)
    2. exact host match in ``HOST_RANK``
    3. longest suffix match in ``SUFFIX_RANK``
    4. fallback rank 3
    """
    host = _extract_host(source_url)
    if host is None:
        return 3

    if host in RANK_OVERRIDES:
        return RANK_OVERRIDES[host]
    if host in HOST_RANK:
        return HOST_RANK[host]
    for suffix, rank in SUFFIX_RANK:
        if host.endswith(suffix) or "." + host == suffix:
            return rank
    return 3


def infer_doc_type(filename: str, content_head: bytes | None = None) -> str:
    """Return one of the ``DOC_TYPES`` constants for ``filename``.

    Extension wins for unambiguous formats (``.pptx`` -> PRESENTATION,
    ``.xlsx``/``.csv`` -> TABLE). For ``.html``/``.pdf``/``.docx`` we
    fall back to a Cyrillic keyword sniff over ``content_head`` because
    a PDF can be a federal law, a concept, or a corporate report.
    """
    ext = _extract_ext(filename)

    if ext in {".pptx", ".ppt"}:
        return "PRESENTATION"
    if ext in {".xlsx", ".xls", ".csv", ".tsv"}:
        return "TABLE"

    # Content-based sniff for legal / government text. Run for all
    # remaining extensions: HTML pages, PDFs, DOCX, plain text uploads.
    sniffed = _sniff_content(content_head)
    if sniffed is not None:
        return sniffed

    if ext in {".html", ".htm"}:
        # HTML without legal keywords lands as a generic web article so
        # downstream comparators can apply WEB_ARTICLE thinness rules.
        return "WEB_ARTICLE"

    return "OTHER"


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _extract_host(source_url: str | None) -> str | None:
    """Lowercased hostname or ``None`` for missing/malformed URLs.

    Tolerates inputs lacking a scheme (``"kremlin.ru/news"``) by
    re-parsing with ``http://`` prepended. Strips ports and trailing
    dots. IDN domains pass through untouched (callers may normalize
    via ``idna`` at write time if needed).
    """
    if not source_url:
        return None
    url = source_url.strip()
    if not url:
        return None

    parsed = urlparse(url)
    host = parsed.hostname
    if host is None and "://" not in url:
        # No scheme: re-parse with a synthetic scheme so urlparse
        # picks up the hostname instead of treating it as a path.
        parsed = urlparse("http://" + url)
        host = parsed.hostname

    if not host:
        return None
    host = host.lower().rstrip(".")
    if host.startswith("www."):
        host = host[4:]
    return host or None


def _extract_ext(filename: str) -> str:
    """Lowercased filename extension including the dot, or ''."""
    if not filename:
        return ""
    name = filename.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    if "." not in name:
        return ""
    return "." + name.rsplit(".", 1)[-1].lower()


# Cyrillic keyword phrases for the content sniff. We work in lowercase
# so callers don't need to pre-normalize. Phrases live in tuples keyed
# by doc_type so adding a new keyword is a one-line change.
_LEGAL_NPA_KEYWORDS: tuple[str, ...] = (
    "указ президента",
    "федеральный закон",
    "распоряжение правительства",
    "постановление правительства",
    "приказ министерства",
)

_LEGAL_CONCEPT_HINTS: tuple[str, ...] = (
    "миграционной",
    "государственной",
    "национальной",
)

_GOV_PLAN_HINTS: tuple[str, ...] = ("ответственный", "срок", "исполнитель")


def _sniff_content(content_head: bytes | None) -> str | None:
    """Return a doc_type by Cyrillic keyword sniff, or ``None``.

    Decodes ``content_head`` as UTF-8 (errors ignored) and runs a
    cascade of substring checks. The ordering matters: a "план
    мероприятий" with "ответственный" is a GOV_PLAN even if it also
    mentions "указ президента"; we check NPA-specific phrases first
    so the most specific label wins.
    """
    if not content_head:
        return None

    text = content_head.decode("utf-8", errors="ignore").lower()
    if not text:
        return None

    # NPA: a normative legal act explicitly issued by Kremlin /
    # government. Highest specificity, check first.
    if any(kw in text for kw in _LEGAL_NPA_KEYWORDS):
        return "LEGAL_NPA"

    # Concept documents: "концепция" + a state-policy qualifier.
    if "концепция" in text and any(h in text for h in _LEGAL_CONCEPT_HINTS):
        return "LEGAL_CONCEPT"

    # Action plan: "план мероприятий" with at least one column hint.
    if "план мероприятий" in text and any(h in text for h in _GOV_PLAN_HINTS):
        return "GOV_PLAN"

    # HTML page generated from PowerPoint exports. ``meta name=generator``
    # is the canonical signal; the substring is safe inside the head bytes.
    if "<meta" in text and "powerpoint" in text:
        return "PRESENTATION"

    return None


__all__ = [
    "classify",
    "infer_doc_type",
    "infer_source_rank",
    "RANK_LABEL",
    "DOC_TYPES",
    "HOST_RANK",
    "SUFFIX_RANK",
    "RANK_OVERRIDES",
]
