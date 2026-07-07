"""Algorithm 4.2: Property vs Relation decision tree.

Decides whether a value should be represented as a property (literal)
or a relation (entity reference) in the ontology.
"""
from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger("ontology_gen.prop_rel_decider")


class PropertyRelationDecider:
    """Decision tree for property vs relation classification."""

    def __init__(self, reasoning_engine: str = "neo4j"):
        """
        Args:
            reasoning_engine: "neo4j" or "owl" — affects Q3 decision
        """
        self.reasoning_engine = reasoning_engine

    def decide(
        self,
        value: any,
        value_type: str,
        has_independent_attrs: bool = False,
        needs_reasoning: bool = False,
    ) -> tuple[str, str]:
        """
        Apply decision tree to classify value as property or relation.

        Q1: Is the value a literal (int/date/string)?
            Yes -> property
            No -> Q2

        Q2: Does the value need independent attributes?
            Yes -> relation (value is an entity node)
            No -> property

        Q3 (special): Does the value participate in reasoning?
            Neo4j Cypher -> property (Cypher supports property comparison)
            OWL reasoner -> relation (OWL axioms work better with object properties)

        Args:
            value: The actual value
            value_type: Type of the value ("int", "float", "date", "string", "entity", "enum")
            has_independent_attrs: Whether the value has its own properties
            needs_reasoning: Whether this value participates in reasoning rules

        Returns:
            ("property" | "relation", reason)
        """
        # Q1: Literal check
        if self._is_literal(value_type):
            # But check Q3: if reasoning is needed
            if needs_reasoning and self.reasoning_engine == "owl":
                return ("relation", f"Value type '{value_type}' is literal, but OWL reasoning requires object property")
            return ("property", f"Value type '{value_type}' is a literal -> property")

        # Q2: Independent attributes check
        if has_independent_attrs:
            return ("relation", "Value has independent attributes -> entity node (relation)")

        # Q3: Reasoning check
        if needs_reasoning:
            if self.reasoning_engine == "neo4j":
                return ("property", "Neo4j Cypher supports property comparison for reasoning")
            elif self.reasoning_engine == "owl":
                return ("relation", "OWL reasoner works better with object properties for reasoning")

        # Default: FK and reference types are always relations (entity references)
        # "entity" type without independent attrs -> property (Q2 "No" branch)
        if value_type in ("reference", "fk"):
            return ("relation", f"Value type '{value_type}' indicates entity reference -> relation")

        return ("property", f"Default: value type '{value_type}' treated as property")

    @staticmethod
    def _is_literal(value_type: str) -> bool:
        """Check if a value type is a literal type."""
        literal_types = {"int", "float", "double", "decimal", "date", "datetime",
                         "time", "string", "varchar", "text", "bool", "boolean", "enum"}
        return value_type.lower() in literal_types

    def decide_batch(self, items: list[dict]) -> list[dict]:
        """
        Apply decision tree to a batch of items.

        Args:
            items: List of {name, value_type, has_independent_attrs, needs_reasoning}

        Returns:
            List of {name, decision, reason}
        """
        results = []
        for item in items:
            decision, reason = self.decide(
                value=item.get("value"),
                value_type=item.get("value_type", "string"),
                has_independent_attrs=item.get("has_independent_attrs", False),
                needs_reasoning=item.get("needs_reasoning", False),
            )
            results.append({
                "name": item.get("name", ""),
                "decision": decision,
                "reason": reason,
            })

        prop_count = sum(1 for r in results if r["decision"] == "property")
        rel_count = sum(1 for r in results if r["decision"] == "relation")
        logger.info(f"Property vs Relation: {prop_count} properties, {rel_count} relations")

        return results
