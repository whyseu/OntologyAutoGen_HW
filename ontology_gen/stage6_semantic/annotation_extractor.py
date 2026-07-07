"""Semantic annotation extractor (Category 2.6).

Extracts business context annotations from documents and DDL comments.
"""
from __future__ import annotations

import logging

from ..config import Config
from ..llm_client import LLMClient
from ..models import Concept, Property, SemanticAnnotation
from .prompts import ANNOTATION_EXTRACTION_PROMPT

logger = logging.getLogger("ontology_gen.annotation_extractor")


class AnnotationExtractor:
    def __init__(self, config: Config, llm: LLMClient):
        self.config = config
        self.llm = llm

    def extract(
        self,
        docs_text: str,
        concepts: list[Concept],
        properties: list[Property],
        parsed_tables: list[dict] | None = None,
    ) -> list[SemanticAnnotation]:
        annotations: list[SemanticAnnotation] = []

        # Rule-based: extract DDL comments as annotations
        if parsed_tables:
            annotations.extend(self._from_ddl_comments(parsed_tables, concepts, properties))

        # LLM-based: extract from docs
        if self.config.llm_available and self.llm and docs_text:
            annotations.extend(self._from_text(docs_text, concepts, properties))

        logger.info(f"Semantic annotations: {len(annotations)}")
        return annotations

    def _from_ddl_comments(
        self,
        parsed_tables: list[dict],
        concepts: list[Concept],
        properties: list[Property],
    ) -> list[SemanticAnnotation]:
        annotations = []
        concept_name_to_id = {}
        for c in concepts:
            concept_name_to_id[c.name] = c.id
            if c.name_en:
                concept_name_to_id[c.name_en.lower()] = c.id

        for table in parsed_tables:
            tname = table.get("table_name", "")
            table_comment = table.get("comment", "")
            if table_comment and tname.lower() in concept_name_to_id:
                annotations.append(SemanticAnnotation(
                    target_id=concept_name_to_id[tname.lower()],
                    target_type="concept",
                    annotation_key="ddl_comment",
                    annotation_value=table_comment,
                ))

            for col in table.get("columns", []):
                col_comment = col.get("comment", "")
                if col_comment:
                    for p in properties:
                        if p.name == col["name"] and p.source_ref and tname in p.source_ref:
                            annotations.append(SemanticAnnotation(
                                target_id=p.id,
                                target_type="property",
                                annotation_key="ddl_comment",
                                annotation_value=col_comment,
                            ))
                            break

        return annotations

    def _from_text(
        self,
        docs_text: str,
        concepts: list[Concept],
        properties: list[Property],
    ) -> list[SemanticAnnotation]:
        elements = []
        for c in concepts[:20]:
            elements.append(f"概念: {c.name}")
        for p in properties[:20]:
            elements.append(f"属性: {p.name}")

        prompt = ANNOTATION_EXTRACTION_PROMPT.format(
            elements="\n".join(elements),
            text=docs_text[:2000],
        )
        messages = [{"role": "system", "content": "You are a data governance expert. Respond in JSON only."}, {"role": "user", "content": prompt}]
        result = self.llm.chat_json(messages)
        if not result:
            return []

        concept_name_to_id = {c.name: c.id for c in concepts}
        prop_name_to_id = {p.name: p.id for p in properties}

        annotations = []
        for item in result.get("annotations", []):
            target_name = item.get("target_name", "")
            target_type = item.get("target_type", "")
            target_id = ""
            if target_type == "concept" and target_name in concept_name_to_id:
                target_id = concept_name_to_id[target_name]
            elif target_type == "property" and target_name in prop_name_to_id:
                target_id = prop_name_to_id[target_name]
            else:
                continue

            annotations.append(SemanticAnnotation(
                target_id=target_id,
                target_type=target_type,
                annotation_key=item.get("key", "business_context"),
                annotation_value=item.get("value", ""),
            ))

        return annotations
