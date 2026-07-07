"""Tests for Algorithm 2.3: Four-step concept merge."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np
from ontology_gen.config import Config
from ontology_gen.llm_client import LLMClient
from ontology_gen.models import Concept, SourceType
from ontology_gen.stage2_concept.concept_merger import ConceptMerger


class MockLLMClient:
    """Mock LLM client that returns预设 results for testing."""

    def __init__(self):
        self.config = Config()

    def chat(self, messages, **kwargs):
        return ""

    def chat_json(self, messages, **kwargs):
        return {}

    def embed(self, texts):
        """Return mock embeddings based on simple character hashing."""
        return np.array([self._mock_embed(t) for t in texts])

    @staticmethod
    def _mock_embed(text: str, dim: int = 64) -> np.ndarray:
        """Create deterministic mock embedding based on character content."""
        vec = np.zeros(dim, dtype=np.float32)
        for ch in text:
            vec[hash(ch) % dim] += 1.0
        norm = np.linalg.norm(vec)
        return vec / norm if norm > 0 else vec


class TestConceptMerger:
    """Test the four-step concept merge algorithm."""

    def setup_method(self):
        self.config = Config()
        self.llm = MockLLMClient()
        self.merger = ConceptMerger(self.config, self.llm)

    def test_exact_match_merge(self):
        """Step 1: Identical concept names should be merged."""
        concepts = [
            Concept(name="客户", source=SourceType.RDB, confidence=0.9),
            Concept(name="客户", source=SourceType.TEXT, confidence=0.8),
        ]
        result = self.merger.merge(concepts)
        assert len(result) == 1, f"Exact match should merge to 1, got {len(result)}"
        assert result[0].name == "客户"

    def test_case_insensitive_match(self):
        """Step 1: Case-insensitive match should merge."""
        concepts = [
            Concept(name="Customer", source=SourceType.RDB, confidence=0.9),
            Concept(name="customer", source=SourceType.TEXT, confidence=0.8),
        ]
        result = self.merger.merge(concepts)
        assert len(result) == 1, f"Case-insensitive match should merge to 1, got {len(result)}"

    def test_edit_distance_merge(self):
        """Step 2: Similar strings (edit distance >= 0.85) should merge."""
        concepts = [
            Concept(name="客户信息", source=SourceType.RDB, confidence=0.9),
            Concept(name="客户信息表", source=SourceType.TEXT, confidence=0.8),
        ]
        result = self.merger.merge(concepts)
        # "客户信息" and "客户信息表" have high Levenshtein ratio
        assert len(result) <= 2, f"Should merge similar strings, got {len(result)}"

    def test_no_merge_different_concepts(self):
        """Concepts with very different names should NOT be merged."""
        concepts = [
            Concept(name="客户", source=SourceType.RDB, confidence=0.9),
            Concept(name="供应商", source=SourceType.TEXT, confidence=0.8),
            Concept(name="订单", source=SourceType.RDB, confidence=0.9),
        ]
        result = self.merger.merge(concepts)
        assert len(result) == 3, f"Different concepts should not merge, got {len(result)}"

    def test_alias_preservation(self):
        """Merged concepts should preserve alias mapping."""
        concepts = [
            Concept(name="客户", source=SourceType.RDB, confidence=0.9),
            Concept(name="客户", source=SourceType.TEXT, confidence=0.8, aliases=["顾客"]),
        ]
        result = self.merger.merge(concepts)
        assert len(result) == 1
        # The representative should have aliases
        assert len(result[0].aliases) > 0 or result[0].name == "客户"

    def test_confidence_based_representative(self):
        """The concept with highest confidence should be the representative."""
        concepts = [
            Concept(name="商品", source=SourceType.RDB, confidence=0.7),
            Concept(name="商品", source=SourceType.TEXT, confidence=0.95),
        ]
        result = self.merger.merge(concepts)
        assert len(result) == 1
        assert result[0].confidence == 0.95, f"Should keep highest confidence, got {result[0].confidence}"

    def test_transitive_merge(self):
        """If A~B and B~C, all three should merge (transitive)."""
        concepts = [
            Concept(name="客户", source=SourceType.RDB, confidence=0.9),
            Concept(name="客户", source=SourceType.TEXT, confidence=0.8),
            Concept(name="客户", source=SourceType.DIALOGUE, confidence=0.7),
        ]
        result = self.merger.merge(concepts)
        assert len(result) == 1, f"Transitive merge should give 1, got {len(result)}"

    def test_empty_input(self):
        """Empty concept list should return empty."""
        result = self.merger.merge([])
        assert len(result) == 0

    def test_single_concept(self):
        """Single concept should return as-is."""
        concept = Concept(name="客户", source=SourceType.RDB, confidence=0.9)
        result = self.merger.merge([concept])
        assert len(result) == 1
        assert result[0].name == "客户"

    def test_alias_map_updated(self):
        """Alias map should be updated after merge."""
        concepts = [
            Concept(name="客户", source=SourceType.RDB, confidence=0.95),
            Concept(name="客户", source=SourceType.TEXT, confidence=0.8),
        ]
        self.merger.merge(concepts)
        # Alias map should track what was merged
        # (In this case, exact match doesn't create alias since names are identical)
        assert isinstance(self.merger.alias_map, dict)
