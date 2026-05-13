"""End-to-end orchestrator for the v10 presentation bundle.

Runs the full build pipeline in dependency order:
  1. ``charts.build_all_charts()`` — generate the 18 PNGs (10 base + 5 new + 4 microcharts).
  2. ``pptx_builder.build_pptx()`` — assemble the 153-slide PPTX.
  3. ``docx_builder.build_docx()`` — render the parallel DOCX.
  4. ``html_builder.build_html()`` — render the HTML one-pager.
  5. ``xlsx_summary.build_xlsx()`` — assemble the 17-sheet consolidated Excel.
  6. ``soffice --headless --convert-to pdf`` — export PDF from the PPTX.

All outputs land in ``migration_v10_out/presentation/`` (PPTX/PDF/DOCX/HTML)
plus ``migration_v10_out/Сводный_отчёт_v10.xlsx`` (consolidated workbook).

Run from ``docdiffops_mvp/``:
    python -m scripts.presentation_v10.build_all
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import time
from pathlib import Path

from .charts import build_all_charts
from .data_loader import REPO_ROOT, load_data
from .docx_builder import build_docx
from .html_builder import build_html
from .pptx_builder import build_pptx
from .xlsx_summary import build_xlsx

OUT_DIR = REPO_ROOT / "migration_v10_out" / "presentation"
ASSETS_DIR = OUT_DIR / "assets"
PPTX_PATH = OUT_DIR / "DocDiffOps_v10_presentation.pptx"
DOCX_PATH = OUT_DIR / "DocDiffOps_v10_presentation.docx"
HTML_PATH = OUT_DIR / "DocDiffOps_v10_presentation.html"
PDF_PATH = OUT_DIR / "DocDiffOps_v10_presentation.pdf"
XLSX_PATH = REPO_ROOT / "migration_v10_out" / "Сводный_отчёт_v10.xlsx"


def _kb(path: Path) -> int:
    return path.stat().st_size // 1024


def _step(label: str) -> None:
    print(f"\n=== {label} ===", flush=True)


def _fail(msg: str) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    t0 = time.time()

    _step("1/6 Loading bundle data")
    data = load_data()
    cn = data.control_numbers
    print(f"docs={cn['documents']} pairs={cn['pairs']} events={cn['events']}"
          f" qa={data.qa['verdict']} ({data.qa['passed']}/{data.qa['total']})")

    _step("2/6 Generating charts")
    charts = build_all_charts(ASSETS_DIR, data=data)
    for name, path in charts.items():
        print(f"  {name}: {_kb(path)} KB")

    _step("3/6 Building PPTX")
    build_pptx(PPTX_PATH, data=data)
    print(f"  {PPTX_PATH.name}: {_kb(PPTX_PATH)} KB")

    _step("4/6 Building DOCX + HTML")
    build_docx(DOCX_PATH, data=data)
    print(f"  {DOCX_PATH.name}: {_kb(DOCX_PATH)} KB")
    build_html(HTML_PATH, data=data)
    print(f"  {HTML_PATH.name}: {_kb(HTML_PATH)} KB")

    _step("5/6 Building consolidated XLSX")
    build_xlsx(XLSX_PATH, data=data)
    print(f"  {XLSX_PATH.name}: {_kb(XLSX_PATH)} KB")

    _step("6/6 Converting PPTX -> PDF (soffice)")
    if shutil.which("soffice") is None:
        _fail("soffice not found in PATH; cannot produce PDF")
    proc = subprocess.run(
        ["soffice", "--headless", "--convert-to", "pdf",
         str(PPTX_PATH), "--outdir", str(OUT_DIR)],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        _fail(f"soffice failed: {proc.stderr.strip()}")
    if not PDF_PATH.exists():
        _fail(f"expected PDF not produced: {PDF_PATH}")
    print(f"  {PDF_PATH.name}: {_kb(PDF_PATH)} KB")

    elapsed = time.time() - t0
    _step(f"DONE in {elapsed:.1f}s")
    for p in (PPTX_PATH, PDF_PATH, DOCX_PATH, HTML_PATH, XLSX_PATH):
        print(f"  {p.name:50s} {_kb(p):>6} KB")


if __name__ == "__main__":
    main()
