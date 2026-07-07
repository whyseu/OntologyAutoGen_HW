"""Prompt 3.2: Relation type classification.

Classifies the relationship between two concepts as:
  is-a / part-of / attribute-of / related-to

Only is-a relations are used for taxonomy construction.
Other relation types are passed to Stage 4 (relation construction).
"""
from __future__ import annotations

import logging
from typing import Optional

from ..config import Config
from ..llm_client import LLMClient
from ..models import RelationType
from .prompts import RELATION_TYPE_PROMPT

logger = logging.getLogger("ontology_gen.relation_type_classifier")


class RelationTypeClassifier:
    """Classify relation type between two concepts."""

    def __init__(self, config: Config, llm_client: LLMClient):
        self.config = config
        self.llm = llm_client

    def classify(self, concept_a: str, concept_b: str) -> tuple[RelationType, str]:
        """
        Classify the relation between two concepts.

        Args:
            concept_a: First concept name
            concept_b: Second concept name

        Returns:
            (RelationType, reason)
        """
        # Try LLM classification first
        if self.config.llm_available and self.llm:
            result = self._llm_classify(concept_a, concept_b)
            if result:
                return result

        # Fallback: rule-based classification
        return self._rule_based_classify(concept_a, concept_b)

    def _llm_classify(self, concept_a: str, concept_b: str) -> tuple[RelationType, str] | None:
        """Use LLM (Prompt 3.2) to classify relation type."""
        prompt = RELATION_TYPE_PROMPT.format(concept_a=concept_a, concept_b=concept_b)
        messages = [
            {"role": "system", "content": "You are an ontology engineer. Respond in JSON only."},
            {"role": "user", "content": prompt},
        ]

        result = self.llm.chat_json(messages, temperature=0.1)

        rel_type_str = result.get("relation_type", "")
        reason = result.get("reason", "")

        type_map = {
            "is-a": RelationType.IS_A,
            "part-of": RelationType.PART_OF,
            "attribute-of": RelationType.ATTRIBUTE_OF,
            "related-to": RelationType.RELATED_TO,
        }

        if rel_type_str in type_map:
            return (type_map[rel_type_str], reason)

        return None

    @staticmethod
    def _rule_based_classify(concept_a: str, concept_b: str) -> tuple[RelationType, str]:
        """Rule-based relation type classification (fallback)."""
        # Check for is-a pattern (A contains B as substring or vice versa)
        if concept_b in concept_a and len(concept_a) > len(concept_b):
            return (RelationType.IS_A, f"'{concept_a}' contains '{concept_b}', likely sub-class")
        if concept_a in concept_b and len(concept_b) > len(concept_a):
            return (RelationType.IS_A, f"'{concept_b}' contains '{concept_a}', likely super-class")

        # Check for part-of patterns
        part_keywords = ["部分", "组件", "元素", "成员"]
        if any(kw in concept_a or kw in concept_b for kw in part_keywords):
            return (RelationType.PART_OF, "Contains part-of keyword")

        # Default: related-to
        return (RelationType.RELATED_TO, "No clear pattern, defaulting to related-to")

    def classify_all_pairs(
        self,
        concepts: list[str],
    ) -> list[tuple[str, str, RelationType, str]]:
        """
        Classify relation type for all concept pairs.

        Returns:
            List of (concept_a, concept_b, relation_type, reason)
        """
        results = []
        for i, a in enumerate(concepts):
            for j, b in enumerate(concepts):
                if i >= j:
                    continue
                rel_type, reason = self.classify(a, b)
                results.append((a, b, rel_type, reason))

        # Separate is-a relations from others
        is_a_count = sum(1 for _, _, t, _ in results if t == RelationType.IS_A)
        logger.info(f"Relation classification: {len(results)} pairs, {is_a_count} is-a relations")

        return results
