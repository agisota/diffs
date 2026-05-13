# DocDiffOps

**Сравнение документов всех-со-всеми с inline-просмотром правок и review-workflow.**

🌐 **Live:** [https://diff.zed.md](https://diff.zed.md) · Swagger: [/docs](https://diff.zed.md/docs)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                                                                             │
│   📄 PDF/DOCX/PPTX/XLSX/HTML/TXT  ──►  🔍 Сравнение  ──►  ✓ Принять/✗ Отк.  │
│                                          (all-to-all)         (review)      │
│                                                                             │
│   📤 Загрузка N документов  ──►  📊 N×(N-1)/2 пар  ──►  📥 Merged DOCX     │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

DocDiffOps берёт **2 или больше документов**, сравнивает каждый с каждым (Cn,2 пар),
показывает правки **визуально поверх страниц PDF** с цветовой кодировкой,
даёт reviewer'у принять или отклонить каждую правку, и выдаёт **итоговый
Word-документ** с применёнными решениями.

---

## 📋 Что внутри (содержание)

1. [Быстрый старт](#-быстрый-старт)
2. [Что загружать](#-что-загружать)
3. [Что получаешь на выходе](#-что-получаешь-на-выходе)
4. [Пользовательский flow](#-пользовательский-flow)
5. [Веб-интерфейс — гайд по экранам](#️-веб-интерфейс--гайд-по-экранам)
6. [Inline viewer — горячие клавиши](#️-inline-viewer--горячие-клавиши)
7. [API endpoints](#-api-endpoints)
8. [Архитектура](#-архитектура)
9. [Деплой](#-деплой)
10. [Переменные окружения](#-переменные-окружения)
11. [Troubleshooting](#-troubleshooting)

---

## 🚀 Быстрый старт

### Web-интерфейс (рекомендуется)

```
1. Откройте https://diff.zed.md/
2. Перетащите 2+ документа в drop-zone (или клик "Browse files")
3. Введите название batch'а → нажмите "Создать batch + Загрузить + Запустить"
4. Дождитесь pipeline (5 сек – 60 мин в зависимости от размера)
5. Открывается просмотр результатов с inline viewer
```

### CLI / API

```bash
# 1. Создать batch
BID=$(curl -sS -X POST https://diff.zed.md/batches \
  -H 'Content-Type: application/json' \
  -d '{"title":"Мой batch"}' | jq -r .batch_id)

# 2. Загрузить файлы
curl -X POST "https://diff.zed.md/batches/$BID/documents" \
  -F "files=@doc1.pdf" -F "files=@doc2.pdf"

# 3. Запустить pipeline (async)
TID=$(curl -X POST "https://diff.zed.md/batches/$BID/run?profile=fast" | jq -r .task_id)

# 4. Опрашивать статус (async + polling)
while true; do
  R=$(curl -sS "https://diff.zed.md/tasks/$TID")
  STATE=$(echo "$R" | jq -r .state)
  echo "$STATE"
  [ "$STATE" = "SUCCESS" ] && break
  sleep 5
done

# 5. Скачать merged DOCX (применены все accept/reject решения)
curl "https://diff.zed.md/batches/$BID/merged.zip" -o merged.zip
```

### Локальная разработка

```bash
cd docdiffops_mvp
docker compose up --build
# → http://localhost:8000/
```

---

## 📥 Что загружать

```
┌──────────┬───────────────────────────┬─────────────────────────────────┐
│ Формат   │ Что внутри                │ Visual bbox-подсветка           │
├──────────┼───────────────────────────┼─────────────────────────────────┤
│ .pdf     │ Документы PDF (любые)     │ ✅ Точные координаты от fitz    │
│ .docx    │ Word                      │ ✅ Через LibreOffice→PDF        │
│ .pptx    │ PowerPoint                │ ✅ Через LibreOffice + shape    │
│ .xlsx    │ Excel                     │ ⚠️ По sheet'ам, без cell-bbox  │
│ .html    │ Web-страницы              │ ✅ Через LibreOffice→PDF        │
│ .txt     │ Plain text                │ ✅ Через LibreOffice→PDF        │
│ .md      │ Markdown                  │ ✅ Через LibreOffice→PDF        │
│ .csv     │ CSV                       │ ✅ Через LibreOffice→PDF        │
└──────────┴───────────────────────────┴─────────────────────────────────┘
```

**Минимум 2 документа** для появления хотя бы одной пары сравнения.
Максимум не ограничен — но 12+ документов = C(12,2) = 66 пар × 30 сек = ~30 мин прогона.

---

## 📤 Что получаешь на выходе

```
┌─────────────────────────────────────────────────────────────────────────┐
│                                                                         │
│   Per-pair артефакты (для каждой пары документов):                      │
│   ┌─────────────────────────────────────────────────────────────────┐  │
│   │  📄 lhs_red.pdf          — левый документ с КРАСНОЙ подсветкой │  │
│   │  📄 rhs_green.pdf        — правый со ЗЕЛЁНОЙ подсветкой        │  │
│   │  📄 pagewise_redgreen.pdf — side-by-side с tooltip'ами         │  │
│   │  📝 track_changes.docx   — Word с реальными w:ins/w:del        │  │
│   │  📥 merged.docx          — итоговый Word с применёнными        │  │
│   │                            accept/reject решениями              │  │
│   └─────────────────────────────────────────────────────────────────┘  │
│                                                                         │
│   Batch-level артефакты (на весь корпус):                              │
│   ┌─────────────────────────────────────────────────────────────────┐  │
│   │  📊 evidence_matrix.xlsx — 10 листов: события, пары, KPI       │  │
│   │  📄 executive_diff.md    — executive summary Markdown          │  │
│   │  📄 executive_diff.docx  — то же, но Word                      │  │
│   │  🌐 full_diff_report.html — полный отчёт с поиском             │  │
│   │  📊 events.csv           — все события в CSV (UTF-8 BOM)       │  │
│   │  📦 merged.zip           — все merged.docx по парам в архиве   │  │
│   └─────────────────────────────────────────────────────────────────┘  │
│                                                                         │
│   Forensic-уровень (опционально, V10_BUNDLE_ENABLED=true):             │
│   ┌─────────────────────────────────────────────────────────────────┐  │
│   │  📊 14-листный XLSX с correlation/dependency/coverage          │  │
│   │  📄 10-главная пояснительная записка (DOCX + PDF, ru-RU)       │  │
│   │  🗺️ Интегральная матрица N×N (PDF, A3 если N≥13)              │  │
│   │  📈 4 CSV: correlation_matrix, dependency_graph,               │  │
│   │            claim_provenance, coverage_heatmap                  │  │
│   └─────────────────────────────────────────────────────────────────┘  │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 🎯 Пользовательский flow

```
   ┌─────────────────────────────────────────────────────────────────┐
   │  1. ЗАГРУЗКА                                                    │
   ├─────────────────────────────────────────────────────────────────┤
   │                                                                 │
   │     ┌───────────────────────┐                                   │
   │     │ Drag-and-drop файлов  │ ─── 2+ документов ─────┐          │
   │     │ → Drop zone           │                        │          │
   │     └───────────────────────┘                        │          │
   │                                                      ▼          │
   │     ┌───────────────────────┐         ┌─────────────────────┐   │
   │     │ Указать title batch'а │ ────►   │  POST /batches     │   │
   │     │ (опционально)         │         │  POST /documents   │   │
   │     └───────────────────────┘         └─────────────────────┘   │
   │                                                                 │
   └─────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
   ┌─────────────────────────────────────────────────────────────────┐
   │  2. PIPELINE (async через Celery + polling)                     │
   ├─────────────────────────────────────────────────────────────────┤
   │                                                                 │
   │   ┌─────────────┐   ┌──────────┐   ┌────────┐   ┌─────────┐    │
   │   │ Normalize    │──►│ Extract  │──►│Compare │──►│ Render  │   │
   │   │ (LibreOffice │   │ (fitz +  │   │(rapid- │   │(red/green│  │
   │   │  → PDF)      │   │  блоки)  │   │ fuzz / │   │ + DOCX) │   │
   │   │              │   │          │   │  LLM)  │   │         │   │
   │   └─────────────┘   └──────────┘   └────────┘   └─────────┘    │
   │     ⏳ 0-20%         ⏳ 20%        ⏳ 20-70%     ⏳ 70-100%      │
   │                                                                 │
   │   Sub-progress публикуется через Celery PROGRESS state.         │
   │   SPA показывает stage label + percentage в realtime.           │
   │                                                                 │
   └─────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
   ┌─────────────────────────────────────────────────────────────────┐
   │  3. REVIEW (главная фича)                                       │
   ├─────────────────────────────────────────────────────────────────┤
   │                                                                 │
   │   Веб-UI открывает inline viewer:                               │
   │                                                                 │
   │   ┌────┬──────────────────────┬──────────────────────┬──────┐   │
   │   │mini│  LHS document (PDF)  │  RHS document (PDF)  │ side │   │
   │   │map │                      │                      │bar:  │   │
   │   │ 📑 │  ┌──────────────┐   │  ┌──────────────┐    │      │   │
   │   │ ●  │  │              │   │  │              │    │ ev1  │   │
   │   │ ●  │  │  [red box]   │   │  │  [green box] │    │ ev2  │   │
   │   │ ●  │  │              │   │  │              │    │ ev3  │   │
   │   │    │  └──────────────┘   │  └──────────────┘    │      │   │
   │   └────┴──────────────────────┴──────────────────────┴──────┘   │
   │                                                                 │
   │   • Клик по красной/зелёной рамке → popover                    │
   │   • Popover: [✓ Accept] [✨ AI] [✗ Reject]                     │
   │   • Hotkeys: J/K — следующий/предыдущий, A — accept, R — reject │
   │   • Bulk: "Принять все same", "Отклонить все added"            │
   │                                                                 │
   └─────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
   ┌─────────────────────────────────────────────────────────────────┐
   │  4. ЭКСПОРТ                                                     │
   ├─────────────────────────────────────────────────────────────────┤
   │                                                                 │
   │   ┌─────────────────────────────────────────────────────┐       │
   │   │  📥 merged.docx — итоговый Word с применёнными      │       │
   │   │     accept/reject решениями. confirmed → принято в  │       │
   │   │     RHS, rejected → восстановлено из LHS, pending → │       │
   │   │     остаётся как Word track-changes.                │       │
   │   │                                                     │       │
   │   │  📦 merged.zip — все pair'ы одним архивом           │       │
   │   │                  + README.txt с manifest'ом         │       │
   │   │                                                     │       │
   │   │  📊 events.csv — таблица всех правок для Excel/BI   │       │
   │   └─────────────────────────────────────────────────────┘       │
   │                                                                 │
   └─────────────────────────────────────────────────────────────────┘
```

---

## 🖥️ Веб-интерфейс — гайд по экранам

### Экран 1: Загрузка (`#upload`)

```
┌──────────────────────────────────────────────────────────────────────┐
│ ●●● DocDiffOps    [Upload] [Batches]      📊 5 batches · 47 events   │
├──────────────────────────────────────────────────────────────────────┤
│                                                                      │
│   СОЗДАТЬ ПАКЕТ СРАВНЕНИЯ                                            │
│                                                                      │
│   ┌──────────────────────────┐  ┌─────────────────────────────────┐ │
│   │                          │  │ Staged files (3)        Clear   │ │
│   │      📤                  │  │                                 │ │
│   │  Перетащите файлы сюда   │  │ ┌─ Batch title (optional) ───┐  │ │
│   │  PDF, DOCX, PPTX, XLSX,  │  │ ├─────────────────────────────┤  │ │
│   │  HTML, TXT — до 50 за    │  │                                 │ │
│   │  раз                     │  │ • document_v1.pdf      2.4MB  ✕│ │
│   │                          │  │ • document_v2.pdf      2.5MB  ✕│ │
│   │   [ Browse files ]       │  │ • appendix.docx        120KB  ✕│ │
│   │                          │  │                                 │ │
│   └──────────────────────────┘  │ [ Создать batch + Загрузить +  ]│ │
│                                  │ [ Запустить                    ]│ │
│                                  └─────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────┘
```

### Экран 2: Список batches (`#batches`)

```
┌──────────────────────────────────────────────────────────────────────┐
│  Все батчи (12)   [🔍 Поиск...]   [↻ Обновить]                       │
├──────────────────────────────────────────────────────────────────────┤
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐       │
│  │ bat_abc12345 🗑 │  │ bat_def67890 🗑 │  │ bat_ghi13579 🗑 │       │
│  │ My corporate    │  │ Q3 review       │  │ Legal compare   │       │
│  │ Документы: 12   │  │ Документы: 4    │  │ Документы: 2    │       │
│  │ Пар: 66         │  │ Пар: 6          │  │ Пар: 1          │       │
│  │ Событий: 865    │  │ Событий: 47     │  │ Событий: 23     │       │
│  │ High risk: 4    │  │                 │  │                 │       │
│  │ 2026-05-12      │  │ 2026-05-10      │  │ 2026-05-09      │       │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘       │
└──────────────────────────────────────────────────────────────────────┘
```

### Экран 3: Детали batch (`#batch/<id>`)

```
┌──────────────────────────────────────────────────────────────────────┐
│  ← Все батчи    [batch title (клик чтобы переименовать)]   [↻] [↻↻] │
│  bat_abc12345                            [📦 Все merged.zip]         │
│                                          [📊 CSV events]             │
│                                                                      │
│   КPI:                                                               │
│   ┌────┬────┬────┬────┬────┬────┬────┐                              │
│   │Docs│Pair│Ev. │High│Rev.│ ✓  │ ✗  │ ⏳ Pending                  │
│   │ 12 │ 66 │865 │ 4  │ 12 │ 8  │ 2  │  855                         │
│   └────┴────┴────┴────┴────┴────┴────┘                              │
│                                                                      │
│   📊 Distribution (donut):     🔄 Прогресс review:                  │
│   ┌─────────┐                  ▓▓░░░░░░░░░░░  10/865 (1%)           │
│   │   865   │ ● same 600       ✓ 8 · ✗ 2 · ⏳ 855 pending           │
│   │  total  │ ● modified 180                                        │
│   └─────────┘ ● added 50                                            │
│                ● deleted 35                                          │
│                                                                      │
│  [События] [Пары ▾] [Документы] [Артефакты] [Topics] [Audit]        │
│                                                                      │
│  ─── PAIRS TAB (default landing) ───────────────────────────────     │
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │ pair_abc_xyz                                          [85] │    │
│  │ 📄 document_v1.pdf  ↔  📄 document_v2.pdf            green │    │
│  │ Краткое описание разницы (narrative)…                     │    │
│  │                                                            │    │
│  │ same 580  partial 12  + 50  − 35  high 2                  │    │
│  │                                                            │    │
│  │ Прогресс review ▓▓▓░░░░░░░░░  3/47 (6%)                   │    │
│  │                                                            │    │
│  │ [✓ same (580)] [✓ low (0)] [✗ added (50)]   bulk actions │    │
│  │                                                            │    │
│  │ ┌──────────────┐  ┌──────────────┐                        │    │
│  │ │ [LHS] thumb  │  │ [RHS] thumb  │  inline превью         │    │
│  │ │ first page   │  │ first page   │                        │    │
│  │ └──────────────┘  └──────────────┘                        │    │
│  │                                                            │    │
│  │ ┌───────────────────────────────────────────────────────┐ │    │
│  │ │ 📖 ОТКРЫТЬ ДОКУМЕНТЫ С ПОДСВЕТКОЙ ПРАВОК (CTA)        │ │    │
│  │ └───────────────────────────────────────────────────────┘ │    │
│  │                                                            │    │
│  │ [track_changes.docx ↓] [📥 merged] [view events →]        │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
```

### Экран 4: Inline viewer (`📖 ОТКРЫТЬ ДОКУМЕНТЫ`)

```
┌──────────────────────────────────────────────────────────────────────┐
│ 📖 Inline viewer | pair_abc_xyz  [PDF|Текст] [🔍 Поиск] [−100%+⤢]   │
│                  [LHS ◀ 1/12 ▶]  [RHS ◀ 1/12 ▶]               [✕] │
├──┬─────────────────────────┬─────────────────────────┬──────────────┤
│M │ LHS document_v1.pdf     │ RHS document_v2.pdf     │ События 47   │
│i │ ┌─────────────────────┐ │ ┌─────────────────────┐ │┌─────────────┐│
│n │ │                     │ │ │                     │ ││🔍 Filter… ││
│i │ │   Заголовок         │ │ │   Заголовок         │ ││☑ hide done ││
│  │ │                     │ │ │                     │ ││☐ only ★    ││
│m │ │ [▓▓▓▓▓▓▓▓▓▓▓▓]     │ │ │ [▓▓▓▓▓▓▓▓▓▓▓▓]     │ ││             ││
│a │ │  ↑ красная рамка    │ │ │  ↑ зелёная рамка    │ ││ ev1 mod ★ ⚡ ││
│p │ │   на удалённом      │ │ │   на добавленном    │ ││  стр.3-3   ││
│  │ │   тексте            │ │ │   тексте            │ ││  "число…"  ││
│ ● │ │                     │ │ │                     │ ││            ││
│ ● │ │  Дальше параграф    │ │ │  Дальше параграф    │ ││ ev2 add  ⚡ ││
│ ● │ │  без изменений      │ │ │  без изменений      │ ││  стр.4    ││
│ ● │ │                     │ │ │                     │ ││  "новый…" ││
│   │ │ [▓▓▓▓▓▓▓] жёлтое   │ │ │ [▓▓▓▓▓▓▓] жёлтое   │ ││            ││
│   │ │  modified           │ │ │  modified           │ ││ ev3 del  ⚡ ││
│   │ │                     │ │ │                     │ ││  стр.5    ││
│   │ └─────────────────────┘ │ └─────────────────────┘ ││            ││
│   │                         │                         │└─────────────┘│
├──┴─────────────────────────┴─────────────────────────┴──────────────┤
│ ⌨ J/K следующее/предыдущее · A принять · R отклонить · 0 fit · Esc │
└──────────────────────────────────────────────────────────────────────┘
```

При клике по цветной рамке или по ⚡ открывается popover:

```
                  ┌──────────────────────────────────┐
                  │ Event · modified           ✕     │
                  ├──────────────────────────────────┤
                  │ LHS: Срок исполнения — 30 дней   │
                  │ RHS: Срок исполнения — 60 дней   │
                  │                                  │
                  │ Pipeline: число изменилось       │
                  │                                  │
                  │ ┌────────────────────────────┐   │
                  │ │ Comment (optional)         │   │
                  │ └────────────────────────────┘   │
                  │                                  │
                  │ [✓ Accept] [✨ AI] [✗ Reject]    │
                  │                                  │
                  │ ✨ AI: rejected (60%)            │
                  │ Удвоение срока — существенная    │
                  │ правка, требует подтверждения... │
                  └──────────────────────────────────┘
```

---

## ⌨️ Inline viewer — горячие клавиши

```
┌─────────────────────────────────────────────────────────────────────┐
│  Навигация по событиям                                              │
├─────────────────────────────────────────────────────────────────────┤
│   J  /  K     ► Следующее / предыдущее событие (pending-first)      │
│                                                                     │
│  Review                                                             │
│   A           ✓ Принять активное событие (auto-advance)             │
│   R           ✗ Отклонить активное событие                          │
│                                                                     │
│  Zoom & navigation                                                  │
│   +  /  -     Zoom in / out                                         │
│   0           Fit-to-width                                          │
│                                                                     │
│  Modals                                                             │
│   Esc         Закрыть help / toast / viewer (в этом порядке)        │
│   ?           Показать эту подсказку                                │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 🌐 API endpoints

### Управление batches

```
POST    /batches                       Создать batch
GET     /batches                       Список всех batches
GET     /batches/{id}                  Детали batch'а
PATCH   /batches/{id}                  Переименовать (body: {title})
DELETE  /batches/{id}                  Удалить batch (DB + диск)
```

### Pipeline (async через Celery)

```
POST    /batches/{id}/documents        Загрузить файлы (multipart)
POST    /batches/{id}/run              Запустить pipeline → task_id
POST    /batches/{id}/rerender-compare Пересчитать compare → task_id
POST    /batches/{id}/rerender-full    Полный rerender (re-extract) → task_id
GET     /tasks/{task_id}               Опрос статуса (PENDING / PROGRESS / SUCCESS)
                                         PROGRESS возвращает {stage, pct, message}
```

### Review workflow

```
POST    /events/{id}/review            Принять/отклонить/прокомментировать
                                         body: {decision, reviewer_name, comment}
                                         decision: confirmed | rejected | comment | …
GET     /events/{id}/reviews           История всех review-решений
POST    /events/{id}/ai-suggest        Спросить LLM — accept или reject?
                                         returns {decision, confidence, reasoning}
```

### Скачивание артефактов

```
GET     /batches/{id}/download/{path}        Любой артефакт по пути
GET     /batches/{id}/artifacts              Список всех артефактов
GET     /batches/{id}/docs/{doc_id}/canonical.pdf
                                              Канонический PDF документа
GET     /batches/{id}/pair/{pid}/merged.docx Per-pair merged DOCX
GET     /batches/{id}/merged.zip             Все merged.docx архивом
GET     /batches/{id}/events.csv             Все события CSV (UTF-8 BOM)
GET     /batches/{id}/forensic               v8 forensic JSON bundle
GET     /batches/{id}/forensic/{kind}        v8/v10 kind: xlsx, docx, pdf, …
GET     /batches/{id}/forensic/v10           v10 bundle JSON (если включён)
GET     /batches/{id}/forensic/v10.zip       v10 bundle архивом
GET     /forensic/trend?ids=A,B,C             Multi-batch временной trend
```

### Сервисные

```
GET     /health                        Liveness probe
GET     /docs                          Swagger UI (автодок FastAPI)
GET     /openapi.json                  OpenAPI 3.x спецификация
GET     /batches/{id}/audit            Журнал действий по batch'у
GET     /batches/{id}/clusters         Topic-кластеры (если LLM включён)
```

---

## 🏗️ Архитектура

```
                                ┌──────────────────────┐
                                │  Cloudflare (CDN)    │
                                └──────────┬───────────┘
                                           │ HTTPS
                                ┌──────────▼───────────┐
                                │  Caddy (TLS, gzip)   │ :80, :443
                                │  reverse_proxy api   │
                                └──────────┬───────────┘
                                           │
                ┌──────────────────────────┼─────────────────────────┐
                │                          │                         │
       ┌────────▼─────────┐      ┌────────▼─────────┐      ┌───────▼────────┐
       │  api (FastAPI)   │      │  worker (Celery) │      │  redis :6379   │
       │  uvicorn :8000   │      │  4 prefork procs │      │  broker+result │
       │                  │      │  -Q high,low     │      │  + batch_lock  │
       │  • HTML SPA      │      │                  │      │  + rate_limit  │
       │  • API endpoints │      │  • run_batch     │      │                │
       │  • Basic auth    │      │  • rerender_*    │      └────────────────┘
       │  • Rate limit    │      │  PROGRESS state  │
       │  • PDF.js bundle │      └────────┬─────────┘
       └────────┬─────────┘               │
                │                         │ shared volume
                │      ┌──────────────────┴─────┐
                │      │  /data/batches/{id}/   │ filesystem
                │      │    raw/                │ (uploaded files)
                │      │    normalized/         │ (LibreOffice PDF)
                │      │    extracted/          │ (parsed blocks JSON)
                │      │    pairs/{pid}/        │ (per-pair artifacts)
                │      │    reports/            │ (batch reports)
                │      └────────────────────────┘
                │
       ┌────────▼─────────┐
       │ Postgres :5432   │
       │ docdiff DB       │
       │ Alembic schema   │
       │ • batches        │
       │ • documents      │
       │ • diff_events    │
       │ • review_decis…  │
       │ • artifacts      │
       │ • audit_log      │
       └──────────────────┘
```

### Pipeline stages

```
  Upload  ──►  normalize_and_extract  ──►  run_all_pairs  ──►  render
              │                            │                    │
              │ LibreOffice → PDF          │ For each pair:     │
              │ fitz → blocks + bbox       │ • compare_pair     │
              │ (cached by sha256+ver)     │   (rapidfuzz)      │
              │                            │ • LLM pair_diff    │
              │                            │   (optional)       │
              │                            │ • enrich_positions │
              │                            │   (fuzzy-match     │
              │                            │    quote → bbox)   │
              │                            │ • legal_structural │
              │                            │   diff (if NPA)    │
              │                            │ • claim_validation │
              │                            │ • apply_rank_gate  │
              │                            └────────────────────┘
              │
              ├──► render outputs:
              │     • XLSX evidence matrix (10 sheets)
              │     • Executive MD + DOCX
              │     • Full HTML report
              │     • Per-pair: red/green PDF + track_changes DOCX
              │     • JSONL events
              │
              └──► forensic v8 bundle (always)
              └──► forensic v10 bundle (если V10_BUNDLE_ENABLED=true)
                    • 4 BOM CSV
                    • 14-листный XLSX
                    • 10-главная пояснительная DOCX+PDF
                    • Интегральная матрица N×N PDF
```

### Кэширование

Каждая stage кэширует результат по `sha256 + EXTRACTOR_VERSION` (или `+COMPARATOR_VERSION` для compare).
Повторная загрузка того же файла — мгновенно. Бамп переменной — инвалидация всего.

---

## 🚢 Деплой

### Локально через docker-compose

```bash
cd docdiffops_mvp
docker compose up --build
docker compose exec api alembic upgrade head    # миграции БД
# → http://localhost:8000/
```

### Прод на любом Linux-хосте

```bash
# 1. SSH на хост
ssh root@<host>

# 2. Клонировать репо
git clone https://github.com/agisota/diffs.git /opt/diffs
cd /opt/diffs/docdiffops_mvp

# 3. Запустить
docker compose up -d --build
docker compose exec api alembic upgrade head

# 4. Поставить Caddy как reverse-proxy (или nginx)
# Caddyfile минимальный пример:
#   :443 {
#       tls /path/to/cert.crt /path/to/key
#       reverse_proxy api:8000
#       encode gzip
#       header / Cache-Control "no-store"   # HTML mutable
#   }
```

### Обновление прода

```bash
ssh root@<host>
cd /opt/diffs
git pull
cd docdiffops_mvp
docker compose up -d --build api worker
```

---

## ⚙️ Переменные окружения

```
┌──────────────────────────────────┬─────────────┬────────────────────────────┐
│ Переменная                       │ Default     │ Что делает                 │
├──────────────────────────────────┼─────────────┼────────────────────────────┤
│ DATA_DIR                         │ ./data      │ Корень для batch_dir'ов    │
│ DATABASE_URL                     │ compose pg  │ Postgres connection string │
│ REDIS_URL                        │ redis:6379  │ Celery broker + cache      │
│ STORAGE_BACKEND                  │ fs          │ fs или minio               │
│ EXTRACTOR_VERSION                │ 2.A.0       │ Бамп = invalidate extract  │
│ COMPARATOR_VERSION               │ 1.0.0       │ Бамп = invalidate compare  │
│ RETENTION_DAYS                   │ 30          │ Срок хранения batches      │
├──────────────────────────────────┼─────────────┼────────────────────────────┤
│ LLM_API_BASE                     │ OpenAI compat │ Совместимый endpoint     │
│ LLM_API_KEY                      │ —           │ API key                    │
│ LLM_MODEL                        │ gpt-4o-mini │ Default model              │
│ SEMANTIC_COMPARATOR_ENABLED      │ false       │ LLM ride-along verdict     │
│ SEMANTIC_MAX_CLAIMS_PER_PAIR     │ 10          │ Cost guard для LLM         │
│ LLM_PAIR_DIFF_ENABLED            │ false       │ LLM-events заменяют fuzzy  │
│ LLM_PAIR_DIFF_MODEL              │ —           │ Model для pair-diff        │
│ LLM_PAIR_DIFF_CHAR_BUDGET        │ 12000       │ Per-pair char budget       │
│ KEEP_FUZZY_WITH_LLM_PAIR_DIFF    │ false       │ Оставить fuzzy + LLM       │
├──────────────────────────────────┼─────────────┼────────────────────────────┤
│ V10_BUNDLE_ENABLED               │ false       │ Включить v10 артефакты     │
├──────────────────────────────────┼─────────────┼────────────────────────────┤
│ BASIC_AUTH_USER                  │ —           │ Включить Basic Auth        │
│ BASIC_AUTH_PASS                  │ —           │ (оба нужны одновременно)   │
│ RATE_LIMIT_DISABLED              │ false       │ Отключить rate-limit       │
│ BATCH_LOCK_DISABLED              │ false       │ Отключить concurrent lock  │
│ BATCH_LOCK_TTL_SEC               │ 7200        │ Lock TTL (2 часа)          │
└──────────────────────────────────┴─────────────┴────────────────────────────┘
```

---

## 🆘 Troubleshooting

### «При нажатии на просмотр документа написано что pdf.js не может загрузиться»

pdf.js bundled в Docker-образ через Dockerfile (curl из unpkg.com во время build).
Если 404 на `/static/pdfjs/pdf.min.js`:

```bash
docker compose exec api ls -lh /app/docdiffops/static/pdfjs/
# Должно показать pdf.min.js (~370KB) + pdf.worker.min.js (~1.1MB)
```

Если их нет — пересобрать без cache: `docker compose build --no-cache api`.

### «Бесконечная загрузка после нажатия "Создать batch + Запустить"»

Проверь, что Celery worker запущен:

```bash
docker compose ps worker
docker compose logs worker --tail 30
```

Если worker не отвечает или crashed — `docker compose restart worker`.

SPA имеет hard cap 90 минут на polling. После таймаута покажется ошибка.

### «Batch создался, но pipeline закончился с FAILURE»

Проверь worker logs:

```bash
docker compose logs worker --tail 100 | grep -A 3 ERROR
```

Чаще всего:
- PDF поврежден → `pymupdf.FileDataError: code=7: no objects found`
- LLM API недоступен → `LLM transport error: …`
- Disk full → `OSError: [Errno 28] No space left on device`

### «Bbox-подсветки не появляются на документах»

Bbox генерируется только из реальных PDF (через fitz). Если документ HTML/TXT/DOCX:
- LibreOffice должен сначала конвертировать его в canonical PDF
- Затем extract идёт через `extract_pdf(canonical)` который даёт bbox

Если canonical_pdf=None для документа → нажми `🔁 Полный rerender` в detail view.
Это удалит cached extract и перепрогонит pipeline через canonical PDF.

### «409 Conflict при попытке запустить pipeline»

Это **фича**, не баг: на одном batch'е может быть только одна long-running операция.
Дождись завершения предыдущего run/rerender, или отмени его (TODO: endpoint).

Lock автоматически освобождается через 2 часа (или раньше — когда задача завершается / падает).

### «429 Too Many Requests»

Rate-limit per-IP:
- POST `/batches`: 30/мин
- POST `/events/{id}/review`: 60/мин
- POST `/events/{id}/ai-suggest`: 10/мин (LLM cost)

Дождись окошка `Retry-After` секунд (значение в header'е), либо включи `RATE_LIMIT_DISABLED=true`.

---

## 📞 Контакты

- **Прод:** [https://diff.zed.md](https://diff.zed.md)
- **Repo:** [github.com/agisota/diffs](https://github.com/agisota/diffs)
- **Issue tracker:** GitHub Issues
- **Swagger:** [https://diff.zed.md/docs](https://diff.zed.md/docs)

Сервис **анонимный** (не требует регистрации) и **не сертифицирован для PII**.
Не загружайте конфиденциальные документы без понимания этого ограничения.

---

## 📜 Лицензия

Internal — confidential. Не для публичного распространения.
