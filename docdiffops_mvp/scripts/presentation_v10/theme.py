"""Ocean Gradient brand theme + immutable status palette import.

The status palette (match/partial/contradiction/...) MUST come from
``docdiffops.forensic_render`` so the presentation stays visually consistent
with the XLSX/DOCX/PDF artifacts already in ``migration_v10_out/bundle/``.
The Ocean Gradient palette is the *brand* layer — backgrounds, dividers,
title bars, footers — wrapped around the unchanged semantic colors.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Make ``docdiffops`` importable when this package is invoked from
# ``docdiffops_mvp/`` as ``python -m scripts.presentation_v10.<module>``.
_REPO_PKG = Path(__file__).resolve().parents[2]
if str(_REPO_PKG) not in sys.path:
    sys.path.insert(0, str(_REPO_PKG))

from docdiffops.forensic_render import (  # noqa: E402
    PALETTE as FORENSIC_PALETTE,
    STATUS_PALETTE,
    STATUS_RU,
)
from docdiffops.forensic import (  # noqa: E402
    STATUS_CONTRADICTION,
    STATUS_GAP,
    STATUS_MATCH,
    STATUS_NC,
    STATUS_OUTDATED,
    STATUS_PARTIAL,
    STATUS_REVIEW,
    STATUS_TO_MARK,
    V8_STATUSES,
)

# ---------------------------------------------------------------------------
# Brand: Ocean Gradient
# ---------------------------------------------------------------------------

OCEAN: dict[str, str] = {
    "primary":          "065A82",  # Deep blue — title bars, gradient start
    "secondary":        "1C7293",  # Teal — gradient end, secondary headers
    "accent":           "21295C",  # Midnight — outline / footer text
    "bg_light":         "F9FAFB",  # Body background
    "bg_dark":          "0F172A",  # Cover/divider backup
    "ink":              "0F172A",  # Body text on light
    "ink_inv":          "FFFFFF",  # Text on dark gradient
    "muted":            "6B7280",  # Footer, captions
    "rule":             "D1D5DB",  # Divider lines, table borders
    "tile_bg":          "EAF3F8",  # Light teal tint for KPI tiles
    # Premium additions
    "bronze":           "B5651D",  # Bronze accent for hero moments
    "bg_dark_premium":  "054566",  # Slightly darker premium gradient start
    "secondary_premium":"1A6582",  # Slightly darker teal for premium gradient end
}

# Color-blind dual-coding glyphs (large unicode for primary signal)
STATUS_GLYPHS_BIG: dict[str, str] = {
    "match":           "✓",
    "partial_overlap": "≈",
    "contradiction":   "⚠",
    "outdated":        "↻",
    "source_gap":      "∅",
    "manual_review":   "?",
    "not_comparable":  "—",
}

# New typography sizes for hero/event cards
SIZE_HERO_STAT_PT = 120
SIZE_EVENT_QUOTE_PT = 14
SIZE_THEME_TITLE_PT = 28

# ---------------------------------------------------------------------------
# Effective status colors (delegate to forensic_render to stay consistent)
# ---------------------------------------------------------------------------

STATUS_HEX: dict[str, str] = {
    status: FORENSIC_PALETTE[STATUS_PALETTE[status]] for status in V8_STATUSES
}
"""Status code → hex color (no leading '#'), authoritative from forensic_render."""

# Light tint backgrounds for status table cells (mirrors XLSX fills).
STATUS_TINT_BG: dict[str, str] = {
    STATUS_MATCH:         "DCFCE7",
    STATUS_PARTIAL:       "FEF3C7",
    STATUS_CONTRADICTION: "FEE2E2",
    STATUS_OUTDATED:      "DBEAFE",
    STATUS_GAP:           "EDE9FE",
    STATUS_REVIEW:        "FFEDD5",
    STATUS_NC:            "F3F4F6",
}

# ---------------------------------------------------------------------------
# Typography
# ---------------------------------------------------------------------------

FONT_HEADER = "DejaVu Sans"        # Bold for titles & dividers (Cyrillic-safe)
FONT_BODY = "DejaVu Sans"          # Regular for body text & table cells
FONT_MONO = "DejaVu Sans Mono"     # IDs (D01, RV-001, ПАРА-001)

SIZE_TITLE_PT = 36
SIZE_DIVIDER_PT = 44
SIZE_KPI_VALUE_PT = 60
SIZE_KPI_LABEL_PT = 14
SIZE_BULLET_PT = 16
SIZE_TABLE_HEADER_PT = 11
SIZE_TABLE_BODY_PT = 9
SIZE_FOOTER_PT = 9
SIZE_CAPTION_PT = 11

# ---------------------------------------------------------------------------
# Slide geometry (16:9 widescreen, EMU-friendly inches)
# ---------------------------------------------------------------------------

SLIDE_W_IN = 13.333
SLIDE_H_IN = 7.5
MARGIN_IN = 0.5
TITLE_BAR_H_IN = 0.9
FOOTER_BAR_H_IN = 0.4
CONTENT_H_IN = SLIDE_H_IN - TITLE_BAR_H_IN - FOOTER_BAR_H_IN - 2 * MARGIN_IN

# ---------------------------------------------------------------------------
# Localization helpers
# ---------------------------------------------------------------------------

# Russian status labels (re-exported from forensic_render for one-stop import).
__all__ = [
    "OCEAN",
    "STATUS_HEX",
    "STATUS_TINT_BG",
    "STATUS_GLYPHS_BIG",
    "STATUS_RU",
    "STATUS_PALETTE",
    "STATUS_TO_MARK",
    "V8_STATUSES",
    "FONT_HEADER",
    "FONT_BODY",
    "FONT_MONO",
    "SIZE_TITLE_PT",
    "SIZE_DIVIDER_PT",
    "SIZE_KPI_VALUE_PT",
    "SIZE_KPI_LABEL_PT",
    "SIZE_BULLET_PT",
    "SIZE_TABLE_HEADER_PT",
    "SIZE_TABLE_BODY_PT",
    "SIZE_FOOTER_PT",
    "SIZE_CAPTION_PT",
    "SIZE_HERO_STAT_PT",
    "SIZE_EVENT_QUOTE_PT",
    "SIZE_THEME_TITLE_PT",
    "SLIDE_W_IN",
    "SLIDE_H_IN",
    "MARGIN_IN",
    "TITLE_BAR_H_IN",
    "FOOTER_BAR_H_IN",
    "CONTENT_H_IN",
]
