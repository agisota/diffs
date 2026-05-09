"""JSON Schema for the v8.0 forensic bundle (draft-07).

This is the **formal contract** that any DocDiffOps-produced bundle must
satisfy. The schema is consumed by ``forensic_actions.validate_bundle``
and by the test suite to guarantee any caller-supplied bundle conforms.

The schema is generated programmatically rather than read from disk so
the source of truth is one Python literal that travels with the module.
``BUNDLE_SCHEMA_DICT`` is exported for tools and tests.
"""
from __future__ import annotations

from typing import Any

V8_STATUS_ENUM = [
    "match",
    "partial_overlap",
    "contradiction",
    "outdated",
    "source_gap",
    "manual_review",
    "not_comparable",
]

BUNDLE_SCHEMA_DICT: dict[str, Any] = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "$id": "https://docdiffops/forensic/v8_bundle.schema.json",
    "title": "DocDiffOps Forensic v8 Bundle",
    "description": "Evidence-grade cross-comparison bundle produced by docdiffops.forensic.build_forensic_bundle.",
    "type": "object",
    "required": [
        "schema_version",
        "generated_at",
        "documents",
        "pairs",
        "topic_clusters",
        "amendment_graph",
        "status_scale",
        "status_distribution_pairs",
        "rank_pair_distribution",
        "control_numbers",
    ],
    "additionalProperties": True,
    "properties": {
        "schema_version": {
            "type": "string",
            "pattern": "^v8\\.[0-9]+$",
            "description": "Major v8 with minor revisions (v8.0, v8.1, ...).",
        },
        "generated_at": {
            "type": "string",
            "description": "ISO-like timestamp 'YYYY-MM-DD HH:MM:SSZ'.",
        },
        "documents": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["id", "code", "rank", "title", "type"],
                "additionalProperties": True,
                "properties": {
                    "id":    {"type": "string", "minLength": 1},
                    "code":  {"type": "string"},
                    "rank":  {"type": "integer", "minimum": 1, "maximum": 3},
                    "title": {"type": "string"},
                    "type":  {"type": "string"},
                    "url":   {"type": "string"},
                },
            },
        },
        "pairs": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["id", "left", "right", "v8_status"],
                "additionalProperties": True,
                "properties": {
                    "id":           {"type": "string", "minLength": 1},
                    "left":         {"type": "string", "minLength": 1},
                    "right":        {"type": "string", "minLength": 1},
                    "left_rank":    {"type": ["integer", "null"]},
                    "right_rank":   {"type": ["integer", "null"]},
                    "v8_status":    {"type": "string", "enum": V8_STATUS_ENUM},
                    "events_count": {"type": "integer", "minimum": 0},
                    "topics":       {"type": "array", "items": {"type": "string"}},
                    "rank_pair":    {"type": "string"},
                    "actions":      {"type": "array", "items": {"type": "string"}},
                    "explanations": {"type": "array", "items": {"type": "string"}},
                },
            },
        },
        "topic_clusters": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["id", "label", "needles"],
                "properties": {
                    "id":      {"type": "string"},
                    "label":   {"type": "string"},
                    "needles": {"type": "array", "items": {"type": "string"}},
                },
            },
        },
        "amendment_graph": {
            "type": "object",
            "additionalProperties": {
                "type": "array",
                "items": {"type": "string"},
            },
            "description": "Mapping {newer_doc_id: [older_doc_ids amended/superseded]}.",
        },
        "known_contradictions": {
            "type": "array",
            "items": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 2,
                "maxItems": 2,
            },
        },
        "status_scale": {
            "type": "array",
            "items": {"type": "string", "enum": V8_STATUS_ENUM},
            "minItems": 7,
            "maxItems": 7,
            "uniqueItems": True,
        },
        "status_distribution_pairs": {
            "type": "object",
            "additionalProperties": {"type": "integer", "minimum": 0},
            "description": "Histogram of pair v8_status → count.",
        },
        "rank_pair_distribution": {
            "type": "object",
            "additionalProperties": {"type": "integer", "minimum": 0},
            "description": "Histogram of rank-pair key (e.g. '1↔3') → count.",
        },
        "control_numbers": {
            "type": "object",
            "required": ["documents", "pairs", "events"],
            "properties": {
                "documents": {"type": "integer", "minimum": 0},
                "pairs":     {"type": "integer", "minimum": 0},
                "events":    {"type": "integer", "minimum": 0},
            },
            "additionalProperties": True,
        },
        # Optional v8.1+ extensions
        "corpus": {
            "type": "string",
            "enum": ["generic", "migration_v8"],
            "description": "Corpus identifier; controls which supplementary catalogues are attached.",
        },
        "actions_catalogue": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["id", "category", "severity", "what_is_wrong",
                             "what_to_do", "owner"],
                "properties": {
                    "id":              {"type": "string", "pattern": "^FA-[0-9]{2}$"},
                    "category":        {"type": "string"},
                    "severity":        {"type": "string", "enum": ["low", "medium", "high"]},
                    "where":           {"type": "string"},
                    "what_is_wrong":   {"type": "string"},
                    "why":             {"type": "string"},
                    "what_to_do":      {"type": "string"},
                    "owner":           {"type": "string"},
                    "related_docs":    {"type": "array", "items": {"type": "string"}},
                    "v8_status":       {"type": "string"},
                    "raci":            {
                        "type": "object",
                        "properties": {
                            "R": {"type": "string"},
                            "A": {"type": "string"},
                            "C": {"type": "string"},
                            "I": {"type": "string"},
                        },
                    },
                },
            },
        },
        "raci_matrix": {
            "type": "object",
            "additionalProperties": {
                "type": "object",
                "properties": {
                    "R": {"type": "string"}, "A": {"type": "string"},
                    "C": {"type": "string"}, "I": {"type": "string"},
                },
            },
        },
        "brochure_redgreen": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["id", "before", "after"],
                "additionalProperties": True,
            },
        },
        "klerk_npa_links": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["id", "thesis", "npa_doc"],
                "additionalProperties": True,
            },
        },
        "eaeu_split": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["id", "group", "countries"],
                "additionalProperties": True,
            },
        },
        "amendment_chain": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["id", "chain", "base_act"],
                "additionalProperties": True,
            },
        },
    },
}


def get_bundle_schema() -> dict[str, Any]:
    """Return a fresh dict copy of the v8 bundle JSON schema."""
    import copy
    return copy.deepcopy(BUNDLE_SCHEMA_DICT)


def validate_bundle(bundle: dict[str, Any]) -> list[str]:
    """Validate bundle against the v8 schema; return list of error messages.

    Empty list = bundle is valid. Uses jsonschema if available; falls back
    to a minimal manual check if jsonschema is missing.
    """
    try:
        import jsonschema
    except ImportError:
        return _manual_validate(bundle)

    validator = jsonschema.Draft7Validator(BUNDLE_SCHEMA_DICT)
    errors = []
    for err in sorted(validator.iter_errors(bundle), key=lambda e: list(e.absolute_path)):
        path = "/".join(str(p) for p in err.absolute_path) or "<root>"
        errors.append(f"{path}: {err.message}")
    return errors


def _manual_validate(bundle: dict[str, Any]) -> list[str]:
    """Minimal manual fallback validator (subset of the schema)."""
    errors = []
    for key in BUNDLE_SCHEMA_DICT["required"]:
        if key not in bundle:
            errors.append(f"<root>: missing required key {key!r}")
    if "schema_version" in bundle and not str(bundle["schema_version"]).startswith("v8."):
        errors.append(f"schema_version: must start with 'v8.', got {bundle['schema_version']!r}")
    for p in bundle.get("pairs", []):
        st = p.get("v8_status")
        if st not in V8_STATUS_ENUM:
            errors.append(f"pairs/{p.get('id','?')}: invalid v8_status {st!r}")
    return errors


__all__ = [
    "BUNDLE_SCHEMA_DICT",
    "V8_STATUS_ENUM",
    "get_bundle_schema",
    "validate_bundle",
]
