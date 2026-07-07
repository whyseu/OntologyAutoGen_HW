"""Consistency checking for the final ontology.

Checks:
1. Taxonomy graph has no cycles
2. subClassOf transitivity consistency
3. domain/range consistency with actual usage
4. DisjointWith violation detection
5. Rule chain cycle detection
6. SWRL variable binding completeness
"""
from __future__ import annotations

import logging
from typing import Optional

from ..models import Ontology, Axiom, AxiomType, Rule
from ..stage3_taxonomy.cycle_detector import CycleDetector

logger = logging.getLogger("ontology_gen.consistency_checker")


class ConsistencyChecker:
    """Multi-dimensional consistency checking for ontology."""

    def __init__(self):
        self.cycle_detector = CycleDetector()

    def check(self, ontology: Ontology) -> dict:
        """
        Run all consistency checks on the ontology.

        Returns:
            {
                "is_consistent": bool,
                "violations": list[dict],  # Critical issues
                "warnings": list[dict],    # Non-critical issues
                "checks_run": list[str],   # Names of checks performed
            }
        """
        violations = []
        warnings = []
        checks_run = []

        # Check 1: Taxonomy cycle detection
        checks_run.append("taxonomy_cycle")
        cycle_result = self._check_taxonomy_cycles(ontology)
        if cycle_result:
            violations.extend(cycle_result)

        # Check 2: subClassOf transitivity
        checks_run.append("subclass_transitivity")
        trans_result = self._check_subclass_transitivity(ontology)
        warnings.extend(trans_result)

        # Check 3: domain/range consistency
        checks_run.append("domain_range_consistency")
        dr_result = self._check_domain_range_consistency(ontology)
        warnings.extend(dr_result)

        # Check 4: DisjointWith violations
        checks_run.append("disjoint_violations")
        disjoint_result = self._check_disjoint_violations(ontology)
        violations.extend(disjoint_result)

        # Check 5: Rule chain cycles
        checks_run.append("rule_chain_cycles")
        rule_result = self._check_rule_chain_cycles(ontology.rules)
        warnings.extend(rule_result)

        # Check 6: SWRL variable binding
        checks_run.append("swrl_variable_binding")
        swrl_result = self._check_swrl_variables(ontology.rules)
        violations.extend(swrl_result)

        is_consistent = len(violations) == 0

        logger.info(
            f"Consistency check: {'PASS' if is_consistent else 'FAIL'} - "
            f"{len(violations)} violations, {len(warnings)} warnings"
        )

        return {
            "is_consistent": is_consistent,
            "violations": violations,
            "warnings": warnings,
            "checks_run": checks_run,
        }

    def _check_taxonomy_cycles(self, ontology: Ontology) -> list[dict]:
        """Check 1: Detect cycles in taxonomy graph."""
        violations = []
        edges = []
        for node in ontology.taxonomy.nodes.values():
            if node.parent_id:
                edges.append((node.concept_id, node.parent_id))

        result = self.cycle_detector.detect(edges)
        if result["has_cycle"]:
            for cycle in result["cycles"]:
                violations.append({
                    "check": "taxonomy_cycle",
                    "severity": "critical",
                    "message": f"Cycle detected in taxonomy: {' -> '.join(cycle)}",
                    "cycle": cycle,
                })

        return violations

    @staticmethod
    def _check_subclass_transitivity(ontology: Ontology) -> list[dict]:
        """Check 2: Verify subClassOf transitivity consistency."""
        warnings = []
        # Get all subClassOf axioms
        subclass_axioms = [a for a in ontology.axioms if a.axiom_type == AxiomType.SUBCLASS_OF]

        # Build parent map
        parent_map = {}
        for axiom in subclass_axioms:
            parent_map.setdefault(axiom.subject, []).append(axiom.obj)

        # Check for conflicting parents (A -> B and A -> C where B and C are not related)
        for child, parents in parent_map.items():
            if len(parents) > 1:
                # Check if all parents are in a chain (transitive)
                # If not, it's a warning (multiple inheritance might be intentional)
                root_parents = [p for p in parents if p not in parent_map or all(pp not in parents for pp in parent_map.get(p, []))]
                if len(root_parents) > 1:
                    warnings.append({
                        "check": "subclass_transitivity",
                        "severity": "warning",
                        "message": f"Concept '{child}' has multiple unrelated parents: {parents}",
                    })

        return warnings

    @staticmethod
    def _check_domain_range_consistency(ontology: Ontology) -> list[dict]:
        """Check 3: Verify domain/range axioms are consistent with relations."""
        warnings = []
        concept_names = {c.id for c in ontology.entity_types}
        concept_name_map = {c.name: c.id for c in ontology.entity_types}

        for axiom in ontology.axioms:
            if axiom.axiom_type == AxiomType.DOMAIN:
                # Check if subject (relation) exists
                rel = next((r for r in ontology.relations if r.name == axiom.subject), None)
                if rel:
                    # Check if domain matches
                    expected_domain = axiom.obj
                    actual_domain_id = rel.domain_concept_id
                    actual_domain_concept = next((c for c in ontology.entity_types if c.id == actual_domain_id), None)
                    if actual_domain_concept and actual_domain_concept.name != expected_domain:
                        warnings.append({
                            "check": "domain_range_consistency",
                            "severity": "warning",
                            "message": f"Domain axiom says '{axiom.subject}' domain is '{expected_domain}', "
                                       f"but relation defines domain as '{actual_domain_concept.name}'",
                        })

        return warnings

    @staticmethod
    def _check_disjoint_violations(ontology: Ontology) -> list[dict]:
        """Check 4: Detect disjointWith violations in instance data."""
        violations = []
        disjoint_axioms = [a for a in ontology.axioms if a.axiom_type == AxiomType.DISJOINT_WITH]

        for axiom in disjoint_axioms:
            # Check if any concept is both a subclass of both disjoint classes
            subclass_axioms = [a for a in ontology.axioms if a.axiom_type == AxiomType.SUBCLASS_OF]
            children_a = {a.subject for a in subclass_axioms if a.obj == axiom.subject}
            children_b = {a.subject for a in subclass_axioms if a.obj == axiom.obj}

            overlap = children_a & children_b
            if overlap:
                violations.append({
                    "check": "disjoint_violations",
                    "severity": "critical",
                    "message": f"Concepts {overlap} are subclasses of both '{axiom.subject}' and '{axiom.obj}' "
                               f"which are declared disjoint",
                })

        return violations

    @staticmethod
    def _check_rule_chain_cycles(rules: list[Rule]) -> list[dict]:
        """Check 5: Detect cycles in rule chains (Rule A's head = Rule B's body)."""
        warnings = []

        # Build a graph: if Rule A's head predicate appears in Rule B's body
        for i, rule_a in enumerate(rules):
            head_predicates = {atom.predicate for atom in rule_a.head}
            for j, rule_b in enumerate(rules):
                if i == j:
                    continue
                body_predicates = {atom.predicate for atom in rule_b.body}
                overlap = head_predicates & body_predicates
                if overlap:
                    # Check if the reverse is also true (cycle)
                    rule_b_head = {atom.predicate for atom in rule_b.head}
                    rule_a_body = {atom.predicate for atom in rule_a.body}
                    if rule_b_head & rule_a_body:
                        warnings.append({
                            "check": "rule_chain_cycles",
                            "severity": "warning",
                            "message": f"Rule chain cycle: '{rule_a.name}' and '{rule_b.name}' "
                                       f"reference each other's conclusions",
                        })

        return warnings

    @staticmethod
    def _check_swrl_variables(rules: list[Rule]) -> list[dict]:
        """Check 6: SWRL variable binding completeness."""
        violations = []

        for rule in rules:
            if not rule.body or not rule.head:
                violations.append({
                    "check": "swrl_variable_binding",
                    "severity": "critical",
                    "message": f"Rule '{rule.name}' has empty body or head",
                })
                continue

            body_vars = set()
            for atom in rule.body:
                body_vars.update(v for v in atom.variables if v.startswith("?"))

            head_vars = set()
            for atom in rule.head:
                head_vars.update(v for v in atom.variables if v.startswith("?"))

            unbound = head_vars - body_vars
            if unbound:
                violations.append({
                    "check": "swrl_variable_binding",
                    "severity": "critical",
                    "message": f"Rule '{rule.name}': head variables {unbound} not bound in body",
                })

        return violations
