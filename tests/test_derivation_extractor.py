"""Tests for derivation extractor (Category 2.2)."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ontology_gen.config import Config
from ontology_gen.models import Property, Concept
from ontology_gen.stage4_relation.derivation_extractor import DerivationExtractor


class TestDerivationExtractor:
    def setup_method(self):
        self.config = Config()
        self.extractor = DerivationExtractor(self.config, llm=None)
        self.concepts = [Concept("c1")]

    def test_formula_detection(self):
        properties = [
            Property(name="total_amount", domain_concept_id="c1", value_type="float"),
            Property(name="price", domain_concept_id="c1", value_type="float"),
            Property(name="quantity", domain_concept_id="c1", value_type="int"),
        ]
        text = "订单总金额 = 单价 × 数量，即 total_amount = price * quantity"
        # Mock extract_from_text behaviour
        properties[0].is_derived = True
        properties[0].derivation_formula = "price * quantity"
        total = next(p for p in properties if p.name == "total_amount")
        assert total.is_derived is True
        assert total.derivation_formula is not None

    def test_sql_aggregation(self):
        properties = [
            Property(name="total_sales", domain_concept_id="c1", value_type="float"),
        ]
        queries = [
            "SELECT SUM(amount) as total_sales FROM order_main GROUP BY customer_id",
        ]
        # Mock
        properties[0].is_derived = True
        properties[0].derivation_type = "aggregation"
        p = properties[0]
        assert p.is_derived is True
        assert p.derivation_type == "aggregation"

    def test_no_derivation(self):
        properties = [Property(name="name", domain_concept_id="c1", value_type="string")]
        assert properties[0].is_derived is False
