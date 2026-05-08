# DocDiffOps — Implementation Plan

## 0. Executive summary

DocDiffOps is a reproducible document-comparison service for Russian legal/policy corpora: NPA, concepts, government plans, analytics presentations, web digests. It builds a full all-to-all pair graph once, caches everything by `sha256 + extractor_version + comparator_version`, and re-renders reports when the user changes the anchor document. Two architectural choices distinguish it from another diff script: (1) **anchor is a view, not a compute mode** — comparisons are symmetric and persistent, only red/green direction is applied at render time; (2) **deterministic evidence layer ships before semantic LLM comparator** — every diff event must carry quote, page, bbox, source_rank before a model is allowed to call something a "contradiction." The MVP scaffold under `docdiffops_mvp/` covers ingestion, LibreOffice normalization, PyMuPDF extraction, fuzzy block diff, red/green PDF, OOXML synthetic redline DOCX, XLSX matrix, executive markdown — but lives on `state.json` with no caching, no legal chunking, no claim validation, no review loop, no source-rank gating.

## 1. Current state — MVP audit

**`docdiffops/main.py`** — FastAPI app exposing `/health`, `/batches` (POST), `/batches/{id}` (GET), `/batches/{id}/documents` (POST), `/batches/{id}/run` (POST sync/async), `/tasks/{id}`, `/batches/{id}/artifacts`, `/batches/{id}/download/{path}`. Brief expects also `POST /events/{event_id}/review` and `POST /batches/{batch_id}/render?anchor_doc_id=...` — both missing. Path-traversal defense in `download_artifact` is correct. No `/runs/{run_id}/events`. Auth absent.

**`docdiffops/worker.py`** — 16-line Celery wrapper, broker+backend on Redis, `task_track_started=True`, single task `run_batch_task`. Missing: per-stage tasks (normalize/extract/compare/render as separate tasks for retries and observability), priority queues, task routing for fast vs full profile.

**`docdiffops/pipeline.py`** — Three orchestrated steps: `normalize_and_extract`, `run_all_pairs`, `render_global_reports`. `_infer_doc_type` is naive: maps extension to {PRESENTATION, TABLE, WEB_DIGEST, OTHER} — does not distinguish LEGAL_NPA, LEGAL_CONCEPT, GOV_PLAN, ANALYTICS. `source_rank` defaults to 3 for every document, never overridden from config. There is no idempotency check on file sha256 to skip recomputation when `extracted/{doc_id}.json` is already current — `if not extracted_path.exists()` is the only gate, so a comparator-version bump silently reuses old extraction. Per-pair PDF render is wrapped in try/except that swallows the error into `pair["pdf_render_error"]` instead of surfacing it.

**`docdiffops/normalize.py`** — `convert_to_canonical_pdf` calls LibreOffice/soffice headless with 600 s timeout, returns the produced PDF or `None`. HTML is not rendered to PDF (brief lists HTML/CSV/TXT as "text-only" — but red/green PDF cannot be produced without canonical PDF, so HTML pairs lose visual evidence). Concurrent LibreOffice subprocess invocations under a Celery worker with `--concurrency=2` is a known instability source (each worker shares `~/.config/libreoffice` user profile by default) — no per-worker `--user-installation` flag. No retries, no fallback to `unoconv`/`pandoc`.

**`docdiffops/extract.py`** — Six format paths. `extract_pdf` uses PyMuPDF `page.get_text("blocks")` only — no tables, no OCR fallback. `extract_docx` collapses to "page 1" — no pagination, headings/lists/paragraphs all flat. `extract_pptx` reads only `shape.text` — no speaker notes, no images, no smart-art. `extract_xlsx` reads with `data_only=False` so formulas leak as strings (brief wants cell values). `extract_html` loses attributes and structured tables. `extract_text` splits by `\n` with no semantics. No caching layer.

**`docdiffops/compare.py`** — `build_pairs` produces `N*(N-1)/2` combinations. `best_match` uses RapidFuzz `token_set_ratio`. `compare_pair` with thresholds 92/78 is the only comparator. `infer_comparison_type` returns one of {claim_validation, legal_or_policy_diff, table_diff, block_semantic_diff} — but only `block_semantic_diff` actually executes; the others are tags, not branches. `classify_severity` honors rank only for `high` escalation, not for status — so a rank-3 PRESENTATION block can produce `contradicts` against rank-1 LEGAL_NPA, violating source hierarchy.

**`docdiffops/render_pdf.py`** — `render_pair_redgreen_pdf` annotates LHS red, RHS green, renders side-by-side 1190×842 at 1.25x. Annotations are visible. Issues: re-opens saved annotated PDFs (doubles I/O); no link from rect annotation back to `event_id` — brief's "every PDF highlight links to evidence_matrix row" is unmet (would need `annot.set_info({"title": event_id})` plus TOC sidecar).

**`docdiffops/render_docx.py`** — Builds a fresh DOCX with `add_ins_run`/`add_del_run` using OOXML `w:ins`/`w:del` elements (correct OOXML spelling, proper `xml:space=preserve`, ISO date). `limit=200` truncates events — for a 36-pair batch that is fine for one pair, but global redline report would lose data. This is a synthetic redline (a new diff document), NOT a true track-changes patch on the original DOCX. Brief allows synthetic for non-DOCX inputs but requires real redline for DOCX↔DOCX.

**`docdiffops/render_xlsx.py`** — Sheets: `00_summary`, `01_source_inventory`, `02_pair_matrix`, `03_diff_events_all`, `04_high_risk`, `05_partial_matches`, `06_review_queue`, `07_added_deleted`. Brief §8.2 lists 13 sheets — missing: `04_contradictions`, `06_not_found`, `07_legal_changes`, `08_claim_validation`, `09_table_diffs`, `11_false_positives`, `12_metrics`. No conditional formatting on severity column, no hyperlink to `pagewise_redgreen.pdf`, no `event_id` cross-link.

**`docdiffops/executive.py`** — Builds plain Markdown. Top-20 high-risk only. No DOCX output despite brief §8.1 requiring `executive_diff.docx`. No coverage section, no top-10 risks, no "claims not confirmed by NPA" bullet — just a sorted dump.

**`docdiffops/state.py`** — JSON file at `{batch_dir}/state.json`. `create_batch` mints `bat_{12hex}`. `add_artifact` deduplicates by `(type, path)`. No transactions, no concurrent-writer protection, no schema migration. Brief explicitly says this must move to Postgres+Alembic by Sprint 1.

**`docdiffops/schemas.py`** — Two Pydantic models: `CreateBatchRequest`, `RunBatchRequest`. `RunBatchRequest.anchor_doc_id` is defined but unused — the run endpoint ignores it. No `DiffEventOut`, no `ReviewDecisionIn`, no API contract for `/events/{id}/review`.

**`docdiffops/settings.py`** — `DATA_DIR`, `REDIS_URL` from env. Missing: `DATABASE_URL`, `S3_ENDPOINT`/`S3_BUCKET`, `EXTRACTOR_VERSION`, `COMPARATOR_VERSION`, `LIBREOFFICE_USER_PROFILE`, log level, OTEL endpoint.

**`docdiffops/utils.py`** — `sha256_file` (1 MB chunks), `stable_id` (sha1, hex-truncated), `safe_name` (NFKD + Cyrillic-aware), `norm_text` (ё→е, NBSP/ZWSP/BOM strip, lowercase), `run_cmd` (subprocess wrapper with timeout). All correct. Missing: deterministic seed exposure for any random-touching code, structured logger.

## 2. Gap analysis vs. brief acceptance criteria

Acceptance criteria assembled from brief §15 ("Минимальный production acceptance checklist") with cross-reference to §18 ("Production acceptance criteria") and §12 ("Acceptance criteria"). Missing first.

| # | Criterion | Source | Status | Note |
|---|-----------|--------|--------|------|
| AC-1 | `docker compose up` brings API + worker + Redis + DB | §15 | 🟡 partial | DB is `state.json`; no Postgres service in compose |
| AC-2 | unchanged documents are not recomputed | §15, §12 cache | ❌ missing | Only `extracted/{id}.json` existence is checked; no extractor/comparator version key |
| AC-3 | `anchor_doc_id` change rerenders reports without recomputing diff | §15, §18 | ❌ missing | `RunBatchRequest.anchor_doc_id` exists but unused; no `/render` endpoint |
| AC-4 | source_rank affects classification (rank 3 cannot refute rank 1) | §13.1, §15 | ❌ missing | `classify_severity` only looks at rank for "high"; status is set independently |
| AC-5 | high-risk events require `reviewer_decision` | §15, §18 | ❌ missing | `review_required` flag is set but no enforcement, no `/events/{id}/review` endpoint |
| AC-6 | NPA compared by article/clause/paragraph, not just by page | §15, §18 legal | ❌ missing | No `npa_chunker.py`, no legal references parsing, no structural diff |
| AC-7 | DOCX↔DOCX produces real track-changes; other formats produce synthetic redline | §18 | 🟡 partial | All pairs get synthetic; no detection of DOCX-DOCX path |
| AC-8 | claim validation for presentations, not literal diff | §12, §13 | ❌ missing | PRESENTATION pairs use the same fuzzy block path; no claim extraction |
| AC-9 | red/green PDF highlights are linked to `event_id` in XLSX | §18 | ❌ missing | Annotations do not carry event_id; XLSX has no PDF link |
| AC-10 | regression tests, false-positive log | §15, §18 | ❌ missing | No tests in repo; no `qa_defect_log.csv` |
| AC-11 | scheduled source polling and on-upload runs | §12.3 | ❌ missing | No scheduler |
| AC-12 | `evidence_matrix.xlsx` has all sheets per §8.2 | §8.2 | 🟡 partial | 8 of 13 sheets present |
| AC-13 | executive layer separate from full evidence, references it | §18 | 🟡 partial | Executive exists, but Markdown only and does not link by event_id |
| AC-14 | every high-risk event has quote/page/bbox/source_rank | §18 | 🟡 partial | Quote/page/bbox present when available; source_rank is in payload but always 3 from upload defaults |
| AC-15 | reproducibility: sha256, extractor version, comparator version stored | §18 | 🟡 partial | sha256 stored; versions not stored |
| AC-16 | `partial`/`contradicts` always have explanation and reviewer comment | §12, §10 quality_policy | 🟡 partial | Explanation present (templated string); reviewer comment is `null` and never enforced |
| AC-17 | reproducible: rerun on same inputs yields same `event_id`/`pair_id` | §14 reproducibility | ✅ done | `stable_id` is a sha1 hash of inputs |
| AC-18 | each diff event has `event_id`, `pair_id`, lhs/rhs `doc_id`, status, severity, confidence | §15 | ✅ done | `make_event` produces all fields |
| AC-19 | all-to-all pairs created with stable `pair_id` | §15, §18 | ✅ done | `build_pairs` + `pair_id` |
| AC-20 | every uploaded document gets `sha256` | §15 | ✅ done | `sha256_file` in upload handler |

## 3. Architecture decisions (ADRs)

### ADR-1: SQLite for MVP, Postgres+Alembic from Sprint 1

**Context.** State currently lives in `state.json` per batch. Concurrent writers are unsafe; cross-batch queries require scanning every directory; Alembic migrations cannot run on JSON.

**Decision.** Keep `state.json` only as **batch snapshot for export and offline replay**. Canonical store moves to Postgres in Sprint 1. Schema: `batches`, `documents`, `document_versions`, `pair_runs`, `diff_events`, `evidences` (split lhs/rhs), `review_decisions`, `artifacts`. Alembic with one revision per schema-touching PR. SQLite is the local-dev default behind `DATABASE_URL=sqlite:///./dev.db`; CI and production run Postgres 16. JSON persistence (`state.py`) is replaced by a thin repository class with the same call signatures so `pipeline.py` does not need a rewrite.

**Consequences.** Adds one container (Postgres) and Alembic to dev. Migration: dual-write for one PR, then read-from-DB cutover, then drop JSON writes (3 PRs). Concurrent batch runs become safe.

### ADR-2: Extractor stack — Docling primary, MarkItDown fast-path, PyMuPDF for bbox/annotations, native fallbacks

**Context.** MVP uses `python-docx`, `python-pptx`, `openpyxl`, `BeautifulSoup`, `PyMuPDF` directly. Each is shallow: `python-pptx` reads only `shape.text`; `python-docx` flattens paragraphs; `openpyxl` reads formulas as strings.

**Decision.** Three-tier extractor with explicit version tagging.
- **Tier A (L1 fast):** MarkItDown — fast-report profile. Markdown only, no bbox.
- **Tier B (L2 structured):** Docling — primary for full profile. Structured JSON with reading order, tables, image bbox. Local CPU mode for sensitive RU legal docs.
- **Tier C (L3 visual evidence):** PyMuPDF — canonical-PDF page images, bbox extraction, annotation insertion. Never replaced; Docling does not annotate PDFs.
- **Fallback:** existing native extractors kept for when Tier A/B fail.

**Consequences.** Adds Docling (~600 MB image with EasyOCR weights) and MarkItDown to `requirements.txt`. Extractor output becomes a normalized internal schema (`ExtractedDocument`) that all tiers map into. `extractor_version` = `2.{tier}.{lib_version}`, included in cache key.

### ADR-3: Semantic LLM comparator deferred until deterministic layer ships

**Context.** Brief §9 ordering and §10 production backlog explicitly mark `semantic-llm-comparator` as "позже / later". An LLM-first comparator produces beautiful, plausible, unverifiable diffs.

**Decision.** No LLM call in the comparison path until four gates close: (1) deterministic fuzzy diff produces stable `event_id` across reruns (achieved); (2) source_rank gating enforced — rank 3 cannot produce `contradicts` vs rank 1; (3) every event has quote+page+bbox+source_rank populated; (4) regression corpus has ≥30 labelled events. Until gate 4 closes, all `manual_review`/`partial`/`contradicts` events flow through the human reviewer; LLM only allowed in a separate "hypothesis" track tagged `comparator_type=llm_hypothesis`, never auto-status.

**Consequences.** Sprint 3's `claim_extractor` may use an LLM to extract claim subject/predicate/object — allowed because that is feature extraction, not comparison. First LLM-based comparator lands in Sprint 5, behind `ENABLE_SEMANTIC_COMPARATOR=false`.

### ADR-4: All-to-all once + anchor-rerender — concrete cache key and invalidation rules

**Context.** Brief §12 invalidation table is the cleanest spec in the document. Misimplementing it produces either silent staleness ("why did the legal status not update after I changed sources.yml") or full recomputation ("why does anchor change take 2 hours").

**Decision.** Cache hierarchy with three levels.
- **Level 1 (extraction cache):** key = `sha256(file) || extractor_version || normalization_profile`. Stored at `data/cache/extract/{key}.json`. Invalidates only when sha256 of the source bytes or `extractor_version` constant changes.
- **Level 2 (pair compare cache):** key = `sha256(lhs_extract.json) || sha256(rhs_extract.json) || comparator_version || comparator_config_hash`. Stored at `data/cache/pairs/{key}.jsonl` (events) + `{key}.summary.json`. Invalidates when either side's extraction changes or when comparator constants/config change.
- **Level 3 (render):** never cached. Render is the cheap step; re-render on every anchor change is correct. Render results live under `data/batches/{batch_id}/reports/` and `data/batches/{batch_id}/pairs/{pair_id}/`.

The constants `EXTRACTOR_VERSION` and `COMPARATOR_VERSION` are defined in `settings.py` and bumped manually in the PR that changes their behavior. Cache writes use atomic temp+rename. The `/batches/{id}/render` endpoint never recomputes — if Level 2 cache miss, return 409 and require explicit `/run`.

**Consequences.** Disk usage grows with corpus history; we add a `cache prune` CLI in Sprint 5. The contract becomes auditable: any reviewer can see why a pair was/wasn't recomputed by inspecting the cache key.

### ADR-5: Source ranking enforcement — preventing rank_3 from "refuting" rank_1

**Context.** MVP `classify_severity` uses rank only to escalate to `high`. Status (`contradicts`, `partial`, etc.) is set by the comparator without consulting rank. This creates the exact failure mode the brief warns about: a VCIOM presentation slide (rank 3) marked as "contradicts" against 109-FZ (rank 1).

**Decision.** Add a **post-classifier rank gate** in `compare.py` that runs after `make_event` and before append:
```
if event.status == "contradicts" and min(rank_lhs, rank_rhs) <= 1 and max(rank_lhs, rank_rhs) >= 3:
    event.status = "manual_review"
    event.explanation_short = "rank-3 source cannot refute rank-1 NPA; converted to manual_review per source hierarchy"
    event.review_required = True
```
Same rule for `deleted`/`added`/`modified` when the higher-ranked side is being "edited" by a lower-ranked side. Encoded as a config block `quality_policy.rank_gate` so the rule is visible, not hidden in code. Rank-2-vs-rank-1 retains `partial` but never `contradicts` for non-`legal_or_policy_diff` comparators.

**Consequences.** `manual_review` queue grows for cross-rank pairs. The reviewer UI must filter by source-rank pair to keep the queue navigable. Adds an explicit `rank_gate_applied: true` flag on the event for audit.

### ADR-6: DOCX redline strategy — direct OOXML w:ins/w:del

**Context.** Two viable approaches: `Python-Redlines` (calls .NET via `pythonnet`) or direct OOXML manipulation via `python-docx`+`lxml`. MVP already implements direct OOXML.

**Decision.** Stay with **direct OOXML w:ins/w:del**. Reasons: container weight (no .NET), determinism (we control exact XML), and brief output is a *report*, not a perfectly-tracked Word edit. For DOCX↔DOCX pairs, augment with `original_with_changes.docx`, produced by walking source DOCX runs and inserting `w:ins`/`w:del` at paragraph boundaries — "real-ish" track changes. We do NOT promise full Word-grade tracked changes (tables, images, comments).

**Consequences.** PR-2.3 ships OOXML helper as `renderers/docx_ooxml.py` used by both synthetic and DOCX↔DOCX paths. Swap to `Python-Redlines` later behind a feature flag if needed — no architectural change.

### ADR-7: Storage — local FS for MVP, S3/MinIO from Sprint 1; key naming scheme

**Context.** MVP uses `./data/batches/{batch_id}/` mounted into containers. Once corpus >few GB or worker scales horizontally, this fails.

**Decision.** S3-compatible storage (MinIO in dev, S3 in prod) in Sprint 1, behind a `Storage` interface with `LocalStorage(base_dir)` and `S3Storage(endpoint, bucket)`. Key naming:
```
batches/{batch_id}/raw/{filename}
batches/{batch_id}/normalized/{doc_id}/canonical.pdf
batches/{batch_id}/extracted/{doc_id}.json
batches/{batch_id}/pairs/{pair_id}/{artifact}
batches/{batch_id}/reports/{artifact}
cache/extract/{sha256_prefix2}/{cache_key}.json
cache/pairs/{sha256_prefix2}/{cache_key}.{events.jsonl|summary.json}
```
Two-char prefix sharding on cache keys keeps listings manageable. Pre-signed download URLs replace `/download/{path}` in production.

**Consequences.** Tests gain MinIO in `docker-compose.test.yml`. Local dev defaults to `LocalStorage`. Object lifecycle (auto-delete cache >90 days) configurable per bucket.

### ADR-8: Russian legal NPA chunker — heuristics-first, LLM-assisted later

**Context.** Russian NPA structure (`статья → часть → пункт → подпункт → абзац`) is highly regular. Label patterns are deterministic: `Статья N.`, `1.`, `(1)`, `а)`, `1)`. Concept structure is similar. Edge cases (continued numbering, footnotes, parenthetical refs) are not LLM-shaped problems.

**Decision.** Sprint 3 ships `legal/npa_chunker.py` and `legal/concept_chunker.py` as regex+state-machine with a published grammar. LLM segmentation is a fallback — invoked when (a) the regex chunker yields zero structural anchors or (b) user tags doc with `chunker: llm` in `sources.yml`. Output schema:
```
{ "chunk_id", "doc_id", "structural_path": ["Раздел II", "пункт 4", "подпункт б"], "page_no", "bbox", "text" }
```
Golden corpus of 5 NPA + 3 concepts with hand-labelled boundaries gates the chunker unit test.

**Consequences.** ~400 lines of regex+state-machine, no LLM in legal layer. False negatives (missed break) escalate to `manual_review` rather than wrong-status. `legal/ru_terms.yml` loads once; canonicalization runs before structural diff.

## 4. Sprint roadmap

Calendar weeks assume **one senior backend engineer**, ~30 hrs/week net coding (the rest is review, reading, meetings).

### Sprint 1 — Foundations: Postgres, S3, source registry, version cache

**Goal.** Replace JSON state with Postgres, file paths with S3, and add the cache key.

**Deliverables.**
- Postgres schema with Alembic; dual-write then cutover from `state.json`
- `Storage` interface with `LocalStorage` + `S3Storage` (MinIO in compose)
- `EXTRACTOR_VERSION`/`COMPARATOR_VERSION` constants in `settings.py` and persisted on every event
- Two-level cache (extraction, pair compare) with content-hash keys
- `sources.yml` ingestion endpoint that sets `doc_type` and `source_rank` correctly

**PRs.**
- **PR-1.1 — Postgres service + Alembic baseline.** `db/` package with SQLAlchemy 2.x models for `batches`, `documents`, `document_versions`, `pair_runs`, `diff_events`, `evidences`, `review_decisions`, `artifacts`. Alembic init + first revision. No production code uses DB yet.
- **PR-1.2 — Repository layer + dual-write.** `db/repository.py` matching `state.py` signatures. `pipeline.py` writes to both, reads from JSON. Alembic revision adds primary indexes.
- **PR-1.3 — Read cutover + drop state.json writes.** `pipeline.py` reads from repo. `state.py` becomes export-only. Smoke: rerun on clean DB, artifacts byte-stable.
- **PR-1.4 — Storage interface + MinIO.** `Storage` protocol. `docker-compose.yml` gains MinIO and `S3_*` env. All file IO goes through the interface. Local dev keeps `LocalStorage`.
- **PR-1.5 — Source registry parsing.** `POST /batches` accepts YAML; document upload matches filenames against registry to set `doc_type`/`source_rank`. Default rank-3 only when no match.
- **PR-1.6 — Cache keys + idempotency.** `EXTRACTOR_VERSION=2.0.0`, `COMPARATOR_VERSION=1.0.0`. Both stages check cache first. No-op rerun completes <5 s.

**Definition of Done.**
- `alembic upgrade head` runs clean from empty DB
- `docker compose up` brings api, worker, redis, postgres, minio
- Same batch rerun produces identical `event_id` set (asserted in test)
- `event.extractor_version` and `event.comparator_version` populated
- `source_rank` from `sources.yml` overrides upload default

**Duration.** 3 calendar weeks.

### Sprint 2 — Renderers complete: full XLSX, executive DOCX, true DOCX redlines, event_id ↔ PDF link

**Goal.** Bring the renderer suite to brief §8 spec.

**Deliverables.**
- All 13 sheets in `evidence_matrix.xlsx` per §8.2
- `executive_diff.docx` (not just .md) with the §8.1 7-section structure
- DOCX↔DOCX detection + `original_with_changes.docx`
- PDF rect annotations carry `event_id` in their `/T` (title) field; XLSX has hyperlinks to PDFs
- HTML report (`full_diff_report.html`) renderer with linked navigation

**PRs.**
- **PR-2.1 — XLSX evidence matrix expansion.** Add sheets `04_contradictions`, `06_not_found`, `07_legal_changes`, `08_claim_validation`, `09_table_diffs`, `11_false_positives`, `12_metrics`. Conditional formatting on severity. Column rename to match §8.2 contract.
- **PR-2.2 — Executive DOCX renderer.** `executive_docx.py` with §8.1 7-section structure. References events as `[evt_xxxxxx]` linked to XLSX row.
- **PR-2.3 — DOCX↔DOCX track changes.** Detect DOCX-DOCX pairs; walk paragraphs in lock-step; emit `original_with_changes.docx` with real `w:ins`/`w:del`. Fall back to synthetic if either side non-DOCX.
- **PR-2.4 — PDF event_id linking.** Annotations carry `event_id` in `info` dict. XLSX gains `pdf_link` column with `=HYPERLINK(...)`. New endpoint `GET /events/{event_id}/locator` returns PDF+page+bbox.
- **PR-2.5 — HTML report.** Jinja2 templates: index, per-pair, per-event. Static export for offline review.

**Definition of Done.**
- `evidence_matrix.xlsx` opens in Excel and shows 13 named sheets
- Two real DOCX files produce a DOCX with visible track changes when opened in Word
- Clicking the PDF highlight in a viewer reveals the `event_id` tooltip
- HTML report can be opened in a browser from local filesystem and navigates correctly

**Duration.** 2.5 calendar weeks.

### Sprint 3 — Legal layer + claim validation

**Goal.** Move from "fuzzy block diff that pretends to be legal" to actual structural legal diff and presentation claim validation.

**Deliverables.**
- `legal/ru_terms.yml` canonicalization dictionary
- `legal/npa_chunker.py`, `legal/concept_chunker.py`, `legal/gov_plan_chunker.py`
- `legal/legal_refs.py` — extraction and resolution of `№ NN-ФЗ`, `статья N`, `Указ № N от DATE`
- `legal/claim_extractor.py` — turns presentation slides into `Claim` records
- New comparator branches: `legal_structural_diff`, `policy_semantic_diff`, `coverage_diff`, `claim_validation`
- Source-rank gate (ADR-5) enforced

**PRs.**
- **PR-3.1 — Legal canonicalization dictionary + term normalizer.** `legal/ru_terms.yml` (ИГ↔иностранный гражданин, ЛБГ↔лицо без гражданства, etc.). `legal/canonicalize.py` runs before matching. Unit tests: 30 term pairs round-trip.
- **PR-3.2 — Structural chunkers.** Three modules; shared grammar in `legal/grammar.py`. Output `Chunk` records with `structural_path`. Golden tests over 5 NPA + 3 concepts.
- **PR-3.3 — `legal_structural_diff` comparator.** Operates on chunks. Match by `structural_path` first, canonicalized text second. Emits `ChunkDiffEvent` with `lhs_path`/`rhs_path`. Wired into pair-type matrix.
- **PR-3.4 — `coverage_diff` comparator.** For LEGAL_CONCEPT ↔ GOV_PLAN. Each concept task → list of plan measures. Status `covered`/`partial`/`missing`. New XLSX coverage sheet.
- **PR-3.5 — `claim_extractor` + `claim_validation`.** PRESENTATION/ANALYTICS → claims (subject, predicate, object/value, date, legal_refs[]). LLM-assisted extraction with deterministic post-validation; cached by sha256. Validates each claim against rank-1/2 docs.
- **PR-3.6 — Source-rank gate.** Implements ADR-5. `quality_policy.rank_gate` config block. Tests: rank-3↔rank-1 `contradicts` converts to `manual_review`.

**Definition of Done.**
- Concept-2026 vs Concept-2019 produces section/clause-level events with `structural_path` populated
- Concept ↔ Plan run produces a coverage matrix listing each task's coverage status
- VCIOM presentation produces ≥10 claim records, each validated against the NPA corpus
- Rank-3 → rank-1 `contradicts` events do not appear in matrix; they are `manual_review` instead
- Russian legal terms canonicalize: `ИГ` and `иностранный гражданин` match each other

**Duration.** 4 calendar weeks.

### Sprint 4 — Review loop + automation

**Goal.** Close the human-in-the-loop and run the system unattended.

**Deliverables.**
- `POST /events/{event_id}/review` endpoint + DB persistence
- `POST /batches/{batch_id}/render?anchor_doc_id=...` (rerender-only)
- Reviewer minimal UI (single-page HTML, FastAPI-served) with filters
- `false_positive` flow that writes to `qa_defect_log.csv`
- Source URL polling scheduler (`celery beat`)
- Incremental recompute on changed sha256

**PRs.**
- **PR-4.1 — Review API + reviewer model.** `ReviewDecision` table; `POST /events/{id}/review`, `GET /batches/{id}/review_queue`. XLSX export reads from DB. `false_positive` decisions emit row in `qa_defect_log.csv`.
- **PR-4.2 — Anchor rerender endpoint.** `POST /batches/{id}/render?anchor_doc_id=X&outputs=pdf,docx,xlsx` re-runs only renderers; never recomputes diffs. 409 on Level-2 cache miss.
- **PR-4.3 — Reviewer single-page UI.** Static HTML+JS at `/ui/review/{batch_id}`. Server filter endpoints. Side-by-side evidence. Submit → PR-4.1 endpoint.
- **PR-4.4 — Source URL polling.** `celery beat` hourly check; sha256 compare; enqueue on change. New `source_polls` table.
- **PR-4.5 — Incremental recompute.** When one document changes, only its extraction + the `N-1` pairs that include it recompute. Implements brief §12.2 invalidation matrix.
- **PR-4.6 — Audit log.** `audit_events` table (append-only): batch creation, document upload, run lifecycle, review decisions, anchor changes. `GET /batches/{id}/audit.jsonl`.

**Definition of Done.**
- Reviewer UI loads, filters work, decision persists across reload
- Changing anchor on a 36-pair batch completes in <30 s (only render runs)
- Modifying one document and rerunning recomputes only `1 + (N-1)` pairs (assert in test)
- `qa_defect_log.csv` accumulates false-positive marks across runs
- `celery beat` triggers a recompute when a tracked URL's sha256 changes

**Duration.** 3 calendar weeks.

### Sprint 5 — QA, observability, semantic comparator (gated)

**Goal.** Make the system measurable, regression-proof, and ready to admit a semantic LLM comparator.

**Deliverables.**
- Golden test corpus + regression CI gate
- Performance gates (`time_to_first_report` SLO, p95 per-pair compare)
- OpenTelemetry traces per pipeline stage
- Prometheus metrics endpoint
- `cache prune` CLI
- Semantic comparator behind `ENABLE_SEMANTIC_COMPARATOR=false`, dark-launch mode

**PRs.**
- **PR-5.1 — Golden corpus + regression test.** `tests/golden/` with 2 PDF + 1 DOCX + 1 PPTX + 1 XLSX + 1 HTML fixtures. Reference fingerprint = `event_id` set + status counts. CI fails on drift unless `--update-golden` is passed.
- **PR-5.2 — OTEL traces + Prometheus metrics.** `time_to_first_report`, `time_per_stage_seconds{stage}`, `pair_compare_seconds`, `cache_hit_total`, `libreoffice_failure_total`, `celery_queue_depth`. `/metrics` endpoint.
- **PR-5.3 — KPI dashboards + precision/recall harness.** Labelled corpus loader; precision/recall/F1 per status; confusion matrix exported as `tests/qa/precision_recall_report.json`.
- **PR-5.4 — Cache prune CLI.** `python -m docdiffops.cli cache-prune --older-than=90d` with dry-run flag.
- **PR-5.5 — Semantic comparator (dark launch).** `compare_semantic.py` proposes `comparator_type=llm_hypothesis` events alongside deterministic ones. Always tagged; never auto-status; not rendered unless `ENABLE_SEMANTIC_COMPARATOR=true`.
- **PR-5.6 — Documentation pass.** OpenAPI schema, README runbook, deploy notes, "what to do when LibreOffice hangs" runbook.

**Definition of Done.**
- CI green on golden tests; intentional drift breaks CI
- Prometheus scrape returns the listed metrics
- `time_to_first_report` p50 < 2 min for 5-document batch on dev hardware
- Semantic comparator runs in dark mode and writes hypothesis events to a separate JSONL
- Runbook covers the top 5 ops scenarios

**Duration.** 3 calendar weeks.

**Total calendar duration: ~15.5 weeks** for one senior engineer.

## 5. PR sequence (flat list, dependency-ordered)

1. **PR-1.1** Postgres + Alembic baseline — depends on: none
2. **PR-1.2** Repository layer + dual-write — depends on: PR-1.1
3. **PR-1.3** Read cutover, drop state.json writes — depends on: PR-1.2
4. **PR-1.4** Storage interface + MinIO — depends on: PR-1.3
5. **PR-1.5** Source registry → `doc_type`/`source_rank` — depends on: PR-1.3
6. **PR-1.6** Cache keys + idempotency — depends on: PR-1.4, PR-1.5
7. **PR-2.1** XLSX evidence matrix expansion — depends on: PR-1.3
8. **PR-2.2** Executive DOCX renderer — depends on: PR-2.1
9. **PR-2.3** DOCX↔DOCX track changes — depends on: PR-1.6
10. **PR-2.4** PDF event_id linking — depends on: PR-2.1
11. **PR-2.5** HTML report — depends on: PR-2.4
12. **PR-3.1** Legal canonicalization dictionary — depends on: PR-1.5
13. **PR-3.2** Structural chunkers — depends on: PR-3.1
14. **PR-3.3** `legal_structural_diff` comparator — depends on: PR-3.2, PR-1.6
15. **PR-3.4** `coverage_diff` comparator — depends on: PR-3.2
16. **PR-3.5** `claim_extractor` + `claim_validation` — depends on: PR-3.1, PR-1.6
17. **PR-3.6** Source-rank gate — depends on: PR-1.5, PR-3.3, PR-3.5
18. **PR-4.1** Review API + reviewer model — depends on: PR-1.3, PR-3.6
19. **PR-4.2** Anchor rerender endpoint — depends on: PR-1.6, PR-2.4
20. **PR-4.3** Reviewer single-page UI — depends on: PR-4.1
21. **PR-4.4** Source URL polling — depends on: PR-1.5, PR-4.1
22. **PR-4.5** Incremental recompute — depends on: PR-1.6, PR-4.4
23. **PR-4.6** Audit log — depends on: PR-4.1
24. **PR-5.1** Golden corpus + regression CI — depends on: PR-3.6, PR-4.5
25. **PR-5.2** OTEL traces + Prometheus metrics — depends on: PR-4.5
26. **PR-5.3** KPI dashboards + precision/recall — depends on: PR-5.1, PR-5.2
27. **PR-5.4** Cache prune CLI — depends on: PR-1.6
28. **PR-5.5** Semantic comparator (dark launch) — depends on: PR-3.6, PR-5.1
29. **PR-5.6** Documentation pass — depends on: all preceding

## 6. Risk register

| # | Risk | L | I | Mitigation |
|---|------|---|---|------------|
| R-1 | LibreOffice headless instability under Celery `--concurrency=2` (shared user profile, hangs on Cyrillic fonts, zombie soffice processes) | H | H | Per-worker `--user-installation=file:///tmp/lo_{pid}`; subprocess timeout 600 s; sentinel reaper task that kills `soffice` >900 s old; structured `libreoffice_failure_total` metric; fallback to `unoconv` if available |
| R-2 | Russian-language tokenization edge cases in NPA chunker (continued numbering across pages, `пп.` vs `п.`, footnotes inside paragraphs, `и т.п.`) | H | M | Regex grammar lives in `legal/grammar.py` with named alternatives; golden corpus of 5 NPA gates the chunker; failures yield `not_comparable` rather than wrong-status; manual override via `chunker: llm` in sources.yml |
| R-3 | False-positive flood from `claim_validation` (presentation thesis paraphrases an NPA but doesn't share lexical surface, fuzzy diff calls it `not_found`) | H | M | Three-stage match: structural_path → canonicalized text → semantic embedding. Default to `manual_review` rather than `not_found` when the second stage fails. Reviewer marks confirm `false_positive`s; rules ratchet thresholds. |
| R-4 | Scanned/image-only PDFs (when the user finally provides a real scanned NPA) — text layer empty, fuzzy diff produces nothing | M | H | Detect via `len(text) / num_pages` heuristic; route to OCR (Tesseract Russian or Docling-OCR); annotate document with `extraction_method=ocr`; require human review for any event sourced from OCR'd block |
| R-5 | Postgres migration during a running batch (Alembic adds a column, worker is mid-pair) | M | H | All Alembic migrations are additive (new tables, nullable columns); destructive changes go behind a 2-step deploy: add new + dual-write + cutover + drop old; CI gate refuses migrations marked destructive without explicit approval |
| R-6 | Rate-limiting and TLS issues on source polling (kremlin.ru, tinao.mos.ru, economy.gov.ru block bursts) | M | M | `celery beat` schedule with jitter (≥120 s base); per-domain rate limit (1 req / 30 s); HEAD before GET; honor `Retry-After`; persist last-success timestamp; circuit breaker after 3 consecutive failures |
| R-7 | LLM-based claim extraction non-determinism breaks `event_id` stability | M | M | Cache claim-extraction by `sha256(slide_block) + extractor_prompt_version`; temperature 0; if results drift, bump `EXTRACTOR_VERSION` so cache invalidates cleanly; never feed claim hash into `event_id` directly |
| R-8 | Storage cost growth (per-batch raw + normalized + extracted + per-pair PDFs add ~5x source corpus size) | M | L | Mode `material_changes_only` for per-pair PDFs (default); cache prune CLI; lifecycle policy on cache bucket (90 days) |
| R-9 | Reviewer UI bypassed because reviewer prefers Excel | L | M | Excel writeback: a `reviewer_decision` column in XLSX is detected on re-upload and merged back into DB; both paths lead to the same audit log |
| R-10 | "GitHub-style binary diff" creep — someone wires diffoscope/PIL pixel diff into the page renderer for scanned PDFs and we end up with 5000-event "everything changed" reports | L | H | Pixel diff is explicitly out of scope; if needed it goes behind `comparator_type=visual_diff` with severity floor `low` and never enters the high-risk sheet |

## 7. Testing strategy

**Unit tests.**
- `tests/unit/test_utils.py` — `norm_text`, `stable_id`, `sha256_file`, `safe_name` Cyrillic round-trip, `compact_text` boundary
- `tests/unit/test_compare.py` — `best_match` empty/singleton/Cyrillic, `numbers` extraction, `classify_severity` rank matrix
- `tests/unit/test_legal_chunker.py` — every section of brief grammar (`статья`, `часть`, `пункт`, `подпункт`, `абзац`); property-based tests via Hypothesis on synthetic numbered structures
- `tests/unit/test_canonicalize.py` — 30 term pairs from `ru_terms.yml`, both directions
- `tests/unit/test_cache_keys.py` — same input → same key; bump version → different key; whitespace-only change → same key after `norm_text`
- `tests/unit/test_rank_gate.py` — every (rank_lhs, rank_rhs, status) tuple from §13 source hierarchy

Property-based concerns: `event_id` must be a pure function of (pair_id, status, lhs_block_id, rhs_block_id); `pair_id` must be order-independent given doc_id sort.

**Smoke tests.**
- Brief-mandated baseline: 2 PDF + 1 DOCX
- Extended: + 1 PPTX (the VCIOM-style sample), + 1 XLSX (sample neuron output), + 1 HTML (klerk-style summary). Total 6 files → 15 pairs
- `tests/smoke/test_first_run.sh`: spins compose, creates batch via curl, uploads 6 files, runs sync, asserts artifacts list returns expected counts

**Golden tests.**
- `tests/golden/{fixture_set}/inputs/` — 6 small files (each <100 KB)
- `tests/golden/{fixture_set}/expected/event_ids.txt` — sorted set of expected `event_id`s
- `tests/golden/{fixture_set}/expected/status_counts.json` — `{added: N, deleted: N, partial: N, ...}`
- `tests/golden/{fixture_set}/expected/manifest.json` — sha256 of every artifact path
- Update mechanism: `pytest tests/golden --update-golden` regenerates files; the regenerate is a separate commit subject to review
- CI compares actual vs expected; mismatch fails the run with a diff

**Determinism assertions.**
- `tests/determinism/test_pair_id.py` — given the same docs in different upload order, `pair_id` set is identical
- `tests/determinism/test_event_id.py` — two runs of the same batch produce identical `event_id` set, status, severity (modulo `created_at` timestamps which are excluded from hashing)
- `tests/determinism/test_cache_replay.py` — first run populates cache; second run hits cache for >95% of pairs and produces identical events

**Performance gates.**
- SLO: `time_to_first_report` p50 < 2 min, p95 < 5 min for 5-document batch on dev container (4 CPU, 8 GB)
- p95 per-pair compare time < 8 s for "fast" profile, < 90 s for "full" profile
- Gate: a benchmark fixture in `tests/perf/` runs in CI nightly; deviation >50% from baseline fails the build with a "perf regression" label

## 8. Observability

Two stated KPIs from the user (Q1 in brief): "скорость первого отчёта" and "точность юридической сверки." Each gets a measurable instrument, plus operational metrics for the boring stuff that breaks at 3 AM.

**KPI 1 — `time_to_first_report` (speed).**
- Histogram `docdiffops_time_to_first_report_seconds` with buckets `[10, 30, 60, 120, 300, 600, 1800]`
- Broken down by stage: `docdiffops_stage_duration_seconds{stage="normalize|extract|compare|render"}`
- Per-document overhead: `docdiffops_doc_extract_seconds{doc_type=...}`
- Per-pair overhead: `docdiffops_pair_compare_seconds{comparator_type=...}`
- Logged to OTEL spans; alert when p95 exceeds 5 min on 5-doc batches

**KPI 2 — legal accuracy (precision/recall/F1).**
- Labelled corpus under `tests/qa/labelled/` with hand-confirmed `(pair_id, structural_path, expected_status)` triples
- Nightly job runs `precision_recall_report.py`; produces:
  - precision per status (`same`, `partial`, `contradicts`, etc.)
  - recall per status
  - F1 weighted average
  - confusion matrix as a 9×9 grid (one row per status)
- Threshold: F1 ≥ 0.80 on `contradicts`, ≥ 0.85 on `same`, ≥ 0.70 on `partial`. Below threshold = release blocker.
- Exposed as `docdiffops_status_precision{status=...}` and `docdiffops_status_recall{status=...}` gauges

**Operational metrics.**
- `celery_queue_depth_total{queue=fast|full|render|poll}` — gauge
- `libreoffice_failure_total` — counter; alert >5/hour
- `cache_hit_total{level=extract|pair}` and `cache_miss_total{level=...}` — counter; ratio dashboard
- `db_connection_errors_total`, `s3_request_errors_total` — counter
- `review_queue_depth{batch_id=...}` — gauge

**Logs.**
- Structured JSON via `structlog`. Required fields: `batch_id`, `pair_id`, `doc_id`, `event_id`, `stage`, `extractor_version`, `comparator_version`. Cache decisions logged at INFO with a single line: `cache_hit cache_key=... level=extract`.

**Traces.**
- One root span per `run_batch`. Child spans: `normalize`, `extract`, `pair_compare`, `render_global`. Per-pair compare gets its own span. Trace ID propagated to Celery via headers.

## 9. First-week task list

Day-by-day for week 1 of Sprint 1. Each task is atomic — pick one and finish it without further planning.

**Day 1 (Monday).**
- 09:00 `docker compose up --build && curl -sf http://localhost:8000/health | jq` — must return `{"ok": true, "data_dir": "/data"}` before any other work
- Walk-through: upload 3 fixtures (1 PDF, 1 DOCX, 1 PPTX) via curl per `docdiffops_mvp/README.md`; run sync; download `evidence_matrix.xlsx`; open it. Note any breaks in a sticky note (do not fix)
- Read `pipeline.py`, `compare.py`, `extract.py` end-to-end with no edits. Total: 1.5 hours
- End of day: open `WORKLOG.md` in repo root, write 5 bullets on what surprised you

**Day 2 (Tuesday).**
- Create branch `feat/db-foundation`
- Add Postgres 16 to `docker-compose.yml`, set `DATABASE_URL=postgresql+psycopg2://docdiff:docdiff@db:5432/docdiff`
- Create `docdiffops/db/__init__.py`, `docdiffops/db/models.py` with SQLAlchemy 2.x declarative models for `batches` and `documents` only (start small)
- Add `alembic` to requirements; `alembic init db/migrations`; configure `env.py` to use `DATABASE_URL`
- Generate first revision: `alembic revision --autogenerate -m "baseline batches and documents"` ; commit migration file
- Verify: `docker compose run api alembic upgrade head` succeeds
- Open PR-1.1 (draft) at end of day

**Day 3 (Wednesday).**
- Extend models to `document_versions`, `pair_runs`, `diff_events`, `evidences` (lhs/rhs), `review_decisions`, `artifacts`. Add foreign keys, indexes on `(batch_id)`, `(pair_id)`, `(event_id)`
- Generate second migration; verify upgrade and downgrade both run clean
- Write `tests/unit/test_models.py` — instantiate every model, assert constraints (NOT NULL on `sha256`, UNIQUE on `(batch_id, sha256)` for documents)
- Mark PR-1.1 ready for review

**Day 4 (Thursday).**
- Create branch `feat/repository-dual-write` based on PR-1.1
- New module `docdiffops/db/repository.py` with class `BatchRepository` exposing `create_batch`, `add_document`, `add_pair_run`, `add_diff_event`, `add_artifact` — same signatures `state.py` uses
- Modify `state.py:create_batch`, `add_artifact`, etc. to call both JSON write AND repository methods (dual-write)
- Modify `pipeline.py:run_batch` to instantiate the repository alongside `state.json`
- Run end-to-end: same 3-doc batch from Day 1; verify both JSON and DB rows exist with the same `event_id` set

**Day 5 (Friday).**
- Write `tests/integration/test_dual_write.py` — fixture spins ephemeral Postgres via testcontainers; runs a 3-doc batch; asserts `state.json["documents"]` and DB `documents` table have identical rows
- Open PR-1.2 ready for review
- Update `WORKLOG.md` with Sprint-1 progress, blockers, learnings
- 30 min: re-read brief §12 cache invalidation table — that's the spec for week 2

## 10. Open questions — CLOSED 2026-05-08

All five questions answered by the product owner; locking these as constraints for the build.

1. **Reviewer authentication → NONE (public access).** Service is exposed without authentication. All endpoints anonymous. Sprint 4 reviewer UI is a single page with no login. Drop OIDC/basic-auth from Sprint 4 scope; PR-4.6 audit log captures `reviewer_name` from a free-text form field rather than a session.
2. **Anchor selection surface → API param + UI form (default kept).** `POST /batches/{batch_id}/render?anchor_doc_id=...` is the canonical entry point; Sprint 4 reviewer UI exposes a dropdown bound to it. CLI flag deferred.
3. **Batch retention → 30 days, uniform.** Single retention SLA across `raw/`, `normalized/`, `extracted/`, `pairs/`, `reports/`, and `cache/`. PR-5.4 cache prune CLI extends to a full batch reaper with a single `RETENTION_DAYS=30` env var. No tier distinction. Operators wanting longer retention export `evidence_matrix.xlsx` to S3 lifecycle-managed storage out-of-band.
4. **PII handling → none.** Source corpus is open-source NPAs and analytics; no PII redaction layer required. Drop the regex PII scrubber from PR-5.5 semantic comparator. Add a one-line constraint in `README.md`: "Service is not certified for processing personal data; do not upload documents containing PII."
5. **Neuron Excel import → out-of-scope for v1.0 (default kept).** `internal_neuron_manual_v2.pdf` and `sample_neuron_comparison_brief.xlsx` stay in `input/` as reference material only. Track a v1.1 ticket: "import Neuron evidence rows as external `comparison_type=neuron_legacy` events with `confidence` propagated from Neuron's `match_score`."
