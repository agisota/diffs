"""Offline rebuild CLI for forensic v8 bundles.

Usage:
    python -m docdiffops.forensic_cli rebuild <bundle.json> --out <dir>
    python -m docdiffops.forensic_cli compare <old.json> <new.json> --out <delta.json>

``rebuild`` reads a saved bundle JSON, optionally applies the actions catalogue,
and re-renders all five artifacts into ``--out``.

``compare`` loads two saved bundles and writes a delta report JSON.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .forensic_actions import apply_actions_to_bundle
from .forensic_delta import compare_bundles
from .forensic_render import (
    render_v8_docx_explanatory,
    render_v8_docx_redgreen,
    render_v8_pdf_summary,
    render_v8_xlsx,
)


def cmd_rebuild(args: argparse.Namespace) -> int:
    bundle_path = Path(args.bundle)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    corpus = "migration_v8" if args.with_actions else None
    if args.with_actions:
        bundle = apply_actions_to_bundle(bundle, corpus=corpus)

    (out_dir / "bundle.json").write_text(
        json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    render_v8_xlsx(bundle, out_dir / "forensic_v8.xlsx")
    render_v8_docx_explanatory(bundle, out_dir / "forensic_v8_explanatory.docx")
    render_v8_docx_redgreen(bundle, out_dir / "forensic_v8_redgreen.docx")
    render_v8_pdf_summary(bundle, out_dir / "forensic_v8_summary.pdf")

    print(f"rebuilt 5 artifacts under {out_dir}")
    return 0


def cmd_compare(args: argparse.Namespace) -> int:
    old_bundle = json.loads(Path(args.old_bundle).read_text(encoding="utf-8"))
    new_bundle = json.loads(Path(args.new_bundle).read_text(encoding="utf-8"))
    try:
        delta = compare_bundles(old_bundle, new_bundle)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(delta, ensure_ascii=False, indent=2), encoding="utf-8")
    changed = delta["control_numbers"]["pairs_changed"]
    print(f"delta written to {out} ({changed} pair(s) changed)")

    if args.render_artifacts:
        from .forensic_delta_render import (
            render_delta_docx, render_delta_pdf, render_delta_xlsx,
        )
        artifact_dir = out.parent
        stem = out.stem
        render_delta_xlsx(delta, artifact_dir / f"{stem}.xlsx")
        render_delta_docx(delta, artifact_dir / f"{stem}.docx")
        render_delta_pdf(delta, artifact_dir / f"{stem}.pdf")
        print(f"rendered artifacts: {stem}.xlsx, {stem}.docx, {stem}.pdf "
              f"in {artifact_dir}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="forensic_cli")
    sub = parser.add_subparsers(dest="cmd", required=True)

    rb = sub.add_parser("rebuild", help="Rebuild bundle artifacts from saved JSON")
    rb.add_argument("bundle", help="Path to bundle.json")
    rb.add_argument("--out", required=True, help="Output directory")
    rb.add_argument("--with-actions", action="store_true",
                    help="Apply v8.1 actions catalogue (migration_v8 corpus)")
    rb.set_defaults(func=cmd_rebuild)

    cmp = sub.add_parser("compare", help="Compare two forensic bundles, write delta JSON")
    cmp.add_argument("old_bundle", help="Path to baseline bundle.json")
    cmp.add_argument("new_bundle", help="Path to current bundle.json")
    cmp.add_argument("--out", required=True, help="Output delta JSON path")
    cmp.add_argument("--render-artifacts", action="store_true",
                     help="Also render .xlsx, .docx, .pdf alongside the delta JSON")
    cmp.set_defaults(func=cmd_compare)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
