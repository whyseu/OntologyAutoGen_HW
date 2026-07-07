"""Tests for trigger rule extraction (Category 4)."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ontology_gen.config import Config
from ontology_gen.models import Concept
from ontology_gen.stage6_semantic.trigger_rule_extractor import TriggerRuleExtractor


class TestTriggerRuleExtractor:
    def setup_method(self):
        self.config = Config()
        self.extractor = TriggerRuleExtractor(self.config, llm=None)

    def test_timeout_trigger(self):
        text = "如果客户在24小时内未支付，系统将自动取消订单。"
        concepts = [Concept(name="客户"), Concept(name="订单")]
        rules = self.extractor.extract_from_text(text, concepts)
        assert len(rules) >= 1
        timeout_rules = [r for r in rules if r.event_type == "time_based"]
        assert len(timeout_rules) >= 1

    def test_post_action_trigger(self):
        text = "支付完成后，系统会自动更新库存数量。"
        concepts = [Concept(name="订单"), Concept(name="库存")]
        rules = self.extractor.extract_from_text(text, concepts)
        status_rules = [r for r in rules if r.event_type == "status_transition"]
        assert len(status_rules) >= 1

    def test_empty_text(self):
        rules = self.extractor.extract_from_text("", [])
        assert rules == []
