"""Algorithm 4.4: Many-to-Many relation reification.

Detects N:M (many-to-many) relations and introduces intermediate nodes
to decompose them into two 1:N relations.
"""
from __future__ import annotations

import logging
import uuid
from typing import Optional

from ..models import Concept, Relation, RelationType, SourceType

logger = logging.getLogger("ontology_gen.m2m_reifier")


class M2MReifier:
    """Detect and reify many-to-many relations."""

    def reify(
        self,
        relation: Relation,
        concept_registry: dict[str, Concept],
    ) -> tuple[Relation, Concept, Relation] | None:
        """
        Check if a relation is N:M and reify it if so.

        Reification: A -[:R]-> B  (N:M)
                   => A -[:participatesIn]-> C -[:involves]-> B  (two 1:N)

        Args:
            relation: The relation to check/reify
            concept_registry: {concept_id: Concept} all known concepts

        Returns:
            (relation_a_to_c, intermediate_concept_c, relation_c_to_b) if reified,
            None if relation is not N:M
        """
        if relation.cardinality != "N:M":
            return None

        domain_concept = concept_registry.get(relation.domain_concept_id)
        range_concept = concept_registry.get(relation.range_concept_id)
        if not domain_concept or not range_concept:
            return None

        # Create intermediate concept
        inter_name = self._generate_intermediate_name(domain_concept.name, range_concept.name, relation.name)
        intermediate = Concept(
            name=inter_name,
            description=f"Reified intermediate concept for {relation.name} ({domain_concept.name}-{range_concept.name})",
            source=SourceType.RDB,
            confidence=0.8,
            is_entity_type=True,
        )

        # Create relation A -> C
        rel_a_to_c = Relation(
            name=f"has{inter_name}",
            domain_concept_id=relation.domain_concept_id,
            range_concept_id=intermediate.id,
            relation_type=RelationType.BUSINESS,
            cardinality="1:N",
            confidence=0.8,
            description=f"Reified from {relation.name}: {domain_concept.name} -> {inter_name}",
            is_reified=True,
            reified_concept_id=intermediate.id,
        )

        # Create relation C -> B
        rel_c_to_b = Relation(
            name=f"has{range_concept.name}",
            domain_concept_id=intermediate.id,
            range_concept_id=relation.range_concept_id,
            relation_type=RelationType.BUSINESS,
            cardinality="1:N",
            confidence=0.8,
            description=f"Reified from {relation.name}: {inter_name} -> {range_concept.name}",
            is_reified=True,
            reified_concept_id=intermediate.id,
        )

        # Mark original relation as reified
        relation.is_reified = True
        relation.reified_concept_id = intermediate.id

        logger.info(f"Reified N:M relation '{relation.name}': "
                     f"{domain_concept.name} -> {inter_name} -> {range_concept.name}")

        return (rel_a_to_c, intermediate, rel_c_to_b)

    def reify_all(
        self,
        relations: list[Relation],
        concepts: list[Concept],
    ) -> tuple[list[Relation], list[Concept]]:
        """
        Reify all N:M relations in a relation list.

        Returns:
            (updated_relations, new_concepts) — original N:M relations are replaced
            by their reified pairs, plus new intermediate concepts are added.
        """
        concept_registry = {c.id: c for c in concepts}
        updated_relations = []
        new_concepts = []

        for relation in relations:
            if relation.cardinality == "N:M":
                result = self.reify(relation, concept_registry)
                if result:
                    rel_a, inter_concept, rel_b = result
                    updated_relations.extend([rel_a, rel_b])
                    new_concepts.append(inter_concept)
                    concept_registry[inter_concept.id] = inter_concept
                else:
                    updated_relations.append(relation)
            else:
                updated_relations.append(relation)

        reified_count = len(new_concepts)
        if reified_count > 0:
            logger.info(f"Reified {reified_count} N:M relations, "
                         f"added {reified_count} intermediate concepts")

        return updated_relations, new_concepts

    @staticmethod
    def _generate_intermediate_name(domain_name: str, range_name: str, relation_name: str) -> str:
        """Generate a name for the intermediate concept."""
        # Try to create a meaningful name
        # e.g., "customer" + "product" + "purchase" -> "PurchaseRecord"
        # Simple heuristic: combine names
        return f"{domain_name}_{range_name}_Relation"

    @staticmethod
    def detect_m2m_from_ddl(tables: list[dict]) -> list[dict]:
        """
        Detect M:N relations from DDL structure.

        A table with exactly 2 FK columns and a composite PK is likely a M:N junction table.

        Args:
            tables: List of parsed DDL tables

        Returns:
            List of {junction_table, entity_a_table, entity_b_table, fk_a, fk_b}
        """
        m2m_relations = []

        for table in tables:
            fks = table.get("foreign_keys", [])
            columns = table.get("columns", [])

            # Heuristic: table has exactly 2 FKs and both FK columns are in PK
            if len(fks) == 2:
                pk_columns = {c["name"] for c in columns if c.get("is_primary_key")}
                fk_columns = {fk["fk_column"] for fk in fks}

                # If all columns are FK columns (junction table pattern)
                if fk_columns.issubset(pk_columns) or len(columns) <= 3:
                    m2m_relations.append({
                        "junction_table": table["table_name"],
                        "entity_a_table": fks[0]["ref_table"],
                        "entity_b_table": fks[1]["ref_table"],
                        "fk_a": fks[0]["fk_column"],
                        "fk_b": fks[1]["fk_column"],
                    })

        logger.info(f"Detected {len(m2m_relations)} M:N relations from DDL")
        return m2m_relations
