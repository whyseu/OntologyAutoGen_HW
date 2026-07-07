"""Prompt 3.1: LLM taxonomy induction.

Uses LLM to infer is-a (generalization-specialization) relations between concepts.
"""
from __future__ import annotations

import logging
from typing import Optional

from ..config import Config
from ..llm_client import LLMClient
from ..models import Concept, Taxonomy, TaxonomyNode, RelationType
from .prompts import TAXONOMY_INDUCTION_PROMPT
from .cycle_detector import CycleDetector

logger = logging.getLogger("ontology_gen.taxonomy_inducer")


class TaxonomyInducer:
    """LLM-based taxonomy induction with cycle detection."""

    def __init__(self, config: Config, llm_client: LLMClient):
        self.config = config
        self.llm = llm_client
        self.cycle_detector = CycleDetector()

    def induce(self, concepts: list[Concept]) -> Taxonomy:
        """
        Build taxonomy from concept list.

        Strategy:
        1. Use LLM to find is-a relations
        2. Use cycle detection to remove invalid cycles
        3. Build Taxonomy tree

        Args:
            concepts: List of confirmed concepts

        Returns:
            Taxonomy object with nodes and root_ids
        """
        if not concepts:
            return Taxonomy()

        # Get is-a relations from LLM
        relations = self._llm_induce_relations(concepts)

        # Also try instance-based hierarchy (if instance_count is available)
        instance_relations = self._instance_based_hierarchy(concepts)
        relations.extend(instance_relations)

        # Deduplicate
        seen = set()
        unique_relations = []
        for child, parent, conf, reason in relations:
            key = (child, parent)
            if key not in seen:
                seen.add(key)
                unique_relations.append((child, parent, conf, reason))

        # Build concept name -> ID mapping
        name_to_id = {c.name: c.id for c in concepts}
        name_to_id.update({alias: c.id for c in concepts for alias in c.aliases})

        # Convert to (child_id, parent_id) edges
        edges = []
        edge_confidences = {}
        for child_name, parent_name, conf, reason in unique_relations:
            child_id = name_to_id.get(child_name)
            parent_id = name_to_id.get(parent_name)
            if child_id and parent_id and child_id != parent_id:
                edges.append((child_id, parent_id))
                edge_confidences[(child_id, parent_id)] = conf

        # Remove cycles
        clean_edges = self.cycle_detector.remove_cycles(edges, edge_confidences)

        # Build Taxonomy
        taxonomy = Taxonomy()
        all_concept_ids = {c.id for c in concepts}

        # Add all concepts as nodes first
        for concept in concepts:
            taxonomy.nodes[concept.id] = TaxonomyNode(concept_id=concept.id)

        # Set parent-child relationships
        for child_id, parent_id in clean_edges:
            if child_id in taxonomy.nodes and parent_id in taxonomy.nodes:
                node = taxonomy.nodes[child_id]
                node.parent_id = parent_id
                node.confidence = edge_confidences.get((child_id, parent_id), 0.8)
                # Update parent's children list
                parent_node = taxonomy.nodes[parent_id]
                if child_id not in parent_node.children_ids:
                    parent_node.children_ids.append(child_id)

        # Set root IDs (concepts with no parent)
        taxonomy.root_ids = [
            cid for cid in all_concept_ids
            if taxonomy.nodes[cid].parent_id is None
        ]

        # Calculate depths
        self._calculate_depths(taxonomy)

        logger.info(f"Taxonomy built: {len(taxonomy.nodes)} nodes, {len(clean_edges)} edges, "
                     f"{len(taxonomy.root_ids)} roots")

        return taxonomy

    def _llm_induce_relations(self, concepts: list[Concept]) -> list[tuple[str, str, float, str]]:
        """Use LLM (Prompt 3.1) to find is-a relations."""
        if not self.config.llm_available:
            return []

        concept_names = [c.name for c in concepts]
        prompt = TAXONOMY_INDUCTION_PROMPT.format(concepts=concept_names)
        messages = [
            {"role": "system", "content": "You are an ontology engineer. Respond in JSON only."},
            {"role": "user", "content": prompt},
        ]

        result = self.llm.chat_json(messages, temperature=0.1)

        relations = []
        confidence_map = {"high": 0.9, "medium": 0.7, "low": 0.5}

        for item in result.get("taxonomy", []):
            parent = item.get("parent", "")
            child = item.get("child", "")
            conf_str = item.get("confidence", "medium")
            reason = item.get("reason", "")
            relations.append((child, parent, confidence_map.get(conf_str, 0.7), reason))

        return relations

    @staticmethod
    def _instance_based_hierarchy(concepts: list[Concept]) -> list[tuple[str, str, float, str]]:
        """
        Instance-based hierarchy: if A's instances ⊆ B's instances, A is-a B.
        Uses instance_count as a simple heuristic.
        """
        relations = []
        for a in concepts:
            for b in concepts:
                if a.id == b.id or a.name == b.name:
                    continue
                # Simple heuristic: if a.name contains b.name and a has fewer instances
                if b.name in a.name and a.instance_count > 0 and b.instance_count > a.instance_count:
                    relations.append((a.name, b.name, 0.6, "instance_count based: subset relation"))
        return relations

    @staticmethod
    def _calculate_depths(taxonomy: Taxonomy) -> None:
        """Calculate depth for each node in the taxonomy."""
        def set_depth(node_id: str, depth: int) -> None:
            node = taxonomy.nodes.get(node_id)
            if node:
                node.depth = depth
                for child_id in node.children_ids:
                    set_depth(child_id, depth + 1)

        for root_id in taxonomy.root_ids:
            set_depth(root_id, 0)
