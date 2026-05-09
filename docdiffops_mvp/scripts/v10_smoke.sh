#!/usr/bin/env bash
# v10_smoke.sh — E2E smoke test for v10 forensic bundle endpoints
# Requires: docker compose up + sample files in /home/dev/diff/input/
# Idempotent: safe to run multiple times; each run creates a fresh batch.
set -euo pipefail

OUT=/tmp/v10_smoke_out
API=http://localhost:8000
COMPOSE_FILE="$(cd "$(dirname "$0")/.." && pwd)/docker-compose.yml"
INPUT_DIR=/home/dev/diff/input

mkdir -p "$OUT"

# ---------------------------------------------------------------
# 0. Pre-flight: docker compose must be running
# ---------------------------------------------------------------
echo "=== v10 smoke test ==="
if ! docker compose -f "$COMPOSE_FILE" ps 2>/dev/null | grep -q "Up"; then
  echo "ERROR: docker compose not running."
  echo "  Start with: cd docdiffops_mvp && docker compose up -d"
  exit 1
fi

# ---------------------------------------------------------------
# 1. Create batch
# ---------------------------------------------------------------
BATCH=$(curl -sX POST "$API/batches" \
  -H "Content-Type: application/json" \
  -d '{"title":"v10 smoke"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['batch_id'])")
echo "Batch: $BATCH"

# ---------------------------------------------------------------
# 2. Collect sample documents (cap at 6 file args = 3 pairs max)
# ---------------------------------------------------------------
SAMPLES=()
for f in "$INPUT_DIR"/*.pdf "$INPUT_DIR"/*.html; do
  [ -f "$f" ] || continue
  SAMPLES+=("-F" "files=@$f")
  [ "${#SAMPLES[@]}" -ge 6 ] && break
done

if [ "${#SAMPLES[@]}" -lt 4 ]; then
  echo "ERROR: need ≥2 sample files in $INPUT_DIR (found $((${#SAMPLES[@]} / 2)))"
  echo "  Place at least 2 .pdf or .html files there and re-run."
  exit 1
fi

curl -sX POST "$API/batches/$BATCH/documents" "${SAMPLES[@]}" > /dev/null
echo "Documents uploaded: $((${#SAMPLES[@]} / 2)) files"

# ---------------------------------------------------------------
# 3. Run pipeline (sync, fast profile)
# Note: V10_BUNDLE_ENABLED=true must be set on the API container
# (docker-compose.yml env section or .env file in docdiffops_mvp/).
# ---------------------------------------------------------------
echo "Running pipeline (sync, profile=fast)..."
RUN=$(curl -sX POST "$API/batches/$BATCH/run?profile=fast&sync=true")
echo "$RUN" | python3 -m json.tool > "$OUT/run_result.json"

# ---------------------------------------------------------------
# 4. Fetch /forensic/v10 index
# ---------------------------------------------------------------
echo "Fetching /forensic/v10..."
V10=$(curl -s "$API/batches/$BATCH/forensic/v10")
echo "$V10" | python3 -m json.tool > "$OUT/v10_index.json"

URL_COUNT=$(echo "$V10" | python3 -c \
  "import sys,json; print(len(json.load(sys.stdin).get('artifacts', {})))")
if [ "$URL_COUNT" != "8" ]; then
  echo "ERROR: expected 8 artifact URLs, got $URL_COUNT"
  cat "$OUT/v10_index.json"
  exit 1
fi
echo "✓ /forensic/v10 returned 8 URLs"

# ---------------------------------------------------------------
# 5. Download all 8 artifact kinds
# ---------------------------------------------------------------
KINDS=(
  xlsx_v10
  note_docx
  note_pdf
  integral_matrix_pdf
  correlation_matrix_csv
  dependency_graph_csv
  claim_provenance_csv
  coverage_heatmap_csv
)
for kind in "${KINDS[@]}"; do
  echo "  GET /forensic/$kind ..."
  curl -fsS "$API/batches/$BATCH/forensic/$kind" -o "$OUT/$kind"
done

# ---------------------------------------------------------------
# 6. Validate artifacts
# ---------------------------------------------------------------
echo
echo "=== Validation ==="

# CSVs: must have UTF-8 BOM (EF BB BF)
CSV_KINDS=(correlation_matrix_csv dependency_graph_csv claim_provenance_csv coverage_heatmap_csv)
for csv in "${CSV_KINDS[@]}"; do
  if head -c 3 "$OUT/$csv" | od -An -t x1 | tr -d ' \n' | grep -q "efbbbf"; then
    echo "✓ $csv has UTF-8 BOM"
  else
    echo "✗ $csv missing UTF-8 BOM"
    exit 1
  fi
done

# PDFs: check Cyrillic rendering via pdftotext (best-effort; warns if unavailable)
PDF_KINDS=(note_pdf integral_matrix_pdf)
for pdf in "${PDF_KINDS[@]}"; do
  if command -v pdftotext > /dev/null 2>&1; then
    if pdftotext "$OUT/$pdf" - 2>/dev/null | grep -qE "[А-Яа-я]"; then
      echo "✓ $pdf renders Cyrillic"
    else
      echo "✗ $pdf missing Cyrillic — font fallback issue?"
      exit 1
    fi
  else
    echo "  (skip) $pdf — pdftotext not available, skipping Cyrillic check"
  fi
done

# XLSX: must have ≥14 sheets
python3 - "$OUT/xlsx_v10" <<'PYEOF'
import sys
import openpyxl
path = sys.argv[1]
wb = openpyxl.load_workbook(path, data_only=True)
n = len(wb.sheetnames)
assert n >= 14, f"expected ≥14 sheets, got {n}"
print(f"✓ xlsx_v10 has {n} sheets")
PYEOF

echo
echo "=== v10 smoke test PASS ==="
echo "Outputs: $OUT/"
echo "Batch:   $BATCH"
