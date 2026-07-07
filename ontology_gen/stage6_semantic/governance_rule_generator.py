"""Governance rule generator (Category 2.7).

Auto-generates governance rules based on ontology structure and conventions.
"""
from __future__ import annotations

import logging
import re

from ..config import Config
from ..models import Ontology, Concept, Property, Relation, GovernanceRule

logger = logging.getLogger("ontology_gen.governance_rule_generator")


class GovernanceRuleGenerator:
    def __init__(self, config: Config):
        self.config = config

    def generate(
        self,
        concepts: list[Concept],
        properties: list[Property],
        relations: list[Relation],
        domain_config: dict,
    ) -> list[GovernanceRule]:
        rules: list[GovernanceRule] = []

        rules.extend(self._naming_conventions(concepts, properties, relations, domain_config))
        rules.extend(self._completeness_rules(concepts, properties, relations))
        rules.extend(self._consistency_rules(concepts, relations))

        logger.info(f"Governance rules: {len(rules)} generated")
        return rules

    def _naming_conventions(
        self,
        concepts: list[Concept],
        properties: list[Property],
        relations: list[Relation],
        domain_config: dict,
    ) -> list[GovernanceRule]:
        rules = []
        conventions = domain_config.get("governance_conventions", {})

        if conventions.get("concept_naming"):
            rules.append(GovernanceRule(
                name="concept_naming_convention",
                description=f"概念命名规范: {conventions['concept_naming']}",
                rule_type="naming_convention",
                target_scope="all_concepts",
                check_expression=conventions["concept_naming"],
                severity="warning",
            ))

        if conventions.get("property_naming"):
            rules.append(GovernanceRule(
                name="property_naming_convention",
                description=f"属性命名规范: {conventions['property_naming']}",
                rule_type="naming_convention",
                target_scope="all_properties",
                check_expression=conventions["property_naming"],
                severity="warning",
            ))

        # Auto-detect: if all concept names are Chinese
        if concepts:
            chinese_pattern = re.compile(r"^[一-龥\w]+$")
            all_chinese = all(chinese_pattern.match(c.name) for c in concepts)
            if all_chinese and not conventions.get("concept_naming"):
                rules.append(GovernanceRule(
                    name="concept_chinese_naming",
                    description="所有概念名称使用中文",
                    rule_type="naming_convention",
                    target_scope="all_concepts",
                    check_expression="中文名称",
                    severity="info",
                ))

        return rules

    def _completeness_rules(
        self,
        concepts: list[Concept],
        properties: list[Property],
        relations: list[Relation],
    ) -> list[GovernanceRule]:
        rules = []

        # Every concept should have a description
        no_desc = [c for c in concepts if not c.description]
        if no_desc:
            rules.append(GovernanceRule(
                name="concept_description_required",
                description=f"概念缺少描述信息 ({len(no_desc)}/{len(concepts)})",
                rule_type="completeness_check",
                target_scope="all_concepts",
                check_expression="description IS NOT NULL",
                severity="warning",
            ))

        # Every relation should have a description
        no_desc_rel = [r for r in relations if not r.description]
        if no_desc_rel:
            rules.append(GovernanceRule(
                name="relation_description_required",
                description=f"关系缺少描述信息 ({len(no_desc_rel)}/{len(relations)})",
                rule_type="completeness_check",
                target_scope="all_relations",
                check_expression="description IS NOT NULL",
                severity="info",
            ))

        # Every entity type should have at least one property
        concept_ids_with_props = {p.domain_concept_id for p in properties}
        no_props = [c for c in concepts if c.id not in concept_ids_with_props]
        if no_props:
            rules.append(GovernanceRule(
                name="concept_has_properties",
                description=f"概念缺少属性定义 ({len(no_props)}/{len(concepts)})",
                rule_type="completeness_check",
                target_scope="all_concepts",
                check_expression="property_count >= 1",
                severity="warning",
            ))

        return rules

    def _consistency_rules(
        self,
        concepts: list[Concept],
        relations: list[Relation],
    ) -> list[GovernanceRule]:
        rules = []

        # Check for orphan concepts (no relations)
        concept_ids_in_rels = set()
        for r in relations:
            concept_ids_in_rels.add(r.domain_concept_id)
            concept_ids_in_rels.add(r.range_concept_id)

        orphans = [c for c in concepts if c.id not in concept_ids_in_rels]
        if orphans:
            rules.append(GovernanceRule(
                name="no_orphan_concepts",
                description=f"存在孤立概念（无关系） ({len(orphans)}/{len(concepts)})",
                rule_type="consistency_axiom",
                target_scope="all_concepts",
                check_expression="relation_count >= 1",
                severity="info",
            ))

        return rules
