#!/usr/bin/env bash
# Forensic v8 quality gate — combines tests + coverage + import sanity.
#
# Usage:
#   ./scripts/forensic_quality_check.sh
#
# Output: human-readable report on stdout + machine-readable JSON in
# /tmp/forensic_qa.json suitable for CI to gate merges on.
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO=$(dirname "$SCRIPT_DIR")
PY="$REPO/.venv/bin/python"
PIP="$REPO/.venv/bin/pip"
PYTEST="$REPO/.venv/bin/python -m pytest"

cd "$REPO"

REPORT=/tmp/forensic_qa.json
SUMMARY=/tmp/forensic_qa.txt
echo "=== Forensic v8 quality check ==="
echo "Repo: $REPO"
echo "Started: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo

# ---------------------------------------------------------------------------
# 1. Run forensic tests
# ---------------------------------------------------------------------------
echo "--- 1. Running forensic test suite ---"
TESTS_OUT=$($PYTEST \
  tests/unit/test_forensic.py \
  tests/unit/test_forensic_render.py \
  tests/unit/test_forensic_pipeline_hook.py \
  tests/unit/test_forensic_actions.py \
  tests/unit/test_forensic_schema.py \
  tests/unit/test_forensic_reproducibility.py \
  tests/unit/test_forensic_delta.py \
  tests/unit/test_forensic_cli.py \
  tests/unit/test_forensic_pipeline_integration.py \
  tests/unit/test_forensic_delta_render.py \
  tests/unit/test_forensic_trend.py \
  tests/unit/test_forensic_csv.py \
  tests/unit/test_forensic_correlations.py \
  tests/unit/test_forensic_note.py \
  -q --tb=short 2>&1 || true)
TESTS_LINE=$(echo "$TESTS_OUT" | grep -E "^[0-9]+ (passed|failed)" | tail -1)
echo "$TESTS_LINE"
TESTS_PASSED=$(echo "$TESTS_LINE" | grep -oP '\d+(?= passed)' || echo "0")
TESTS_FAILED=$(echo "$TESTS_LINE" | grep -oP '\d+(?= failed)' || echo "0")

# ---------------------------------------------------------------------------
# 2. Coverage on forensic-* modules
# ---------------------------------------------------------------------------
echo
echo "--- 2. Coverage on docdiffops/forensic*.py ---"
if "$PY" -c "import coverage" 2>/dev/null; then
  COV_OK=1
else
  echo "(installing coverage)"
  "$PIP" install -q coverage 2>&1 | tail -1
  COV_OK=1
fi

if [ "$COV_OK" = "1" ]; then
  $PY -m coverage erase
  $PY -m coverage run --include="docdiffops/forensic*.py" \
    -m pytest \
    tests/unit/test_forensic.py \
    tests/unit/test_forensic_render.py \
    tests/unit/test_forensic_pipeline_hook.py \
    tests/unit/test_forensic_actions.py \
    tests/unit/test_forensic_schema.py \
    tests/unit/test_forensic_reproducibility.py \
    tests/unit/test_forensic_delta.py \
    tests/unit/test_forensic_cli.py \
    tests/unit/test_forensic_pipeline_integration.py \
    tests/unit/test_forensic_delta_render.py \
    tests/unit/test_forensic_trend.py \
    tests/unit/test_forensic_correlations.py \
    tests/unit/test_forensic_note.py \
    -q > /dev/null 2>&1 || true
  COV_REPORT=$($PY -m coverage report --include="docdiffops/forensic*.py" 2>/dev/null || echo "(coverage failed)")
  echo "$COV_REPORT"
  COV_TOTAL=$(echo "$COV_REPORT" | tail -1 | grep -oP '\d+%' | head -1)
else
  COV_TOTAL="n/a"
fi

# ---------------------------------------------------------------------------
# 3. Import sanity — every forensic module loads without side effects
# ---------------------------------------------------------------------------
echo
echo "--- 3. Import sanity ---"
IMPORT_OK=true
for mod in forensic forensic_render forensic_actions forensic_schema forensic_cli forensic_delta forensic_delta_render forensic_trend forensic_csv; do
  if $PY -c "import docdiffops.$mod" 2>/dev/null; then
    echo "  ✓ docdiffops.$mod"
  else
    echo "  ✗ docdiffops.$mod"
    IMPORT_OK=false
  fi
done

# ---------------------------------------------------------------------------
# 4. Schema sanity — generate empty bundle + validate
# ---------------------------------------------------------------------------
echo
echo "--- 4. Schema sanity ---"
SCHEMA_RESULT=$($PY - <<'PYEOF' 2>&1
from docdiffops.forensic import build_forensic_bundle
from docdiffops.forensic_schema import validate_bundle
from docdiffops.forensic_actions import apply_actions_to_bundle

docs = [{"id": f"D{i}", "code": f"C{i}", "rank": (1 if i%2 else 3),
         "title": f"d{i}", "type": "law"} for i in range(1, 6)]
pairs = [{"id": "P1", "left": "D1", "right": "D2", "events": [{"status":"partial"}]}]
b = build_forensic_bundle(documents=docs, pairs=pairs, events=[], amendment_graph={})
b = apply_actions_to_bundle(b)
errs = validate_bundle(b)
print("OK" if not errs else f"FAIL: {len(errs)} errors")
PYEOF
)
echo "  $SCHEMA_RESULT"
SCHEMA_OK=$(echo "$SCHEMA_RESULT" | grep -c "OK" || true)

# ---------------------------------------------------------------------------
# 5. Final verdict
# ---------------------------------------------------------------------------
echo
echo "--- 5. Verdict ---"
echo "  Tests:    $TESTS_PASSED passed / $TESTS_FAILED failed"
echo "  Coverage: $COV_TOTAL"
echo "  Imports:  $($IMPORT_OK && echo "OK" || echo "FAIL")"
echo "  Schema:   $([ "$SCHEMA_OK" -gt 0 ] && echo "OK" || echo "FAIL")"

VERDICT="PASS"
[ "$TESTS_FAILED" != "0" ] && VERDICT="FAIL"
$IMPORT_OK || VERDICT="FAIL"
[ "$SCHEMA_OK" = "0" ] && VERDICT="FAIL"
echo
echo "VERDICT: $VERDICT"

# Machine-readable JSON
cat > "$REPORT" <<JSON
{
  "verdict": "$VERDICT",
  "tests_passed": $TESTS_PASSED,
  "tests_failed": $TESTS_FAILED,
  "coverage_total": "$COV_TOTAL",
  "imports_ok": $($IMPORT_OK && echo "true" || echo "false"),
  "schema_sanity_ok": $([ "$SCHEMA_OK" -gt 0 ] && echo "true" || echo "false"),
  "generated_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}
JSON
echo "Report → $REPORT"

[ "$VERDICT" = "PASS" ] && exit 0 || exit 1
