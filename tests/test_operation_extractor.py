"""Tests for operation extractor (Category 5)."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ontology_gen.config import Config
from ontology_gen.models import Concept
from ontology_gen.stage7_process.operation_extractor import OperationExtractor


class TestOperationExtractor:
    def setup_method(self):
        self.config = Config()
        self.extractor = OperationExtractor(self.config, llm=None)

    def test_extract_from_query_log(self):
        concepts = [
            Concept(name="客户", name_en="customer"),
            Concept(name="订单", name_en="order_main"),
        ]
        queries = [
            "SELECT * FROM customer WHERE customer_id = 1",
            "UPDATE order_main SET status = 'shipped' WHERE order_id = 1",
            "INSERT INTO order_main (customer_id, total_amount) VALUES (1, 100)",
        ]
        ops = self.extractor.extract_from_query_log(queries, concepts)
        assert len(ops) >= 2
        op_names = {op.name for op in ops}
        assert "查询客户" in op_names or "更新订单" in op_names

    def test_empty_query_log(self):
        ops = self.extractor.extract_from_query_log([], [])
        assert ops == []
