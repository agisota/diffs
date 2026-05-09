# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repo layout

The actual application is a Python package nested one directory down. Most commands must be run from `docdiffops_mvp/`, not the repo root.

```
diff/
├── README.md                  # Public-facing overview, sprint status, env flags
├── diff.md                    # Full architectural brief (scope document)
├── PLAN.md                    # Sprint plan + ADRs (PR-1.x .. PR-5.x)
├── WORKLOG.md                 # Running development notes
├── docdiffops_mvp/            # ← Run all dev commands from here
│   ├── docdiffops/            # Python package
│   ├── tests/{unit,integration}
│   ├── scripts/forensic_quality_check.sh
│   ├── docker-compose.yml     # api + worker + postgres + redis
│   ├── alembic.ini
│   ├── mypy.ini               # strict on 6 forensic_* modules
│   ├── pytest.ini
│   └── Makefile
├── input/                     # Comparison inputs (legal docs, analytics)
├── migration_v7_evidence/     # Reference outputs from a prior run
├── migration_v8_out/          # Reference v8 forensic bundle (the contract)
└── migration_v9_integral/     # Newer reference bundle
```

## Common commands

All from `docdiffops_mvp/` unless noted. The repo expects a `.venv` at `docdiffops_mvp/.venv` for the Makefile and quality script.

### Develop locally

```bash
cd docdiffops_mvp
docker compose up --build
# api → http://localhost:8000  ·  /docs (Swagger)  ·  /  (SPA web UI)
docker compose exec api alembic upgrade head    # apply migrations
```

### Run the test suite

```bash
make test                  # full pytest suite (tests/)
make test-forensic         # forensic-only subset (matches CI path-filter)
make check                 # test-forensic + mypy on forensic modules
make quality               # = scripts/forensic_quality_check.sh (full gate)
make coverage              # alias of quality

# Single test:
.venv/bin/python -m pytest tests/unit/test_forensic_render.py::test_xlsx_renders -q

# Integration tests that need Postgres are gated by the `requires_compose_db`
# marker (see pytest.ini). Either bring up `docker compose up db` or set
# `DATABASE_URL` to a reachable Postgres before running them.
```

### Type-check (strict on forensic modules only)

```bash
make mypy
# Same flags listed explicitly per-module in mypy.ini (mypy issue #11401:
# `strict = True` does not propagate to per-module sections).
```

### Forensic CLI (offline rebuild / delta from saved bundles)

```bash
python -m docdiffops.forensic_cli rebuild path/to/bundle.json --out out/ [--with-actions]
python -m docdiffops.forensic_cli compare old.json new.json --out delta.json [--render-artifacts]
```

### Retention prune (PR-5.4)

```bash
python -m docdiffops.cli_prune --days 30           # default = RETENTION_DAYS env
python -m docdiffops.cli_prune --dry-run           # report only
python -m docdiffops.cli_prune --cache-only        # skip batch dirs
```

### Demo artifacts (smoke check)

```bash
make demo         # writes 4 forensic artifacts to /tmp/forensic_demo/
make clean-demo
```

## High-level architecture

DocDiffOps is an all-to-all document comparison pipeline (PDF/DOCX/PPTX/XLSX/HTML/TXT). It is **deterministic-first, LLM-second**: every claim must have evidence-grade rationale before any semantic verdict rides along.

### Request lifecycle

```
POST /batches                         → create batch (state.create_batch)
POST /batches/{id}/documents          → upload + classify (source_registry.classify)
POST /batches/{id}/run?profile=fast   → pipeline.run_batch (sync) or worker.run_batch_task (Celery)
GET  /batches/{id}/artifacts          → list rendered files
POST /events/{id}/review              → reviewer decision (writes ReviewDecision + AuditLog)
POST /batches/{id}/render?anchor_doc_id=… → re-render only, cache-hit
GET  /batches/{id}/forensic           → v8 forensic JSON bundle
GET  /batches/{a}/forensic/compare/{b} → forensic delta
GET  /forensic/trend?ids=a,b,c         → multi-batch time-series aggregation
```

The web UI is a single-page app served from `/` (`docdiffops/app_html.py` ships the entire HTML inline — it is not a separate frontend build).

### Pipeline stages (`pipeline.py`)

1. **normalize_and_extract** — convert each upload to a canonical PDF (LibreOffice via `normalize.py`), then extract blocks (`extract_any` in `extract.py`). Both stages cache by `sha256 + EXTRACTOR_VERSION`.
2. **run_all_pairs** — for each `C(N,2)` pair:
   - `compare_pair` (rapidfuzz block-level fuzzy match) — every pair
   - `legal_structural_diff` if both sides are LEGAL_NPA / LEGAL_CONCEPT / GOV_PLAN
   - `claim_validation_events` for rank-3 ↔ rank-1 pairs
   - Optional `llm_pair_diff` (replaces or augments fuzzy events; PR-5.7)
   - Optional semantic verdict ride-along (PR-5.5)
   - `apply_rank_gate` enforces the **rank-3 cannot refute rank-1** invariant
3. **render** — XLSX (10 sheets), executive MD+DOCX, full HTML, per-pair red/green PDF, per-pair track-changes DOCX, JSONL events, plus the v8 forensic bundle (XLSX/DOCX/PDF/JSON).
4. Compare results cache by `(lhs_sha, rhs_sha) + COMPARATOR_VERSION`. Cache key construction is order-independent (`cache.make_key` sorts inputs).

### Source ranking (load-bearing)

- **rank 1** = official NPA (federal laws, decrees)
- **rank 2** = departmental
- **rank 3** = analytics, presentations
- `apply_rank_gate` (in `legal/rank_gate.py`) enforces that rank-3 events flagged as `contradicts` against rank-1 are downgraded to `manual_review`. This is enforced inline in the comparator, **and again** inside `forensic.aggregate_pair_status_v8`. Don't re-implement this rule elsewhere.

### Storage / state plumbing (`state.py`)

The dual-write pattern is governed by three env flags:

| Flag | Default | Effect |
|---|---|---|
| `DUAL_WRITE_ENABLED` | true | DB write side enabled |
| `READ_FROM_DB` | true | Reads via `repository.to_state_dict`; JSON fallback when DB has fewer rows |
| `WRITE_JSON_STATE` | true | `state.json` + per-pair JSONL still written (belt-and-suspenders) |

`load_state` merges DB rows with JSON-only fields (`config`, `runs`, `metrics`, per-document file paths). The merge prefers JSON lists when their length exceeds the DB's — this catches partial dual-write failures and the upload→run gap. **Don't change `_merge_db_with_json` without re-reading its docstring**: counting beats existence-checking on this surface.

DB calls in pipeline / state are wrapped in `_safe(...)` — failures log and swallow so the JSON write remains authoritative.

### Forensic v8 subsystem (`docdiffops/forensic*.py`)

`forensic.py` is the **single source of truth** for the v8 forensic shape:

- `V8_STATUSES` — exact 7-status scale (`match`, `partial_overlap`, `contradiction`, `outdated`, `source_gap`, `manual_review`, `not_comparable`)
- `EVENT_STATUS_TO_V8` — maps DocDiffOps event vocabulary to v8 vocabulary
- `aggregate_pair_status_v8` — pair-status aggregator with the rank-3 ↔ rank-1 invariant
- `build_forensic_bundle` — pure function returning the v8 JSON-serialisable bundle

The forensic system has its own CI gate (`.github/workflows/forensic-ci.yml`) that runs on path changes to `docdiffops/forensic*.py`, the matching tests, `mypy.ini`, the quality script, or the Makefile. **mypy strict applies only to the 6 forensic modules** (`forensic`, `forensic_schema`, `forensic_actions`, `forensic_delta`, `forensic_trend`, `forensic_cli`); the rest of the package is unchecked.

Renderers (`forensic_render.py`, `forensic_delta_render.py`) consume the bundle dict and emit XLSX/DOCX/PDF in **ru-RU** with a shared color palette. Reuse the vocabulary in `forensic_render` (`PALETTE`, `STATUS_RU`, `STATUS_PALETTE`, `_docx_set_cell_bg`, `_pdf_page_decoration`) — don't re-define palettes per renderer. See `docs/FORENSIC_API.md` for the full surface.

### v10 forensic bundle (Sprint 6, opt-in)

Setting `V10_BUNDLE_ENABLED=true` extends `pipeline.run_batch` with a final stage that produces 8 v10-quality artifacts:

- 4 BOM CSVs: `correlation_matrix`, `dependency_graph`, `claim_provenance`, `coverage_heatmap`
- 14-sheet XLSX with conditional formatting + hyperlinks + heatmap color scales
- 10-chapter Пояснительная записка (DOCX + PDF, Cyrillic-safe NotoSans→DejaVu fallback)
- Integral N×N matrix PDF (A3 landscape if N≥13, else A4)

API endpoints:
- `GET /batches/{id}/forensic/v10` — JSON with 8 download URLs
- `GET /batches/{id}/forensic/{kind}` — supports new kinds: `xlsx_v10`, `note_docx`, `note_pdf`, `integral_matrix_pdf`, `correlation_matrix_csv`, `dependency_graph_csv`, `claim_provenance_csv`, `coverage_heatmap_csv`

Production modules: `forensic_correlations`, `forensic_render` (extended), `forensic_note`. All under mypy strict.

E2E smoke: `bash scripts/v10_smoke.sh` (dev-time only; requires `docker compose up` + sample files in `input/`).

### Cache layer (`cache.py`)

```
cache_key = sha256("|".join([scope, version, *sorted(content_sha256s)]))
```

Inputs are sorted, so `compare_key(lhs, rhs) == compare_key(rhs, lhs)`. Storage backend is whatever `get_storage()` returns (`fs` or `minio` per `STORAGE_BACKEND`). Files live at `cache/{scope}/{key}.json`.

To invalidate the world without code changes: bump `EXTRACTOR_VERSION` (default `2.A.0`) or `COMPARATOR_VERSION` (default `1.0.0`) via env.

### DB schema (`db/models.py`)

Tables: `batches`, `documents`, `document_versions`, `pair_runs`, `diff_events`, `review_decisions`, `artifacts`, `audit_log`, `source_registry`. All FKs cascade on batch delete except `pair_runs.{lhs,rhs}_document_version_id` which restricts. `event_id` on `diff_events` is exposed as a Python-side property aliasing the `id` PK column.

Migrations live in `docdiffops/db/migrations/versions/`. Use Alembic from inside `docdiffops_mvp/`:

```bash
alembic revision --autogenerate -m "your message"
alembic upgrade head
alembic downgrade -1
```

Tests use SQLite in-memory automatically when `TESTING=1` (see `settings.py`).

### Worker (`worker.py`)

A single Celery app (`docdiffops.worker.celery_app`) with one task `run_batch_task`. Broker + backend are both Redis (`REDIS_URL`). When `POST /batches/{id}/run?sync=true`, the API calls `pipeline.run_batch` directly and skips Celery — useful for local dev and tests.

## Important constraints

These come from `diff.md` §scope and are enforced in code; check before changing comparator/forensic behavior:

- All-to-all comparison; `anchor_doc_id` only affects **report rendering**, never recompute. The compare graph is symmetric (PR-1.5 ADR-4).
- Cache by `sha256 + extractor_version + comparator_version`.
- High-risk events (`status == manual_review` or `review_required == true`) require a reviewer decision via `POST /events/{id}/review`.
- `rank 3` cannot "refute" `rank 1` — enforced by `apply_rank_gate`.
- Deterministic evidence layer first; semantic LLM comparator is **opt-in** (`SEMANTIC_COMPARATOR_ENABLED=true`) and rides along for A/B comparison until reviewers sign off.
- Service is **anonymous** (no auth) and **not certified for PII** — don't add code that assumes either.

## Environment flags

| Flag | Default | Effect |
|---|---|---|
| `DATA_DIR` | `./data` | All batches + cache live here |
| `DATABASE_URL` | compose Postgres | `sqlite:///:memory:` when `TESTING=1` |
| `REDIS_URL` | `redis://localhost:6379/0` | Celery broker + backend |
| `DUAL_WRITE_ENABLED` | `true` | Toggle DB writes |
| `READ_FROM_DB` | `true` | Reads via DB; JSON fallback when DB sparser |
| `WRITE_JSON_STATE` | `true` | `state.json` still written (will flip to false in PR-1.4/1.6) |
| `STORAGE_BACKEND` | `fs` | `fs` or `minio` |
| `EXTRACTOR_VERSION` | `2.A.0` | Bump to invalidate extract cache |
| `COMPARATOR_VERSION` | `1.0.0` | Bump to invalidate compare cache |
| `RETENTION_DAYS` | `30` | `cli_prune` retention SLA |
| `SEMANTIC_COMPARATOR_ENABLED` | `false` | LLM ride-along verdict on `claim_validation` |
| `LLM_API_BASE` / `LLM_API_KEY` / `LLM_MODEL` | OpenAI-compat | Provider-agnostic |
| `SEMANTIC_MAX_CLAIMS_PER_PAIR` | `10` | LLM cost guard |
| `LLM_PAIR_DIFF_ENABLED` | `false` | Replace fuzzy block-diff events with curated LLM list (PR-5.7) |
| `LLM_PAIR_DIFF_MODEL` | — | Model id for pair-diff |
| `LLM_PAIR_DIFF_CHAR_BUDGET` | `12000` | Per-pair character budget |
| `KEEP_FUZZY_WITH_LLM_PAIR_DIFF` | `false` | Retain both layers when LLM pair-diff is on |
| `LLM_PAIR_SUMMARY_ENABLED` | `true` | Per-pair LLM narrative |
| `V10_BUNDLE_ENABLED` | `false` | Sprint 6: when `true`, after `pipeline.run_batch` produces v10-quality bundle (correlations CSVs + 14-sheet XLSX + 10-chapter note + integral matrix PDF) in `batch_dir/reports/v10/`. Endpoints: `GET /batches/{id}/forensic/v10` + 8 new kinds in `/batches/{id}/forensic/{kind}`. |

## Conventions

- Python ≥ 3.10 syntax; runtime container is 3.11. Use modern `X | None` / `list[T]` annotations and `from __future__ import annotations`.
- All ID prefixes are stable: `bat_*` (batch), `doc_*`, `dv_*` (document version), `evt_*`, `rd_*` (review decision), `ae_*` (audit entry). Generated via `utils.stable_id` from deterministic input strings.
- Renderers and pipeline write to `data/batches/{batch_id}/reports/...`; the forensic v8 bundle lives at `data/batches/{batch_id}/reports/forensic_v8/bundle.json`.
- When in doubt about a forensic contract, the reference truth is `migration_v8_out/` (or the newer `migration_v9_integral/`); `forensic.py` was lifted from the script that produced them.
