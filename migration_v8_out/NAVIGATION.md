# Forensic v8 — Навигатор пакета (v8.3)

**Корпус:** миграционный, Россия, 2018–2026. **Сгенерировано:** 2026-05-09 04:36:28Z
**Источник данных:** `/home/dev/diff/migration_v7_evidence/` (read-only)
**Этот пакет:** `/home/dev/diff/migration_v8_out/` (writable)

## Контрольные числа (все сходятся ✓)

| Параметр | Значение |
|---|---|
| Документов | 26 |
| Пар | 325 |
| Событий | 281 |
| Очередь ручной проверки | 183 |
| Финальные противоречия v7 | 3 |
| Source gaps v7 | 3 |
| Defect log v7 | 3 |
| Fallback-зеркал | 71 |
| FA-actions | 10 |
| Brochure red/green правок | 6 |
| Klerk → НПА footnotes | 6 |
| ЕАЭС split групп | 3 |
| Amendment chains | 5 |
| RACI ролей × FA | 40 |

## Релиз-таймлайн

| Версия | Дата | Что добавлено |
|---|---|---|
| **v8.0** | base | 15-листовой Excel + explanatory DOCX/PDF + red/green DOCX/PDF + 9 CSV + JSON bundle |
| **v8.1** | actionable | FA-01..FA-10 каталог; brochure red/green; Klerk→NPA links; ЕАЭС split; amendment chain; provenance actions; top-20 priority; Что делать DOCX/PDF; Несоответствия XLSX |
| **v8.2** | visual + system | 5 PNG visuals (heatmap, pie, bars, cover); cover PDF; RACI matrix CSV + Excel sheet; system module `docdiffops/forensic_actions.py` (16 tests); offline CLI `forensic_cli rebuild` |
| **v8.3** | schema + signoff | Formal JSON Schema (draft-07, 9 tests); doc xref index; sign-off form DOCX/PDF; updated NAVIGATION |

## Основные документы (читать сначала)

| Файл | Что внутри | Размер |
|---|---|---|
| **`docs/Forensic_v8_cover.pdf`** | Обложка с heatmap + pie + контрольные числа + RACI | ~480 KB |
| **`docs/Что_делать.docx`** + `.pdf` | План действий: FA-01..FA-10 с координатами и владельцами | 45/52 KB |
| **`docs/Лист_согласования.docx`** + `.pdf` | Sign-off form для юриста | new in v8.3 |
| **`docs/Интегральное_перекрестное_сравнение.xlsx`** | 15-листовой основной workbook | 89 KB |
| **`docs/Несоответствия_и_действия.xlsx`** | 9-листовой supplementary с heatmap + RACI | 152 KB |
| **`docs/Пояснительная_записка.docx`** + `.pdf` | Методика, ограничения, источники | 41/43 KB |
| **`docs/Редакционный_diff.docx`** + `.pdf` | Red/green editorial diff с основанием | 42/52 KB |

## Визуальный слой

| Файл | Что показывает |
|---|---|
| `docs/visuals/heatmap_doc_x_doc.png` | 26×26 цветная карта статусов |
| `docs/visuals/cover_summary.png` | Композит: pie + ranks + контрольные + top FA |
| `docs/visuals/topic_bar.png` | Bar-chart покрытия 17 тем |
| `docs/visuals/status_pie.png` | Распределение пар по 5 статусам |
| `docs/visuals/rank_pair_bar.png` | Распределение по rank-pair |

## Машинно-читаемые данные (`data/`)

| CSV/JSON | Что |
|---|---|
| `01_источники_v8.csv` | 26 источников + provenance статус |
| `02_pairs_v8.csv` | 325 пар с агрегированным v8-статусом и основанием |
| `03_doc_x_doc_matrix.csv` | 26×26 символьная матрица |
| `04_topic_x_doc.csv` | 17 кластеров × 26 документов |
| `05_thesis_x_npa.csv` | 128 тезисов вторичных vs НПА |
| `06_old_vs_new_redactions.csv` | 12 amendment-связок |
| `07_regime_x_regime.csv` | 8 правовых режимов |
| `08_provenance_risk.csv` | 27 строк + fallback aggregate |
| `09_manual_review_queue.csv` | 183 ручных проверки |
| `10_actions_catalogue.csv` | 10 FA-actions с WHERE/WHAT/FIX |
| `11_brochure_redgreen_diff.csv` | 6 cells: «более» → «не менее» |
| `12_klerk_npa_links.csv` | 6 footnotes |
| `13_eaeu_split.csv` | 3 группы (ЕАЭС / безвиз-патент / визовые-разрешение) |
| `14_amendment_chain.csv` | 5 цепочек поправок |
| `15_provenance_actions.csv` | 4 fallback-плана |
| `16_top_priority_review.csv` | 20 пар, ranked, с дедлайнами |
| `17_raci_matrix.csv` | RACI × FA-01..FA-10 |
| `18_doc_xref.csv` | new v8.3: для каждого D01..D26 — пары, темы, FA, поправки |
| `integral_cross_comparison.json` | Полный JSON snapshot (schema v8.0) |
| `v8_bundle.schema.json` | new v8.3: формальная JSON Schema (draft-07) |

## Системный код DocDiffOps (`/home/dev/diff/docdiffops_mvp/docdiffops/`)

| Модуль | Что делает | Тестов |
|---|---|---|
| `forensic.py` | V8_STATUSES, aggregate_pair_status_v8, build_forensic_bundle | 27 |
| `forensic_render.py` | render_v8_xlsx, render_v8_docx_explanatory/_redgreen, render_v8_pdf_summary | 4 |
| `forensic_actions.py` | DEFAULT_ACTIONS (10), apply_actions_to_bundle, raci_for_action | 16 |
| `forensic_schema.py` | BUNDLE_SCHEMA_DICT, validate_bundle | 9 |
| `forensic_cli.py` | `python -m docdiffops.forensic_cli rebuild bundle.json --out dir/` | (CLI) |
| `pipeline.py` | hook в render_global_reports → 5 артефактов | 6 |
| `main.py` | API: GET /batches/{id}/forensic[/{kind}] | — |
| **Итого** | | **62 forensic tests** |

## Шкала статусов v8

- `match` ✓ — совпадает
- `partial_overlap` ≈ — частично совпадает
- `contradiction` ⚠ — противоречие
- `outdated` ↻ — устарело после поправки
- `source_gap` ∅ — тезис без первичного подтверждения
- `manual_review` ? — нужен юрист
- `not_comparable` — — содержательно несопоставимо

## Иерархия источников (invariant)

- **rank-1** — первичный НПА (114-ФЗ, 115-ФЗ, 109-ФЗ, 260-ФЗ, 270-ФЗ, 271-ФЗ, 281-ФЗ, 121-ФЗ, ПП 2573, ПП 1510, ПП 1562, ПП 468, Указ 467, Концепция 2026/2019, План 4171-р/30-р, КоАП, Договор ЕАЭС, НК)
- **rank-2** — ведомственные материалы Минэка (D10, D18)
- **rank-3** — аналитика (D01 Нейрон, D02 пример выгрузки, D03 ВЦИОМ, D09 Клерк)
- **Правило C-02:** rank-3 не опровергает rank-1; пересечение rank-3 ↔ rank-1 → `manual_review`.

## CLI: offline rebuild

```bash
python -m docdiffops.forensic_cli rebuild bundle.json --out dir/ --with-actions
# rebuilds 5 artifacts under dir/
```

## Re-build всего пакета

```bash
# v8.0 базовый пакет
.venv/bin/python /home/dev/diff/migration_v8_out/scripts/build_integral.py

# v8.1 enhancement (FA-каталог, brochure, Klerk, ЕАЭС, amendments)
.venv/bin/python /home/dev/diff/migration_v8_out/scripts/enhance_v8.py

# v8.2 visuals + RACI + cover PDF
.venv/bin/python /home/dev/diff/migration_v8_out/scripts/build_visuals.py
.venv/bin/python /home/dev/diff/migration_v8_out/scripts/build_v8_2.py

# v8.3 schema + signoff + doc xref + NAVIGATION
.venv/bin/python /home/dev/diff/migration_v8_out/scripts/build_v8_3.py
```

## Ключевые риски — короткое резюме

- **C-01 / FA-02** Минэк-проект «Работа в ЕАЭС» включает Узбекистан/Таджикистан — НЕ члены ЕАЭС, должны быть в группе «патент» по 115-ФЗ.
- **C-03 / FA-01 / BR-01..BR-06** Брошюра Минэка использует «более X», ПП №2573 — «не менее X». Инвестор с пороговой суммой выпадает.
- **C-02 / FA-03 / KL-01..KL-06** Клерк (D09, rank-3) даёт 6 фактов без footnote-ссылок на НПА.
- **FA-04** Концепция 2019–2025 цитируется без отметки «утратила силу с D04».
- **FA-05 / AC-01** ПП №1510 цитируется без редакции 1562/468.
- **FA-06 / AC-02** 115/109-ФЗ без отметки «в ред. 270-ФЗ».
- **FA-07 / AC-03** КоАП ст.18.x без «в ред. 281-ФЗ».
- **FA-08** ВЦИОМ-claims смешаны с НПА.
- **FA-09 / PV-01..PV-04** Provenance: consultant.ru/pravo.gov.ru/mvd.ru нестабильны → fallback-mirrors.
- **FA-10 / U-01..U-03** Source gaps: внешние юрисдикции, статьи НК, постатейные планы.
