"""Algorithm 2.4: Concept granularity decision tree.

Decides whether each candidate concept should become an independent concept type,
be merged into a parent concept, or be treated as a property value.
"""
from __future__ import annotations

import logging
from typing import Optional

from ..config import Config
from ..models import Concept, SourceType

logger = logging.getLogger("ontology_gen.granularity")


class GranularityDecider:
    """Decide concept granularity based on instance count and business relevance."""

    # Minimum instance count for a concept to be independent
    MIN_INSTANCE_COUNT = 3

    def __init__(self, config: Config):
        self.config = config

    def decide(
        self,
        concepts: list[Concept],
        taxonomy: dict[str, str] | None = None,
        query_patterns: list[str] | None = None,
    ) -> list[Concept]:
        """
        Apply granularity decision tree to filter concepts.

        Decision logic:
        1. If instance_count < 3 and has parent concept -> merge into parent
        2. If concept has a parent and business doesn't need distinction -> keep only parent
        3. If concept is actually a property value -> don't create as entity type

        Args:
            concepts: List of candidate concepts
            taxonomy: {concept_name: parent_name} known parent relationships
            query_patterns: Business query patterns (to check if concept is needed)

        Returns:
            Filtered concept list with granularity decisions applied
        """
        taxonomy = taxonomy or {}
        query_patterns = query_patterns or []
        result = []

        for concept in concepts:
            decision = self._evaluate(concept, concepts, taxonomy, query_patterns)

            if decision == "keep":
                result.append(concept)
            elif decision == "merge_into_parent":
                parent_name = taxonomy.get(concept.name)
                logger.info(f"Granularity: '{concept.name}' merged into parent '{parent_name}' (too few instances)")
                # Don't add to result — it will be covered by parent
            elif decision == "property_value":
                logger.info(f"Granularity: '{concept.name}' treated as property value (not entity type)")
                concept.is_entity_type = False
                result.append(concept)
            # else: "pending" — keep but mark as uncertain
            else:
                concept.confidence *= 0.7  # Lower confidence for uncertain concepts
                result.append(concept)

        logger.info(f"Granularity decision: {len(concepts)} -> {len(result)} concepts")
        return result

    def _evaluate(
        self,
        concept: Concept,
        all_concepts: list[Concept],
        taxonomy: dict[str, str],
        query_patterns: list[str],
    ) -> str:
        """Evaluate a single concept and return decision."""
        # Rule 1: Instance count too low
        if concept.instance_count < self.MIN_INSTANCE_COUNT:
            parent = taxonomy.get(concept.name)
            if parent:
                return "merge_into_parent"
            # No parent but too few instances — mark as pending
            return "pending"

        # Rule 2: Check if this concept is mentioned in query patterns
        # (if no query pattern mentions it, it might not be needed)
        if query_patterns:
            mentioned = any(concept.name in q for q in query_patterns)
            if not mentioned and concept.confidence < 0.6:
                # Low confidence and not mentioned in queries
                parent = taxonomy.get(concept.name)
                if parent:
                    return "merge_into_parent"
                return "pending"

        # Rule 3: Check if this is actually a property value
        # (heuristic: very short name + has a parent that could own it as enum)
        if len(concept.name) <= 3 and concept.instance_count > 0:
            # Could be an enum value rather than a concept
            # Check if there's a more general concept that could own it
            potential_parents = [
                c for c in all_concepts
                if c.name != concept.name and c.is_entity_type
            ]
            if potential_parents:
                # If this concept's name appears as an enum value somewhere
                for parent in potential_parents:
                    if concept.name in (parent.aliases or []):
                        return "property_value"

        return "keep"
