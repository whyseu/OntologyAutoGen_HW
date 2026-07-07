"""Tests for concept layer classification (Category 2.1)."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ontology_gen.config import Config
from ontology_gen.models import Concept, ConceptLayer
from ontology_gen.stage2_concept.layer_classifier import LayerClassifier


class TestLayerClassifier:
    def setup_method(self):
        self.config = Config()
        self.classifier = LayerClassifier(self.config, llm=None)

    def test_rdb_source_classified_as_data(self):
        concepts = [Concept(name="客户", source_ref="table:customer")]
        tables = [{"table_name": "customer"}]
        self.classifier.classify(concepts, tables, "")
        assert concepts[0].layer == ConceptLayer.DATA

    def test_logic_keywords(self):
        concepts = [Concept(name="折扣计算规则")]
        self.classifier.classify(concepts, [], "")
        assert concepts[0].layer == ConceptLayer.LOGIC

    def test_application_keywords(self):
        concepts = [Concept(name="用户界面配置")]
        self.classifier.classify(concepts, [], "")
        assert concepts[0].layer == ConceptLayer.APPLICATION
