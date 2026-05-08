"""Russian legal term constants + regex patterns.

The patterns are deliberately conservative — they match the headers that
sit on their own line (after collapsing whitespace), not arbitrary
inline mentions. Inline references are handled by ``refs.py``.

Document structures (from brief §13):
  LEGAL_NPA:     статья → часть → пункт → подпункт → абзац
  LEGAL_CONCEPT: раздел → пункт → подпункт → абзац
  GOV_PLAN:      мероприятие → срок → ответственный → ожидаемый результат
"""
from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Header patterns — match a single header line, return (number, title).
# ---------------------------------------------------------------------------

# "Статья 5", "Статья 5.", "Статья 12.3.", "СТАТЬЯ 7. Учёт мигрантов"
ARTICLE_RE = re.compile(
    r"^\s*(?:Статья|СТАТЬЯ)\s+(?P<num>\d+(?:\.\d+)*)\s*[. ]?\s*(?P<title>.*)$"
)

# "Раздел I", "РАЗДЕЛ II", "Раздел 3" — Roman or Arabic numerals
SECTION_RE = re.compile(
    r"^\s*(?:Раздел|РАЗДЕЛ)\s+(?P<num>[IVXLCDM]+|\d+)\s*[. ]?\s*(?P<title>.*)$"
)

# "Глава 2"
CHAPTER_RE = re.compile(
    r"^\s*(?:Глава|ГЛАВА)\s+(?P<num>\d+)\s*[. ]?\s*(?P<title>.*)$"
)

# "Часть 1", "Часть первая"
PART_HEADER_RE = re.compile(
    r"^\s*(?:Часть|ЧАСТЬ)\s+(?P<num>\d+|первая|вторая|третья|четвёртая|пятая)\s*[. ]?\s*(?P<title>.*)$"
)

# Numbered point inline (no header word): "1. Текст пункта" / "12. ..."
# Caller decides whether this is a ПУНКТ or ЧАСТЬ based on parent context.
NUMBERED_POINT_RE = re.compile(r"^\s*(?P<num>\d+(?:\.\d+)*)\.\s+(?P<text>\S.*)$")

# Bracketed enumerator: "1) ...", "12) ..."
BRACKETED_NUM_RE = re.compile(r"^\s*(?P<num>\d+)\)\s+(?P<text>\S.*)$")

# Cyrillic letter sub-point: "а) ...", "б) ...", "в) ..."
CYRILLIC_LETTER_RE = re.compile(
    r"^\s*(?P<letter>[а-яё])\)\s+(?P<text>\S.*)$",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Inline abbreviations used by ``refs.parse_refs``.
# ---------------------------------------------------------------------------

# "ст." / "статья" → ARTICLE; "ч." / "часть" → PART; etc.
ABBR = {
    "ст": "article",
    "статья": "article",
    "ст.": "article",
    "ч": "part",
    "часть": "part",
    "ч.": "part",
    "п": "point",
    "пункт": "point",
    "п.": "point",
    "пп": "subpoint",
    "пп.": "subpoint",
    "подп": "subpoint",
    "подп.": "subpoint",
    "подпункт": "subpoint",
    "абз": "paragraph",
    "абз.": "paragraph",
    "абзац": "paragraph",
    "р": "section",
    "раздел": "section",
    "р.": "section",
    "гл": "chapter",
    "гл.": "chapter",
    "глава": "chapter",
}

# ---------------------------------------------------------------------------
# NPA-doc identifiers: "ФЗ № 109-ФЗ", "Указ № 622", "Распоряжение № 30-р".
# ---------------------------------------------------------------------------

NPA_DOC_RE = re.compile(
    r"(?P<kind>"
    r"Федеральн(?:ый|ого|ому|ым|ом)\s+закон[а-я]*"
    r"|ФЗ"
    r"|Указ(?:а|у|ом|е)?\s+Президента"
    r"|Указ"
    r"|Постановлени(?:е|я|ю|ем|и)\s+Правительства"
    r"|Постановление"
    r"|Распоряжени(?:е|я|ю|ем|и)\s+Правительства"
    r"|Распоряжение"
    r"|Конституци(?:я|и|ю|ей|и)\s+Российской\s+Федерации"
    r"|Концепци(?:я|и|ю|ей|и)"
    r")"
    r"(?:[^№\d]{0,40}?(?:№|N)\s*(?P<num>[\d\-/A-Za-zа-яёА-ЯЁ\.]+))?",
    re.IGNORECASE,
)

# Date "от ДД.ММ.ГГГГ" or "от ДД месяца ГГГГ"
DATE_RE = re.compile(
    r"от\s+(\d{1,2})\s*[.\-/]\s*(\d{1,2})\s*[.\-/]\s*(\d{4})|"
    r"от\s+(\d{1,2})\s+(января|февраля|марта|апреля|мая|июня|"
    r"июля|августа|сентября|октября|ноября|декабря)\s+(\d{4})",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Stop-tokens that mark the END of a section preamble (used to skip over
# tables of contents, signatures, "Приложение" headers, etc.).
# ---------------------------------------------------------------------------

PREAMBLE_END = re.compile(
    r"^\s*(?:Приложени[еяю]|Подпис[ьаи]|УТВЕРЖДЕН[АО]?|Согласовано)\b",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def normalize_ws(s: str) -> str:
    """Collapse runs of whitespace into a single space, strip ends, NBSP→space."""
    return re.sub(r"\s+", " ", (s or "").replace(" ", " ")).strip()
