"""Ontology builder: assembles the final Ontology object from pipeline results.

Collects all intermediate outputs from the 5 stages and assembles them
into a validated Ontology object ready for JSON export.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from ..models import (
    Ontology, Concept, Property, Relation,
    Taxonomy, Axiom, Rule,
    SemanticAnnotation, GovernanceRule, GlossaryTerm,
    ExternalMapping, TriggerRule, AtomicOperation,
    ServiceComposition, PermissionSubject, PermissionRule,
    QueryPattern,
)
from .json_schema import validate_ontology_dict

logger = logging.getLogger("ontology_gen.ontology_builder")


class OntologyBuilder:
    """Assemble the final Ontology from pipeline stage outputs."""

    def __init__(self, domain: str = "unknown"):
        self.domain = domain
        self.entity_types: list[Concept] = []
        self.properties: list[Property] = []
        self.relations: list[Relation] = []
        self.taxonomy: Taxonomy = Taxonomy()
        self.axioms: list[Axiom] = []
        self.rules: list[Rule] = []
        self.semantic_annotations: list[SemanticAnnotation] = []
        self.governance_rules: list[GovernanceRule] = []
        self.glossary: list[GlossaryTerm] = []
        self.external_mappings: list[ExternalMapping] = []
        self.trigger_rules: list[TriggerRule] = []
        self.operations: list[AtomicOperation] = []
        self.service_compositions: list[ServiceComposition] = []
        self.permission_subjects: list[PermissionSubject] = []
        self.permission_rules: list[PermissionRule] = []
        self.query_patterns: list[QueryPattern] = []
        self.metadata: dict = {
            "domain": domain,
            "created_at": datetime.now().isoformat(),
            "stages_executed": [],
            "stats": {},
        }

    def set_concepts(self, concepts: list[Concept]) -> None:
        """Set entity types from Stage 2 output."""
        self.entity_types = [c for c in concepts if c.is_entity_type]
        self.metadata["stages_executed"].append("stage2_concepts")
        self.metadata["stats"]["entity_type_count"] = len(self.entity_types)
        logger.info(f"Ontology builder: {len(self.entity_types)} entity types")

    def set_properties(self, properties: list[Property]) -> None:
        """Set properties from Stage 4 output."""
        self.properties = properties
        self.metadata["stages_executed"].append("stage4_properties")
        self.metadata["stats"]["property_count"] = len(properties)
        logger.info(f"Ontology builder: {len(properties)} properties")

    def set_relations(self, relations: list[Relation]) -> None:
        """Set relations from Stage 4 output."""
        self.relations = relations
        self.metadata["stages_executed"].append("stage4_relations")
        self.metadata["stats"]["relation_count"] = len(relations)
        logger.info(f"Ontology builder: {len(relations)} relations")

    def set_taxonomy(self, taxonomy: Taxonomy) -> None:
        """Set taxonomy from Stage 3 output."""
        self.taxonomy = taxonomy
        self.metadata["stages_executed"].append("stage3_taxonomy")
        self.metadata["stats"]["taxonomy_node_count"] = len(taxonomy.nodes)
        self.metadata["stats"]["taxonomy_root_count"] = len(taxonomy.root_ids)
        logger.info(f"Ontology builder: {len(taxonomy.nodes)} taxonomy nodes, "
                     f"{len(taxonomy.root_ids)} roots")

    def set_axioms(self, axioms: list[Axiom]) -> None:
        """Set axioms from Stage 5 output."""
        self.axioms = axioms
        self.metadata["stages_executed"].append("stage5_axioms")
        self.metadata["stats"]["axiom_count"] = len(axioms)
        logger.info(f"Ontology builder: {len(axioms)} axioms")

    def set_rules(self, rules: list[Rule]) -> None:
        """Set SWRL rules from Stage 5 output."""
        self.rules = rules
        self.metadata["stages_executed"].append("stage5_rules")
        self.metadata["stats"]["rule_count"] = len(rules)
        logger.info(f"Ontology builder: {len(rules)} rules")

    def set_semantic_annotations(self, annotations: list[SemanticAnnotation]) -> None:
        self.semantic_annotations = annotations
        self.metadata["stages_executed"].append("stage6_annotations")
        self.metadata["stats"]["annotation_count"] = len(annotations)
        logger.info(f"Ontology builder: {len(annotations)} semantic annotations")

    def set_governance_rules(self, rules: list[GovernanceRule]) -> None:
        self.governance_rules = rules
        self.metadata["stages_executed"].append("stage6_governance")
        self.metadata["stats"]["governance_rule_count"] = len(rules)
        logger.info(f"Ontology builder: {len(rules)} governance rules")

    def set_glossary(self, terms: list[GlossaryTerm]) -> None:
        self.glossary = terms
        self.metadata["stages_executed"].append("stage6_glossary")
        self.metadata["stats"]["glossary_term_count"] = len(terms)
        logger.info(f"Ontology builder: {len(terms)} glossary terms")

    def set_external_mappings(self, mappings: list[ExternalMapping]) -> None:
        self.external_mappings = mappings
        self.metadata["stages_executed"].append("stage6_mappings")
        self.metadata["stats"]["external_mapping_count"] = len(mappings)
        logger.info(f"Ontology builder: {len(mappings)} external mappings")

    def set_trigger_rules(self, rules: list[TriggerRule]) -> None:
        self.trigger_rules = rules
        self.metadata["stages_executed"].append("stage6_triggers")
        self.metadata["stats"]["trigger_rule_count"] = len(rules)
        logger.info(f"Ontology builder: {len(rules)} trigger rules")

    def set_operations(self, operations: list[AtomicOperation]) -> None:
        self.operations = operations
        self.metadata["stages_executed"].append("stage7_operations")
        self.metadata["stats"]["operation_count"] = len(operations)
        logger.info(f"Ontology builder: {len(operations)} operations")

    def set_service_compositions(self, compositions: list[ServiceComposition]) -> None:
        self.service_compositions = compositions
        self.metadata["stages_executed"].append("stage7_compositions")
        self.metadata["stats"]["service_composition_count"] = len(compositions)
        logger.info(f"Ontology builder: {len(compositions)} service compositions")

    def set_permission_subjects(self, subjects: list[PermissionSubject]) -> None:
        self.permission_subjects = subjects
        self.metadata["stages_executed"].append("stage7_subjects")
        self.metadata["stats"]["permission_subject_count"] = len(subjects)
        logger.info(f"Ontology builder: {len(subjects)} permission subjects")

    def set_permission_rules(self, rules: list[PermissionRule]) -> None:
        self.permission_rules = rules
        self.metadata["stages_executed"].append("stage7_permissions")
        self.metadata["stats"]["permission_rule_count"] = len(rules)
        logger.info(f"Ontology builder: {len(rules)} permission rules")

    def set_query_patterns(self, patterns: list[QueryPattern]) -> None:
        self.query_patterns = patterns
        self.metadata["stages_executed"].append("stage7_queries")
        self.metadata["stats"]["query_pattern_count"] = len(patterns)
        logger.info(f"Ontology builder: {len(patterns)} query patterns")

    def add_concepts(self, concepts: list[Concept]) -> None:
        """Add additional concepts (e.g., reified intermediate concepts)."""
        existing_ids = {c.id for c in self.entity_types}
        for c in concepts:
            if c.id not in existing_ids:
                self.entity_types.append(c)
                existing_ids.add(c.id)
        self.metadata["stats"]["entity_type_count"] = len(self.entity_types)

    def build(self) -> Ontology:
        """
        Assemble the final Ontology object.

        Performs cross-reference validation:
        - Property domains reference valid concept IDs
        - Relation domain/range reference valid concept IDs
        - Taxonomy nodes reference valid concept IDs
        - Axiom subjects/objects reference valid elements

        Returns:
            Ontology object
        """
        ontology = Ontology(
            version="2.0",
            domain=self.domain,
            entity_types=self.entity_types,
            properties=self.properties,
            relations=self.relations,
            taxonomy=self.taxonomy,
            axioms=self.axioms,
            rules=self.rules,
            semantic_annotations=self.semantic_annotations,
            governance_rules=self.governance_rules,
            glossary=self.glossary,
            external_mappings=self.external_mappings,
            trigger_rules=self.trigger_rules,
            operations=self.operations,
            service_compositions=self.service_compositions,
            permission_subjects=self.permission_subjects,
            permission_rules=self.permission_rules,
            query_patterns=self.query_patterns,
            metadata=self._finalize_metadata(),
        )

        # Run built-in validation
        errors = ontology.validate()
        if errors:
            logger.warning(f"Ontology validation found {len(errors)} issues:")
            for err in errors:
                logger.warning(f"  - {err}")
        else:
            logger.info("Ontology validation: PASS (no structural errors)")

        # Run JSON Schema validation
        ontology_dict = ontology.to_dict()
        schema_errors = validate_ontology_dict(ontology_dict)
        if schema_errors:
            logger.warning(f"JSON Schema validation found {len(schema_errors)} issues:")
            for err in schema_errors:
                logger.warning(f"  - {err}")
        else:
            logger.info("JSON Schema validation: PASS")

        return ontology

    def _finalize_metadata(self) -> dict:
        """Finalize metadata with computed stats."""
        # Count by source
        source_counts = {}
        for c in self.entity_types:
            src = c.source.value if hasattr(c.source, "value") else str(c.source)
            source_counts[src] = source_counts.get(src, 0) + 1

        # Count axioms by risk level
        risk_counts = {}
        for a in self.axioms:
            risk = a.risk_level.value if hasattr(a.risk_level, "value") else str(a.risk_level)
            risk_counts[risk] = risk_counts.get(risk, 0) + 1

        # Count relations by cardinality
        cardinality_counts = {}
        for r in self.relations:
            cardinality_counts[r.cardinality] = cardinality_counts.get(r.cardinality, 0) + 1

        self.metadata["stats"].update({
            "source_distribution": source_counts,
            "axiom_risk_distribution": risk_counts,
            "relation_cardinality_distribution": cardinality_counts,
            "validated_axiom_count": sum(1 for a in self.axioms if a.validated),
            "validated_rule_count": sum(1 for r in self.rules if r.validated),
        })

        if self.trigger_rules:
            event_type_counts = {}
            for tr in self.trigger_rules:
                event_type_counts[tr.event_type] = event_type_counts.get(tr.event_type, 0) + 1
            self.metadata["stats"]["trigger_event_type_distribution"] = event_type_counts

        return self.metadata
