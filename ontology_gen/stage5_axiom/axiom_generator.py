"""Prompt 5.2-B: LLM-driven axiom generation.

Uses LLM to generate OWL axioms (subClassOf, domain/range, inverseOf)
from business descriptions and confirmed concepts/relations.
"""
from __future__ import annotations

import logging
from typing import Optional

from ..config import Config
from ..llm_client import LLMClient
from ..models import Axiom, AxiomType, RiskLevel, Concept, Relation
from .prompts import AXIOM_GENERATION_PROMPT

logger = logging.getLogger("ontology_gen.axiom_generator")


class AxiomGenerator:
    """LLM-driven OWL axiom generation."""

    def __init__(self, config: Config, llm_client: LLMClient):
        self.config = config
        self.llm = llm_client

    def generate(
        self,
        domain_description: str,
        concepts: list[Concept],
        relations: list[Relation],
    ) -> list[Axiom]:
        """
        Generate axioms using LLM (Prompt 5.2-B).

        Constraints:
        - Only use confirmed concept/relation names
        - Don't generate disjointWith (needs human)
        - Don't generate equivalentClass (unless synonym labels)
        - Don't output axioms with confidence < 0.7

        Returns:
            List of Axiom objects
        """
        if not self.config.llm_available:
            logger.warning("LLM not available, skipping axiom generation")
            return []

        concept_names = [c.name for c in concepts]
        relation_names = [r.name for r in relations]

        prompt = AXIOM_GENERATION_PROMPT.format(
            domain_description=domain_description,
            concepts=concept_names,
            relations=relation_names,
        )

        messages = [
            {"role": "system", "content": "You are an ontology engineer. Respond in JSON only."},
            {"role": "user", "content": prompt},
        ]

        result = self.llm.chat_json(messages, temperature=0.1)

        axioms = []
        type_map = {
            "subClassOf": AxiomType.SUBCLASS_OF,
            "domain": AxiomType.DOMAIN,
            "range": AxiomType.RANGE,
            "inverseOf": AxiomType.INVERSE_OF,
            "equivalentClass": AxiomType.EQUIVALENT_CLASS,
            "disjointWith": AxiomType.DISJOINT_WITH,
            "TransitiveProperty": AxiomType.TRANSITIVE_PROPERTY,
        }

        for item in result.get("axioms", []):
            axiom_type_str = item.get("axiom_type", "")
            axiom_type = type_map.get(axiom_type_str)
            if not axiom_type:
                continue

            confidence = item.get("confidence", 0.5)
            if confidence < 0.7:
                continue  # Skip low-confidence axioms

            axiom = Axiom(
                axiom_type=axiom_type,
                subject=item.get("subject", ""),
                obj=item.get("object", ""),
                confidence=confidence,
                source="llm_driven",
                rationale=item.get("rationale", ""),
            )
            axioms.append(axiom)

        logger.info(f"LLM axiom generation: {len(axioms)} axioms")
        return axioms

    def generate_from_taxonomy(self, taxonomy_nodes: dict) -> list[Axiom]:
        """
        Convert taxonomy (is-a hierarchy) to subClassOf axioms.

        This is a deterministic conversion — no LLM needed.
        """
        axioms = []
        for concept_id, node in taxonomy_nodes.items():
            if node.parent_id:
                axiom = Axiom(
                    axiom_type=AxiomType.SUBCLASS_OF,
                    subject=concept_id,
                    obj=node.parent_id,
                    confidence=node.confidence,
                    risk_level=RiskLevel.MEDIUM,
                    source="data_driven",
                    rationale="Converted from taxonomy hierarchy",
                    validated=True,
                )
                axioms.append(axiom)

        logger.info(f"Taxonomy -> axioms: {len(axioms)} subClassOf axioms")
        return axioms
