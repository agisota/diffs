# Инструкция агенту: Интегральное перекрёстное сравнение v10

## 1. Цель

Выполнить **полное all-to-all попарное сравнение** корпуса из 26 документов по миграционной политике РФ (2025-2026). Каждый документ сравнивается с каждым (C(26,2) = 325 пар). Результат — структурированный деливери-пакет: пояснительная записка, визуальные таблицы, машинные CSV/XLSX, PDF/DOCX отчёты.

## 2. Контекст проекта

Это **DocDiffOps** — воспроизводимый пайплайн сравнения русскоязычных юридических/политических документов: НПА, концепции, госпланы, аналитические презентации, веб-дайджесты. Ключевые принципы:

- **Anchor — это view, не compute.** Сравнения симметричны и персистентны. Смена якорного документа только переключает red/green направление при рендере.
- **Детерминированный слой — до LLM.** Каждый diff-event обязан нести quote, page, bbox, source_rank ДО того, как модель получает право назвать что-то «противоречием».
- **Source rank gate.** rank-3 (презентация, аналитика) не может породить `contradicts` против rank-1 (ФЗ, Указ). rank-3→rank-1 максимум `suggests_review`.
- **Все CSV с UTF-8 BOM** (`﻿`), чтобы Excel открывал кириллицу без ручной настройки.
- **PDF с Noto Sans / DejaVu fallback** для кириллицы, нумерация «Страница N».

## 3. Входные данные

### 3.1. Корпус документов (26 штук)

Реестр источников: `04_машинные_приложения/01_реестр_источников.csv` (UTF-8 BOM, 27 строк с заголовком).

Поля: `id, name, short, type, rank, force, date, provenance, url, notes`

**Source rank иерархия:**

| Rank | Тип | Примеры | Вес в сравнении |
|------|-----|---------|-----------------|
| 1 | primary law / strategy | Концепция 2026-2030, ФЗ, ПП | Безусловный приоритет |
| 2 | secondary regulation / plan | Госпрограммы, планы мероприятий | Подчинён rank-1 |
| 3 | analytics / claim source | Презентации, ВЦИОМ, брошюры | Может подтверждать, не опровергать rank-1 |
| 4 | methodology / examples | Инструкции, примеры выгрузок | Контекст, не evidence |

### 3.2. Исходные тексты документов

`06_исходные_НПА_и_forensic_snapshot/` — forensic-снимки релевантных положений каждого НПА + скачанные оригиналы в `downloaded_sources/`.

Формат снимков: `D{NN}_{название}_снимок_релевантных_положений_v7.txt` — извлечённые статьи/пункты/абзацы, релевантные миграционной тематике.

### 3.3. Результаты предыдущих итераций (входной бенчмарк)

- `09_integral_cross_comparison_v8/` — данные v8 для сравнения с v10 (тренд изменений)
- `migration_v7_evidence/` — полная evidence-grade база v7 (26 доков, 325 пар, 281 событие)

### 3.4. Машинные данные (CSV)

Все CSV в `04_машинные_приложения/`:

| Файл | Строк | Содержание |
|------|-------|------------|
| `01_реестр_источников.csv` | 27 | Реестр всех 26 документов |
| `02_документ_документ.csv` | 352 | Попарные отношения (doc↔doc) |
| `03_тема_документ.csv` | 379 | Связь тема↔документ |
| `04_тезисы_НПА.csv` | 88 | Извлечённые тезисы из НПА |
| `05_риски_и_противоречия.csv` | 55 | Выявленные риски |
| `06_очередь_ручной_проверки.csv` | 55 | Очередь на manual review |
| `07_provenance_downloaded_sources.csv` | 113 | Provenance скачанных файлов |
| `08_redgreen_diff_layer.csv` | 11 | Red/green diff metadata |
| `09_QA.csv` | 9 | QA-проверки |
| `10_все_события.csv` | 313 | Все diff-события |
| `11_ЕАЭС.csv` | 6 | Данные по ЕАЭС (Договор, ст.96-98) |
| `12_ruID_ПП1510.csv` | 16 | Russian ID / ПП-1510 маппинг |
| `13_ВНЖ_инвестор.csv` | 12 | ВНЖ инвестор данные |
| `14_ВЦИОМ.csv` | 13 | ВЦИОМ claims |
| `состояние_интегрального_сравнения.json` | — | Полный state v9 |

## 4. Что нужно сделать

### 4.1. All-to-all попарное сравнение (325 пар)

Для каждой пары (doc_A, doc_B):

1. **Текстовое извлечение:** загрузить forensic-снимки обоих документов, нормализовать текст (ё→е, strip NBSP/ZWSP/BOM, lowercase для fuzzy, оригинал для quote).

2. **Структурное сравнение:**
   - Если оба документа — НПА (rank 1-2): сравнить по статье→пункту→абзацу (legal_structural_diff). Сопоставить формулировки, выявить изменения в регулировании.
   - Если хотя бы один — analytics/presentation (rank 3): извлечь claims из аналитического документа и проверить каждый claim против релевантных положений НПА (claim_validation).
   - Для пар одного типа: fuzzy block diff (rapidfuzz token_set_ratio с порогами 92/78).

3. **Классификация каждого diff-события:**
   - `status`: `identical` | `minor_edit` | `partial` | `contradicts` | `not_found` | `added` | `deleted` | `structural_change`
   - `severity`: `info` | `low` | `medium` | `high` | `critical`
   - `confidence`: 0.0-1.0
   - `source_rank_applied`: фактический rank-gate (например, «rank-3→rank-1, downgrade: suggests_review»)

4. **Source rank gating (КРИТИЧНО):**
   - rank-3 vs rank-1: максимум `suggests_review`, никогда `contradicts`
   - rank-3 vs rank-2: максимум `partial`, никогда `contradicts`
   - rank-1 vs rank-1: полный спектр статусов
   - rank-2 vs rank-2: полный спектр
   - rank-2 vs rank-1: `contradicts` допустим если quote точный

5. **Обязательные поля каждого события:**
   ```
   event_id, pair_id, lhs_doc_id, rhs_doc_id,
   status, severity, confidence, comparison_type,
   lhs_quote, rhs_quote,          # точные цитаты
   lhs_page, rhs_page,            # номера страниц
   lhs_bbox, rhs_bbox,            # координаты на странице
   lhs_rank, rhs_rank,            # source ranks
   source_rank_applied,           # какой gate применился
   explanation,                   # человекочитаемое объяснение
   reviewer_decision,             # null / confirmed / rejected / modified
   ```

### 4.2. Корреляционный анализ

Для каждой темы (миграция, ВНЖ инвестор, ЕАЭС, ПП-1510, ВЦИОМ и т.д.):

1. **Cross-document correlation matrix:** какие документы подтверждают друг друга по конкретным тезисам, какие противоречат.
2. **Claim provenance chain:** откуда пришел тезис → в каких документах он подтверждается → в каких оспаривается → какой rank у подтверждающих/оспаривающих источников.
3. **Dependency graph:** какие нормы ссылаются на какие, какие тезисы зависят от каких положений.
4. **Coverage heatmap:** какие темы покрыты какими документами, где пробелы.

### 4.3. Пояснительная записка (обязательный deliverable)

Структура (объём 10-15 страниц):

```
1. Введение
   - Цель сравнения, методология, ограничения
   - Состав корпуса (26 документов), период, source-rank иерархия

2. Методология
   - All-to-all (325 пар), типы сравнения (legal_structural / claim_validation / block_semantic)
   - Source rank gating
   - Пороги и confidence

3. Сводка результатов
   - Всего событий, по статусам (pie chart)
   - По severity (bar chart)
   - По comparison_type
   - Тренд v7→v8→v9→v10 (если есть предыдущие итерации)

4. Ключевые противоречия (top-20 high/critical)
   - Для каждого: какие документы, какие цитаты, какой rank-gate, рекомендация
   - Группировка по темам

5. Подтверждённые нормы (consensus)
   - Тезисы, которые подтверждаются 3+ независимыми источниками
   - Cross-reference matrix

6. Пробелы в регулировании
   - Темы, которые поднимаются в analytics (rank-3), но не покрыты НПА (rank-1-2)
   - Конкретные цитаты-сигналы

7. Корреляции и зависимости
   - Claim provenance chains для ключевых тезисов
   - Dependency graph (описание + ссылка на визуализацию)

8. Очередь ручной проверки
   - Events со status=partial / confidence<0.7, требующие юриста
   - Приоритизация по severity × impact

9. Ограничения и caveats
   - Что не проверялось (OCR, таблицы, изображения)
   - Где confidence низкий и почему
   - Версия пайплайна, дата запуска

10. Приложения
    - Ссылки на XLSX, CSV, PDF, DOCX
    - Glossary терминов
```

### 4.4. Визуальные таблицы (XLSX, 10+ листов)

Листы в `Интегральное_перекрестное_сравнение_v10.xlsx`:

| # | Лист | Содержание | Форматирование |
|---|------|-----------|----------------|
| 00 | summary | Метрики: кол-во пар, событий, по статусам/severity | KPI-style |
| 01 | source_inventory | Реестр 26 документов (rank, type, date) | Conditional formatting по rank |
| 02 | pair_matrix | 26×26 матрица статусов (heatmap) | Color-coded: red=contradicts, yellow=partial, green=identical |
| 03 | events_all | Все diff-события (full columns) | Auto-filter, severity conditional |
| 04 | contradictions | Только status=contradicts | Hyperlink на PDF страницу |
| 05 | partial_matches | Только status=partial | С explanation |
| 06 | not_found | Тезисы не найденные в контрагенте | С claim source |
| 07 | legal_changes | Структурные изменения НПА | по статье/пункту |
| 08 | claim_validation | Claims из analytics vs НПА | rank-gate column |
| 09 | correlation_matrix | Тема×Документ coverage | Heatmap |
| 10 | dependency_graph | Норма A → влияет на → Норму B | С весом связи |
| 11 | review_queue | Очередь ручной проверки | Приоритет × severity |
| 12 | false_positives | Отклонённые reviewer-ом события | С причиной |
| 13 | trend_v7_v8_v10 | Тренд по итерациям | Timeline chart |
| 14 | metrics | Precision/Recall/F1 vs manual labels | Если есть |

**Форматирование XLSX:**
- UTF-8 BOM во всех CSV/листах
- Conditional formatting: severity (critical=red, high=orange, medium=yellow, low=green)
- Hyperlinks: event_id → PDF страница, doc_id → source_registry
- Frozen panes: header row frozen, first 2 columns frozen
- Column widths: auto-fit
- Print area: настроен для A4 landscape

### 4.5. PDF/DOCX отчёты

**Пояснительная записка (DOCX + PDF):**
- Формат A4, поля 20mm, шрифт Noto Sans / DejaVu Sans
- Нумерация: «Страница N из M»
- Содержание с гиперссылками
- Таблицы внутри текста (correlation matrix, top-20 contradictions)
- Сноски на source documents

**Редакционный diff (DOCX + PDF):**
- Red/green аннотации на canonical PDF
- LHS = red (удалено/изменено), RHS = green (добавлено/новое)
- Каждая аннотация связана с event_id (title в PDF annot info dict)

**Интегральное перекрёстное сравнение (PDF):**
- Визуальная матрица 26×26 с цветовой кодировкой
- Легенда статусов
- Топ-10 рисков с цитатами

## 5. Порядок выполнения

### Фаза 1: Ingestion (1 час)
1. Загрузить `01_реестр_источников.csv` → получить список 26 документов
2. Загрузить forensic-снимки из `06_исходные_НПА_и_forensic_snapshot/` для каждого doc_id
3. Загрузить все CSV из `04_машинные_приложения/` как baseline
4. Загрузить state v9 (`состояние_интегрального_сравнения.json`) для delta detection

### Фаза 2: Comparison (основная работа, 4-6 часов)
1. Сгенерировать 325 пар (all-to-all)
2. Для каждой пары выполнить comparison по типу (legal_structural / claim_validation / block_semantic)
3. Применить source_rank_gate к каждому событию
4. Записать все события в `10_все_события.csv` (update)
5. Вычислить корреляции и зависимости

### Фаза 3: Analysis (2-3 часа)
1. Correlation matrix по темам
2. Claim provenance chains
3. Dependency graph
4. Coverage heatmap
5. Trend v7→v8→v10

### Фаза 4: Reporting (2-3 часа)
1. XLSX (14 листов)
2. Пояснительная записка (DOCX → PDF)
3. Редакционный diff (DOCX + PDF)
4. Интегральная таблица (PDF)

### Фаза 5: QA (1 час)
1. Все CSV открываются в Excel без encoding артефактов
2. Все PDF рендерят кириллицу корректно
3. Все event_id уникальны и стабильны
4. Source rank gate применён корректно (ни одного rank-3→rank-1 contradicts)
5. XLSX hyperlinks работают
6. Quotes в событиях реально найдены в исходных текстах

## 6. Выходной деливери-пакет

```
/tmp/forensic_final_v10/
├── bundle/
│   ├── forensic_v10_summary.pdf        # Интегральный отчёт PDF
│   ├── forensic_v10_explanatory.docx    # Пояснительная записка DOCX
│   ├── forensic_v10_explanatory.pdf     # Пояснительная записка PDF
│   ├── forensic_v10_redgreen.docx       # Red/green diff DOCX
│   ├── forensic_v10.xlsx                # 14-листный XLSX
│   ├── bundle.json                      # Машинный state
│   ├── actions.csv                      # UTF-8 BOM
│   ├── documents.csv
│   └── pairs.csv
├── delta/
│   ├── delta.docx / delta.pdf / delta.xlsx / delta.json
│   ├── distribution_diff.csv
│   └── status_changes.csv
├── trend/
│   ├── trend.json
│   └── trend_timeline.csv              # v7→v8→v10 тренд
└── README_v10.txt
```

Все CSV с UTF-8 BOM. Все PDF с кириллицей (Noto Sans/DejaVu). Нумерация «Страница N». Открываются в Excel/Word/Acrobat без дополнительной обработки.

## 7. Критерии приёмки

- [ ] 325 пар обработано, 0 пропущено
- [ ] Ни одного rank-3→rank-1 `contradicts` (gate работает)
- [ ] Каждое событие имеет quote + page + source_rank
- [ ] CSV открываются в Excel → кириллица OK (BOM)
- [ ] PDF рендерятся → кириллица OK (Noto Sans/DejaVu)
- [ ] XLSX имеет 14 листов, conditional formatting, hyperlinks
- [ ] Пояснительная записка ≥10 страниц, все 10 разделов
- [ ] Correlation matrix построена, dependency graph описан
- [ ] Review queue сформирован (все partial/low-confidence)
- [ ] Trend v7→v10 показан (если есть дельта)
- [ ] `rsync` деливери на `bit:/home/dev/diff/` прошёл без ошибок
