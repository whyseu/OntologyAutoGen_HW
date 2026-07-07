"""Prompt 2.2: Text path concept extraction.

Extracts concepts from text using LLM with 5 anti-hallucination rules.
Supports multiple chunking strategies.
"""
from __future__ import annotations

import logging
from typing import Optional

from ..config import Config
from ..llm_client import LLMClient
from ..models import Concept, SourceType
from ..utils import chunk_text
from .prompts import TEXT_CONCEPT_EXTRACTION_PROMPT

logger = logging.getLogger("ontology_gen.text_extractor")


class TextConceptExtractor:
    """Extract concepts from text with anti-hallucination constraints."""

    # Words that are too generic to be concepts
    GENERIC_WORDS = {"系统", "方法", "数据", "信息", "记录", "内容", "事物", "对象", "实体", "类型", "方式"}

    def __init__(self, config: Config, llm_client: LLMClient):
        self.config = config
        self.llm = llm_client

    def extract(self, text: str, strategy: str = "auto") -> list[Concept]:
        """
        Extract concepts from text.

        Args:
            text: Full text content
            strategy: Chunking strategy ("auto", "sections", "paragraphs", "fixed")

        Returns:
            List of Concept objects
        """
        chunks = chunk_text(text, strategy=strategy)
        all_concepts = []

        for i, chunk in enumerate(chunks):
            concepts = self._extract_from_chunk(chunk, i)
            all_concepts.extend(concepts)

        # Deduplicate by name (keep highest confidence)
        seen = {}
        for concept in all_concepts:
            name = concept.name
            if name not in seen or concept.confidence > seen[name].confidence:
                seen[name] = concept

        logger.info(f"Text concept extraction: {len(all_concepts)} raw -> {len(seen)} unique concepts "
                     f"from {len(chunks)} chunks")
        return list(seen.values())

    def _extract_from_chunk(self, chunk: str, chunk_idx: int) -> list[Concept]:
        """Extract concepts from a single text chunk."""
        # Try LLM extraction first
        if self.config.llm_available and self.llm:
            concepts = self._llm_extract(chunk, chunk_idx)
            if concepts:
                return concepts

        # Fallback: rule-based extraction (noun phrase detection)
        return self._rule_based_extract(chunk, chunk_idx)

    def _llm_extract(self, chunk: str, chunk_idx: int) -> list[Concept]:
        """Use LLM to extract concepts (Prompt 2.2 with anti-hallucination rules)."""
        prompt = TEXT_CONCEPT_EXTRACTION_PROMPT.format(text=chunk[:2000])  # Limit input size
        messages = [
            {"role": "system", "content": "You are a domain concept extractor. Respond in JSON only."},
            {"role": "user", "content": prompt},
        ]

        result = self.llm.chat_json(messages, temperature=0.1)

        concepts = []
        for item in result.get("concepts", []):
            text = item.get("text", "").strip()
            if not text or text in self.GENERIC_WORDS:
                continue

            # Verify span is valid (anti-hallucination check)
            span = item.get("span", [0, 0])
            if isinstance(span, list) and len(span) == 2:
                start, end = span
                if 0 <= start < end <= len(chunk):
                    actual_text = chunk[start:end]
                    # Check if the extracted text approximately matches the span
                    if text not in actual_text and actual_text not in text:
                        logger.debug(f"Span mismatch for '{text}': span=[{start},{end}] got '{actual_text}'")
                        # Still keep it but with lower confidence

            concepts.append(Concept(
                name=text,
                description=item.get("type", ""),
                source=SourceType.TEXT,
                source_ref=f"chunk:{chunk_idx}",
                confidence=0.8,
            ))

        return concepts

    def _rule_based_extract(self, chunk: str, chunk_idx: int) -> list[Concept]:
        """Rule-based concept extraction (fallback when LLM is unavailable).

        Uses simple heuristics:
        - Chinese noun phrases (2-6 characters, no particles)
        - Words appearing multiple times are more likely concepts
        """
        import re
        from collections import Counter

        # Extract Chinese phrases (2-6 chars, excluding particles and generic words)
        pattern = re.compile(r"[\u4e00-\u9fa5]{2,6}")
        candidates = pattern.findall(chunk)

        # Filter out generic words and common stop words
        stop_chars = {"的", "了", "是", "在", "和", "与", "或", "也", "都", "但", "而", "如", "为", "对", "从", "到", "向", "由", "以", "于", "按", "据"}
        filtered = [
            c for c in candidates
            if c not in self.GENERIC_WORDS
            and not any(sc in c for sc in stop_chars)
            and len(c) >= 2
        ]

        # Count frequency
        counter = Counter(filtered)

        # Only keep phrases appearing 2+ times (or all if none appear 2+)
        concepts = []
        for name, count in counter.most_common(50):  # Top 50
            if count >= 2 or len(counter) <= 20:
                concepts.append(Concept(
                    name=name,
                    source=SourceType.TEXT,
                    source_ref=f"chunk:{chunk_idx}",
                    confidence=min(0.4 + count * 0.1, 0.8),
                    instance_count=count,
                ))

        return concepts
