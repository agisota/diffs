"""Forensic actions catalogue (v8.1 contract).

Domain-specific data describing **what to do** about every category of
mismatch documented in the migration v8 reference package. Reusable for
any batch where the same families of mismatches appear (rank-3 vs rank-1
content, brochure-vs-NPA wording, amendment chains, EAEU vs non-EAEU).

Public surface:
  * ``Action`` / ``BrochureRedGreenEntry`` / ``KlerkNPALink`` /
    ``EAEUSplitEntry`` / ``AmendmentChainEntry`` — typed dataclasses.
  * ``DEFAULT_ACTIONS`` (10), ``DEFAULT_BROCHURE_REDGREEN`` (6),
    ``DEFAULT_KLERK_NPA_LINKS`` (6), ``DEFAULT_EAEU_SPLIT`` (3),
    ``DEFAULT_AMENDMENT_CHAIN`` (5).
  * ``actions_for_pair(left, right)`` — returns matching actions for a pair.
  * ``raci_for_action(action_id)`` — returns Responsible/Accountable/
    Consulted/Informed for an action.
  * ``apply_actions_to_bundle(bundle)`` — annotates each pair in the v8
    bundle with relevant action IDs and attaches the full catalogue.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

# ---------------------------------------------------------------------------
# Severity & category vocabulary
# ---------------------------------------------------------------------------

SEVERITY_LEVELS: tuple[str, ...] = ("low", "medium", "high")

ACTION_CATEGORIES: tuple[str, ...] = (
    "brochure_vs_npa",
    "department_page_split",
    "secondary_digest_links",
    "concept_supersession",
    "amendment_chain",
    "amendment_to_law",
    "amendment_to_koap",
    "analytic_separation",
    "provenance_risk",
    "source_gap",
)


# ---------------------------------------------------------------------------
# Typed catalogue entries
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Action:
    """Single FA-XX action item with WHERE/WHAT/WHY/FIX."""
    id: str
    category: str
    severity: str
    where: str
    what_is_wrong: str
    why: str
    what_to_do: str
    owner: str
    related_docs: list[str]
    v8_status: str
    # Set of {(doc_a, doc_b)} ordered pairs that match this action; either
    # order works — actions_for_pair() canonicalises before lookup.
    matches_pairs: list[tuple[str, str]] = field(default_factory=list)
    # If matches_pairs is empty but matches_doc is set, the action triggers
    # whenever ANY pair includes the listed document (used for D09 Klerk).
    matches_doc: str | None = None


@dataclass(frozen=True)
class BrochureRedGreenEntry:
    id: str
    section: str
    location: str
    before: str
    after: str
    basis: str
    effect: str


@dataclass(frozen=True)
class KlerkNPALink:
    id: str
    thesis: str
    npa_doc: str
    specific_place: str
    footnote: str
    v8_status: str


@dataclass(frozen=True)
class EAEUSplitEntry:
    id: str
    group: str
    countries: str
    work_regime: str
    basis: str
    employer_action: str
    minek_text_should_be: str


@dataclass(frozen=True)
class AmendmentChainEntry:
    id: str
    chain: str
    base_act: str
    amendments_chronology: str
    related: str
    cite_now: str
    where_to_verify: str


# ---------------------------------------------------------------------------
# Default catalogue (mirrors v8.1 supplement)
# ---------------------------------------------------------------------------


DEFAULT_ACTIONS: list[Action] = [
    Action(
        id="FA-01", category="brochure_vs_npa", severity="high",
        where="D18 Брошюра «Упрощённое получение ВНЖ инвестору», стр. 1, бокс «Условия»",
        what_is_wrong="Брошюра использует «более 15 / 30 / 6 млн». ПП №2573 — «не менее».",
        why="«более» = строгое неравенство (X > 15). «не менее» = нестрогое (X ≥ 15). Инвестор с ровно 15 млн НЕ пройдёт по брошюре, но пройдёт по ПП.",
        what_to_do="Заменить «более» на «не менее» в 6 ячейках брошюры (4 критерия × все языки).",
        owner="Юрист миграционного права + контент-менеджер Минэка",
        related_docs=["D18", "D20"],
        v8_status="manual_review",
        matches_pairs=[("D18", "D20")],
    ),
    Action(
        id="FA-02", category="department_page_split", severity="high",
        where="D10 Минэк-страница, блок «Работа в ЕАЭС»",
        what_is_wrong="Узбекистан и Таджикистан попадают в один блок с государствами-членами ЕАЭС.",
        why="Узбекистан и Таджикистан — НЕ члены ЕАЭС. Их граждане работают по 115-ФЗ через патент.",
        what_to_do="Разделить на 3 блока: ЕАЭС / безвиз-патент / визовые-разрешение.",
        owner="Контент-менеджер Минэка + юрист",
        related_docs=["D10", "D26", "D11"],
        v8_status="contradiction",
        matches_pairs=[("D10", "D26"), ("D10", "D11")],
    ),
    Action(
        id="FA-03", category="secondary_digest_links", severity="medium",
        where="D09 Клерк — все 6 тематических тезисов",
        what_is_wrong="rank-3 источник без footnote-ссылок на конкретные статьи первичных НПА.",
        why="Клерк не может ратифицировать или опровергнуть НПА. Использование как источник истины — методологический риск.",
        what_to_do="Добавить footnote с конкретной статьёй первичного НПА к каждому тезису (KL-01..KL-06).",
        owner="Юрист миграционного права",
        related_docs=["D09", "D11", "D12", "D13", "D15", "D16", "D17", "D21"],
        v8_status="manual_review",
        matches_doc="D09",
    ),
    Action(
        id="FA-04", category="concept_supersession", severity="medium",
        where="D04 (Концепция 2026–2030) vs D05 (Концепция 2019–2025)",
        what_is_wrong="Концепция 2019–2025 цитируется без отметки «утратила силу с D04».",
        why="После вступления D04 старая Концепция формально утратила силу. Часть формулировок перенесена, часть заменена, часть исчезла.",
        what_to_do="Маркер «утратила силу с D04» при цитировании D05; сверить, перенесено ли положение.",
        owner="Юрист + методолог",
        related_docs=["D04", "D05", "D07", "D08"],
        v8_status="outdated",
        matches_pairs=[("D04", "D05"), ("D08", "D07")],
    ),
    Action(
        id="FA-05", category="amendment_chain", severity="high",
        where="D21 ПП №1510 (07.11.2024) → D22 ПП №1562 (08.10.2025) → D23 ПП №468 (27.04.2026)",
        what_is_wrong="ПП №1510 цитируется без указания актуальной редакции.",
        why="3 редакции; апелляция к исходному тексту даёт ссылку на устаревшую версию.",
        what_to_do="Везде писать «ПП №1510 в ред. ПП №468 от 27.04.2026»; Указ №467 — в связке.",
        owner="Юрист + цифровой профиль (Минцифры/МВД)",
        related_docs=["D21", "D22", "D23", "D17"],
        v8_status="outdated",
        matches_pairs=[("D21", "D22"), ("D21", "D23"), ("D22", "D23"), ("D17", "D21")],
    ),
    Action(
        id="FA-06", category="amendment_to_law", severity="high",
        where="D24 270-ФЗ от 31.07.2025 → D11 (115-ФЗ) и D06 (109-ФЗ)",
        what_is_wrong="Ссылки на 115/109-ФЗ без оговорки «в ред. 270-ФЗ».",
        why="270-ФЗ затронул отдельные положения; для claims 2025 нужна актуальная редакция.",
        what_to_do="Везде указывать редакцию: «115-ФЗ в ред. 270-ФЗ»; «109-ФЗ в ред. 270-ФЗ».",
        owner="Юрист",
        related_docs=["D24", "D11", "D06"],
        v8_status="outdated",
        matches_pairs=[("D11", "D24"), ("D06", "D24")],
    ),
    Action(
        id="FA-07", category="amendment_to_koap", severity="high",
        where="D25 281-ФЗ → D13 КоАП ст.18.8/18.9/18.10/18.15",
        what_is_wrong="Ссылки на ст.18.x КоАП без оговорки «в ред. 281-ФЗ».",
        why="Размер штрафов и составы могли поменяться; неверная квалификация.",
        what_to_do="Везде указывать «КоАП ст.18.x в ред. 281-ФЗ от 31.07.2025».",
        owner="Юрист + комплаенс",
        related_docs=["D25", "D13"],
        v8_status="outdated",
        matches_pairs=[("D13", "D25")],
    ),
    Action(
        id="FA-08", category="analytic_separation", severity="low",
        where="D03 ВЦИОМ слайды 3-5 — миграционные тезисы",
        what_is_wrong="Тезисы ВЦИОМ преподнесены как факты в одной сводке с НПА.",
        why="Это data-driven наблюдения, не нормы. Смешивание формирует ложное ощущение, что аналитика — это норма.",
        what_to_do="Маркировать «по данным опроса»; блок отдельно от норм.",
        owner="Аналитик-составитель + юрист",
        related_docs=["D03", "D04", "D05", "D07", "D08"],
        v8_status="manual_review",
        matches_doc="D03",
    ),
    Action(
        id="FA-09", category="provenance_risk", severity="medium",
        where="consultant.ru, pravo.gov.ru, mvd.ru, economy.gov.ru — недоступны из download host",
        what_is_wrong="Direct fetch актуальной редакции с official-источников нестабилен.",
        why="Без устойчивого первоисточника невозможно гарантировать актуальность ссылки.",
        what_to_do="Fallback-цепочка Гарант → Контур → Меганорм; зафиксировать использованный mirror в отчёте.",
        owner="Operations / DevOps; юрист на финальной валидации",
        related_docs=["D11", "D06", "D15", "D24", "D25", "D17", "D21", "D22", "D23"],
        v8_status="manual_review",  # provenance-risk overlay
    ),
    Action(
        id="FA-10", category="source_gap", severity="medium",
        where="U-01 (внешние юрисдикции), U-02 (НК ст.227.1 + 115-ФЗ ст.13.3), U-03 (планы 30-р/4171-р построчно)",
        what_is_wrong="Корпус не покрывает 3 группы источников, упоминаемых в claims.",
        why="Без этих данных нельзя закрыть claims «глобальные тренды миграции» (ВЦИОМ) и «объёмы патентных платежей» (Клерк).",
        what_to_do="U-01: external источники IOM/OECD; U-02: получить тексты статей через Гарант; U-03: запросить полные приложения к 30-р/4171-р.",
        owner="Аналитик + юрист",
        related_docs=["D03", "D11", "D12", "D07", "D08"],
        v8_status="source_gap",
    ),
]


DEFAULT_BROCHURE_REDGREEN: list[BrochureRedGreenEntry] = [
    BrochureRedGreenEntry(
        id="BR-01", section="Критерий 1: социально значимые проекты",
        location="стр. 1, бокс «Условия», п.1",
        before="более 15 млн руб. в социально значимые проекты за 3 года",
        after="не менее 15 млн руб. в социально значимые проекты за 3 года",
        basis="ПП №2573, пп.«а» п.1 — «не менее 15 миллионов рублей»",
        effect="Инвестор с ровно 15 млн ₽ должен проходить (X ≥ 15), но текущий текст требует X > 15",
    ),
    BrochureRedGreenEntry(
        id="BR-02", section="Критерий 2: собственное юрлицо и налоги",
        location="стр. 1, бокс «Условия», п.2",
        before="юрлицо в РФ работает 2 года, ежегодно платит более 4 млн руб. налогов",
        after="юрлицо в РФ работает не менее 2 лет, ежегодные налоги/взносы не менее 4 млн руб.",
        basis="ПП №2573, пп.«б» п.1 — «не менее 4 миллионов рублей в год»",
        effect="Юрлицо с ровно 4 млн отчислений выпадает из критерия по тексту брошюры",
    ),
    BrochureRedGreenEntry(
        id="BR-03", section="Критерий 3: инвестиции в российское юрлицо",
        location="стр. 1, бокс «Условия», п.3",
        before="инвестиции более 30 млн руб., налоги юрлица более 6 млн в год",
        after="инвестиции не менее 30 млн руб., налоги/взносы юрлица не менее 6 млн в год",
        basis="ПП №2573, пп.«в» п.1 — «не менее 30 миллионов» / «не менее 6 миллионов»",
        effect="Двойной перекос — оба порога строгие, обрезает легитимных кандидатов",
    ),
    BrochureRedGreenEntry(
        id="BR-04", section="Критерий 4: недвижимость",
        location="стр. 1, бокс «Условия», п.4",
        before="недвижимость во владении более 1 года, кадастр: более 50 / 20 / 25 млн",
        after="недвижимость во владении не менее 1 года, кадастр: не менее 50 / 20 / 25 млн",
        basis="ПП №2573, пп.«г» п.1 — «не менее»",
        effect="Самый частый случай в практике — кадастр ровно на пороговой отметке",
    ),
    BrochureRedGreenEntry(
        id="BR-05", section="Сноска",
        location="стр. 1, нижняя сноска",
        before="в соответствии с ПП РФ от 31.12.2022 №2573",
        after="в соответствии с ПП РФ от 31.12.2022 №2573 (актуальная редакция; сверить с base.garant.ru/406067851/)",
        basis="—",
        effect="Без указания редакции невозможно отследить применимость",
    ),
    BrochureRedGreenEntry(
        id="BR-06", section="Локализации",
        location="9 языковых страниц",
        before="Поправки 1-5 повторить в EN/CN/AR/FR/DE/ES/JA/KO",
        after="Унифицированно «not less than» / «不少于» / «少なくとも» — formal-quantitative",
        basis="Соответствие исходному «не менее»",
        effect="Арабская страница OCR битая (D-003 v7) — повторно вычитать вручную",
    ),
]


DEFAULT_KLERK_NPA_LINKS: list[KlerkNPALink] = [
    KlerkNPALink(
        id="KL-01",
        thesis="90 дней безвизового пребывания в году",
        npa_doc="D15 260-ФЗ от 08.08.2024",
        specific_place="ст.5 (изменения в 115-ФЗ ст.5)",
        footnote="«260-ФЗ от 08.08.2024 ввёл сокращение безвизового срока до 90 дней в календарном году (ранее — 90 из 180)»",
        v8_status="manual_review",
    ),
    KlerkNPALink(
        id="KL-02",
        thesis="Реестр контролируемых лиц",
        npa_doc="D15 260-ФЗ + D11 115-ФЗ (в ред. 260-ФЗ)",
        specific_place="ст.4 260-ФЗ + 115-ФЗ ст.32 (новая редакция)",
        footnote="«Реестр введён 260-ФЗ; ведёт МВД; основание включения — нарушение режима пребывания/трудовой деятельности»",
        v8_status="manual_review",
    ),
    KlerkNPALink(
        id="KL-03",
        thesis="Цифровой профиль иностранного гражданина",
        npa_doc="D17 Указ Президента №467 от 09.07.2025; D21 ПП №1510",
        specific_place="Указ №467 п.1 — создание ГИС до 30.06.2026; ПП №1510 — эксперимент",
        footnote="«Указ №467 от 09.07.2025: создание ГИС «Цифровой профиль иностранного гражданина» до 30.06.2026; апробация по ПП №1510 (в ред. ПП №468)»",
        v8_status="manual_review",
    ),
    KlerkNPALink(
        id="KL-04",
        thesis="НДФЛ по патенту: фиксированные авансовые платежи",
        npa_doc="D12 НК РФ ст.227.1; D11 115-ФЗ ст.13.3",
        specific_place="НК ст.227.1 п.2 — фикс. авансовый платёж; п.3 — индексация",
        footnote="«НК ст.227.1: ежемесячный фиксированный авансовый платёж × коэффициент-дефлятор × региональный коэффициент»",
        v8_status="manual_review",
    ),
    KlerkNPALink(
        id="KL-05",
        thesis="Госпошлины 2025",
        npa_doc="D16 271-ФЗ от 31.07.2025; D12 НК ст.333.28-333.29",
        specific_place="271-ФЗ → НК ст.333.28 (выдача документов на въезд/выезд) и ст.333.29 (учёт по месту пребывания)",
        footnote="«Госпошлины пересмотрены 271-ФЗ от 31.07.2025; новые ставки см. НК ст.333.28-333.29 в редакции 271-ФЗ»",
        v8_status="manual_review",
    ),
    KlerkNPALink(
        id="KL-06",
        thesis="Ответственность работодателей",
        npa_doc="D13 КоАП ст.18.15 (в ред. 281-ФЗ); D11 115-ФЗ ст.13",
        specific_place="КоАП ст.18.15 (привлечение иностранца без разрешения); ст.18.10 (трудовая деятельность вне региона/специальности)",
        footnote="«КоАП ст.18.15 в ред. 281-ФЗ от 31.07.2025; уведомление о приёме/увольнении в МВД — 115-ФЗ ст.13 п.8»",
        v8_status="manual_review",
    ),
]


DEFAULT_EAEU_SPLIT: list[EAEUSplitEntry] = [
    EAEUSplitEntry(
        id="EA-01", group="Государства-члены ЕАЭС",
        countries="Армения, Беларусь, Казахстан, Киргизия, Россия",
        work_regime="БЕЗ разрешения на трудовую деятельность",
        basis="Договор о ЕАЭС, ст.97 п.1: «Работодатели и (или) заказчики работ (услуг) государства-члена вправе привлекать к осуществлению трудовой деятельности трудящихся государств-членов без учёта ограничений по защите национального рынка труда».",
        employer_action="Уведомить МВД о приёме на работу (115-ФЗ ст.13 п.8), оформить трудовой договор. Патент НЕ требуется.",
        minek_text_should_be="«Только эти 4 государства освобождены от разрешения на труд по Договору ЕАЭС».",
    ),
    EAEUSplitEntry(
        id="EA-02", group="Прочие государства (вне ЕАЭС, безвизовый порядок)",
        countries="Узбекистан, Таджикистан, Молдова, Азербайджан, Грузия, Туркменистан и др.",
        work_regime="Общий порядок: ПАТЕНТ (115-ФЗ ст.13.3)",
        basis="115-ФЗ ст.13.3 — патент на работу для безвизовых иностранных граждан. Регион ограничен субъектом РФ выдачи.",
        employer_action="Проверить наличие патента, его срок и регион. Принять только при действующем патенте.",
        minek_text_should_be="«Иностранные граждане в безвизовом порядке вне ЕАЭС: требуется ПАТЕНТ».",
    ),
    EAEUSplitEntry(
        id="EA-03", group="Граждане визовых государств",
        countries="Большинство стран без безвизовых соглашений с РФ",
        work_regime="РАЗРЕШЕНИЕ НА РАБОТУ (115-ФЗ ст.13)",
        basis="115-ФЗ ст.13 — разрешение в пределах квот; для ВКС/IT/инвестор — особый режим.",
        employer_action="Получить квоту, разрешение на привлечение, разрешение на работу для конкретного сотрудника.",
        minek_text_should_be="«Граждане визовых государств — разрешение на работу (квота)».",
    ),
]


DEFAULT_AMENDMENT_CHAIN: list[AmendmentChainEntry] = [
    AmendmentChainEntry(
        id="AC-01", chain="ruID / эксперимент въезда-выезда",
        base_act="D21 ПП РФ №1510 от 07.11.2024",
        amendments_chronology="D22 ПП №1562 от 08.10.2025 → D23 ПП №468 от 27.04.2026",
        related="D17 Указ №467 от 09.07.2025 (ГИС «Цифровой профиль» до 30.06.2026)",
        cite_now="«ПП №1510 в ред. ПП №468 от 27.04.2026»",
        where_to_verify="https://base.garant.ru/410728090/",
    ),
    AmendmentChainEntry(
        id="AC-02", chain="Базовая нормативная рамка",
        base_act="D11 115-ФЗ + D06 109-ФЗ + D19 114-ФЗ",
        amendments_chronology="D24 270-ФЗ от 31.07.2025 (изменения в 115/109-ФЗ)",
        related="D15 260-ФЗ (режим высылки, реестр контролируемых лиц)",
        cite_now="«115-ФЗ в ред. 260-ФЗ и 270-ФЗ»; «109-ФЗ в ред. 270-ФЗ»",
        where_to_verify="Гарант + Контур + Консультант (round-1 fallback)",
    ),
    AmendmentChainEntry(
        id="AC-03", chain="КоАП — ответственность",
        base_act="D13 КоАП ст.18.8/18.9/18.10/18.15",
        amendments_chronology="D25 281-ФЗ от 31.07.2025",
        related="D14 121-ФЗ (эксперимент Москва/МО)",
        cite_now="«КоАП ст.18.x в ред. 281-ФЗ от 31.07.2025»",
        where_to_verify="https://publication.pravo.gov.ru/Document/View/0001202507310012",
    ),
    AmendmentChainEntry(
        id="AC-04", chain="НК — налоги и пошлины",
        base_act="D12 НК ст.227.1 + ст.333.28-333.29",
        amendments_chronology="D16 271-ФЗ от 31.07.2025",
        related="—",
        cite_now="«НК ст.227.1, 333.28-333.29 в ред. 271-ФЗ от 31.07.2025»",
        where_to_verify="Гарант + Контур",
    ),
    AmendmentChainEntry(
        id="AC-05", chain="Концепции и планы",
        base_act="D05 Концепция 2019–2025 + D07 План 30-р",
        amendments_chronology="D04 Концепция 2026–2030 + D08 План 4171-р",
        related="—",
        cite_now="«Концепция 2026–2030 (Указ Президента); План 4171-р реализации»",
        where_to_verify="https://www.kremlin.ru/acts/bank/52490",
    ),
]


# ---------------------------------------------------------------------------
# RACI matrix
# ---------------------------------------------------------------------------

# RACI per FA action: Responsible (does), Accountable (signs off),
# Consulted (provides input), Informed (kept aware).
_RACI: dict[str, dict[str, str]] = {
    "FA-01": {
        "R": "Контент-менеджер Минэка",
        "A": "Юрист миграционного права (Минэк)",
        "C": "Заказчик ВНЖ инвестора (Минэк отдел инвест-резидентства)",
        "I": "Налоговая, МВД (миграционная служба)",
    },
    "FA-02": {
        "R": "Контент-менеджер Минэка",
        "A": "Юрист по международным договорам",
        "C": "ЕЭК, ФМС/МВД",
        "I": "Граждане ЕАЭС / работодатели",
    },
    "FA-03": {
        "R": "Редактор Клерка",
        "A": "Юрист миграционного права",
        "C": "Налоговая, МВД",
        "I": "Подписчики Клерка / HR",
    },
    "FA-04": {
        "R": "Методолог по миграционной политике",
        "A": "Юрист (Минэк/Минцифры)",
        "C": "Профильные ведомства",
        "I": "Стейкхолдеры реализации",
    },
    "FA-05": {
        "R": "Юрист цифрового профиля (Минцифры/МВД)",
        "A": "Старший юрист профильного департамента",
        "C": "Operations / DevOps",
        "I": "Технические команды эксперимента",
    },
    "FA-06": {
        "R": "Юрист (миграционное право)",
        "A": "Главный юрист департамента",
        "C": "Аналитик, методолог",
        "I": "Все, кто ссылается на 115-ФЗ/109-ФЗ",
    },
    "FA-07": {
        "R": "Юрист (КоАП)",
        "A": "Главный юрист + комплаенс",
        "C": "МВД, ФССП",
        "I": "Работодатели, кадровые службы",
    },
    "FA-08": {
        "R": "Аналитик-составитель презентаций",
        "A": "Юрист (надзор за корректностью norms vs analytics)",
        "C": "ВЦИОМ (источник данных)",
        "I": "Заказчики презентаций",
    },
    "FA-09": {
        "R": "Operations / DevOps",
        "A": "Технический руководитель сервиса",
        "C": "Юрист (валидация финальных ссылок)",
        "I": "Все потребители отчётов",
    },
    "FA-10": {
        "R": "Аналитик корпуса",
        "A": "Юрист (минимальный объём)",
        "C": "Заказчик отчёта",
        "I": "Стейкхолдеры пакета v8",
    },
}


def raci_for_action(action_id: str) -> dict[str, str]:
    """Return RACI matrix for one action; empty values for unknown IDs."""
    return _RACI.get(action_id, {"R": "", "A": "", "C": "", "I": ""})


# ---------------------------------------------------------------------------
# Pair → applicable actions
# ---------------------------------------------------------------------------


def actions_for_pair(
    left: str,
    right: str,
    catalogue: list[Action] | None = None,
) -> list[Action]:
    """Return actions whose ``matches_pairs`` or ``matches_doc`` apply to (left, right)."""
    cat = catalogue if catalogue is not None else DEFAULT_ACTIONS
    pair_set = frozenset({left, right})
    matched: list[Action] = []
    for a in cat:
        if a.matches_doc and (a.matches_doc == left or a.matches_doc == right):
            matched.append(a)
            continue
        for la, lb in a.matches_pairs:
            if frozenset({la, lb}) == pair_set:
                matched.append(a)
                break
    return matched


# ---------------------------------------------------------------------------
# Bundle integration
# ---------------------------------------------------------------------------


def _action_to_dict(a: Action) -> dict[str, Any]:
    return {
        "id": a.id,
        "category": a.category,
        "severity": a.severity,
        "where": a.where,
        "what_is_wrong": a.what_is_wrong,
        "why": a.why,
        "what_to_do": a.what_to_do,
        "owner": a.owner,
        "related_docs": list(a.related_docs),
        "v8_status": a.v8_status,
        "raci": raci_for_action(a.id),
    }


def apply_actions_to_bundle(
    bundle: Mapping[str, Any],
    catalogue: list[Action] | None = None,
    *,
    corpus: str | None = None,
) -> dict[str, Any]:
    """Annotate each pair with relevant action IDs and attach the catalogue.

    ``corpus="migration_v8"`` also attaches the corpus-literal supplementary
    catalogues (brochure_redgreen, klerk_npa_links, eaeu_split, amendment_chain).
    Without it those keys are omitted, keeping bundles free of domain-specific
    Russian migration-law content for non-migration batches.
    """
    cat = catalogue if catalogue is not None else DEFAULT_ACTIONS
    out = dict(bundle)
    out["pairs"] = [
        {**p, "actions": [a.id for a in actions_for_pair(p["left"], p["right"], cat)]}
        for p in bundle.get("pairs", [])
    ]
    out["actions_catalogue"] = [_action_to_dict(a) for a in cat]
    out["raci_matrix"] = {a.id: raci_for_action(a.id) for a in cat}
    out["corpus"] = "migration_v8" if corpus == "migration_v8" else "generic"
    if corpus == "migration_v8":
        out["brochure_redgreen"] = [vars(b) for b in DEFAULT_BROCHURE_REDGREEN]
        out["klerk_npa_links"] = [vars(k) for k in DEFAULT_KLERK_NPA_LINKS]
        out["eaeu_split"] = [vars(e) for e in DEFAULT_EAEU_SPLIT]
        out["amendment_chain"] = [vars(c) for c in DEFAULT_AMENDMENT_CHAIN]
    return out


__all__ = [
    "Action", "BrochureRedGreenEntry", "KlerkNPALink",
    "EAEUSplitEntry", "AmendmentChainEntry",
    "ACTION_CATEGORIES", "SEVERITY_LEVELS",
    "DEFAULT_ACTIONS", "DEFAULT_BROCHURE_REDGREEN", "DEFAULT_KLERK_NPA_LINKS",
    "DEFAULT_EAEU_SPLIT", "DEFAULT_AMENDMENT_CHAIN",
    "actions_for_pair", "raci_for_action", "apply_actions_to_bundle",
]
