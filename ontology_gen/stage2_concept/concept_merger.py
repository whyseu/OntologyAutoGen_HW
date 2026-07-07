"""Algorithm 2.3: Four-step concept merge algorithm.

Merges synonymous concepts from different data sources using a cascading strategy:
  Step 1: Exact match (literal string equality)
  Step 2: Edit distance (Levenshtein ratio >= 0.85)
  Step 3: Semantic embedding (cosine similarity >= 0.85)
  Step 4: LLM auxiliary judgment (for borderline cases)

Merge is irreversible — alias mapping is preserved.
"""
from __future__ import annotations

import logging
from typing import Optional

import numpy as np

from ..config import Config
from ..llm_client import LLMClient
from ..models import Concept, SourceType
from .prompts import CONCEPT_MERGE_LLM_PROMPT

logger = logging.getLogger("ontology_gen.concept_merger")


class ConceptMerger:
    """Four-step cascading concept merge."""

    def __init__(self, config: Config, llm_client: LLMClient):
        self.config = config
        self.llm = llm_client
        self._alias_map: dict[str, str] = {}  # alias_name -> standard_name

    @property
    def alias_map(self) -> dict[str, str]:
        """Mapping from alias names to standard names (for audit trail)."""
        return self._alias_map

    def merge(self, concepts: list[Concept], domain: str = "") -> list[Concept]:
        """
        Merge synonymous concepts using four-step algorithm.

        Args:
            concepts: List of candidate concepts from different sources
            domain: Business domain (for LLM judge context)

        Returns:
            Merged concept list (each concept's aliases contains merged names)
        """
        if len(concepts) <= 1:
            return concepts

        # Pre-compute embeddings for all concept names
        names = [c.name for c in concepts]
        embeddings = self._compute_embeddings(names)

        # Union-Find for transitive merge
        n = len(concepts)
        parent = list(range(n))

        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(x, y):
            px, py = find(x), find(y)
            if px != py:
                parent[px] = py

        # Four-step merge
        for i in range(n):
            for j in range(i + 1, n):
                if find(i) == find(j):
                    continue  # Already in same group

                should_merge = self._should_merge(
                    concepts[i], concepts[j],
                    embeddings[i] if embeddings is not None else None,
                    embeddings[j] if embeddings is not None else None,
                    domain,
                )

                if should_merge:
                    union(i, j)

        # Group concepts by their root
        groups: dict[int, list[int]] = {}
        for i in range(n):
            root = find(i)
            groups.setdefault(root, []).append(i)

        # Merge each group into one concept
        merged = []
        for group_indices in groups.values():
            if len(group_indices) == 1:
                merged.append(concepts[group_indices[0]])
            else:
                # Pick the concept with highest confidence as representative
                group_concepts = [concepts[i] for i in group_indices]
                representative = max(group_concepts, key=lambda c: c.confidence)

                for other in group_concepts:
                    if other.id != representative.id:
                        representative.merge_from(other)
                        self._alias_map[other.name] = representative.name

                merged.append(representative)

        logger.info(f"Concept merge: {len(concepts)} -> {len(merged)} concepts "
                     f"({len(concepts) - len(merged)} merged)")

        return merged

    def _should_merge(
        self,
        a: Concept,
        b: Concept,
        emb_a: np.ndarray | None,
        emb_b: np.ndarray | None,
        domain: str,
    ) -> bool:
        """Four-step cascading check."""

        # Step 1: Exact match
        if self._exact_match(a.name, b.name):
            return True

        # Step 2: Edit distance
        edit_sim = self._edit_distance(a.name, b.name)
        if edit_sim >= self.config.merge_threshold_edit:
            return True

        # Step 3: Semantic embedding
        if emb_a is not None and emb_b is not None:
            sem_sim = self._semantic_similarity(emb_a, emb_b)
            if sem_sim >= self.config.merge_threshold_semantic:
                return True

            # Step 4: LLM judge for borderline cases
            if sem_sim >= self.config.merge_threshold_llm:
                return self._llm_judge(a.name, b.name, domain)

        return False

    @staticmethod
    def _exact_match(a: str, b: str) -> bool:
        """Step 1: Exact string match (case-insensitive, trim whitespace)."""
        return a.strip().lower() == b.strip().lower()

    @staticmethod
    def _edit_distance(a: str, b: str) -> float:
        """Step 2: Levenshtein ratio (0-1, higher = more similar)."""
        try:
            import Levenshtein
            return Levenshtein.ratio(a, b)
        except ImportError:
            # Fallback: simple character-level ratio
            if not a or not b:
                return 0.0
            max_len = max(len(a), len(b))
            min_len = min(len(a), len(b))
            # Count matching characters at same positions
            matches = sum(1 for i in range(min_len) if a[i] == b[i])
            return matches / max_len

    @staticmethod
    def _semantic_similarity(emb_a: np.ndarray, emb_b: np.ndarray) -> float:
        """Step 3: Cosine similarity between embeddings."""
        return LLMClient.cosine_similarity(emb_a, emb_b)

    def _llm_judge(self, a: str, b: str, domain: str) -> bool:
        """Step 4: LLM auxiliary judgment for borderline cases."""
        prompt = CONCEPT_MERGE_LLM_PROMPT.format(domain=domain, concept_a=a, concept_b=b)
        messages = [
            {"role": "system", "content": "You are a domain expert. Respond in JSON only."},
            {"role": "user", "content": prompt},
        ]
        result = self.llm.chat_json(messages, temperature=0.0)
        same = result.get("same_concept", False)
        if same:
            logger.info(f"LLM judge: '{a}' ~ '{b}' -> same concept")
        return bool(same)

    def _compute_embeddings(self, texts: list[str]) -> list[np.ndarray] | None:
        """Compute embeddings for all concept names."""
        if not texts:
            return None
        try:
            embeddings = self.llm.embed(texts)
            return [embeddings[i] for i in range(len(texts))]
        except Exception as e:
            logger.warning(f"Embedding computation failed: {e}. Using edit distance only.")
            return None
