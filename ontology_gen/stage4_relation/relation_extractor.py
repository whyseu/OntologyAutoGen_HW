"""Prompt 4.1: Relation triple extraction.

Extracts relation triples (subject-predicate-object) and properties from text,
with built-in property vs relation distinction rules.
"""
from __future__ import annotations

import logging
from typing import Optional

from ..config import Config
from ..llm_client import LLMClient
from ..models import Concept, Relation, Property, RelationType, SourceType
from ..utils import parse_ddl, chunk_text
from .prompts import RELATION_EXTRACTION_PROMPT
from .property_relation_decider import PropertyRelationDecider

logger = logging.getLogger("ontology_gen.rel_extractor")


class RelationExtractor:
    """Extract relations and properties from text and DDL."""

    def __init__(self, config: Config, llm_client: LLMClient):
        self.config = config
        self.llm = llm_client
        self.decider = PropertyRelationDecider(reasoning_engine="neo4j")

    def extract_from_text(
        self,
        text: str,
        concepts: list[Concept],
    ) -> dict[str, list]:
        """
        Extract relations and properties from text using Prompt 4.1.

        Args:
            text: Input text
            concepts: List of confirmed concepts (for domain/range constraint)

        Returns:
            {"relations": [Relation], "properties": [Property]}
        """
        if not self.config.llm_available:
            return {"relations": [], "properties": []}

        concept_names = [c.name for c in concepts]
        name_to_concept = {c.name: c for c in concepts}
        for c in concepts:
            for alias in c.aliases:
                name_to_concept[alias] = c

        # Chunk text if too long
        chunks = chunk_text(text, strategy="auto")
        all_relations = []
        all_properties = []

        for chunk in chunks:
            prompt = RELATION_EXTRACTION_PROMPT.format(
                concepts=concept_names[:50],  # Limit context size
                text=chunk[:2000],
            )
            messages = [
                {"role": "system", "content": "You are an ontology engineer. Respond in JSON only."},
                {"role": "user", "content": prompt},
            ]

            result = self.llm.chat_json(messages, temperature=0.1)

            # Parse relations
            for rel_data in result.get("relations", []):
                domain_name = rel_data.get("domain", "")
                range_name = rel_data.get("range", "")
                domain_concept = name_to_concept.get(domain_name)
                range_concept = name_to_concept.get(range_name)

                if domain_concept and range_concept:
                    relation = Relation(
                        name=rel_data.get("predicate", ""),
                        domain_concept_id=domain_concept.id,
                        range_concept_id=range_concept.id,
                        relation_type=RelationType.BUSINESS,
                        source=SourceType.TEXT,
                        confidence=0.7,
                        description=rel_data.get("subject", "") + " -> " + rel_data.get("object", ""),
                    )
                    all_relations.append(relation)

            # Parse properties
            for prop_data in result.get("properties", []):
                domain_name = prop_data.get("subject", "")
                domain_concept = name_to_concept.get(domain_name)
                if domain_concept:
                    prop = Property(
                        name=prop_data.get("property", ""),
                        domain_concept_id=domain_concept.id,
                        value_type=prop_data.get("value_type", "string"),
                        source=SourceType.TEXT,
                        confidence=0.7,
                    )
                    all_properties.append(prop)

        logger.info(f"Text relation extraction: {len(all_relations)} relations, "
                     f"{len(all_properties)} properties")
        return {"relations": all_relations, "properties": all_properties}

    def extract_from_ddl(
        self,
        ddl_text: str,
        concept_map: dict[str, str],
        table_tags: dict[str, str] | None = None,
        query_log: list[str] | None = None,
        business_terms: list[str] | None = None,
    ) -> dict[str, list]:
        """
        Extract relations from DDL foreign keys.

        Uses Algorithm 4.3 (FK filter) to filter out non-business FKs.

        Args:
            ddl_text: Raw DDL text
            concept_map: {table_name: concept_id}
            table_tags: {table_name: "system"|"business"}
            query_log: Business query SQL list
            business_terms: Business domain terms

        Returns:
            {"relations": [Relation], "properties": [Property]}
        """
        from .fk_filter import ForeignKeyFilter

        tables = parse_ddl(ddl_text)
        fk_filter = ForeignKeyFilter(table_tags)
        relations = []

        for table in tables:
            table_name = table["table_name"]
            for fk in table.get("foreign_keys", []):
                fk_info = {
                    "fk_table": table_name,
                    "fk_column": fk["fk_column"],
                    "ref_table": fk["ref_table"],
                    "ref_column": fk["ref_column"],
                }

                # Apply FK filter (Algorithm 4.3)
                filter_result = fk_filter.filter(
                    fk_info, table_tags, query_log, business_terms
                )

                if filter_result["status"] == "rejected":
                    continue

                # Create relation from FK
                domain_concept_id = concept_map.get(table_name)
                range_concept_id = concept_map.get(fk["ref_table"])

                if domain_concept_id and range_concept_id:
                    relation = Relation(
                        name=f"has{fk['ref_table'].capitalize()}",
                        domain_concept_id=domain_concept_id,
                        range_concept_id=range_concept_id,
                        relation_type=RelationType.BUSINESS,
                        source=SourceType.RDB,
                        source_ref=f"FK:{table_name}.{fk['fk_column']}->{fk['ref_table']}",
                        confidence=0.9 if filter_result["status"] == "accepted" else 0.6,
                        cardinality="1:N",
                    )
                    relations.append(relation)

        # Detect and reify M:N relations (Algorithm 4.4)
        from .m2m_reifier import M2MReifier
        m2m_detector = M2MReifier()
        m2m_list = m2m_detector.detect_m2m_from_ddl(tables)
        for m2m in m2m_list:
            domain_concept_id = concept_map.get(m2m["entity_a_table"])
            range_concept_id = concept_map.get(m2m["entity_b_table"])
            if domain_concept_id and range_concept_id:
                relation = Relation(
                    name=f"has{m2m['entity_b_table'].capitalize()}",
                    domain_concept_id=domain_concept_id,
                    range_concept_id=range_concept_id,
                    cardinality="N:M",
                    source=SourceType.RDB,
                    source_ref=f"junction:{m2m['junction_table']}",
                    confidence=0.8,
                )
                relations.append(relation)

        logger.info(f"DDL relation extraction: {len(relations)} relations from {len(tables)} tables")
        return {"relations": relations, "properties": []}
