"""Tests for query pattern analyzer (Category 7)."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ontology_gen.config import Config
from ontology_gen.models import Concept, Property
from ontology_gen.stage1_data_prep.query_pattern_analyzer import QueryPatternAnalyzer


class TestQueryPatternAnalyzer:
    def setup_method(self):
        self.config = Config()
        self.config.query_pattern_min_frequency = 1 # Set to 1 so our small test queries pass
        self.analyzer = QueryPatternAnalyzer(self.config)

    def test_crud_patterns(self):
        concepts = [Concept(name="客户", name_en="customer")]
        queries = [
            "SELECT * FROM customer WHERE customer_id = 1",
            "SELECT * FROM customer WHERE customer_id = 2",
            "SELECT * FROM customer WHERE customer_id = 3",
        ]
        patterns = self.analyzer.analyze(queries, concepts, [])
        lookup = [p for p in patterns if p.pattern_type == "entity_lookup"]
        assert len(lookup) >= 1

    def test_aggregation_patterns(self):
        concepts = [Concept(name="订单", name_en="order_main")]
        queries = [
            "SELECT SUM(total_amount), COUNT(*) FROM order_main GROUP BY customer_id",
        ]
        patterns = self.analyzer.analyze(queries, concepts, [])
        agg = [p for p in patterns if p.pattern_type == "aggregation"]
        assert len(agg) >= 1

    def test_join_patterns(self):
        concepts = [
            Concept(name="客户", name_en="customer"),
            Concept(name="订单", name_en="order_main"),
        ]
        queries = [
            "SELECT c.* FROM customer c JOIN order_main o ON c.id = o.customer_id",
        ]
        patterns = self.analyzer.analyze(queries, concepts, [])
        join = [p for p in patterns if "join" in p.pattern_type.lower() or "cross" in p.pattern_type.lower()]
        assert len(join) >= 1

    def test_empty_queries(self):
        patterns = self.analyzer.analyze([], [], [])
        assert patterns == []
