# DocDiffOps MVP

Единый сервис для загрузки пакета документов, all-to-all сравнения и генерации артефактов:

- `evidence_matrix.xlsx` — полный Excel-реестр расхождений.
- `executive_diff.md` — краткий executive diff.
- `pairs/*/pagewise_redgreen.pdf` — red/green PDF по парам, где возможно.
- `pairs/*/track_changes.docx` — synthetic DOCX redline report с OOXML `w:ins` / `w:del`.
- `pairs/*/diff_events.jsonl` — машинный журнал событий.

## Запуск

```bash
docker compose up --build
```

API: http://localhost:8000/docs

## Быстрый тест через curl

```bash
BATCH=$(curl -s -X POST http://localhost:8000/batches \
  -H 'Content-Type: application/json' \
  -d '{"title":"migration policy batch"}' | python3 -c 'import sys,json; print(json.load(sys.stdin)["batch_id"])')

echo $BATCH

curl -X POST "http://localhost:8000/batches/$BATCH/documents" \
  -F "files=@/path/to/doc1.pdf" \
  -F "files=@/path/to/doc2.docx" \
  -F "files=@/path/to/slides.pptx"

curl -X POST "http://localhost:8000/batches/$BATCH/run?profile=fast&sync=true"

curl "http://localhost:8000/batches/$BATCH/artifacts"
```

## Важное

Это MVP-скелет: он уже делает ingestion, normalize, extract, all-to-all diff, red/green PDF, DOCX redline report, XLSX matrix. Для production надо добавить Postgres, S3/MinIO, авторизацию, юридический LLM-компаратор, review UI и регрессионные тесты.

## Sprint 6 — v10 quality bundle in production

**Status:** done (PR-6.1..6.7).

Set `V10_BUNDLE_ENABLED=true` in `docker-compose.yml` or `.env` to enable v10-quality bundle generation after `POST /batches/{id}/run`.

After the run, 8 artifacts are available:

- 14-листный XLSX (`xlsx_v10`) — conditional formatting, heatmap color scales, hyperlinks
- Пояснительная записка (`note_docx`, `note_pdf`) — 10-chapter DOCX + PDF, Cyrillic-safe
- Интегральная матрица (`integral_matrix_pdf`) — A3 landscape PDF for N≥13 docs
- 4 correlation CSVs with UTF-8 BOM: `correlation_matrix_csv`, `dependency_graph_csv`, `claim_provenance_csv`, `coverage_heatmap_csv`

Endpoints:

- `GET /batches/{id}/forensic/v10` — JSON with 8 download URLs
- `GET /batches/{id}/forensic/{kind}` — download any of the 8 kinds above

Key modules:

- `forensic_correlations.py` — 4 cross-pair analyses
- `forensic_note.py` — 10-chapter explanatory note (DOCX + PDF)
- `forensic_render.render_v8_xlsx` extended to 14 sheets when `correlations` kwarg passed
- `forensic_render.render_integral_matrix_pdf` — A3 N×N matrix

E2E smoke test: `bash scripts/v10_smoke.sh` (requires `docker compose up` + sample files in `/home/dev/diff/input/`).

Подробнее: `/home/dev/diff/SPRINT_6_PLAN.md`
