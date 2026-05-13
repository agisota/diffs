"""DocDiffOps v10 presentation builder.

Renders one storyline (~120 slides) into 4 paritetic formats:
  * PPTX (python-pptx) — primary deliverable
  * DOCX (python-docx) — same content as a Word document
  * HTML (Jinja2)      — single-file one-pager with inline CSS/base64 images
  * PDF (soffice)      — exported from PPTX via LibreOffice headless

Source of truth: ``migration_v10_out/`` (bundle.json + 18 CSV + trend/delta/qa).
Theme = Ocean Gradient overlay on the immutable status palette from
``docdiffops.forensic_render``.
"""
from __future__ import annotations
