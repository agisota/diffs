# Sprint 6 — v10-quality bundle in production pipeline

> **Прогресс на 2026-05-09 — SPRINT 6 CLOSED ✅ (7/7 PR done)**:
> - **PR-6.1 ✓** (iter1) — `forensic_correlations.py`, 255 LOC, 9 tests, mypy strict
> - **PR-6.2 ✓** (iter2) — `render_v8_xlsx` 10→14 sheets, +272 LOC, 5 tests, backwards-compat preserved
> - **PR-6.3 ✓** (iter2) — `forensic_note.py`, 1074 LOC, 8 tests, mypy strict
> - **PR-6.4 ✓** (iter1) — `render_integral_matrix_pdf`, +455 LOC, 5 tests
> - **PR-6.5 ✓** (iter3) — `pipeline._render_v10_bundle()` под `V10_BUNDLE_ENABLED`, +130 LOC, 4 tests
> - **PR-6.6 ✓** (iter3) — `main.py` API: 8 new kinds + `GET /forensic/v10`, +53 LOC, 10 tests
> - **PR-6.7 ✓** (iter4) — Web UI v10 download block + `scripts/v10_smoke.sh` + CLAUDE.md/README.md docs, +80 UI LOC + 141 smoke LOC + ~50 docs LOC
>
> **Cumulative:** **2510 LOC + 41 tests** добавлено в production-кодовую базу за 4 autopilot iterations.
>
> **Final quality gates:**
> - `make test-forensic` → **203 passed** (162 baseline → +41)
> - `make mypy` → **8 source files clean** (6 baseline → +forensic_correlations + forensic_note)
> - `make quality` → **VERDICT=PASS, coverage 97%**
> - Backwards-compat **preserved end-to-end** (без env flag поведение неизменно; existing 5 v8 download kinds работают как раньше)
>
> **Verdicts:** `.omx/state/code-review-verdict-sprint6-iter{1,2,3,4}.md` (все APPROVE+CLEAR, 0 blockers).
>
> **diff.zed.md теперь нативно умеет** под `V10_BUNDLE_ENABLED=true`:
> 1. После любого `POST /batches/{id}/run` производит 8 v10-quality артефактов в `batch_dir/reports/v10/`
> 2. Отдаёт их через `GET /forensic/v10` (JSON со списком URL) и `GET /forensic/{kind}` (8 новых kinds)
> 3. Web UI показывает download-блок когда v10 готов
> 4. E2E smoke test покрывает upload→run→download→validate flow


**Цель:** `diff.zed.md` нативно отдаёт бандл v10-качества для любого батча документов, без офлайн-скриптов.

**Входная точка:** наши офлайн-скрипты `migration_v10_out/scripts/01..08` уже работают и прошли code-review CLEAR. Sprint 6 — это **рефакторинг этих скриптов в production-модули `docdiffops/forensic_*`** + проводка через `pipeline.py` + `main.py`.

**Decisions locked** (2026-05-09 user):
- Скоуп: все 4 v10-фичи
- Форма: 7 атомарных PR (PR-6.1..6.7)
- Размещение: расширяем `docdiffops/forensic_*` (а не новый namespace)

---

## PR-6.1 — `forensic_correlations.py` (новый модуль)

**Источник:** `migration_v10_out/scripts/02_correlations.py`

**API:**
```python
# docdiffops/forensic_correlations.py
def compute_correlation_matrix(
    themes: list[dict], docs: list[dict], theme_doc_links: list[dict],
) -> dict[str, dict[str, int]]: ...

def compute_claim_provenance(
    theses: list[dict], events: list[dict], docs: list[dict],
) -> list[dict]: ...

def compute_dependency_graph(
    pair_relations: list[dict], docs: list[dict],
) -> list[dict]: ...

def compute_coverage_heatmap(
    correlation_matrix: dict, docs: list[dict],
) -> dict[str, dict[int, int]]: ...

def emit_correlation_csvs(
    bundle: dict, out_dir: Path, *, write_bom: bool = True,
) -> dict[str, Path]:
    """Compute all 4 analyses and emit BOM-prefixed CSVs.
    Returns dict mapping analysis name → output path."""
```

**Tests** (`tests/unit/test_forensic_correlations.py`):
- `test_correlation_matrix_shape` — 14 тем × 27 доков; non-zero diagonal where doc covers its own theme
- `test_claim_provenance_full_chain` — claim with 3 confirming + 1 refuting docs
- `test_dependency_graph_relation_types` — `amends`, `references`, `provenance`, `methodology`
- `test_coverage_heatmap_rank_distribution` — sums match per-theme totals
- `test_emit_csvs_have_bom` — first 3 bytes == EFBBBF
- `test_empty_inputs_dont_crash` — все 4 функции на пустом input возвращают пустые структуры (не None)

**mypy strict:** добавить `[mypy-docdiffops.forensic_correlations]` блок в `mypy.ini` с теми же флагами что у других forensic-модулей.

**Размер:** ~250 строк, ~6 тестов.

---

## PR-6.2 — Расширение `forensic_render.py` до 14-листного XLSX

**Источник:** `migration_v10_out/scripts/03_render_xlsx.py`

**Изменения в `forensic_render.py`:**

1. Существующий `render_v8_xlsx(bundle, out_path)` → принимает опциональный `correlations: dict | None`
2. Если `correlations` переданы — добавить 4 новых листа:
   - `correlation_matrix` (heatmap по color scale)
   - `claim_provenance`
   - `dependency_graph` (отсортирован по relation_type, weight desc)
   - `coverage_heatmap`
3. Уплотнить листы с conditional formatting:
   - `source_inventory` — color на колонке `rank` (1=green, 2=blue, 3=yellow, 4=gray)
   - `events_all` — color на severity (high=red, medium=orange, low=green)
   - `pair_matrix` — symbolic heatmap по статусу
4. Добавить hyperlinks: где у event есть `pdf_link` или `docx_link` колонки — превратить в `cell.hyperlink`
5. Frozen panes на каждом data-листе (header + 1-2 первых колонки)
6. Обновить `summary` лист до KPI-tile стиля (как v10 Sheet 00)

**Tests** (`tests/unit/test_forensic_render.py` — расширить):
- `test_xlsx_has_14_sheets_when_correlations_supplied` — `len(wb.sheetnames) >= 14`
- `test_xlsx_has_10_sheets_without_correlations` — backwards-compat
- `test_pair_matrix_color_coding` — verify CF rules count
- `test_correlation_heatmap_colorscale` — Color scale rule applied to matrix range
- `test_summary_kpi_tile` — A1=label, A2=value pattern

**Совместимость:** старые вызовы `render_v8_xlsx(bundle, path)` (без correlations) → 10 листов как было.

**Размер:** +~400 строк, +5 тестов.

---

## PR-6.3 — `forensic_note.py` (новый модуль)

**Источник:** `migration_v10_out/scripts/04_render_note.py` (1191 строка — самая объёмная часть)

**API:**
```python
# docdiffops/forensic_note.py
def render_explanatory_note_docx(
    bundle: dict,
    correlations: dict,
    out_path: Path,
    *,
    pipeline_version: str = "10.0.0",
) -> Path: ...

def render_explanatory_note_pdf(
    bundle: dict,
    correlations: dict,
    out_path: Path,
    *,
    pipeline_version: str = "10.0.0",
) -> Path: ...

def _register_cyrillic_font(reportlab_canvas) -> str:
    """Try Noto Sans, then DejaVu Sans, then fallback. Returns font name."""

# Internal chapter renderers (one per chapter, both DOCX and PDF):
def _chapter_introduction(bundle): ...
def _chapter_methodology(bundle): ...
def _chapter_results_summary(bundle): ...
def _chapter_top_contradictions(bundle): ...
def _chapter_consensus_norms(bundle, correlations): ...
def _chapter_regulation_gaps(bundle, correlations): ...
def _chapter_correlations(bundle, correlations): ...
def _chapter_review_queue(bundle): ...
def _chapter_caveats(bundle): ...
def _chapter_appendix(bundle): ...
```

**Tests** (`tests/unit/test_forensic_note.py`):
- `test_docx_has_10_chapters` — `len([p for p in doc.paragraphs if p.style.name == 'Heading 1']) >= 10`
- `test_pdf_renders_cyrillic` — `pdftotext` output contains 'Введение'
- `test_pdf_has_at_least_10_pages` — page count check
- `test_docx_table_of_contents` — TOC entry list matches chapters
- `test_font_fallback_chain` — when Noto missing, falls back to DejaVu
- `test_empty_bundle_doesnt_crash` — minimal bundle still produces valid DOCX

**mypy strict:** добавить блок.

**Размер:** ~600 строк рефакторинга (v10 был 1191, можно сжать), ~6 тестов.

---

## PR-6.4 — Integral matrix renderer в `forensic_render.py`

**Источник:** `migration_v10_out/scripts/05_render_diff.py` (часть про integral PDF)

**Новая функция в `forensic_render.py`:**
```python
def render_integral_matrix_pdf(
    bundle: dict,
    out_path: Path,
    *,
    page_size: str = "A3-landscape",  # auto-fall back to A4 when N <= 12 docs
    top_n_events: int = 10,
) -> Path:
    """Render N×N visual matrix with status colors + legend + top-N events.

    Page layout: cover, status legend page, matrix page (A3 landscape if N>=20),
    top-N events page.
    """
```

**Tests** (`tests/unit/test_forensic_render.py` — расширить):
- `test_integral_matrix_27x27_a3` — N=27 → A3 landscape used
- `test_integral_matrix_8x8_a4` — N=8 → A4 portrait (fallback)
- `test_status_legend_present` — page 2 contains 7 status names
- `test_top_n_events_renderered` — page 4 has N event blocks

**Размер:** ~250 строк, +4 теста.

---

## PR-6.5 — `pipeline.py` wire-up

**Расширение `pipeline.run_batch`:**

После существующего `_render_forensic_bundle` (бандл v8) добавить новый этап:

```python
def _render_v10_bundle(batch_id, state, bundle, repo=None):
    """Generate v10-quality artifacts: correlations, full XLSX, note, integral matrix.

    Idempotent. Outputs go to batch_dir/reports/v10/.
    Each artifact registered via state.add_artifact().
    """
    out_dir = batch_dir(batch_id) / "reports" / "v10"
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1. Correlations
    correlations = forensic_correlations.compute_all(bundle)
    csv_paths = forensic_correlations.emit_correlation_csvs(bundle, out_dir)
    for name, path in csv_paths.items():
        state.add_artifact(state, f"v10_correlation_{name}", path)

    # 2. 14-sheet XLSX (replace the v8 10-sheet one)
    xlsx_path = out_dir / "Интегральное_перекрестное_сравнение_v10.xlsx"
    forensic_render.render_v8_xlsx(bundle, xlsx_path, correlations=correlations)
    state.add_artifact(state, "v10_xlsx", xlsx_path)

    # 3. Explanatory note
    note_docx = out_dir / "Пояснительная_записка_v10.docx"
    note_pdf = out_dir / "Пояснительная_записка_v10.pdf"
    forensic_note.render_explanatory_note_docx(bundle, correlations, note_docx)
    forensic_note.render_explanatory_note_pdf(bundle, correlations, note_pdf)
    state.add_artifact(state, "v10_note_docx", note_docx)
    state.add_artifact(state, "v10_note_pdf", note_pdf)

    # 4. Integral matrix
    matrix_pdf = out_dir / "Интегральное_перекрестное_сравнение_v10.pdf"
    forensic_render.render_integral_matrix_pdf(bundle, matrix_pdf)
    state.add_artifact(state, "v10_integral_matrix", matrix_pdf)
```

**Гейтинг:** этап управляется новым env flag `V10_BUNDLE_ENABLED` (default `false` в первом релизе → opt-in, как у `SEMANTIC_COMPARATOR_ENABLED`). Когда `true` и `pipeline.run_batch` завершает успешно — v10 этап запускается.

**Tests** (`tests/unit/test_forensic_pipeline_integration.py` — расширить):
- `test_v10_bundle_disabled_by_default` — без env var артефакты не появляются
- `test_v10_bundle_enabled_produces_all_artifacts` — с env var все 7 артефактов в reports/v10/
- `test_v10_bundle_idempotent` — двойной запуск не падает
- `test_v10_bundle_after_pipeline_failure` — если основной pipeline failed, v10 не запускается

**Размер:** +~150 строк в pipeline.py, +4 теста.

---

## PR-6.6 — `main.py` API endpoints

**Расширение существующего `GET /batches/{batch_id}/forensic/{kind}`:**

Новые `kind` значения:
- `note_docx`, `note_pdf`
- `integral_matrix_pdf`
- `correlation_matrix_csv`, `dependency_graph_csv`, `claim_provenance_csv`, `coverage_heatmap_csv`
- `xlsx_v10` (14-листный, в дополнение к существующему `xlsx`)

**Новый endpoint:**
```python
@app.get("/batches/{batch_id}/forensic/v10")
def get_batch_v10_bundle(batch_id: str):
    """Return URLs for all v10 artifacts in this batch.

    404 if V10_BUNDLE_ENABLED=false or batch hasn't completed.
    """
    return {
        "batch_id": batch_id,
        "artifacts": {
            "xlsx": "/batches/{batch_id}/forensic/xlsx_v10",
            "note_docx": "/batches/{batch_id}/forensic/note_docx",
            "note_pdf": "/batches/{batch_id}/forensic/note_pdf",
            "integral_matrix_pdf": "/batches/{batch_id}/forensic/integral_matrix_pdf",
            "correlation_csv": "/batches/{batch_id}/forensic/correlation_matrix_csv",
            "dependency_csv": "/batches/{batch_id}/forensic/dependency_graph_csv",
            "claim_provenance_csv": "/batches/{batch_id}/forensic/claim_provenance_csv",
            "coverage_csv": "/batches/{batch_id}/forensic/coverage_heatmap_csv",
        },
    }
```

**Tests** (`tests/integration/test_forensic_api.py` — расширить):
- `test_v10_endpoint_returns_404_when_disabled`
- `test_v10_endpoint_returns_artifact_urls_when_enabled`
- `test_download_each_v10_artifact_kind` — параметризованный тест по 7 kind

**Размер:** +~80 строк, +9 тестов.

---

## PR-6.7 — Web UI + docs + smoke

**`docdiffops/app_html.py`:**
- Когда батч завершён и v10 включён — добавить блок "v10 Forensic Bundle" с 8 download-ссылками (XLSX, DOCX×2, PDF×2, CSV×4)
- Кнопка "Скачать все артефакты v10 zip" — генерирует zip из `reports/v10/`

**`docdiffops_mvp/README.md` + корневой `CLAUDE.md`:**
- Документировать `V10_BUNDLE_ENABLED` env flag
- Список новых артефактов и эндпоинтов
- Sprint 6 entry в README sprint-таблице

**Smoke test** (`scripts/v10_smoke.sh`):
- Поднять docker compose
- Создать batch, загрузить 3 sample documents
- Включить V10_BUNDLE_ENABLED=true
- Запустить pipeline синхронно
- Скачать все 8 v10 артефактов
- Pdftotext каждый PDF, проверить кириллицу
- Openpyxl XLSX, проверить 14 листов

**Размер:** +~150 строк HTML/JS, +~50 строк bash, +~30 строк docs.

---

## Order of merge

```
PR-6.1 (correlations)       ──┐
PR-6.2 (xlsx 14 sheets)     ──┼── могут идти параллельно (independent files)
PR-6.3 (note)               ──┤
PR-6.4 (integral matrix)    ──┘
                              │
PR-6.5 (pipeline wire-up)    ←── зависит от 6.1-6.4
                              │
PR-6.6 (API endpoints)       ←── зависит от 6.5
                              │
PR-6.7 (web UI + smoke)      ←── зависит от 6.5+6.6
```

---

## Acceptance criteria для всего Sprint 6

- [ ] AC-S6-01: `pytest tests/` зелёный, +30 новых тестов прошли
- [ ] AC-S6-02: `make mypy` strict-чистый на 8 forensic-модулях (было 6, стало 8 — +correlations +note)
- [ ] AC-S6-03: `make quality` (forensic_quality_check.sh) verdict=PASS
- [ ] AC-S6-04: `V10_BUNDLE_ENABLED=true` + smoke test — все 8 артефактов скачиваются
- [ ] AC-S6-05: `pdftotext` на новых PDF выдаёт читаемую кириллицу
- [ ] AC-S6-06: `openpyxl.load_workbook(...)` на v10 XLSX — `len(sheetnames) == 14`
- [ ] AC-S6-07: Backwards compat — без env flag поведение pipeline не изменилось
- [ ] AC-S6-08: API contract — старый `GET /batches/{id}/forensic/{kind}` для v8 kinds работает как раньше
- [ ] AC-S6-09: docker compose up + alembic upgrade head + первый прогон работает out of the box
- [ ] AC-S6-10: README + CLAUDE.md актуальны: новый env flag, эндпоинты, артефакты задокументированы

---

## Estimate

| PR | LOC | Tests | Effort |
|---|---|---|---|
| 6.1 | +250 | +6 | small |
| 6.2 | +400 | +5 | medium |
| 6.3 | +600 | +6 | large |
| 6.4 | +250 | +4 | small |
| 6.5 | +150 | +4 | small |
| 6.6 | +80 | +9 | small |
| 6.7 | +230 | smoke | medium |
| **Σ** | **~1960** | **~34** | ~7-10 рабочих дней |

---

## Запуск Sprint 6

Когда готов начать:
```
$autopilot Sprint 6 PR-6.1..6.7 per /home/dev/diff/SPRINT_6_PLAN.md
```

Autopilot пройдёт по 7 PR через ralplan→ralph→code-review цикл, с возможностью dispatching-parallel-agents на PR-6.1..6.4 (они независимы).
