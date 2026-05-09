"""Forensic v8 cross-comparison contract for DocDiffOps.

This module is the single source of truth for the **v8 forensic shape**:
the canonical seven-status scale, the pair-status aggregator (with the
rank-3 ↔ rank-1 invariant), the topic clustering catalogue, the
amendment graph helper, and the bundle serialiser. The migration v8
reference package (``/home/dev/diff/migration_v8_out``) was generated
from a one-off script; this module lifts the same contract into
DocDiffOps so any batch can render evidence-grade output.

Contract:
  * **V8_STATUSES** — exact 7-status scale.
  * **EVENT_STATUS_TO_V8** — maps DocDiffOps's per-event vocabulary
    (same/partial/contradicts/modified/added/deleted/manual_review/
    not_found) into the v8 vocabulary.
  * **aggregate_pair_status_v8(events, left_rank, right_rank, ...)** →
    one v8 status per pair. Honors:
      - empty events → ``not_comparable``
      - explicit ``known_contradictions`` list → ``contradiction``
      - rank-3 ↔ rank-1 → ``manual_review`` (analyst cannot refute NPA)
      - any ``manual_review`` event → ``manual_review``
      - any ``contradicts`` event → ``contradiction``
      - any ``partial / modified / added / deleted`` → ``partial_overlap``
      - all ``same`` → ``match``
  * **cluster_topic_v8(text, clusters)** — stable cluster ID lookup.
  * **derive_outdated(graph, a, b)** — ``True`` if either side is
    superseded/amended by the other per ``amendment_graph``.
  * **build_forensic_bundle(documents, pairs, events, amendment_graph)**
    — pure function returning the v8 JSON-serialisable bundle. Renderers
    (``forensic_render``) consume this dict.
"""
from __future__ import annotations

import datetime as dt
import unicodedata
from collections import Counter
from typing import Any, Iterable, Mapping, Sequence

# ---------------------------------------------------------------------------
# Status scale
# ---------------------------------------------------------------------------

STATUS_MATCH = "match"
STATUS_PARTIAL = "partial_overlap"
STATUS_CONTRADICTION = "contradiction"
STATUS_OUTDATED = "outdated"
STATUS_GAP = "source_gap"
STATUS_REVIEW = "manual_review"
STATUS_NC = "not_comparable"

V8_STATUSES: tuple[str, ...] = (
    STATUS_MATCH,
    STATUS_PARTIAL,
    STATUS_CONTRADICTION,
    STATUS_OUTDATED,
    STATUS_GAP,
    STATUS_REVIEW,
    STATUS_NC,
)

# Glyphs for matrix cells.
STATUS_TO_MARK: dict[str, str] = {
    STATUS_MATCH: "✓",
    STATUS_PARTIAL: "≈",
    STATUS_CONTRADICTION: "⚠",
    STATUS_OUTDATED: "↻",
    STATUS_GAP: "∅",
    STATUS_REVIEW: "?",
    STATUS_NC: "—",
}

# DocDiffOps event vocabulary → v8 vocabulary.
EVENT_STATUS_TO_V8: dict[str, str] = {
    "same": STATUS_MATCH,
    "partial": STATUS_PARTIAL,
    "contradicts": STATUS_CONTRADICTION,
    "modified": STATUS_PARTIAL,
    "added": STATUS_PARTIAL,
    "deleted": STATUS_PARTIAL,
    "manual_review": STATUS_REVIEW,
    "not_found": STATUS_REVIEW,
}


# ---------------------------------------------------------------------------
# Topic clustering
# ---------------------------------------------------------------------------

# (id, label, [case-insensitive substrings]). Specific clusters before
# generic ones — matching is first-hit.
DEFAULT_TOPIC_CLUSTERS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("T01", "ruID, цифровой профиль, биометрия",
     ("цифровой профиль", "ruid", "1510", "биометр", "467")),
    ("T02", "Миграционный учёт и фактическое нахождение",
     ("миграционный учёт", "миграционный учет", "фактическо")),
    ("T03", "Патенты, НДФЛ, госпошлины",
     ("патент", "ндфл", "госпошлин", "налог")),
    ("T04", "Режим высылки, реестр контролируемых лиц",
     ("высылк", "реестр контролируемых")),
    ("T05", "Образовательная миграция",
     ("образовательная миграция", "иностранные студент")),
    ("T06", "Адаптация и интеграция",
     ("адаптация", "интеграц", "анклав", "напряжённ", "напряжен")),
    ("T07", "ВНЖ инвестора (ПП №2573)",
     ("внж инвестор", "инвестор", "критерий", "брошюр",
      "социально значим", "недвижимост")),
    ("T08", "Эксперимент 121-ФЗ Москва/МО, 90 дней",
     ("121-фз", "эксперимент", "90 дней", "безвизов")),
    ("T09", "ВЦИОМ-claims",
     ("вциом",)),
    ("T10", "Концепции и планы",
     ("концепци", "план 30-р", "план 4171", "30-р", "4171", "30р",
      "покрытие старой", "покрытие новой", "смена структуры",
      "эволюция планов", "план 30")),
    ("T11", "ЕАЭС: трудовая миграция",
     ("еаэс", "трудовая миграц", "трудоустрой")),
    ("T12", "КоАП: ответственность",
     ("коап", "ответственност", "штраф")),
    ("T13", "Изменения 2024–2026",
     ("260-фз", "270-фз", "271-фз", "281-фз", "1562", "468",
      "изменения 115", "изменения 109", "изменения")),
    ("T14", "Базовая нормативная рамка (114/115/109)",
     ("114-фз", "115-фз", "109-фз", "въезд", "выезд")),
    ("T15", "Внутренний сервис «Нейрон» (методология)",
     ("нейрон", "работа внутреннего сервиса")),
    ("T16", "Общая миграция (cross-cutting)",
     ("миграция", "правовая основа", "нормативная база")),
    ("T17", "Мониторинг и статистика",
     ("мониторинг", "статистик", "социолог")),
)


def cluster_topic_v8(
    raw_topic: str,
    clusters: Sequence[tuple[str, str, Sequence[str]]] = DEFAULT_TOPIC_CLUSTERS,
) -> tuple[str, str]:
    """Match ``raw_topic`` against ``clusters`` first-hit; ``T00`` if none."""
    if not raw_topic:
        return ("T00", "Без темы")
    n = unicodedata.normalize("NFC", raw_topic).lower().strip()
    for cid, label, needles in clusters:
        for needle in needles:
            if needle in n:
                return (cid, label)
    return ("T00", "Прочее (не кластеризовано)")


# ---------------------------------------------------------------------------
# Pair-status aggregator
# ---------------------------------------------------------------------------


def _normalise_event_status(raw: str) -> str:
    """Translate a DocDiffOps event status into the v8 vocabulary.

    Already-v8 strings pass through unchanged; this lets internal callers
    feed pre-computed v8 events back into the aggregator without round-tripping
    through the DocDiffOps vocabulary.
    """
    if raw in V8_STATUSES:
        return raw
    return EVENT_STATUS_TO_V8.get(raw or "", STATUS_REVIEW)


def aggregate_pair_status_v8(
    events: Sequence[Mapping[str, Any]],
    *,
    left_rank: int,
    right_rank: int,
    known_contradictions: Sequence[tuple[str, str]] = (),
    left_id: str | None = None,
    right_id: str | None = None,
) -> str:
    """Single v8 status from per-event evidence and document ranks.

    Precedence (top wins):
        1. Empty events → not_comparable.
        2. ``(left_id, right_id)`` (in either order) listed in
           ``known_contradictions`` → contradiction.
        3. rank-3 ↔ rank-1 → manual_review (NPA-hierarchy invariant).
        4. Any v8 event status of ``manual_review`` → manual_review.
        5. Any v8 event status of ``contradiction`` → contradiction.
        6. Any v8 event status of ``partial_overlap`` → partial_overlap.
        7. All ``match`` → match.
        8. Otherwise (e.g. only ``not_comparable`` events) → not_comparable.
    """
    if not events:
        return STATUS_NC

    if left_id is not None and right_id is not None:
        pair_set = {left_id, right_id}
        for a, b in known_contradictions:
            if {a, b} == pair_set:
                return STATUS_CONTRADICTION

    rank3_vs_primary = (left_rank, right_rank) in {(1, 3), (3, 1)}

    v8_events = [_normalise_event_status(e.get("status", "")) for e in events]

    if rank3_vs_primary:
        # The analyst cannot directly refute or ratify an NPA.
        return STATUS_REVIEW

    if STATUS_REVIEW in v8_events:
        return STATUS_REVIEW
    if STATUS_CONTRADICTION in v8_events:
        return STATUS_CONTRADICTION
    if STATUS_PARTIAL in v8_events:
        return STATUS_PARTIAL
    if all(e == STATUS_MATCH for e in v8_events):
        return STATUS_MATCH
    return STATUS_NC


# ---------------------------------------------------------------------------
# Amendment graph helper
# ---------------------------------------------------------------------------


def derive_outdated(
    amendment_graph: Mapping[str, Sequence[str]],
    a: str,
    b: str,
) -> bool:
    """Return True if ``{a, b}`` is an amendment-edge in either direction."""
    pair = {a, b}
    for newer, olds in amendment_graph.items():
        for old in olds:
            if {newer, old} == pair:
                return True
    return False


# ---------------------------------------------------------------------------
# Bundle builder
# ---------------------------------------------------------------------------


def _generated_at() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")


def _rank_pair_key(rl: int, rr: int) -> str:
    """Rank-pair key sorted lo↔hi for stable aggregation."""
    a, b = sorted([rl, rr])
    return f"{a}↔{b}"


def build_forensic_bundle(
    *,
    documents: Sequence[Mapping[str, Any]],
    pairs: Sequence[Mapping[str, Any]],
    events: Sequence[Mapping[str, Any]] = (),
    amendment_graph: Mapping[str, Sequence[str]] | None = None,
    known_contradictions: Sequence[tuple[str, str]] = (),
    topic_clusters: Sequence[tuple[str, str, Sequence[str]]] = DEFAULT_TOPIC_CLUSTERS,
    schema_version: str = "v8.0",
) -> dict[str, Any]:
    """Build the v8 forensic bundle dict.

    ``documents`` items must have keys: id, code, rank, title, type.
    ``pairs`` items must have: id, left, right, events (list of dicts with
    ``status`` and optional ``severity``).
    """
    amendment_graph = dict(amendment_graph or {})
    rank_by_id: dict[str, int] = {d["id"]: int(d["rank"]) for d in documents}

    enriched_pairs: list[dict[str, Any]] = []
    for p in pairs:
        l = p["left"]
        r = p["right"]
        ev_list = list(p.get("events", []))
        v8_status = aggregate_pair_status_v8(
            ev_list,
            left_rank=rank_by_id.get(l, 99),
            right_rank=rank_by_id.get(r, 99),
            known_contradictions=known_contradictions,
            left_id=l, right_id=r,
        )
        # If aggregator says match/partial but amendment graph flags this
        # pair, demote to outdated for the older side.
        if v8_status in {STATUS_MATCH, STATUS_PARTIAL} and \
                derive_outdated(amendment_graph, l, r):
            v8_status = STATUS_OUTDATED
        topics = sorted({
            cluster_topic_v8(e.get("topic", ""), topic_clusters)[1]
            for e in ev_list if e.get("topic")
        })
        explanations = sorted({
            e.get("explanation_short", "")
            for e in ev_list
            if e.get("explanation_short", "").strip()
        })[:5]
        enriched_pairs.append({
            "id": p["id"],
            "left": l,
            "right": r,
            "left_rank": rank_by_id.get(l),
            "right_rank": rank_by_id.get(r),
            "v8_status": v8_status,
            "events_count": len(ev_list),
            "topics": topics,
            "explanations": explanations,
            "rank_pair": _rank_pair_key(rank_by_id.get(l, 99), rank_by_id.get(r, 99)),
        })

    status_dist = Counter(p["v8_status"] for p in enriched_pairs)
    rank_dist = Counter(p["rank_pair"] for p in enriched_pairs)

    bundle = {
        "schema_version": schema_version,
        "generated_at": _generated_at(),
        "documents": [dict(d) for d in documents],
        "pairs": enriched_pairs,
        "topic_clusters": [
            {"id": cid, "label": label, "needles": list(needles)}
            for cid, label, needles in topic_clusters
        ],
        "amendment_graph": {k: list(v) for k, v in amendment_graph.items()},
        "known_contradictions": [list(t) for t in known_contradictions],
        "status_scale": list(V8_STATUSES),
        "status_distribution_pairs": dict(status_dist),
        "rank_pair_distribution": dict(rank_dist),
        "control_numbers": {
            "documents": len(documents),
            "pairs": len(enriched_pairs),
            "events": len(events),
        },
    }
    return bundle


def bundle_from_batch_state(
    state: Mapping[str, Any],
    all_events: Sequence[Mapping[str, Any]],
    pair_summaries: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Translate DocDiffOps batch state into a v8 forensic bundle.

    Pure translator. State shape:
      * state["documents"] — list of dicts with doc_id/source_rank/doc_type/source_url
      * state["amendment_graph"] — optional {newer: [olds]}
      * state["known_contradictions"] — optional [(left_id, right_id), …]
    Pair summaries items must have pair_id + lhs_doc_id + rhs_doc_id.
    Events items have pair_id + status + severity + topic.
    """
    docs = []
    for d in state.get("documents", []) or []:
        docs.append({
            "id": d.get("doc_id") or d.get("id") or d.get("filename", ""),
            "code": d.get("doc_id") or d.get("id") or "",
            "rank": int(d.get("source_rank") or 3),
            "title": d.get("filename") or d.get("title") or "",
            "type": d.get("doc_type") or "OTHER",
            "url": d.get("source_url") or "",
        })

    events_by_pair: dict[str, list[dict[str, Any]]] = {}
    for ev in all_events or []:
        events_by_pair.setdefault(ev.get("pair_id", ""), []).append({
            "status": ev.get("status", ""),
            "severity": ev.get("severity", "medium"),
            "topic": ev.get("topic") or ev.get("section") or "",
            "explanation_short": ev.get("explanation_short", ""),
        })

    pairs = []
    for ps in pair_summaries or []:
        pid = ps.get("pair_id") or ps.get("id", "")
        pairs.append({
            "id": pid,
            "left": ps.get("lhs_doc_id") or ps.get("lhs", ""),
            "right": ps.get("rhs_doc_id") or ps.get("rhs", ""),
            "events": events_by_pair.get(pid, []),
        })

    return build_forensic_bundle(
        documents=docs,
        pairs=pairs,
        events=list(all_events or []),
        amendment_graph=state.get("amendment_graph") or {},
        known_contradictions=tuple(
            tuple(t) for t in (state.get("known_contradictions") or [])
        ),
    )


__all__ = [
    "V8_STATUSES",
    "STATUS_TO_MARK",
    "EVENT_STATUS_TO_V8",
    "STATUS_MATCH", "STATUS_PARTIAL", "STATUS_CONTRADICTION",
    "STATUS_OUTDATED", "STATUS_GAP", "STATUS_REVIEW", "STATUS_NC",
    "DEFAULT_TOPIC_CLUSTERS",
    "cluster_topic_v8",
    "aggregate_pair_status_v8",
    "derive_outdated",
    "build_forensic_bundle",
    "bundle_from_batch_state",
]
