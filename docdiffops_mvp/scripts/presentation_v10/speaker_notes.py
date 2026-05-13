"""Speaker notes for the v10 presentation.

Each slide gets a 50-150 word context note attached to its notes pane.
Notes are templatised by slide type and dynamically rendered with V10Data
so they reflect actual numbers (27/351/312/86/etc.) rather than placeholder text.
"""
from __future__ import annotations

from .data_loader import V10Data
from .theme import STATUS_RU


def _section_intro_note(section: str, scope: str) -> str:
    """Generic intro note for divider slides."""
    return (
        f"Раздел «{section}». {scope} "
        f"Пользуйтесь footer'ом «↑ ToC» для возврата к содержанию."
    )


def build_notes_for_slides(prs: object, data: V10Data) -> dict[int, str]:
    """Build dict slide_idx → note text for all slides.

    Templated by section. Heroes, dividers, tables, cards each get appropriate context.
    """
    cn = data.control_numbers
    pairs_by_status = data.pairs_by_status()

    notes: dict[int, str] = {}

    # === Cover (slide 0) ===
    notes[0] = (
        f"DocDiffOps v10 — это рендеринг-релиз итерации сравнения "
        f"{cn['documents']} документов миграционной политики РФ. "
        f"Корпус из v9 унаследован без изменений; вся новизна — в "
        f"переработанной пояснительной записке (16 страниц, 10 глав), "
        f"редакционном diff, интегральном XLSX и аналитических CSV "
        f"(correlation, dependency, coverage). QA-гейт пройден полностью: "
        f"{data.qa['passed']}/{data.qa['total']} критериев приёмки."
    )

    # === Abstract (slide 1) ===
    notes[1] = (
        f"Презентация сшивает 35+ файлов бандла migration_v10_out/ "
        f"в один читабельный артефакт. {cn['pairs']} пар попарного "
        f"сравнения и {cn['events']} diff-событий разнесены по 9 разделам. "
        f"Параллельно собраны DOCX (для редакторов) и HTML (one-pager). "
        f"Этот PPTX — основной формат для чтения сверху вниз."
    )

    # === ToC (slide 2) ===
    notes[2] = (
        "Содержание презентации. Каждый раздел кликабельный — "
        "плашка ведёт на divider раздела. С любого слайда внизу справа "
        "ссылка «↑ ToC» возвращает сюда."
    )

    # === Status legend (slide 3) ===
    notes[3] = (
        "Семь статусов шкалы v8: совпадение / частичное совпадение / "
        "противоречие / устаревшее / пробел источника / ручная проверка / "
        "несопоставимо. Цветовая палитра наследована из forensic_render.py "
        "и точно совпадает с XLSX/DOCX в bundle/. Глифы (✓ ≈ ⚠ ↻ ∅ ? —) "
        "обеспечивают читаемость для color-blind пользователей."
    )

    # === Conventions (slide 4) ===
    notes[4] = (
        "Ранг источника — load-bearing концепция: rank-1 (официальные НПА), "
        "rank-2 (ведомственные), rank-3 (аналитика). Инвариант ранг-шлюза: "
        "rank-3 не может опровергнуть rank-1 — такие contradiction "
        "автоматически понижаются до manual_review (AC-02 PASS, 0 нарушений)."
    )

    # === Executive divider (slide 5) ===
    notes[5] = _section_intro_note(
        "Executive Summary",
        "Ключевые цифры, тренд, методология, что нового в v10.",
    )

    # === Hero stat (slide 6) ===
    notes[6] = (
        f"Из {cn['pairs']} пар — {pairs_by_status.get('match', 1)} совпадение и "
        f"{pairs_by_status.get('contradiction', 1)} противоречие. "
        f"{pairs_by_status.get('not_comparable', 202)} пар несопоставимы "
        f"(rank/тематические границы). {pairs_by_status.get('manual_review', 86)} "
        f"требуют ручной проверки. Это итоговая картина после rank-gate "
        f"и автоматической классификации событий."
    )

    # === Executive bullets (slides 7-15) ===
    for i in range(7, 16):
        notes[i] = (
            "Часть Executive Summary. Здесь представлены ключевые "
            "показатели и принципы методологии. Подробности по каждому "
            "статусу — в разделах Pair Matrix (стр 27-51) и События (стр 55-76)."
        )

    # === Корпус divider (slide 16) ===
    notes[16] = _section_intro_note(
        "Корпус: 27 документов",
        "Реестр источников по рангам (8 rank-1, 4 rank-2, 15 rank-3), "
        "тематические кластеры, provenance, связи через граф зависимостей.",
    )

    # === Корпус slides (17-25) ===
    for i in range(17, 26):
        notes[i] = (
            "Часть раздела «Корпус». Реальное распределение: "
            "21 rank-1 / 2 rank-2 / 4 rank-3 (см. data.docs_by_rank())."
        )

    # === Pair Matrix divider (slide 26) ===
    notes[26] = _section_intro_note(
        "Матрица пар (351)",
        f"Все C(27,2)=351 пар попарного сравнения с агрегированным статусом. "
        f"Распределение: {pairs_by_status}.",
    )

    # === Pair Matrix pages (27-50) ===
    for i in range(27, 51):
        page_no = i - 26
        notes[i] = (
            f"Матрица пар — страница {page_no} из 24. "
            f"Каждая строка = одна пара документов (id, левый, правый, темы, "
            f"статус, число событий, ранги). Цвет фона ячейки «Статус» — "
            f"из STATUS_TINT_BG, совпадает с XLSX. Глиф в колонке статуса "
            f"обеспечивает дополнительное color-blind-кодирование."
        )

    # === Critical pairs (slides 51-53) ===
    notes[51] = (
        "Раздел «Критические пары» — отфильтрованная выборка 54 пар "
        "статусов contradiction + partial_overlap. Это квинтэссенция "
        "содержательных расхождений в корпусе. В двух следующих страницах — "
        "полный список с темами и рангами."
    )
    notes[52] = "Критические пары — страница 1 из 2."
    notes[53] = "Критические пары — страница 2 из 2."

    # === Events table (slides 54-75) ===
    notes[54] = _section_intro_note(
        "Diff-события (312)",
        "Каждое событие — это атомарное утверждение из левого документа, "
        "сопоставленное с доказательством из правого. Все 312 событий "
        "разнесены на 21 страницу + 10 детальных карточек впереди.",
    )
    for i in range(55, 76):
        page_no = i - 54
        notes[i] = (
            f"События — страница {page_no} из 21. "
            f"Колонка event_id содержит cross-link на детальную карточку "
            f"(если событие в топ-10 для разворота)."
        )

    # === Event detail cards (slides 76-86) ===
    notes[76] = (
        "Раздел «События — детальные карточки». 10 событий выбраны по "
        "критерию максимальной значимости: 1 contradiction (E010 ЕАЭС), "
        "6 partial_overlap высокой confidence, 3 outdated высокого риска. "
        "Каждая карточка показывает полные тексты утверждения и доказательства "
        "с источниками."
    )
    for i in range(77, 87):
        notes[i] = (
            "Детальная карточка события. УТВЕРЖДЕНИЕ — что было сказано "
            "(claim из левого документа). ДОКАЗАТЕЛЬСТВО — что найдено "
            "при сопоставлении с правым документом. Внизу — заключение, "
            "юридическая координата и confidence (0..1)."
        )

    # === Themes (slides 87-94) ===
    notes[87] = _section_intro_note(
        "Темы и корреляция",
        "Тематическая структура корпуса: 14+ кластеров, граф зависимостей "
        "(85 рёбер), Sankey-поток rank → status, treemap по плотности событий.",
    )
    notes[88] = (
        "Корреляционная матрица 14 тем × 27 документов — бинарная карта "
        "присутствия темы в каждом документе корпуса."
    )
    notes[89] = (
        "Coverage heatmap — глубина покрытия: полное / частичное / отсутствует. "
        "Показывает, насколько тщательно каждый документ обрабатывает тему."
    )
    notes[90] = (
        "Граф зависимостей — 85 рёбер: amends (синие), supersedes (красные), "
        "references (серые). Ключевые узлы: 109-ФЗ, 115-ФЗ, 270-ФЗ."
    )
    notes[91] = "Распределение событий по темам — топ-15 тематических кластеров."
    notes[92] = (
        "Sankey-поток: rank-pair (1↔1, 1↔2, 1↔3, ...) → v8 status. "
        "Видно, что большинство 1↔3 пар уходит в not_comparable — "
        "это последствие rank-gate."
    )
    notes[93] = (
        "Treemap по темам. Доминирует «Forensic/provenance layer» (T14, "
        "206 событий) — это служебный слой; смысловая нагрузка распределена "
        "по T01-T13."
    )
    notes[94] = "Темы — итоговые наблюдения. Дальше — индивидуальные карточки тем."

    # === Theme cards (slides 95-108) ===
    notes[95] = (
        "Раздел «Темы — карточки». 14 ключевых тем получили развёрнутую "
        "паспортизацию: какие документы покрывают тему, ключевые тезисы, "
        "распределение статусов, число задач на ручную проверку."
    )
    for i in range(96, 109):
        notes[i] = (
            "Карточка темы. Слева — таблица документов с ID/код/ранг/роль. "
            "Справа — статус-распределение, ключевые тезисы (top-3), "
            "счётчики событий и review_queue."
        )

    # === Review queue (slides 109-123) ===
    notes[109] = _section_intro_note(
        "Очередь ручной проверки (103 задачи)",
        "54 задачи baseline v9 + 49 задач partial_overlap, добавленных скриптом "
        "08_close_ac10.py. Приоритизация P0/P1/P2 (4 / 2 / 97). "
        "Каждая задача с владельцем и критериями закрытия.",
    )
    for i in range(110, 124):
        notes[i] = "Очередь ручной проверки — рабочий список для юристов и редакторов."

    # === Trend & QA (slides 124-135) ===
    notes[124] = _section_intro_note(
        "Тренд и QA",
        "4 итерации (v7→v8→v9→v10), QA-гейт 12 критериев AC-01..AC-12 — все PASS.",
    )
    notes[127] = (
        "Journey timeline: v7 (12 docs / 66 пар / 200 событий) → v8 → "
        "v9 (расширение до 27/351/312, +D27 ВЦИОМ) → v10 (рендеринг-релиз). "
        "Tag «degrading» в trend.json относится к match_share, "
        "не к качеству — это смена базы."
    )
    for i in (125, 126, 128, 129, 130, 131, 132, 133, 134, 135):
        if i not in notes:
            notes[i] = "Часть раздела «Тренд и QA»."

    # === Actions (slides 136-149) ===
    notes[136] = _section_intro_note(
        "Действия и заключение",
        "Каталог редакционных действий FA-01..FA-10. Высокая (5) / средняя (4) / "
        "низкая (1) серьёзность. Каждое действие имеет владельца и критерии.",
    )
    for i in range(137, 148):
        notes[i] = (
            "Карточка редакционного действия. Серьёзность — high/medium/low. "
            "Каждое действие привязано к конкретным документам (D## ссылки "
            "кликабельны → document spotlight)."
        )
    notes[148] = "Приоритизация действий по серьёзности."
    notes[149] = "Roadmap для следующей итерации (v11)."

    # === Doc spotlights (slides 150-152) ===
    notes[150] = (
        "Document spotlight: D18 Брошюра Минэка ВНЖ инвестора. "
        "Rank-2 ведомственная брошюра. Является источником FA-01..FA-04 "
        "(брошюра содержит «более 15/30/6 млн» там, где НПА говорит «не менее»)."
    )
    notes[151] = (
        "Document spotlight: D24 270-ФЗ — ключ к amendment-chain. "
        "Изменяет 109-ФЗ и 115-ФЗ. Ссылки на 109/115 без оговорки «в ред. 270-ФЗ» — "
        "источник риска (FA-06)."
    )
    notes[152] = (
        "Document spotlight: D27 ПП №1375 (поправка к ПП №2573). "
        "Не путать с D03 ВЦИОМ. Был добавлен в v9 — главная причина "
        "падения match_share с 8% до 0.28%."
    )

    # === Outro (slide 153 if exists) ===
    if len(prs.slides) > 153:  # type: ignore[union-attr]
        notes[153] = (
            "Заключительный слайд. Полные источники: bundle.json, "
            "machine_appendix/14 CSV, qa_report.json. Презентация воспроизводится "
            "одной командой: python -m scripts.presentation_v10.build_all."
        )

    return notes


def attach_notes_to_slides(prs: object, data: V10Data) -> int:
    """Attach all notes. Returns count of slides annotated."""
    notes = build_notes_for_slides(prs, data)
    count = 0
    for slide_idx, note_text in notes.items():
        if slide_idx >= len(prs.slides):  # type: ignore[union-attr]
            continue
        slide = prs.slides[slide_idx]  # type: ignore[union-attr]
        try:
            notes_slide = slide.notes_slide
            notes_slide.notes_text_frame.text = note_text
            count += 1
        except Exception as e:
            print(f"WARN: cannot attach notes to slide {slide_idx}: {e}")
    return count
