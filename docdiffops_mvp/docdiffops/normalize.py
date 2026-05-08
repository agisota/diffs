from __future__ import annotations

import shutil
from pathlib import Path

from .utils import has_binary, run_cmd, safe_name

PDF_EXTS = {".pdf"}
OFFICE_EXTS = {".doc", ".docx", ".ppt", ".pptx", ".xls", ".xlsx", ".odt", ".ods", ".odp"}
TEXT_EXTS = {".txt", ".md", ".csv", ".json", ".xml", ".html", ".htm"}


def convert_to_canonical_pdf(raw_path: Path, out_dir: Path) -> Path | None:
    """Return a canonical PDF path when possible. Uses LibreOffice for Office formats.

    PDF is the visual/evidence layer: bbox highlights should point to this.
    If conversion is impossible, return None and the pipeline still produces text/XLSX/DOCX reports.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    ext = raw_path.suffix.lower()
    if ext in PDF_EXTS:
        dst = out_dir / f"{raw_path.stem}.canonical.pdf"
        shutil.copy2(raw_path, dst)
        return dst

    if ext in OFFICE_EXTS:
        if not has_binary("libreoffice") and not has_binary("soffice"):
            return None
        cmd_bin = "libreoffice" if has_binary("libreoffice") else "soffice"
        rc, stdout, stderr = run_cmd([
            cmd_bin,
            "--headless",
            "--convert-to",
            "pdf",
            "--outdir",
            str(out_dir),
            str(raw_path),
        ], timeout=600)
        if rc != 0:
            return None
        # LibreOffice writes <stem>.pdf
        produced = out_dir / f"{raw_path.stem}.pdf"
        if produced.exists():
            dst = out_dir / f"{safe_name(raw_path.stem)}.canonical.pdf"
            if produced != dst:
                produced.replace(dst)
            return dst
    return None
