# DocDiffOps Forensic v8 — System API Reference

End-to-end API for the v8 forensic cross-comparison contract. The
system is composed of five modules under `docdiffops/`:

| Module | Role | Tests |
|---|---|---|
| `forensic.py` | Status scale, aggregator, bundle builder | 32 |
| `forensic_render.py` | XLSX/DOCX/PDF bundle renderers (ULTRA-HQ, ru-RU) | 16 |
| `forensic_delta_render.py` | XLSX/DOCX/PDF **delta** renderers (ULTRA-HQ, ru-RU) | 9 |
| `forensic_actions.py` | FA-XX catalogue + RACI + apply-to-bundle | 20 |
| `forensic_schema.py` | JSON Schema (draft-07) + validator | 15 |
| `forensic_cli.py` | Offline rebuild + compare CLI (with `--render-artifacts`) | 6 |
| `forensic_delta.py` | Bundle-to-bundle delta comparison | 18 |
| `forensic_trend.py` | Multi-bundle time-series aggregation | 10 |
| **pipeline.py** + **main.py** | Pipeline hook + REST endpoints | 8 + 2 |
| Reproducibility + perf ceilings | Determinism, input-order invariance, perf | 8 |
| FastAPI integration | `/forensic` endpoints via TestClient | 13 |

155 tests, all green (142 unit + 13 integration). Coverage: 97%.
**mypy strict** clean across 6 forensic modules (`forensic`, `forensic_schema`,
`forensic_actions`, `forensic_delta`, `forensic_trend`, `forensic_cli`).

**Design language**: All artifacts (bundle + delta) are rendered in Russian
(ru-RU) with a shared color palette (slate primary, status-coded accents),
ULTRA-HQ cover pages, KPI tiles, status legends, page numbers, and corporate-grade
typography. Reuse vocabulary lives in `forensic_render` (`PALETTE`, `STATUS_RU`,
`STATUS_PALETTE`, `_docx_set_cell_bg`, `_pdf_page_decoration`).

---

## 1. Quickstart — generate a bundle from scratch

```python
from docdiffops.forensic import build_forensic_bundle
from docdiffops.forensic_actions import apply_actions_to_bundle
from docdiffops.forensic_schema import validate_bundle
from docdiffops.forensic_render import (
    render_v8_xlsx,
    render_v8_docx_explanatory,
    render_v8_docx_redgreen,
    render_v8_pdf_summary,
)

# 1. Build the bundle
bundle = build_forensic_bundle(
    documents=[
        {"id": "D1", "code": "FZ_115", "rank": 1, "title": "115-ФЗ", "type": "law"},
        {"id": "D2", "code": "ANALYTIC", "rank": 3, "title": "ВЦИОМ", "type": "analytic"},
    ],
    pairs=[
        {"id": "P1", "left": "D1", "right": "D2",
         "events": [{"status": "partial"}]},
    ],
    events=[],
    amendment_graph={},
)

# 2. Validate
errors = validate_bundle(bundle)
assert errors == [], errors

# 3. Apply v8.1 actions catalogue
bundle = apply_actions_to_bundle(bundle)

# 4. Render
render_v8_xlsx(bundle, "out/bundle.xlsx")
render_v8_docx_explanatory(bundle, "out/explanatory.docx")
render_v8_docx_redgreen(bundle, "out/redgreen.docx")
render_v8_pdf_summary(bundle, "out/summary.pdf")
```

---

## 2. Module: `docdiffops.forensic`

### Constants

| Name | Value |
|---|---|
| `V8_STATUSES` | `("match", "partial_overlap", "contradiction", "outdated", "source_gap", "manual_review", "not_comparable")` |
| `STATUS_TO_MARK` | `{"match": "✓", "partial_overlap": "≈", "contradiction": "⚠", "outdated": "↻", "source_gap": "∅", "manual_review": "?", "not_comparable": "—"}` |
| `EVENT_STATUS_TO_V8` | DocDiffOps event vocabulary → v8 (`{"same": "match", "partial": "partial_overlap", "contradicts": "contradiction", "modified": "partial_overlap", "added": "partial_overlap", "deleted": "partial_overlap", "manual_review": "manual_review", "not_found": "manual_review"}`) |
| `DEFAULT_TOPIC_CLUSTERS` | 17 cluster tuples `(id, label, needles)` covering ruID, мигучёт, патенты, высылка, ЕАЭС, КоАП, Концепции, ВЦИОМ, … |

### `aggregate_pair_status_v8(events, *, left_rank, right_rank, known_contradictions=(), left_id=None, right_id=None) -> str`

Reduces per-event evidence + ranks → a single v8 status. Precedence:

1. Empty events → `not_comparable`.
2. `(left_id, right_id)` in `known_contradictions` → `contradiction`.
3. `(left_rank, right_rank)` ∈ `{(1,3), (3,1)}` → `manual_review` (rank invariant).
4. Any event status `manual_review` → `manual_review`.
5. Any event status `contradiction` → `contradiction`.
6. Any event status `partial_overlap` → `partial_overlap`.
7. All `match` → `match`.
8. Otherwise → `not_comparable`.

```python
from docdiffops.forensic import aggregate_pair_status_v8

# rank-3 vs rank-1 with "match" event → still manual_review
assert aggregate_pair_status_v8(
    [{"status": "same"}], left_rank=3, right_rank=1
) == "manual_review"
```

### `cluster_topic_v8(raw_topic, clusters=DEFAULT_TOPIC_CLUSTERS) -> tuple[str, str]`

First-hit cluster ID lookup. Returns `("T00", "Без темы")` if unmatched.

### `derive_outdated(amendment_graph, a, b) -> bool`

`True` if `{a, b}` is an edge in the amendment graph.

### `build_forensic_bundle(*, documents, pairs, events=(), amendment_graph=None, known_contradictions=(), topic_clusters=DEFAULT_TOPIC_CLUSTERS, schema_version="v8.0") -> dict`

Pure function. Returns a JSON-serialisable bundle dict that satisfies
`forensic_schema.BUNDLE_SCHEMA_DICT`.

### `bundle_from_batch_state(state, all_events, pair_summaries) -> dict`

Translates a DocDiffOps pipeline state into a v8 bundle. Used by
`pipeline._render_forensic_bundle`. Documents are pulled from
`state["documents"]`, amendment graph and known contradictions from
`state["amendment_graph"]` / `state["known_contradictions"]`.

---

## 3. Module: `docdiffops.forensic_render`

### Design module: `forensic_render`

Module-level constants used across every renderer:

| Constant | Purpose |
|---|---|
| `STATUS_RU` | Code → Russian status label (`STATUS_MATCH → "Совпадение"`, etc.) |
| `PALETTE` | Hex palette without `#` prefix (works for both openpyxl and ReportLab) — `accent`, `primary`, `match`, `partial`, `contradict`, `outdated`, `gap`, `review`, `nc`, `muted`, `border`, `ink` |
| `STATUS_PALETTE` | Status code → palette key (drives badge colors) |
| `CONTROL_RU` | Control-number key → Russian label (`pairs_changed → "Изменено"`) |
| `DOC_TITLE_RU` | "Криминалистический сравнительный анализ — DocDiffOps Forensic v8" |
| `DOC_SUBTITLE_RU` | Standard disclaimer in Russian |

### `render_v8_xlsx(bundle, out_path) -> None`

Multi-sheet workbook with ULTRA-HQ cover sheet (KPI tiles, title bar,
Russian status legend), landscape print setup, document properties set
to `ru-RU`. Always-present sheets:

| # | Sheet | Content |
|---|---|---|
| 00 | Обложка | Title bar, KPI tiles (4–5 colored cells), Russian legend, control numbers |
| 01 | Реестр источников | Document registry with rank, type, URL |
| 02 | Документ × Документ | Pair status matrix with mark-and-count cells |
| 03 | Тема × Документ | Topic frequency per document |
| 04 | Пары v8 | All pairs with status, topics, **explanations**, **actions** |
| 05 | Manual review | Pairs flagged for manual review |
| 06 | Outdated | Amendment graph entries |
| 07 | Topics catalogue | Cluster IDs + needles |
| 08 | **Действия** | Action catalogue + per-action RACI (when actions applied) |
| 13 | QA | Schema sanity & control parameters |

Conditional sheets (only when `corpus="migration_v8"`):

| # | Sheet | Content |
|---|---|---|
| 09 | Брошюра R-G | Concrete brochure red/green edits |
| 10 | Klerk → НПА | Thesis → law citation links |
| 11 | ЕАЭС split | EAEU member-state split rules |
| 12 | Цепочка изменений | Amendment chains with chronology |

### `render_v8_docx_explanatory(bundle, out_path) -> None`

ULTRA-HQ explanatory note. Document `language` is set to `ru-RU`.

**Layout**:
1. Cover page — accent band ("DOCDIFFOPS · FORENSIC v8"), title, subtitle, 4-column metadata table (Дата / Версия схемы / Корпус / Класс), 4 KPI tiles, executive-summary line ("совпадений — N (X%), противоречий — Y, ручная проверка — Z")
2. Оглавление (table of contents)
3. Раздел 1. Цель и методика
4. Раздел 2. Ключевые показатели (table with Russian labels)
5. Раздел 3. Распределение пар по статусам (color-coded status badges)
6. Раздел 4. Источники
7. Раздел 5. Действия (FA-XX) и матрица RACI — when actions are present, with severity-coded cells
8. Раздел 6. Запреты

**Footer**: `Стр. X из Y · DOCDIFFOPS · FORENSIC v8` on every page.

### `render_v8_docx_redgreen(bundle, out_path) -> None`

ULTRA-HQ editorial diff. Document `language` is set to `ru-RU`.

**Layout**:
1. Cover band + title + dated metadata
2. Status legend table (7 cells, color-coded swatches)
3. Раздел A. Пары и статусы v8 — pairs with Russian status labels, topics, explanations, and action references
4. Раздел B. Хронология поправок (outdated)
5. Раздел C. Брошюра — конкретные правки (only when `corpus="migration_v8"`)

**Footer**: page numbers via field codes.

### `render_v8_pdf_summary(bundle, out_path) -> None`

ULTRA-HQ paginated PDF with custom page decoration:

**Cover page**:
- Top accent band with `DOCDIFFOPS · FORENSIC v8` (gold-on-navy)
- Title + Russian subtitle
- 4 KPI tiles (Документов / Пар / Совпадений / Противоречий)
- Metadata block (date / schema / corpus)
- Status legend with colored swatches

**Status pie chart** — distribution of pairs across v8 statuses, with
color-coded slices and an inline Russian-language legend.

**Sections**:
1. Раздел 1. Ключевые показатели (alternating row backgrounds)
2. Раздел 2. Распределение пар по статусам (status badges in first column)
3. Раздел 3. Источники
4. Раздел 4. Действия (FA-XX) и RACI — when actions are present, with severity-coded cells

**Page header/footer**: navy accent strip + `Страница N` + `{DOC_TITLE_RU}` on every page.


Writes a multi-sheet workbook (Dashboard, Реестр, Doc×Doc, Тема×Doc,
Пары v8, Manual review, Outdated, Topics catalogue, QA).

### `render_v8_docx_explanatory(bundle, out_path) -> None`

Writes a stakeholder-facing explanatory DOCX with method, control
numbers, status distribution, document list, and prohibitions.

### `render_v8_docx_redgreen(bundle, out_path) -> None`

Writes the red/green editorial diff: green = match, red = manual/
contradiction/source_gap, blue = outdated, gray = not_comparable.

### `render_v8_pdf_summary(bundle, out_path) -> None`

Writes a compact PDF using NotoSans-Regular for Cyrillic. Falls back
to Liberation/DejaVu/Helvetica in that order.

---

## 4. Module: `docdiffops.forensic_actions`

### Dataclasses

```python
@dataclass(frozen=True)
class Action:
    id: str             # FA-01 … FA-10
    category: str       # one of ACTION_CATEGORIES
    severity: str       # low / medium / high
    where: str
    what_is_wrong: str
    why: str
    what_to_do: str
    owner: str
    related_docs: list[str]
    v8_status: str
    matches_pairs: list[tuple[str, str]] = []
    matches_doc: str | None = None
```

Plus `BrochureRedGreenEntry`, `KlerkNPALink`, `EAEUSplitEntry`,
`AmendmentChainEntry` for the supplementary catalogues.

### Defaults

- `DEFAULT_ACTIONS` — 10 FA actions.
- `DEFAULT_BROCHURE_REDGREEN` — 6 brochure cells.
- `DEFAULT_KLERK_NPA_LINKS` — 6 Klerk → NPA footnotes.
- `DEFAULT_EAEU_SPLIT` — 3 employer groups (ЕАЭС / безвиз-патент / визовые-разрешение).
- `DEFAULT_AMENDMENT_CHAIN` — 5 amendment chains.

### `actions_for_pair(left, right, catalogue=None) -> list[Action]`

Returns actions where `(left, right)` matches `matches_pairs` or
either side equals `matches_doc`.

### `raci_for_action(action_id) -> dict[str, str]`

Returns `{"R": "...", "A": "...", "C": "...", "I": "..."}`.

### `apply_actions_to_bundle(bundle, catalogue=None, *, corpus=None) -> dict`

Returns a copy of `bundle` with pair-level and catalogue-level enrichments.

**Always-on** (corpus-agnostic):
- `pairs[*].actions` — action IDs relevant to each pair.
- `actions_catalogue` — full catalogue with per-action RACI.
- `raci_matrix` — `{action_id: {R,A,C,I}}`.

**Opt-in** (requires `corpus="migration_v8"`):
- `brochure_redgreen`, `klerk_npa_links`, `eaeu_split`, `amendment_chain`.

```python
# Generic batch — no corpus-literal content
enriched = apply_actions_to_bundle(bundle)
assert "actions_catalogue" in enriched
assert "brochure_redgreen" not in enriched

# Migration corpus — includes Russian-domain supplementaries
enriched = apply_actions_to_bundle(bundle, corpus="migration_v8")
assert "brochure_redgreen" in enriched
assert "FA-01" in enriched["pairs"][0]["actions"]  # if pair is D18↔D20
```

---

## 5. Module: `docdiffops.forensic_schema`

### `BUNDLE_SCHEMA_DICT: dict`

JSON Schema draft-07 describing the v8 bundle structure. See
`data/v8_bundle.schema.json` in the reference package for the
exported version.

### `validate_bundle(bundle) -> list[str]`

Returns `[]` for valid bundles, otherwise human-readable error
messages with JSON-pointer-style paths. Uses `jsonschema` if
available; falls back to a manual check otherwise.

```python
from docdiffops.forensic_schema import validate_bundle

errs = validate_bundle(bundle)
if errs:
    raise ValueError(f"v8 contract violation: {errs}")
```

### `get_bundle_schema() -> dict`

Returns a deep copy of the schema dict — safe to mutate.

---

## 6. Module: `docdiffops.forensic_cli`

**`rebuild` subcommand** — rebuild artifacts from a saved bundle:

```bash
python -m docdiffops.forensic_cli rebuild bundle.json --out dir/ [--with-actions]
```

Reads a saved bundle JSON, optionally applies the actions catalogue
(`migration_v8` corpus), and re-renders all five artifacts into `--out`:
`bundle.json`, `forensic_v8.xlsx`, `forensic_v8_explanatory.docx`,
`forensic_v8_redgreen.docx`, `forensic_v8_summary.pdf`.

**`compare` subcommand** — delta between two saved bundles:

```bash
python -m docdiffops.forensic_cli compare old.json new.json --out delta.json
```

Loads two v8 bundles, calls `compare_bundles()`, and writes the delta
report JSON. Exits 1 if schema versions are incompatible. Prints the
number of changed pairs on success.

---

## 7. Pipeline hook (`docdiffops.pipeline._render_forensic_bundle`)

Auto-invoked at the end of `render_global_reports`. After a batch run:

```
batch_dir/reports/forensic_v8/
├── bundle.json
├── forensic_v8.xlsx
├── forensic_v8_explanatory.docx
├── forensic_v8_redgreen.docx
└── forensic_v8_summary.pdf
```

`state["forensic_v8"]` summary is populated. If the bundle fails JSON
Schema validation, warnings are logged and stored in
`state["forensic_v8_schema_warnings"]` (first 20). The pipeline does
**not** fail on schema warnings — production bundles must ship.

**Actions wiring**: `apply_actions_to_bundle` is always called after
`bundle_from_batch_state`, so every bundle includes `actions_catalogue`
and `raci_matrix`. Corpus-literal supplementaries (`brochure_redgreen`,
etc.) are only attached when `FORENSIC_ACTIONS_CORPUS=migration_v8` is
set in the environment.

---

## 8. REST API (`docdiffops.main`)

| Endpoint | Returns |
|---|---|
| `GET /batches/{batch_id}/forensic` | Full v8 bundle JSON. 404 if not yet generated. |
| `GET /batches/{old_id}/forensic/compare/{new_id}` | Delta report (schema `v8-delta`). 404 if either bundle missing; 422 on schema mismatch. Add `?persist=true` to save the delta as a batch artifact under the new batch. |
| `GET /batches/{batch_id}/forensic/{kind}` | Download artifact. `kind` ∈ `json`, `xlsx`, `docx`, `redgreen_docx`, `pdf`. |

> **Route order**: `/compare/{new_id}` is registered before `/{kind}` to prevent FastAPI treating `compare` as a `kind` value.

```bash
# Fetch the bundle
curl https://diff.zed.md/batches/bat_abc123/forensic | jq .control_numbers

# Compare two runs
curl https://diff.zed.md/batches/bat_abc123/forensic/compare/bat_def456 | jq .status_changes

# Download artifacts
curl -OJ https://diff.zed.md/batches/bat_abc123/forensic/xlsx
```

---

## 9. Testing the contract

```bash
# Full unit suite (120 tests)
pytest tests/unit/test_forensic.py \
       tests/unit/test_forensic_render.py \
       tests/unit/test_forensic_pipeline_hook.py \
       tests/unit/test_forensic_actions.py \
       tests/unit/test_forensic_schema.py \
       tests/unit/test_forensic_reproducibility.py \
       tests/unit/test_forensic_delta.py \
       tests/unit/test_forensic_cli.py \
       tests/unit/test_forensic_pipeline_integration.py

# API integration suite (8 tests, no Postgres needed)
pytest tests/integration/test_forensic_api.py

# Or use the quality gate (runs unit suite + coverage + import sanity)
bash scripts/forensic_quality_check.sh
```

`tests/unit/test_forensic*.py` are the system-level contract tests.
Any change to the v8 vocabulary, aggregator precedence, RACI keys,
schema structure, or delta comparison logic must update both code and
tests in lockstep.

---

## 10. Adding a new domain catalogue

`forensic_actions.DEFAULT_ACTIONS` is migration-domain specific.
For a different domain (e.g. financial regs), build your own list
of `Action` instances and pass it explicitly:

```python
from docdiffops.forensic_actions import Action, apply_actions_to_bundle

my_actions = [
    Action(
        id="FA-A1", category="brochure_vs_npa", severity="medium",
        where="...", what_is_wrong="...", why="...", what_to_do="...",
        owner="...", related_docs=["D1", "D2"], v8_status="manual_review",
        matches_pairs=[("D1", "D2")],
    ),
    # … more actions
]
enriched = apply_actions_to_bundle(bundle, catalogue=my_actions)
```

Severity must be one of `SEVERITY_LEVELS`; category must be one of
`ACTION_CATEGORIES` (or extend the constant in your fork).

---

## 11. Delta Comparison (`docdiffops.forensic_delta`)

Compare two v8 bundles across pipeline runs to track how statuses evolve.

### `compare_bundles(old_bundle, new_bundle) -> dict`

Both bundles must have `schema_version` starting with `"v8."`. Raises
`ValueError` if either has an incompatible version. The returned dict
has `schema_version == "v8-delta"` (not a v8 bundle; don't pass to
`validate_bundle`).

```python
from docdiffops.forensic_delta import compare_bundles

delta = compare_bundles(bundle_run1, bundle_run2)
print(delta["control_numbers"])
# {'pairs_total': 5, 'pairs_changed': 2, 'pairs_resolved': 1,
#  'pairs_new': 0, 'pairs_removed': 0}

for change in delta["status_changes"]:
    print(change["pair_id"], change["old_status"], "→",
          change["new_status"], f"({change['direction']})")
```

### Delta output shape

```python
{
    "schema_version": "v8-delta",
    "generated_at": "...",
    "baseline_generated_at": "...",
    "current_generated_at": "...",
    "control_numbers": {
        "pairs_total": N,
        "pairs_changed": K,
        "pairs_resolved": M,   # old_status != "match" → new_status == "match"
        "pairs_new": L,
        "pairs_removed": R,
    },
    "status_changes": [
        {
            "pair_id": "P1",
            "left_id": "D1", "right_id": "D2",
            "old_status": "contradiction",
            "new_status": "partial_overlap",
            "direction": "improved",       # improved | degraded | unchanged
        },
    ],
    "distribution_diff": {"match": +2, "contradiction": -1},
    "new_pairs": [...],
    "removed_pairs": [...],
    "actions_coverage": "symmetric",       # symmetric | old_only | new_only | neither
    "asymmetric_actions_warning": null,    # str when coverage is asymmetric
}
```

### `STATUS_RANK` ordering

Higher rank = better outcome. Direction is `"improved"` when
`STATUS_RANK[new_status] > STATUS_RANK[old_status]`.

| Status | Rank |
|---|---|
| `match` | 6 |
| `partial_overlap` | 5 |
| `outdated` | 4 |
| `manual_review` | 3 |
| `source_gap` | 2 |
| `contradiction` | 1 |
| `not_comparable` | 0 |

### Module-level constants

`DIRECTION_IMPROVED`, `DIRECTION_DEGRADED`, `DIRECTION_UNCHANGED`,
`DIRECTION_NEW`, `DIRECTION_DROPPED`, `ACTIONS_COVERAGE_SYMMETRIC`,
`ACTIONS_COVERAGE_OLD_ONLY`, `ACTIONS_COVERAGE_NEW_ONLY`,
`ACTIONS_COVERAGE_NEITHER`.

---

## 12. Configuration

| Environment variable | Default | Effect |
|---|---|---|
| `FORENSIC_ACTIONS_CORPUS` | _(unset)_ | Set to `migration_v8` to attach corpus-literal supplementaries (`brochure_redgreen`, `klerk_npa_links`, `eaeu_split`, `amendment_chain`) to every bundle produced by the pipeline. Generic batches work without this variable. |
| `DATA_DIR` | `./data` | Root directory for batch state and artifact storage. |
| `READ_FROM_DB` | `true` | Set to `false` to read batch state from JSON files only (useful for tests). |

**ADR — Catalogue split design:**
Pair-level `actions_catalogue` and `raci_matrix` are always-on because
`actions_for_pair` returns `[]` for doc-IDs that don't match any rule —
there is no domain leakage. Corpus-literal supplements are opt-in to
prevent Russian migration content appearing in unrelated batches.
The kill-switch alternative (`FORENSIC_ACTIONS_DISABLED`) was rejected
because it produces two canonical bundle shapes and recreates the
inconsistency it aimed to prevent.

---

## 13. Delta Renderers (`docdiffops.forensic_delta_render`)

Render the JSON delta produced by `forensic_delta.compare_bundles` into
ULTRA-HQ, share-ready artifacts. All three renderers reuse the bundle
design vocabulary (`PALETTE`, `STATUS_RU`, `STATUS_PALETTE`).

### `render_delta_xlsx(delta, out_path) -> None`

Multi-sheet workbook with cover, status changes, distribution diff,
and (when present) new/removed pair sheets:

| # | Sheet | Content |
|---|---|---|
| 00 | Обложка | Title bar, 5 KPI tiles (Пар всего / Изменено / Закрыто / Новых / Удалено), asymmetric-actions warning |
| 01 | Изменения статусов | Pair-level status shifts with Russian column labels and direction badges |
| 02 | Распределение (Δ) | Status-distribution delta with green/red coloring by sign |
| 03 | Новые пары *(conditional)* | Pairs present only in the new bundle |
| 04 | Удалённые пары *(conditional)* | Pairs present only in the old bundle |

### `render_delta_docx(delta, out_path) -> None`

Narrative DOCX with cover, executive summary, and status-shift list.
`language="ru-RU"`. Footer with page numbers via field codes.

### `render_delta_pdf(delta, out_path) -> None`

Paginated PDF with title bar, 5 KPI cards (color-blocked), distribution
table with sign-coded delta column, status-changes table with direction
badges. `Страница N` footer + `DOCDIFFOPS · FORENSIC v8` header on every page.

### CLI usage

```bash
python -m docdiffops.forensic_cli compare old.json new.json --out delta.json --render-artifacts
# → writes delta.json + delta.xlsx + delta.docx + delta.pdf
```

### REST usage

```bash
curl 'https://diff.zed.md/batches/A/forensic/compare/B?artifacts=true'
# Persists delta.json + delta.xlsx + delta.docx + delta.pdf into batch B's
# reports dir and registers them as forensic_delta{,_xlsx,_docx,_pdf} artifacts.
```

---

## 14. Trend Analysis (`docdiffops.forensic_trend`)

Aggregate N consecutive v8 bundles into a time-series view for longitudinal
quality tracking.

### `compute_trend(bundles) -> dict`

Pure function. Bundles must be in chronological order (oldest first) and
each must have `schema_version` starting with `"v8."`.

```python
from docdiffops.forensic_trend import compute_trend

trend = compute_trend([bundle_jan, bundle_feb, bundle_mar])
# {
#   "schema_version": "v8-trend",
#   "bundle_count": 3,
#   "timeline": [{...per-bundle snapshot...}],
#   "status_series": {"match": [10, 12, 15], ...},
#   "match_share_series": [50.0, 60.0, 75.0],
#   "contradiction_series": [4, 3, 1],
#   "review_series": [...],
#   "trend_direction": "improving",  # improving | degrading | stable
# }
```

`trend_direction` compares first-vs-last `match_share`; >1.0pp ⇒ improving,
<-1.0pp ⇒ degrading, otherwise stable.

### REST usage

```bash
curl 'https://diff.zed.md/forensic/trend?ids=batch_jan,batch_feb,batch_mar'
# 200 → v8-trend report
# 404 if any batch's bundle is missing
# 422 on schema version mismatch
# 400 if ids parameter is empty
```

---

## 15. Quality Infrastructure

**`scripts/forensic_quality_check.sh`** — runs the full forensic test
suite, computes coverage, verifies imports, and validates a synthetic
schema-conformant bundle. Verdict: PASS / FAIL.

**`Makefile`** targets:
- `make test-forensic` — run all forensic tests
- `make mypy` — strict type-check on the 6 forensic modules
- `make quality` — full quality gate
- `make demo` — generate sample artifacts under `/tmp/forensic_demo/`

**`mypy.ini`** — strict configuration for `forensic`, `forensic_schema`,
`forensic_actions`, `forensic_delta`, `forensic_trend`, `forensic_cli`.
Per-module `[mypy-X]` blocks list every strict-implied flag explicitly
because `strict = True` doesn't propagate inside per-module sections
(mypy issue #11401).

**`.github/workflows/forensic-ci.yml`** — runs the quality gate + mypy on
every push or PR that touches forensic code. Uploads coverage report as
an artifact.
