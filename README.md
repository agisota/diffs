# DocDiffOps

Production pipeline for all-to-all document comparison across PDF, DOCX, PPTX, XLSX, HTML and TXT.
Outputs: red/green PDF, DOCX track-changes report, XLSX evidence matrix, executive diff, JSONL events.

## Status

**LIVE at https://diff.zed.md** — Sprints 1, 2, and 3 shipped. Web UI on `/`,
Swagger on `/docs`. Service is anonymous (no auth) and not certified for PII.

| Sprint | Status | What landed |
|---|---|---|
| 1 | ✅ done | Postgres + Alembic, repository + dual-write, read cutover, source-registry, storage abstraction, content-addressed cache |
| 2 | ✅ done | XLSX (10 sheets), Executive DOCX, full HTML report, PDF event_id labels, web UI SPA |
| 3 | ✅ done | RU legal terms + refs parser, structural chunkers (NPA/Concept/GovPlan), legal_structural_diff, source-rank gate, claim_extractor + claim_validation |
| 4 | ✅ done | review API, anchor rerender, audit log, reviewer UI controls in SPA |
| 5 | partial | cache + batch prune CLI (PR-5.4), docs (PR-5.6); deferred: OTEL/Prometheus, semantic LLM comparator, scheduled URL polling |

## Quick start

```bash
# Local development
cd docdiffops_mvp
docker compose up --build
# → http://localhost:8000/ (web UI), /docs (Swagger), /health (JSON)

# Production deploy
ssh root@<host>
git clone https://github.com/agisota/diffs.git /opt/diffs
cd /opt/diffs/docdiffops_mvp
docker compose up -d --build
docker compose exec api alembic upgrade head
```

## Pipeline data flow

```
upload (POST /batches/{id}/documents, optional source_urls)
  → classify(filename, url, content_head) → (doc_type, source_rank)
  → dual-write Postgres + JSON state
  → cache extract by sha256+EXTRACTOR_VERSION

run (POST /batches/{id}/run?profile=fast&sync=true)
  → for each pair (all-to-all, C(N,2)):
      block_semantic_diff (rapidfuzz, every pair)
    + legal_structural_diff (LEGAL_NPA / LEGAL_CONCEPT / GOV_PLAN both sides)
    + claim_validation (rank-3 ↔ rank-1 pairs)
    ⤷ apply_rank_gate inline (rank-3 cannot refute rank-1)
  → render (xlsx, executive md+docx, html, pdf, jsonl)
  → cache compare by lhs_sha+rhs_sha+COMPARATOR_VERSION

review (POST /events/{id}/review)
  → write ReviewDecision row
  → write AuditLog entry

prune (python -m docdiffops.cli_prune --days 30)
  → drop cache/* and batches/* older than RETENTION_DAYS
```

## Env flags

| Flag | Default | Effect |
|---|---|---|
| `DUAL_WRITE_ENABLED` | true | DB write enabled (PR-1.2) |
| `READ_FROM_DB` | true | Reads via repository.to_state_dict; JSON fallback when DB has fewer rows |
| `WRITE_JSON_STATE` | true | state.json + per-pair JSONL still written (belt-and-suspenders) |
| `STORAGE_BACKEND` | fs | `fs` or `minio` (S3Storage scaffolded; MVP uses fs) |
| `EXTRACTOR_VERSION` | 2.A.0 | Bump invalidates extract cache |
| `COMPARATOR_VERSION` | 1.0.0 | Bump invalidates compare cache |
| `RETENTION_DAYS` | 30 | cli_prune retention SLA |

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
