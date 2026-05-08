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
