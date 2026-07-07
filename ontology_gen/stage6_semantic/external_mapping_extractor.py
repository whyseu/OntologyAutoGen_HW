"""External mapping extractor (Category 3.3).

Extracts cross-system term mappings from config and text.
"""
from __future__ import annotations

import logging

from ..config import Config
from ..llm_client import LLMClient
from ..models import GlossaryTerm, ExternalMapping
from .prompts import EXTERNAL_MAPPING_PROMPT

logger = logging.getLogger("ontology_gen.external_mapping_extractor")


class ExternalMappingExtractor:
    def __init__(self, config: Config, llm: LLMClient | None = None):
        self.config = config
        self.llm = llm

    def extract_from_config(
        self,
        domain_config: dict,
        glossary: list[GlossaryTerm],
    ) -> list[ExternalMapping]:
        mappings: list[ExternalMapping] = []
        term_name_to_id = {t.standard_term: t.id for t in glossary}

        for item in domain_config.get("external_mappings", []):
            internal_term = item.get("internal_term", "")
            term_id = term_name_to_id.get(internal_term, internal_term)
            mapping = ExternalMapping(
                internal_term_id=term_id,
                external_system=item.get("external_system", ""),
                external_term=item.get("external_term", ""),
                external_code=item.get("external_code"),
                mapping_type=item.get("mapping_type", "equivalent"),
            )
            mappings.append(mapping)

        logger.info(f"External mappings from config: {len(mappings)}")
        return mappings

    def extract_from_text(
        self,
        text: str,
        glossary: list[GlossaryTerm],
    ) -> list[ExternalMapping]:
        if not text or not self.llm or not self.config.llm_available:
            return []

        term_list = ", ".join(t.standard_term for t in glossary[:30])
        prompt = EXTERNAL_MAPPING_PROMPT.format(terms=term_list, text=text[:2000])
        messages = [{"role": "system", "content": "You are a system integration expert. Respond in JSON only."}, {"role": "user", "content": prompt}]
        result = self.llm.chat_json(messages)
        if not result:
            return []

        term_name_to_id = {t.standard_term: t.id for t in glossary}
        mappings: list[ExternalMapping] = []
        for item in result.get("mappings", []):
            internal = item.get("internal_term", "")
            term_id = term_name_to_id.get(internal, internal)
            mapping = ExternalMapping(
                internal_term_id=term_id,
                external_system=item.get("external_system", ""),
                external_term=item.get("external_term", ""),
                external_code=item.get("external_code"),
                mapping_type=item.get("mapping_type", "equivalent"),
            )
            mappings.append(mapping)

        logger.info(f"External mappings from text: {len(mappings)}")
        return mappings
