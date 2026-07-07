"""Tests for Algorithm 4.4: M:N relation reification."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ontology_gen.models import Concept, Relation, RelationType, SourceType
from ontology_gen.stage4_relation.m2m_reifier import M2MReifier


class TestM2MReifier:
    """Test many-to-many relation reification."""

    def setup_method(self):
        self.reifier = M2MReifier()
        self.concept_a = Concept(name="Customer", source=SourceType.RDB, confidence=0.9)
        self.concept_b = Concept(name="Product", source=SourceType.RDB, confidence=0.9)
        self.registry = {
            self.concept_a.id: self.concept_a,
            self.concept_b.id: self.concept_b,
        }

    def test_reify_m2m_relation(self):
        """N:M relation should be reified into two 1:N relations + intermediate concept."""
        relation = Relation(
            name="likesProduct",
            domain_concept_id=self.concept_a.id,
            range_concept_id=self.concept_b.id,
            cardinality="N:M",
        )
        result = self.reifier.reify(relation, self.registry)
        assert result is not None, "N:M relation should be reified"

        rel_a, inter_concept, rel_b = result
        # Check intermediate concept
        assert inter_concept.is_entity_type is True
        assert inter_concept.name != ""

        # Check relation A -> C
        assert rel_a.domain_concept_id == self.concept_a.id
        assert rel_a.range_concept_id == inter_concept.id
        assert rel_a.cardinality == "1:N"
        assert rel_a.is_reified is True

        # Check relation C -> B
        assert rel_b.domain_concept_id == inter_concept.id
        assert rel_b.range_concept_id == self.concept_b.id
        assert rel_b.cardinality == "1:N"
        assert rel_b.is_reified is True

    def test_no_reify_1n_relation(self):
        """1:N relation should NOT be reified."""
        relation = Relation(
            name="hasOrder",
            domain_concept_id=self.concept_a.id,
            range_concept_id=self.concept_b.id,
            cardinality="1:N",
        )
        result = self.reifier.reify(relation, self.registry)
        assert result is None, "1:N relation should not be reified"

    def test_no_reify_11_relation(self):
        """1:1 relation should NOT be reified."""
        relation = Relation(
            name="hasProfile",
            domain_concept_id=self.concept_a.id,
            range_concept_id=self.concept_b.id,
            cardinality="1:1",
        )
        result = self.reifier.reify(relation, self.registry)
        assert result is None

    def test_reify_all(self):
        """reify_all should process multiple relations."""
        relations = [
            Relation(name="likesProduct", domain_concept_id=self.concept_a.id,
                     range_concept_id=self.concept_b.id, cardinality="N:M"),
            Relation(name="hasOrder", domain_concept_id=self.concept_a.id,
                     range_concept_id=self.concept_b.id, cardinality="1:N"),
        ]
        concepts = [self.concept_a, self.concept_b]
        updated_relations, new_concepts = self.reifier.reify_all(relations, concepts)

        # N:M should be split into 2 relations, 1:N should remain
        assert len(updated_relations) == 3  # 2 from reification + 1 original
        assert len(new_concepts) == 1  # 1 intermediate concept

    def test_detect_m2m_from_ddl(self):
        """Detect M:N junction tables from DDL structure."""
        tables = [
            {
                "table_name": "product_tag",
                "columns": [
                    {"name": "product_id", "type": "BIGINT", "is_primary_key": True},
                    {"name": "tag_id", "type": "BIGINT", "is_primary_key": True},
                ],
                "foreign_keys": [
                    {"fk_column": "product_id", "ref_table": "product", "ref_column": "product_id"},
                    {"fk_column": "tag_id", "ref_table": "tag", "ref_column": "tag_id"},
                ],
            },
            {
                "table_name": "customer",
                "columns": [
                    {"name": "customer_id", "type": "BIGINT", "is_primary_key": True},
                    {"name": "customer_name", "type": "VARCHAR(100)"},
                ],
                "foreign_keys": [],
            },
        ]
        m2m_list = self.reifier.detect_m2m_from_ddl(tables)
        assert len(m2m_list) == 1
        assert m2m_list[0]["junction_table"] == "product_tag"
        assert m2m_list[0]["entity_a_table"] == "product"
        assert m2m_list[0]["entity_b_table"] == "tag"
