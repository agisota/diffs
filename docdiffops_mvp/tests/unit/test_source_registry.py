"""Unit tests for ``docdiffops.source_registry`` (PR-1.5).

Covers the three public entry points:

- ``classify(filename, source_url, content_head)``
- ``infer_doc_type(filename, content_head)``
- ``infer_source_rank(source_url)``

The brief §13 doc-type vocabulary and §3 ADR-5 source ranks both
hinge on this module, so these tests are deliberately granular.
Cyrillic literals live in source as UTF-8; the test runner must
honor ``# -*- coding: utf-8 -*-`` (Python 3 default) to read them.
"""
from __future__ import annotations

import pytest

from docdiffops.source_registry import (
    DOC_TYPES,
    HOST_RANK,
    RANK_LABEL,
    RANK_OVERRIDES,
    classify,
    infer_doc_type,
    infer_source_rank,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


def test_rank_label_has_three_ranks() -> None:
    assert RANK_LABEL == {1: "official_npa", 2: "departmental", 3: "analytics"}


def test_doc_types_contains_all_brief_categories() -> None:
    expected = {
        "LEGAL_NPA",
        "LEGAL_CONCEPT",
        "GOV_PLAN",
        "PRESENTATION",
        "TABLE",
        "WEB_ARTICLE",
        "OTHER",
    }
    assert set(DOC_TYPES) == expected


# ---------------------------------------------------------------------------
# infer_source_rank
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url,expected_rank",
    [
        # Rank 1 — official NPA publishers.
        ("https://kremlin.ru/news/100", 1),
        ("https://www.kremlin.ru/", 1),  # www. is stripped → exact match in HOST_RANK
        ("http://pravo.gov.ru/", 1),
        ("https://publication.pravo.gov.ru/Document/View/0001", 1),
        ("https://government.ru/news/123", 1),
        ("https://tinao.mos.ru/news", 1),  # *.mos.ru
        ("https://www.mos.ru/", 1),  # *.mos.ru suffix
        # Rank 2 — ministries / regulatory aggregators.
        ("https://economy.gov.ru/material/x", 2),  # explicit demote
        ("https://kontur.ru/articles/x", 2),
        ("https://www.consultant.ru/document/x", 2),
        ("https://garant.ru/products/x", 2),
        ("https://mvd.ru/news/x", 2),
        # Rank 2 via .gov.ru suffix (anything not in rank 1).
        ("https://minfin.gov.ru/x", 2),
        ("https://random.gov.ru/x", 2),
        # Rank 3 — analytics, media, social.
        ("https://wciom.ru/news/x", 3),
        ("https://klerk.ru/buh/articles/x", 3),
        ("https://vedomosti.ru/x", 3),
        ("https://kommersant.ru/doc/x", 3),
        ("https://t.me/durov", 3),
        ("https://twitter.com/elonmusk", 3),
    ],
)
def test_infer_source_rank_known_hosts(url: str, expected_rank: int) -> None:
    assert infer_source_rank(url) == expected_rank


def test_infer_source_rank_none_returns_three() -> None:
    assert infer_source_rank(None) == 3


def test_infer_source_rank_empty_string_returns_three() -> None:
    assert infer_source_rank("") == 3
    assert infer_source_rank("   ") == 3


def test_infer_source_rank_no_scheme_still_resolves() -> None:
    """A URL like ``kremlin.ru/news`` (no scheme) must still rank 1."""
    assert infer_source_rank("kremlin.ru/news/x") == 1
    assert infer_source_rank("economy.gov.ru/y") == 2


def test_infer_source_rank_with_port_strips_port() -> None:
    assert infer_source_rank("https://kremlin.ru:443/news") == 1
    assert infer_source_rank("http://garant.ru:80/x") == 2


def test_infer_source_rank_idn_domain_passes_through() -> None:
    """IDN hostnames should not crash the parser; unknown -> rank 3."""
    # urlparse normalizes the IDN host to lowercase; not in our table.
    assert infer_source_rank("https://пример.рф/news") == 3


def test_infer_source_rank_uppercased_host() -> None:
    """Hosts must compare case-insensitively."""
    assert infer_source_rank("https://KREMLIN.RU/news") == 1
    assert infer_source_rank("https://Garant.RU/x") == 2


def test_infer_source_rank_economy_gov_ru_is_rank_two() -> None:
    """Spec demands economy.gov.ru drops to rank 2 even though
    .gov.ru would otherwise put it at rank 1.
    """
    assert infer_source_rank("https://economy.gov.ru/material") == 2


def test_infer_source_rank_overrides_take_precedence(monkeypatch) -> None:
    """Operator overrides must beat both exact and suffix matches."""
    monkeypatch.setitem(RANK_OVERRIDES, "kremlin.ru", 3)
    try:
        assert infer_source_rank("https://kremlin.ru/x") == 3
    finally:
        # monkeypatch.setitem reverts on test exit.
        pass


def test_host_rank_table_is_sane() -> None:
    """Sanity: ranks live in {1, 2}; rank 3 entries belong in fallback."""
    for host, rank in HOST_RANK.items():
        assert rank in (1, 2), f"{host} has unexpected rank {rank}"


# ---------------------------------------------------------------------------
# infer_doc_type — extension-driven
# ---------------------------------------------------------------------------


def test_infer_doc_type_pptx_is_presentation() -> None:
    assert infer_doc_type("deck.pptx") == "PRESENTATION"
    assert infer_doc_type("Deck.PPTX") == "PRESENTATION"
    assert infer_doc_type("legacy.ppt") == "PRESENTATION"


def test_infer_doc_type_xlsx_is_table() -> None:
    assert infer_doc_type("data.xlsx") == "TABLE"
    assert infer_doc_type("export.csv") == "TABLE"
    assert infer_doc_type("export.tsv") == "TABLE"
    assert infer_doc_type("export.xls") == "TABLE"


def test_infer_doc_type_html_without_keywords_is_web_article() -> None:
    assert infer_doc_type("page.html") == "WEB_ARTICLE"
    assert infer_doc_type("page.HTM") == "WEB_ARTICLE"


def test_infer_doc_type_unknown_extension_is_other() -> None:
    assert infer_doc_type("blob.bin") == "OTHER"
    assert infer_doc_type("scan.tiff") == "OTHER"


def test_infer_doc_type_no_extension_is_other() -> None:
    assert infer_doc_type("README") == "OTHER"


# ---------------------------------------------------------------------------
# infer_doc_type — content sniff
# ---------------------------------------------------------------------------


def test_infer_doc_type_legal_npa_keyword() -> None:
    head = "УКАЗ Президента Российской Федерации".encode("utf-8")
    assert infer_doc_type("doc.pdf", head) == "LEGAL_NPA"


def test_infer_doc_type_legal_npa_federal_law() -> None:
    head = "Федеральный закон от 24.07.2024".encode("utf-8")
    assert infer_doc_type("doc.pdf", head) == "LEGAL_NPA"


def test_infer_doc_type_legal_npa_government_order() -> None:
    head = "Распоряжение Правительства Российской Федерации".encode("utf-8")
    assert infer_doc_type("doc.pdf", head) == "LEGAL_NPA"


def test_infer_doc_type_legal_concept() -> None:
    head = "Концепция государственной миграционной политики".encode("utf-8")
    assert infer_doc_type("doc.pdf", head) == "LEGAL_CONCEPT"


def test_infer_doc_type_legal_concept_national_variant() -> None:
    head = "Концепция национальной безопасности".encode("utf-8")
    assert infer_doc_type("doc.pdf", head) == "LEGAL_CONCEPT"


def test_infer_doc_type_gov_plan() -> None:
    head = "План мероприятий по реализации\nответственный исполнитель".encode("utf-8")
    assert infer_doc_type("doc.docx", head) == "GOV_PLAN"


def test_infer_doc_type_gov_plan_with_term_only() -> None:
    head = "План мероприятий\nсрок реализации до 2030 года".encode("utf-8")
    assert infer_doc_type("doc.docx", head) == "GOV_PLAN"


def test_infer_doc_type_html_with_legal_keyword_is_legal_npa() -> None:
    """An HTML page that contains a legal NPA keyword takes the NPA label
    even though the extension would default to WEB_ARTICLE."""
    head = b"<html><body>" + "Указ Президента".encode("utf-8") + b"</body></html>"
    assert infer_doc_type("page.html", head) == "LEGAL_NPA"


def test_infer_doc_type_html_powerpoint_meta_is_presentation() -> None:
    head = b'<html><head><meta name="generator" content="Microsoft PowerPoint">'
    assert infer_doc_type("page.html", head) == "PRESENTATION"


def test_infer_doc_type_pdf_without_keywords_is_other() -> None:
    """Permissive default: a PDF with no keyword match stays OTHER."""
    head = b"%PDF-1.7\nrandom binary content"
    assert infer_doc_type("scan.pdf", head) == "OTHER"


def test_infer_doc_type_pdf_with_no_content_is_other() -> None:
    assert infer_doc_type("blob.pdf", None) == "OTHER"
    assert infer_doc_type("blob.pdf", b"") == "OTHER"


def test_infer_doc_type_extension_wins_over_content_for_pptx() -> None:
    """A PPTX with NPA-looking text inside still classifies as PRESENTATION
    because the extension is unambiguous."""
    head = "Указ президента".encode("utf-8")
    assert infer_doc_type("slides.pptx", head) == "PRESENTATION"


def test_infer_doc_type_extension_wins_over_content_for_xlsx() -> None:
    head = "Концепция государственной".encode("utf-8")
    assert infer_doc_type("rows.xlsx", head) == "TABLE"


# ---------------------------------------------------------------------------
# classify (combined)
# ---------------------------------------------------------------------------


def test_classify_returns_doc_type_and_rank_tuple() -> None:
    out = classify("a.pdf", "https://kremlin.ru/news", b"")
    assert isinstance(out, tuple) and len(out) == 2


def test_classify_kremlin_npa_pdf() -> None:
    head = "Указ Президента Российской Федерации № 1 от 1 января".encode("utf-8")
    assert classify("ukaz.pdf", "https://kremlin.ru/acts/123", head) == ("LEGAL_NPA", 1)


def test_classify_mos_table_xlsx() -> None:
    assert classify("plan.xlsx", "https://tinao.mos.ru/data") == ("TABLE", 1)


def test_classify_vciom_web_article() -> None:
    assert classify("page.html", "https://wciom.ru/news/x") == ("WEB_ARTICLE", 3)


def test_classify_no_url_is_rank_three() -> None:
    """Locally-uploaded files have no provenance -> rank 3."""
    head = "Указ Президента".encode("utf-8")
    doc_type, rank = classify("ukaz.pdf", None, head)
    assert doc_type == "LEGAL_NPA"
    assert rank == 3


def test_classify_pptx_no_url() -> None:
    assert classify("deck.pptx") == ("PRESENTATION", 3)


def test_classify_economy_gov_ru_demoted() -> None:
    assert classify("doc.pdf", "https://economy.gov.ru/material/x") == ("OTHER", 2)
