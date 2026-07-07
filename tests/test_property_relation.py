"""Tests for Algorithm 4.2: Property vs Relation decision tree."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ontology_gen.stage4_relation.property_relation_decider import PropertyRelationDecider


class TestPropertyRelationDecider:
    """Test the property vs relation decision tree."""

    def setup_method(self):
        self.decider = PropertyRelationDecider(reasoning_engine="neo4j")

    def test_literal_is_property(self):
        """Q1: Literal value types should be classified as property."""
        decision, reason = self.decider.decide(value=42, value_type="int")
        assert decision == "property"
        assert "literal" in reason.lower() or "property" in reason.lower()

    def test_date_is_property(self):
        """Date type should be property."""
        decision, reason = self.decider.decide(value="2024-01-01", value_type="date")
        assert decision == "property"

    def test_string_is_property(self):
        """String type should be property."""
        decision, reason = self.decider.decide(value="hello", value_type="string")
        assert decision == "property"

    def test_entity_with_attrs_is_relation(self):
        """Q2: Entity with independent attributes should be relation."""
        decision, reason = self.decider.decide(
            value="hospital_A",
            value_type="entity",
            has_independent_attrs=True,
        )
        assert decision == "relation"
        assert "independent" in reason.lower() or "entity" in reason.lower()

    def test_entity_without_attrs_is_property(self):
        """Q2: Entity without independent attributes defaults to property."""
        decision, reason = self.decider.decide(
            value="tag_value",
            value_type="entity",
            has_independent_attrs=False,
        )
        assert decision == "property"

    def test_neo4j_reasoning_prefers_property(self):
        """Q3: Neo4j reasoning engine prefers property for reasoning."""
        decider = PropertyRelationDecider(reasoning_engine="neo4j")
        decision, reason = decider.decide(
            value=100,
            value_type="int",
            needs_reasoning=True,
        )
        assert decision == "property"

    def test_owl_reasoning_prefers_relation(self):
        """Q3: OWL reasoning engine prefers relation for reasoning."""
        decider = PropertyRelationDecider(reasoning_engine="owl")
        decision, reason = decider.decide(
            value=100,
            value_type="int",
            needs_reasoning=True,
        )
        assert decision == "relation"

    def test_fk_column_is_relation(self):
        """FK column type should be relation."""
        decision, reason = self.decider.decide(value="ref_id", value_type="fk")
        assert decision == "relation"

    def test_enum_is_property(self):
        """Enum type should be property."""
        decision, reason = self.decider.decide(value="active", value_type="enum")
        assert decision == "property"

    def test_batch_decision(self):
        """Test batch decision for multiple items."""
        items = [
            {"name": "age", "value_type": "int"},
            {"name": "doctor", "value_type": "entity", "has_independent_attrs": True},
            {"name": "status", "value_type": "enum"},
        ]
        results = self.decider.decide_batch(items)
        assert len(results) == 3
        assert results[0]["decision"] == "property"  # age
        assert results[1]["decision"] == "relation"  # doctor (entity with attrs)
        assert results[2]["decision"] == "property"  # status (enum)
