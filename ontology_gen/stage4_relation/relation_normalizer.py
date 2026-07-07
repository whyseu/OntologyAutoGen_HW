"""Relation synonym normalization.

Normalizes relation names using a synonym table, so that different
expressions of the same relation (e.g., "下单", "创建订单", "提交订单")
are unified to a standard name (e.g., "hasOrder").
"""
from __future__ import annotations

import logging
from typing import Optional

from ..models import Relation, SourceType

logger = logging.getLogger("ontology_gen.rel_normalizer")


class RelationNormalizer:
    """Normalize relation names using synonym table."""

    def __init__(self, synonym_table: list[dict] | None = None):
        """
        Args:
            synonym_table: List of {
                "standard_name": str,
                "aliases": list[str],
                "domain": str,
                "range": str,
                "inverse": str (optional)
            }
        """
        self.synonym_table = synonym_table or []
        self._alias_to_standard: dict[str, str] = {}
        self._inverse_map: dict[str, str] = {}

        for entry in self.synonym_table:
            standard = entry.get("standard_name", "")
            for alias in entry.get("aliases", []):
                self._alias_to_standard[alias.lower()] = standard
            self._alias_to_standard[standard.lower()] = standard
            if entry.get("inverse"):
                self._inverse_map[standard] = entry["inverse"]

    def normalize(self, relations: list[Relation]) -> list[Relation]:
        """
        Normalize relation names using the synonym table.

        - Replace aliases with standard names
        - Merge relations with same standard name + same domain/range
        - Add inverse relation IDs where specified

        Args:
            relations: List of Relation objects

        Returns:
            Normalized relation list
        """
        # Step 1: Replace aliases with standard names
        for rel in relations:
            standard = self._alias_to_standard.get(rel.name.lower())
            if standard and standard != rel.name:
                rel.aliases.append(rel.name)
                rel.name = standard

        # Step 2: Set inverse relations
        for rel in relations:
            if rel.name in self._inverse_map and not rel.inverse_relation_id:
                inverse_name = self._inverse_map[rel.name]
                # Find the inverse relation in the list
                for other in relations:
                    if other.name == inverse_name:
                        rel.inverse_relation_id = other.id
                        other.inverse_relation_id = rel.id
                        break

        # Step 3: Merge relations with same name + domain + range
        merged = {}
        for rel in relations:
            key = (rel.name, rel.domain_concept_id, rel.range_concept_id)
            if key in merged:
                existing = merged[key]
                existing.aliases.extend(rel.aliases)
                existing.aliases = list(set(existing.aliases))
                existing.confidence = max(existing.confidence, rel.confidence)
            else:
                merged[key] = rel

        result = list(merged.values())
        normalized_count = len(relations) - len(result)
        if normalized_count > 0:
            logger.info(f"Relation normalization: {len(relations)} -> {len(result)} "
                         f"({normalized_count} merged)")

        return result

    def add_synonym_entry(self, standard_name: str, aliases: list[str],
                          domain: str = "", range: str = "", inverse: str = "") -> None:
        """Add a new synonym entry at runtime."""
        self.synonym_table.append({
            "standard_name": standard_name,
            "aliases": aliases,
            "domain": domain,
            "range": range,
            "inverse": inverse,
        })
        for alias in aliases:
            self._alias_to_standard[alias.lower()] = standard_name
        self._alias_to_standard[standard_name.lower()] = standard_name
        if inverse:
            self._inverse_map[standard_name] = inverse

    @property
    def inverse_map(self) -> dict[str, str]:
        """Mapping from relation name to its inverse relation name."""
        return self._inverse_map
