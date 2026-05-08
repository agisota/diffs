"""Unit tests for the Russian legal layer (PR-3.1 + PR-3.2)."""
from __future__ import annotations

import pytest

from docdiffops.legal import Chunk, chunk_text, parse_refs
from docdiffops.legal.chunker import chunk_concept, chunk_gov_plan, chunk_npa


# ---------------------------------------------------------------------------
# Refs
# ---------------------------------------------------------------------------


def test_parse_refs_simple_article():
    refs = parse_refs("В соответствии со ст. 5 настоящего закона.")
    assert len(refs) == 1
    assert refs[0].parts == {"article": "5"}


def test_parse_refs_chained_article_part_point():
    refs = parse_refs("См. ст. 109, ч. 2, п. 3 ФЗ.")
    assert len(refs) == 1
    r = refs[0]
    assert r.parts == {"article": "109", "part": "2", "point": "3"}


def test_parse_refs_subpoint_letter():
    refs = parse_refs("Согласно п. 4 подп. а)")
    assert refs[0].parts == {"point": "4", "subpoint": "а"}


def test_parse_refs_multiple_chains_in_one_string():
    refs = parse_refs("См. ст. 5 и ст. 7 настоящего закона.")
    assert len(refs) == 2
    assert refs[0].parts["article"] == "5"
    assert refs[1].parts["article"] == "7"


def test_parse_refs_with_npa_doc_attaches():
    refs = parse_refs("ст. 5 ФЗ № 109-ФЗ от 18.07.2006")
    assert refs[0].doc_num == "109-ФЗ"
    assert refs[0].doc_date == "18.07.2006"


def test_parse_refs_section_roman_numeral():
    refs = parse_refs("раздел II Концепции")
    assert refs[0].parts == {"section": "II"}


def test_parse_refs_empty_input_is_empty_list():
    assert parse_refs("") == []
    assert parse_refs(None) == []  # type: ignore[arg-type]


def test_legal_ref_key_is_dotted_hierarchy():
    refs = parse_refs("ст. 5, ч. 2, п. 3")
    assert refs[0].key() == "article=5/part=2/point=3"


# ---------------------------------------------------------------------------
# NPA chunker
# ---------------------------------------------------------------------------


def test_chunk_npa_single_article():
    text = "Статья 5. Учёт мигрантов\nТекст статьи."
    chunks = chunk_npa(text)
    assert len(chunks) == 1
    assert chunks[0].kind == "article"
    assert chunks[0].number == "5"
    assert "Учёт мигрантов" in chunks[0].title
    assert "Текст статьи" in chunks[0].text


def test_chunk_npa_article_with_parts_and_points():
    text = (
        "Статья 7. Регистрация\n"
        "1. Иностранный гражданин подлежит регистрации.\n"
        "2. Регистрация производится в течение 7 дней.\n"
        "1) при въезде;\n"
        "2) при смене места жительства;\n"
        "а) для безвизовых;\n"
        "б) для визовых.\n"
    )
    chunks = chunk_npa(text)
    kinds = [c.kind for c in chunks]
    assert "article" in kinds
    assert kinds.count("part") == 2
    assert kinds.count("point") == 2
    assert kinds.count("subpoint") == 2
    # Hierarchy: article has no parent; parts parent the article;
    # points parent the (last) part; subpoints parent the (last) point.
    article = next(c for c in chunks if c.kind == "article")
    parts = [c for c in chunks if c.kind == "part"]
    assert all(p.parent_id == article.chunk_id for p in parts)
    points = [c for c in chunks if c.kind == "point"]
    assert all(p.parent_id == parts[-1].chunk_id for p in points)
    subpoints = [c for c in chunks if c.kind == "subpoint"]
    assert all(s.parent_id == points[-1].chunk_id for s in subpoints)


def test_chunk_npa_section_above_article():
    text = (
        "Раздел I. Общие положения\n"
        "Статья 1. Цели закона\n"
        "Текст.\n"
    )
    chunks = chunk_npa(text)
    assert chunks[0].kind == "section"
    assert chunks[1].kind == "article"


def test_chunk_npa_preamble_before_first_article():
    text = "Настоящий федеральный закон регулирует...\nСтатья 1. Цели\nТекст."
    chunks = chunk_npa(text)
    assert chunks[0].kind == "preamble"
    assert "регулирует" in chunks[0].text


def test_chunk_npa_appendix_stops_processing():
    text = (
        "Статья 1. Цели\n"
        "Текст.\n"
        "Приложение № 1\n"
        "Полная таблица.\n"
        "Статья 2. Дальнейшее.\n"
    )
    chunks = chunk_npa(text)
    kinds = [c.kind for c in chunks]
    # Article 2 is INSIDE the appendix and should not become its own chunk.
    assert kinds.count("article") == 1
    assert "appendix" in kinds


def test_chunk_npa_chunk_ids_are_deterministic():
    text = "Статья 5. Учёт\nТекст."
    a = chunk_npa(text, doc_id="d1")
    b = chunk_npa(text, doc_id="d1")
    assert [c.chunk_id for c in a] == [c.chunk_id for c in b]


def test_chunk_npa_chunk_ids_change_with_doc_id():
    text = "Статья 5. Учёт\nТекст."
    a = chunk_npa(text, doc_id="d1")
    b = chunk_npa(text, doc_id="d2")
    assert [c.chunk_id for c in a] != [c.chunk_id for c in b]


# ---------------------------------------------------------------------------
# Concept chunker
# ---------------------------------------------------------------------------


def test_chunk_concept_section_with_numbered_points():
    text = (
        "Раздел I. Общие положения\n"
        "1. Стимулирование интеллектуальной миграции.\n"
        "2. Усиление учёта.\n"
    )
    chunks = chunk_concept(text)
    assert chunks[0].kind == "section"
    assert chunks[1].kind == "point"
    assert chunks[1].number == "1"
    assert chunks[2].kind == "point"
    assert chunks[1].parent_id == chunks[0].chunk_id


def test_chunk_concept_subpoint_under_point():
    text = (
        "Раздел II. Цели\n"
        "1. Развитие миграции.\n"
        "а) трудовой;\n"
        "б) образовательной.\n"
    )
    chunks = chunk_concept(text)
    sub = [c for c in chunks if c.kind == "subpoint"]
    pts = [c for c in chunks if c.kind == "point"]
    assert len(sub) == 2
    assert all(s.parent_id == pts[0].chunk_id for s in sub)


# ---------------------------------------------------------------------------
# Gov plan chunker
# ---------------------------------------------------------------------------


def test_chunk_gov_plan_measures_with_deadline_and_responsible():
    text = (
        "1. Подготовить проект закона. Срок: 2024 год. Ответственный: Минэк.\n"
        "2. Ввести единую систему. Срок: 2025 год. Ожидаемый результат: цифровой учёт.\n"
    )
    chunks = chunk_gov_plan(text)
    assert len(chunks) == 2
    assert all(c.kind == "measure" for c in chunks)
    assert chunks[0].extras.get("has_deadline") is True
    assert chunks[0].extras.get("has_responsible") is True
    assert chunks[1].extras.get("has_outcome") is True


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "doc_type, expected_top_kind",
    [
        ("LEGAL_NPA", "article"),
        ("LEGAL_CONCEPT", "section"),
        ("GOV_PLAN", "measure"),
        (None, "article"),     # default → npa
        ("OTHER", "article"),  # fallback
    ],
)
def test_chunk_text_dispatches_by_doc_type(doc_type, expected_top_kind):
    samples = {
        "article": "Статья 1. Цели\nТекст.",
        "section": "Раздел I. Общие\n1. Тезис.",
        "measure": "1. Принять меры.",
    }
    text = samples[expected_top_kind]
    chunks = chunk_text(doc_type, text)
    kinds = [c.kind for c in chunks]
    assert expected_top_kind in kinds


def test_chunk_returns_dataclass_chunks():
    chunks = chunk_text("LEGAL_NPA", "Статья 1. Цели\nТекст.")
    assert all(isinstance(c, Chunk) for c in chunks)
    assert hasattr(chunks[0], "to_dict")
    d = chunks[0].to_dict()
    assert d["kind"] == "article"
