"""Tests for extended data models (7+1 semantic specification)."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ontology_gen.models import (
    Concept, Property, Ontology, ConceptLayer,
    SemanticAnnotation, GovernanceRule, GlossaryTerm,
    ExternalMapping, TriggerRule, AtomicOperation,
    ServiceComposition, PermissionSubject, PermissionRule,
    QueryPattern,
)


class TestConceptExtended:
    def test_default_layer(self):
        c = Concept(name="客户")
        assert c.layer == ConceptLayer.DATA
        assert c.identity_spec is None

    def test_custom_layer(self):
        c = Concept(name="订单服务", layer=ConceptLayer.APPLICATION)
        assert c.layer == ConceptLayer.APPLICATION

    def test_identity_spec(self):
        c = Concept(name="客户", identity_spec="customer_id")
        assert c.identity_spec == "customer_id"


class TestPropertyExtended:
    def test_validation_fields(self):
        p = Property(
            name="phone",
            domain_concept_id="c1",
            value_type="string",
            validation_regex=r"^1\d{10}$",
            max_length=11,
        )
        assert p.validation_regex == r"^1\d{10}$"
        assert p.max_length == 11
        assert p.min_value is None

    def test_derivation_fields(self):
        p = Property(
            name="total_amount",
            domain_concept_id="c1",
            value_type="float",
            is_derived=True,
            derivation_formula="price * quantity",
            derivation_type="formula",
            derivation_sources=["price", "quantity"],
        )
        assert p.is_derived is True
        assert p.derivation_type == "formula"
        assert len(p.derivation_sources) == 2


class TestNewDataclasses:
    def test_glossary_term(self):
        t = GlossaryTerm(standard_term="客户", aliases=["顾客", "买家"])
        assert t.standard_term == "客户"
        assert len(t.aliases) == 2
        assert t.id  # auto-generated

    def test_trigger_rule(self):
        r = TriggerRule(
            name="超时取消",
            description="超过24小时未支付自动取消订单",
            event_type="time_based",
            event_source="订单",
            event_detail="未支付超过24小时",
            condition_expression="超过24小时未支付",
            action_type="update_field",
            action_detail="取消订单",
        )
        assert r.event_type == "time_based"
        assert r.name == "超时取消"

    def test_atomic_operation(self):
        op = AtomicOperation(
            name="下单",
            description="客户提交订单",
            inputs=[{"name": "商品ID", "type": "string"}],
            outputs=[{"name": "订单ID", "type": "string"}],
        )
        assert op.name == "下单"
        assert len(op.inputs) == 1

    def test_permission_rule(self):
        r = PermissionRule(
            name="客户查看自己订单",
            description="客户只能查看自己的订单",
            subject_id="subj_001",
            object_concept_id="order_001",
            actions=["read"],
            effect="allow",
            object_scope="own",
        )
        assert r.effect == "allow"
        assert r.object_scope == "own"

    def test_query_pattern(self):
        qp = QueryPattern(
            name="查询客户",
            description="根据ID查询客户信息",
            pattern_type="entity_lookup",
            target_concepts=["concept_001"],
            frequency=150,
        )
        assert qp.pattern_type == "entity_lookup"
        assert qp.frequency == 150


class TestOntologyExtended:
    def test_empty_new_fields(self):
        o = Ontology(domain="test", entity_types=[], properties=[], relations=[])
        assert o.glossary == []
        assert o.trigger_rules == []
        assert o.operations == []
        assert o.permission_rules == []
        assert o.query_patterns == []

    def test_to_dict_includes_new_fields(self):
        o = Ontology(
            domain="test",
            entity_types=[],
            properties=[],
            relations=[],
            glossary=[GlossaryTerm(standard_term="测试术语")],
        )
        d = o.to_dict()
        assert "glossary" in d
        assert len(d["glossary"]) == 1
        assert d["glossary"][0]["standard_term"] == "测试术语"

    def test_version_2(self):
        o = Ontology(domain="test", entity_types=[], properties=[], relations=[])
        d = o.to_dict()
        assert d["version"] == "2.0"
