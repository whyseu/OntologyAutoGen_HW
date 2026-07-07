"""JSON Schema definition for ontology output.

Defines the JSON Schema that validates the final ontology output,
ensuring structural integrity for downstream consumers (Neo4j import, etc.).
"""
from __future__ import annotations

import json
from typing import Any

# ============================================================
# JSON Schema for the complete ontology output
# ============================================================

ONTOLOGY_JSON_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "Ontology",
    "description": "Auto-generated ontology from heterogeneous data sources",
    "type": "object",
    "required": ["version", "domain", "entity_types", "properties",
                 "relations", "taxonomy", "axioms", "rules", "metadata"],
    "properties": {
        "version": {
            "type": "string",
            "description": "Ontology version string",
        },
        "domain": {
            "type": "string",
            "description": "Business domain name",
        },
        "entity_types": {
            "type": "array",
            "items": {"$ref": "#/$defs/Concept"},
        },
        "properties": {
            "type": "array",
            "items": {"$ref": "#/$defs/Property"},
        },
        "relations": {
            "type": "array",
            "items": {"$ref": "#/$defs/Relation"},
        },
        "taxonomy": {
            "type": "object",
            "required": ["nodes", "root_ids"],
            "properties": {
                "nodes": {
                    "type": "object",
                    "additionalProperties": {"$ref": "#/$defs/TaxonomyNode"},
                },
                "root_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                },
            },
        },
        "axioms": {
            "type": "array",
            "items": {"$ref": "#/$defs/Axiom"},
        },
        "rules": {
            "type": "array",
            "items": {"$ref": "#/$defs/Rule"},
        },
        "metadata": {
            "type": "object",
            "description": "Pipeline execution metadata",
        },
        "semantic_annotations": {
            "type": "array",
            "items": {"$ref": "#/$defs/SemanticAnnotation"},
        },
        "governance_rules": {
            "type": "array",
            "items": {"$ref": "#/$defs/GovernanceRule"},
        },
        "glossary": {
            "type": "array",
            "items": {"$ref": "#/$defs/GlossaryTerm"},
        },
        "external_mappings": {
            "type": "array",
            "items": {"$ref": "#/$defs/ExternalMapping"},
        },
        "trigger_rules": {
            "type": "array",
            "items": {"$ref": "#/$defs/TriggerRule"},
        },
        "operations": {
            "type": "array",
            "items": {"$ref": "#/$defs/AtomicOperation"},
        },
        "service_compositions": {
            "type": "array",
            "items": {"$ref": "#/$defs/ServiceComposition"},
        },
        "permission_subjects": {
            "type": "array",
            "items": {"$ref": "#/$defs/PermissionSubject"},
        },
        "permission_rules": {
            "type": "array",
            "items": {"$ref": "#/$defs/PermissionRule"},
        },
        "query_patterns": {
            "type": "array",
            "items": {"$ref": "#/$defs/QueryPattern"},
        },
    },
    "$defs": {
        "Concept": {
            "type": "object",
            "required": ["name", "id"],
            "properties": {
                "name": {"type": "string"},
                "id": {"type": "string"},
                "name_en": {"type": ["string", "null"]},
                "aliases": {"type": "array", "items": {"type": "string"}},
                "description": {"type": ["string", "null"]},
                "source": {"type": "string", "enum": ["rdb", "text", "dialogue"]},
                "source_ref": {"type": ["string", "null"]},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                "properties": {"type": "array", "items": {"type": "string"}},
                "is_entity_type": {"type": "boolean"},
                "instance_count": {"type": "integer", "minimum": 0},
                "layer": {"type": "string", "enum": ["data", "logic", "application"]},
                "identity_spec": {"type": ["string", "null"]},
            },
        },
        "Property": {
            "type": "object",
            "required": ["name", "domain_concept_id", "id"],
            "properties": {
                "name": {"type": "string"},
                "domain_concept_id": {"type": "string"},
                "id": {"type": "string"},
                "name_cn": {"type": ["string", "null"]},
                "value_type": {
                    "type": "string",
                    "enum": ["int", "float", "date", "string", "bool", "enum"],
                },
                "enum_values": {"type": "array", "items": {"type": "string"}},
                "description": {"type": ["string", "null"]},
                "source": {"type": "string", "enum": ["rdb", "text", "dialogue"]},
                "source_ref": {"type": ["string", "null"]},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                "nullable": {"type": "boolean"},
                "null_rate": {"type": "number", "minimum": 0, "maximum": 1},
                "validation_regex": {"type": ["string", "null"]},
                "min_value": {"type": ["number", "null"]},
                "max_value": {"type": ["number", "null"]},
                "max_length": {"type": ["integer", "null"]},
                "format_pattern": {"type": ["string", "null"]},
                "is_derived": {"type": "boolean"},
                "derivation_formula": {"type": ["string", "null"]},
                "derivation_type": {"type": ["string", "null"]},
                "derivation_sources": {"type": "array", "items": {"type": "string"}},
                "usage_scope": {"type": "array", "items": {"type": "string"}},
            },
        },
        "Relation": {
            "type": "object",
            "required": ["name", "domain_concept_id", "range_concept_id", "id"],
            "properties": {
                "name": {"type": "string"},
                "domain_concept_id": {"type": "string"},
                "range_concept_id": {"type": "string"},
                "id": {"type": "string"},
                "name_cn": {"type": ["string", "null"]},
                "relation_type": {
                    "type": "string",
                    "enum": ["is-a", "part-of", "attribute-of", "related-to", "business"],
                },
                "inverse_relation_id": {"type": ["string", "null"]},
                "aliases": {"type": "array", "items": {"type": "string"}},
                "description": {"type": ["string", "null"]},
                "source": {"type": "string", "enum": ["rdb", "text", "dialogue"]},
                "source_ref": {"type": ["string", "null"]},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                "cardinality": {
                    "type": "string",
                    "enum": ["1:1", "1:N", "N:M"],
                },
                "is_reified": {"type": "boolean"},
                "reified_concept_id": {"type": ["string", "null"]},
            },
        },
        "TaxonomyNode": {
            "type": "object",
            "required": ["concept_id"],
            "properties": {
                "concept_id": {"type": "string"},
                "parent_id": {"type": ["string", "null"]},
                "children_ids": {"type": "array", "items": {"type": "string"}},
                "depth": {"type": "integer", "minimum": 0},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                "reason": {"type": ["string", "null"]},
            },
        },
        "Axiom": {
            "type": "object",
            "required": ["axiom_type", "subject", "obj", "id"],
            "properties": {
                "axiom_type": {
                    "type": "string",
                    "enum": ["subClassOf", "equivalentClass", "disjointWith",
                             "domain", "range", "inverseOf", "TransitiveProperty"],
                },
                "subject": {"type": "string"},
                "obj": {"type": "string"},
                "id": {"type": "string"},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                "risk_level": {"type": "string", "enum": ["low", "medium", "high"]},
                "source": {"type": "string"},
                "rationale": {"type": ["string", "null"]},
                "validated": {"type": "boolean"},
            },
        },
        "Rule": {
            "type": "object",
            "required": ["name", "description", "id"],
            "properties": {
                "name": {"type": "string"},
                "description": {"type": "string"},
                "body": {"type": "array", "items": {"$ref": "#/$defs/RuleAtom"}},
                "head": {"type": "array", "items": {"$ref": "#/$defs/RuleAtom"}},
                "id": {"type": "string"},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                "validated": {"type": "boolean"},
                "nl_source": {"type": ["string", "null"]},
            },
        },
        "RuleAtom": {
            "type": "object",
            "required": ["atom_type", "predicate"],
            "properties": {
                "atom_type": {
                    "type": "string",
                    "enum": ["class_atom", "property_atom", "builtin_atom", "same_as_atom"],
                },
                "predicate": {"type": "string"},
                "variables": {"type": "array", "items": {"type": "string"}},
            },
        },
        "SemanticAnnotation": {
            "type": "object",
            "required": ["target_id", "target_type", "annotation_key", "annotation_value", "id"],
            "properties": {
                "target_id": {"type": "string"},
                "target_type": {"type": "string", "enum": ["concept", "property", "relation"]},
                "annotation_key": {"type": "string"},
                "annotation_value": {"type": "string"},
                "id": {"type": "string"},
                "author": {"type": ["string", "null"]},
                "created_at": {"type": ["string", "null"]},
            },
        },
        "GovernanceRule": {
            "type": "object",
            "required": ["name", "description", "rule_type", "target_scope", "check_expression", "id"],
            "properties": {
                "name": {"type": "string"},
                "description": {"type": "string"},
                "rule_type": {"type": "string"},
                "target_scope": {"type": "string"},
                "check_expression": {"type": "string"},
                "severity": {"type": "string", "enum": ["error", "warning", "info"]},
                "id": {"type": "string"},
                "enabled": {"type": "boolean"},
                "auto_fix": {"type": "boolean"},
            },
        },
        "GlossaryTerm": {
            "type": "object",
            "required": ["standard_term", "id"],
            "properties": {
                "standard_term": {"type": "string"},
                "aliases": {"type": "array", "items": {"type": "string"}},
                "definition": {"type": "string"},
                "category": {"type": "string"},
                "id": {"type": "string"},
                "domain": {"type": "string"},
                "owner": {"type": ["string", "null"]},
                "status": {"type": "string", "enum": ["active", "deprecated", "draft"]},
            },
        },
        "ExternalMapping": {
            "type": "object",
            "required": ["internal_term_id", "external_system", "external_term", "id"],
            "properties": {
                "internal_term_id": {"type": "string"},
                "external_system": {"type": "string"},
                "external_term": {"type": "string"},
                "external_code": {"type": ["string", "null"]},
                "mapping_type": {"type": "string", "enum": ["equivalent", "broader", "narrower", "related"]},
                "id": {"type": "string"},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                "bidirectional": {"type": "boolean"},
            },
        },
        "TriggerRule": {
            "type": "object",
            "required": ["name", "description", "event_type", "event_source", "event_detail", "condition_expression", "id"],
            "properties": {
                "name": {"type": "string"},
                "description": {"type": "string"},
                "event_type": {"type": "string", "enum": ["data_change", "time_based", "status_transition", "external_event"]},
                "event_source": {"type": "string"},
                "event_detail": {"type": "string"},
                "condition_expression": {"type": "string"},
                "condition_concepts": {"type": "array", "items": {"type": "string"}},
                "action_type": {"type": "string"},
                "action_detail": {"type": "string"},
                "action_target": {"type": "string"},
                "id": {"type": "string"},
                "priority": {"type": "integer"},
                "enabled": {"type": "boolean"},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                "source": {"type": "string"},
                "nl_source": {"type": ["string", "null"]},
            },
        },
        "AtomicOperation": {
            "type": "object",
            "required": ["name", "description", "id"],
            "properties": {
                "name": {"type": "string"},
                "description": {"type": "string"},
                "parent_operation_id": {"type": ["string", "null"]},
                "inputs": {"type": "array", "items": {"type": "object"}},
                "outputs": {"type": "array", "items": {"type": "object"}},
                "preconditions": {"type": "array", "items": {"type": "string"}},
                "postconditions": {"type": "array", "items": {"type": "string"}},
                "id": {"type": "string"},
                "actor_concept_id": {"type": ["string", "null"]},
                "target_concept_id": {"type": ["string", "null"]},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                "source": {"type": "string"},
            },
        },
        "ServiceComposition": {
            "type": "object",
            "required": ["name", "description", "composition_type", "id"],
            "properties": {
                "name": {"type": "string"},
                "description": {"type": "string"},
                "composition_type": {"type": "string", "enum": ["sequential", "parallel", "conditional", "loop", "exception_handling"]},
                "steps": {"type": "array", "items": {"type": "object"}},
                "exception_handlers": {"type": "array", "items": {"type": "object"}},
                "timeout_seconds": {"type": ["integer", "null"]},
                "retry_policy": {"type": ["object", "null"]},
                "id": {"type": "string"},
                "involved_concepts": {"type": "array", "items": {"type": "string"}},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                "source": {"type": "string"},
            },
        },
        "PermissionSubject": {
            "type": "object",
            "required": ["name", "subject_type", "id"],
            "properties": {
                "name": {"type": "string"},
                "subject_type": {"type": "string", "enum": ["role", "user_group", "individual", "system"]},
                "id": {"type": "string"},
                "parent_subject_id": {"type": ["string", "null"]},
                "description": {"type": ["string", "null"]},
            },
        },
        "PermissionRule": {
            "type": "object",
            "required": ["name", "description", "subject_id", "object_concept_id", "id"],
            "properties": {
                "name": {"type": "string"},
                "description": {"type": "string"},
                "subject_id": {"type": "string"},
                "object_concept_id": {"type": "string"},
                "object_scope": {"type": "string"},
                "actions": {"type": "array", "items": {"type": "string"}},
                "effect": {"type": "string", "enum": ["allow", "deny"]},
                "condition": {"type": ["string", "null"]},
                "id": {"type": "string"},
                "priority": {"type": "integer"},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                "source": {"type": "string"},
            },
        },
        "QueryPattern": {
            "type": "object",
            "required": ["name", "description", "pattern_type", "id"],
            "properties": {
                "name": {"type": "string"},
                "description": {"type": "string"},
                "pattern_type": {"type": "string", "enum": ["entity_lookup", "filtered_query", "join_query", "aggregation", "cross_source", "template", "data_gap", "update", "delete"]},
                "target_concepts": {"type": "array", "items": {"type": "string"}},
                "filter_conditions": {"type": "array", "items": {"type": "string"}},
                "join_paths": {"type": "array", "items": {"type": "string"}},
                "aggregation_functions": {"type": "array", "items": {"type": "string"}},
                "suggested_indexes": {"type": "array", "items": {"type": "string"}},
                "cache_strategy": {"type": ["string", "null"]},
                "data_gap_fields": {"type": "array", "items": {"type": "string"}},
                "compensation_strategy": {"type": ["string", "null"]},
                "sql_template": {"type": ["string", "null"]},
                "parameters": {"type": "array", "items": {"type": "object"}},
                "id": {"type": "string"},
                "frequency": {"type": "integer", "minimum": 0},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                "source": {"type": "string"},
            },
        },
    },
}


def validate_ontology_dict(ontology_dict: dict) -> list[str]:
    """
    Validate an ontology dict against the JSON Schema (lightweight check).

    Uses jsonschema if available; otherwise does basic structural checks.

    Args:
        ontology_dict: The ontology as a dict (from Ontology.to_dict())

    Returns:
        List of error messages (empty = valid)
    """
    errors: list[str] = []

    # Try using jsonschema library
    try:
        import jsonschema
        validator = jsonschema.Draft202012Validator(ONTOLOGY_JSON_SCHEMA)
        for error in validator.iter_errors(ontology_dict):
            errors.append(f"{error.message} (at: {list(error.absolute_path)})")
        return errors
    except ImportError:
        pass

    # Fallback: basic structural checks
    required_keys = ["version", "domain", "entity_types", "properties",
                     "relations", "taxonomy", "axioms", "rules", "metadata"]
    for key in required_keys:
        if key not in ontology_dict:
            errors.append(f"Missing required key: '{key}'")

    # Check entity_types
    for i, et in enumerate(ontology_dict.get("entity_types", [])):
        if "name" not in et:
            errors.append(f"entity_types[{i}] missing 'name'")
        if "id" not in et:
            errors.append(f"entity_types[{i}] missing 'id'")

    # Check properties
    for i, prop in enumerate(ontology_dict.get("properties", [])):
        if "name" not in prop:
            errors.append(f"properties[{i}] missing 'name'")
        if "domain_concept_id" not in prop:
            errors.append(f"properties[{i}] missing 'domain_concept_id'")

    # Check relations
    for i, rel in enumerate(ontology_dict.get("relations", [])):
        if "name" not in rel:
            errors.append(f"relations[{i}] missing 'name'")
        if "domain_concept_id" not in rel:
            errors.append(f"relations[{i}] missing 'domain_concept_id'")
        if "range_concept_id" not in rel:
            errors.append(f"relations[{i}] missing 'range_concept_id'")

    return errors


def get_schema() -> dict[str, Any]:
    """Return the JSON Schema dict."""
    return ONTOLOGY_JSON_SCHEMA


def save_schema(path: str) -> None:
    """Save the JSON Schema to a file."""
    from ..utils import save_json
    save_json(ONTOLOGY_JSON_SCHEMA, path)
