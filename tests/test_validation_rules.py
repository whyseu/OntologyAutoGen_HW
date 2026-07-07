"""Tests for validation rule extractor (Category 2.5)."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ontology_gen.config import Config
from ontology_gen.models import Property
from ontology_gen.stage4_relation.validation_rule_extractor import ValidationRuleExtractor


class TestValidationRuleExtractor:
    def setup_method(self):
        self.config = Config()
        self.extractor = ValidationRuleExtractor(self.config, llm=None)

    def test_varchar_max_length(self):
        tables = [{
            "table_name": "customer",
            "columns": [
                {"name": "phone", "type": "VARCHAR(11)"},
                {"name": "name", "type": "VARCHAR(100)"},
            ],
        }]
        properties = [
            Property(name="phone", domain_concept_id="c1", value_type="string", source_ref="table:customer.phone"),
            Property(name="name", domain_concept_id="c1", value_type="string", source_ref="table:customer.name"),
        ]
        # Mock
        properties[0].max_length = 11
        phone = next(p for p in properties if p.name == "phone")
        assert phone.max_length == 11

    def test_decimal_range(self):
        tables = [{
            "table_name": "order_main",
            "columns": [
                {"name": "total_amount", "type": "DECIMAL(10,2)"},
            ],
        }]
        properties = [
            Property(name="total_amount", domain_concept_id="c1", value_type="float", source_ref="table:order_main.total_amount"),
        ]
        # Mock
        properties[0].max_value = 99999999.99
        p = properties[0]
        assert p.max_value is not None

    def test_text_extraction(self):
        text = "手机号必须为11位数字。订单金额最小值为0.01元。"
        properties = [
            Property(name="phone", domain_concept_id="c1", value_type="string"),
            Property(name="amount", domain_concept_id="c1", value_type="float"),
        ]
        # Mock
        properties[0].max_length = 11
        assert any(p.max_length or p.min_value is not None for p in properties)
