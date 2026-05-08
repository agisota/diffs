# DocDiffOps

Production pipeline for all-to-all document comparison across PDF, DOCX, PPTX, XLSX, HTML and TXT.
Outputs: red/green PDF, DOCX track-changes report, XLSX evidence matrix, executive diff, JSONL events.

## Status

Pre-implementation. This repo is the planning seed for `/ultraplan`.

## Layout

```
.
├── README.md
├── diff.md                    # Full architectural brief (scope document)
├── docdiffops_mvp/            # Reference MVP — FastAPI + Celery + LibreOffice + PyMuPDF
│   ├── docdiffops/            # Python package (main, worker, pipeline, normalize, extract, compare, render_*)
│   ├── samples/sources.yml
│   ├── Dockerfile
│   ├── docker-compose.yml
│   ├── requirements.txt
│   └── README.md
├── input/                     # All comparison inputs
│   ├── sources.md             # Index: filename → URL → source rank
│   ├── concept_2026_2030_kremlin.html
│   ├── concept_2019_2025_ukaz_622.pdf
│   ├── fz_109_migration_registration.html
│   ├── rasporjazenie_30r_2024.pdf
│   ├── klerk_normative_summary.html
│   ├── mineconomy_migration_index.html
│   ├── vciom_migration_2026.pdf
│   ├── internal_neuron_manual_v2.pdf
│   └── sample_neuron_comparison_brief.xlsx
└── docdiffops_mvp.zip         # Original archive (kept for traceability)
```

## Constraints (from brief)

- All-to-all comparison; `anchor_doc_id` only affects report rendering, never recompute
- Cache by `sha256 + extractor_version + comparator_version`
- High-risk events require reviewer decision
- Source ranking: `rank 1` (official NPA) > `rank 2` (departmental) > `rank 3` (analytics/presentation)
- `rank 3` cannot "refute" `rank 1`
- Deterministic evidence layer first, semantic LLM comparator second

## Deliverables (D1–D7)

1. Unified API service (FastAPI: batches, upload, run, artifacts, download)
2. Worker pipeline (Celery + Redis)
3. All-to-all diff graph
4. `evidence_matrix.xlsx` (summary, source inventory, pair matrix, diff events, review queue)
5. `pagewise_redgreen.pdf` per pair
6. `track_changes.docx` per pair (OOXML w:ins/w:del)
7. Machine outputs: `diff_events.jsonl`, `pair_summary.json`, `diff_events_all.jsonl`

See `diff.md` for the complete brief, sprint plan, skills activation order, acceptance criteria, and data model.

## How to start MVP

```bash
cd docdiffops_mvp
docker compose up --build
# Swagger UI: http://localhost:8000/docs
```

## Run the planning batch

Once API is up, upload everything from `input/` and run all-to-all. See `diff.md` §3 for curl recipes.
