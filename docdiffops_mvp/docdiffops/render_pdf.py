from __future__ import annotations

from pathlib import Path
from typing import Any

import fitz


def _annotate_events(doc: fitz.Document, events: list[dict[str, Any]], side: str) -> int:
    count = 0
    for e in events:
        ev = e.get(side) or {}
        page_no = ev.get("page_no")
        bbox = ev.get("bbox")
        if not page_no or not bbox:
            continue
        try:
            page = doc[int(page_no) - 1]
            rect = fitz.Rect(*[float(x) for x in bbox])
        except Exception:
            continue
        status = e.get("status")
        if side == "lhs" and status in {"deleted", "partial", "modified", "contradicts"}:
            color = (1, 0, 0)  # red
        elif side == "rhs" and status in {"added", "partial", "modified", "contradicts"}:
            color = (0, 0.65, 0)  # green
        else:
            continue
        annot = page.add_rect_annot(rect)
        annot.set_colors(stroke=color, fill=color)
        annot.set_opacity(0.18)
        annot.set_border(width=1)
        annot.update()
        count += 1
    return count


def _render_side_by_side(lhs_doc: fitz.Document, rhs_doc: fitz.Document, out_pdf: Path, lhs_name: str, rhs_name: str):
    report = fitz.open()
    max_pages = max(len(lhs_doc), len(rhs_doc))
    page_w, page_h = 1190, 842
    margin = 24
    header_h = 34
    gap = 18
    col_w = (page_w - 2 * margin - gap) / 2
    box_h = page_h - 2 * margin - header_h

    for i in range(max_pages):
        rp = report.new_page(width=page_w, height=page_h)
        rp.insert_text((margin, 22), f"LHS page {i+1}: {lhs_name}", fontsize=10)
        rp.insert_text((margin + col_w + gap, 22), f"RHS page {i+1}: {rhs_name}", fontsize=10)
        for src_doc, x in [(lhs_doc, margin), (rhs_doc, margin + col_w + gap)]:
            rect = fitz.Rect(x, margin + header_h, x + col_w, margin + header_h + box_h)
            if i >= len(src_doc):
                rp.insert_text((rect.x0 + 20, rect.y0 + 40), "NO PAGE", fontsize=18)
                continue
            page = src_doc[i]
            pix = page.get_pixmap(matrix=fitz.Matrix(1.25, 1.25), alpha=False, annots=True)
            ratio = min(rect.width / pix.width, rect.height / pix.height)
            img_rect = fitz.Rect(rect.x0, rect.y0, rect.x0 + pix.width * ratio, rect.y0 + pix.height * ratio)
            rp.insert_image(img_rect, pixmap=pix)
    out_pdf.parent.mkdir(parents=True, exist_ok=True)
    report.save(out_pdf)


def render_pair_redgreen_pdf(lhs_pdf: Path, rhs_pdf: Path, events: list[dict[str, Any]], out_dir: Path, lhs_name: str, rhs_name: str) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    lhs_doc = fitz.open(lhs_pdf)
    rhs_doc = fitz.open(rhs_pdf)
    lhs_count = _annotate_events(lhs_doc, events, "lhs")
    rhs_count = _annotate_events(rhs_doc, events, "rhs")

    lhs_annot = out_dir / "lhs_red.pdf"
    rhs_annot = out_dir / "rhs_green.pdf"
    lhs_doc.save(lhs_annot)
    rhs_doc.save(rhs_annot)

    lhs_doc2 = fitz.open(lhs_annot)
    rhs_doc2 = fitz.open(rhs_annot)
    out_pdf = out_dir / "pagewise_redgreen.pdf"
    _render_side_by_side(lhs_doc2, rhs_doc2, out_pdf, lhs_name, rhs_name)
    return {"path": out_pdf, "lhs_annotations": lhs_count, "rhs_annotations": rhs_count}
