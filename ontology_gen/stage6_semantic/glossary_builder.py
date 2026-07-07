"""Glossary builder (Category 3.1/3.2).

Builds a unified business glossary from existing concepts and domain config.
"""
from __future__ import annotations

import logging

from ..config import Config
from ..llm_client import LLMClient
from ..models import Concept, GlossaryTerm
from .prompts import GLOSSARY_EXTRACTION_PROMPT

logger = logging.getLogger("ontology_gen.glossary_builder")


class GlossaryBuilder:
    def __init__(self, config: Config, llm: LLMClient):
        self.config = config
        self.llm = llm

    def build(
        self,
        concepts: list[Concept],
        domain_config: dict,
        docs_text: str,
    ) -> list[GlossaryTerm]:
        terms: list[GlossaryTerm] = []

        # Build from concept synonyms in config
        for syn in domain_config.get("concept_synonyms", []):
            term = GlossaryTerm(
                standard_term=syn.get("standard", ""),
                aliases=syn.get("aliases", []),
                domain=domain_config.get("domain", ""),
            )
            terms.append(term)

        # Build from existing concepts (those not already in config)
        existing_standards = {t.standard_term for t in terms}
        for concept in concepts:
            if concept.name not in existing_standards:
                term = GlossaryTerm(
                    standard_term=concept.name,
                    aliases=concept.aliases,
                    definition=concept.description or "",
                    domain=domain_config.get("domain", ""),
                )
                terms.append(term)

        # LLM enrichment: generate definitions
        if self.config.llm_available and self.llm and docs_text:
            self._enrich_definitions(terms, docs_text)

        logger.info(f"Glossary built: {len(terms)} terms")
        return terms

    def _enrich_definitions(self, terms: list[GlossaryTerm], docs_text: str) -> None:
        terms_without_def = [t for t in terms if not t.definition]
        if not terms_without_def:
            return

        concept_list = ", ".join(t.standard_term for t in terms_without_def[:30])
        prompt = GLOSSARY_EXTRACTION_PROMPT.format(
            concepts=concept_list,
            text=docs_text[:2000],
        )
        messages = [{"role": "system", "content": "You are a business terminology expert. Respond in JSON only."}, {"role": "user", "content": prompt}]
        result = self.llm.chat_json(messages)
        if not result:
            return

        name_to_term = {t.standard_term: t for t in terms}
        for item in result.get("terms", []):
            name = item.get("standard_term", "")
            if name in name_to_term and not name_to_term[name].definition:
                name_to_term[name].definition = item.get("definition", "")
                if item.get("category"):
                    name_to_term[name].category = item["category"]
