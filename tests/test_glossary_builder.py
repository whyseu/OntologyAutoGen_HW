"""Tests for glossary builder (Category 3)."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ontology_gen.config import Config
from ontology_gen.models import Concept
from ontology_gen.stage6_semantic.glossary_builder import GlossaryBuilder


class TestGlossaryBuilder:
    def setup_method(self):
        self.config = Config()
        self.builder = GlossaryBuilder(self.config, llm=None)

    def test_build_from_config_synonyms(self):
        domain_config = {
            "domain": "ecommerce",
            "concept_synonyms": [
                {"standard": "客户", "aliases": ["顾客", "买家"]},
                {"standard": "商品", "aliases": ["产品"]},
            ],
        }
        terms = self.builder.build([], domain_config, "")
        assert len(terms) == 2
        assert terms[0].standard_term == "客户"
        assert "顾客" in terms[0].aliases

    def test_build_from_concepts(self):
        concepts = [
            Concept(name="客户", aliases=["顾客"], description="购买商品的人"),
            Concept(name="订单"),
        ]
        terms = self.builder.build(concepts, {"domain": "test"}, "")
        assert len(terms) == 2
        names = {t.standard_term for t in terms}
        assert "客户" in names
        assert "订单" in names

    def test_no_duplicates(self):
        concepts = [Concept(name="客户")]
        domain_config = {
            "domain": "test",
            "concept_synonyms": [{"standard": "客户", "aliases": ["顾客"]}],
        }
        terms = self.builder.build(concepts, domain_config, "")
        standards = [t.standard_term for t in terms]
        assert standards.count("客户") == 1
