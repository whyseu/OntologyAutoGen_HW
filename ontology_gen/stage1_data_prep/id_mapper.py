"""Algorithm 1.3: Cross-system ID mapping (entity alignment).

Aligns the same business entity across different systems (CRM, ERP, data platform)
by finding bridge fields (phone, email, credit code) and building MDM mapping tables.
"""
from __future__ import annotations

import uuid
from typing import Optional

from ..config import Config
from ..utils import logger

# Common bridge fields that can link entities across systems
BRIDGE_FIELDS = {
    "phone": ["phone", "mobile", "tel", "phone_number", "mobile_number", "contact_phone"],
    "email": ["email", "mail", "email_address"],
    "credit_code": ["credit_code", "unified_social_credit_code", "uscc", "tax_id"],
    "id_card": ["id_card", "id_number", "citizen_id"],
    "external_id": ["external_id", "third_party_id", "open_id"],
}


class IDMapper:
    """Cross-system entity alignment via bridge field matching."""

    def __init__(self, config: Config):
        self.config = config

    def find_bridge_fields(self, systems: list[dict]) -> dict[str, list[str]]:
        """
        Step 1-2: Find unique identifiers and bridge fields across systems.

        Args:
            systems: List of {
                "system_name": str,
                "entity_table": str,
                "id_field": str,
                "columns": list[str],
                "sample_data": list[dict]  # sample rows
            }

        Returns:
            {bridge_type: [(system_name, field_name), ...]}
        """
        bridge_map = {}

        for bridge_type, field_names in BRIDGE_FIELDS.items():
            matches = []
            for system in systems:
                for col in system.get("columns", []):
                    col_lower = col.lower()
                    if col_lower in field_names:
                        matches.append((system["system_name"], col))
            if len(matches) >= 2:  # Need at least 2 systems with this field
                bridge_map[bridge_type] = matches
                logger.info(f"Bridge field '{bridge_type}' found in: {matches}")

        return bridge_map

    def build_mapping(
        self,
        systems: list[dict],
        bridge_fields: dict[str, list[tuple[str, str]]],
    ) -> dict:
        """
        Step 3-4: Build MDM mapping table with confidence scoring.

        Confidence levels:
        - high (>0.95): auto-map
        - medium (0.7-0.95): needs human confirmation
        - low (<0.7): don't auto-map, mark for manual processing

        Returns:
            {
                "mapping_table": list[dict],  # MDM mapping records
                "unmapped": list[dict],       # Records that couldn't be mapped
                "coverage": float,            # Mapping coverage ratio
                "by_confidence": {"high": N, "medium": N, "low": N}
            }
        """
        # Collect all entities from all systems
        all_entities = []
        for system in systems:
            for row in system.get("sample_data", []):
                entity = {
                    "system": system["system_name"],
                    "id_field": system["id_field"],
                    "id_value": row.get(system["id_field"]),
                    "data": row,
                }
                all_entities.append(entity)

        # Group by bridge field values
        bridge_groups = {}  # {bridge_type: {value: [entity_indices]}}
        for bridge_type, field_pairs in bridge_fields.items():
            value_map = {}
            for idx, entity in enumerate(all_entities):
                for sys_name, field_name in field_pairs:
                    if entity["system"] == sys_name:
                        val = entity["data"].get(field_name)
                        if val:
                            if val not in value_map:
                                value_map[val] = []
                            value_map[val].append(idx)
            bridge_groups[bridge_type] = value_map

        # Build mapping records
        mapping_table = []
        mapped_indices = set()

        for bridge_type, value_map in bridge_groups.items():
            for value, indices in value_map.items():
                if len(indices) < 2:
                    continue  # Only 1 system has this value, can't bridge

                # Create master ID
                master_id = str(uuid.uuid4())[:16]

                # Build mapping record
                record = {
                    "master_id": master_id,
                    "match_method": bridge_type,
                    "match_confidence": self._calculate_confidence(bridge_type, len(indices)),
                }

                for idx in indices:
                    entity = all_entities[idx]
                    system_name = entity["system"]
                    record[f"{system_name}_id"] = entity["id_value"]
                    mapped_indices.add(idx)

                mapping_table.append(record)

        # Unmapped entities
        unmapped = [
            {
                "system": all_entities[idx]["system"],
                "id_value": all_entities[idx]["id_value"],
                "reason": "No bridge field match found",
            }
            for idx in range(len(all_entities))
            if idx not in mapped_indices
        ]

        # Coverage
        total = len(all_entities)
        mapped = len(mapped_indices)
        coverage = mapped / total if total > 0 else 0.0

        # By confidence
        by_confidence = {"high": 0, "medium": 0, "low": 0}
        for record in mapping_table:
            conf = record["match_confidence"]
            if conf > 0.95:
                by_confidence["high"] += 1
            elif conf >= 0.7:
                by_confidence["medium"] += 1
            else:
                by_confidence["low"] += 1

        logger.info(
            f"ID Mapping: {mapped}/{total} entities mapped "
            f"(coverage: {coverage:.1%}), "
            f"high={by_confidence['high']}, medium={by_confidence['medium']}, low={by_confidence['low']}"
        )

        return {
            "mapping_table": mapping_table,
            "unmapped": unmapped,
            "coverage": coverage,
            "by_confidence": by_confidence,
        }

    @staticmethod
    def _calculate_confidence(bridge_type: str, match_count: int) -> float:
        """Calculate mapping confidence based on bridge type and match count."""
        base_confidence = {
            "phone": 0.98,        # Phone is highly unique
            "email": 0.97,        # Email is highly unique
            "credit_code": 0.99,  # Unified credit code is unique
            "id_card": 0.99,      # ID card is unique
            "external_id": 0.85,  # External IDs may be less reliable
        }
        conf = base_confidence.get(bridge_type, 0.8)
        # More matches = higher confidence (multiple systems agree)
        if match_count > 2:
            conf = min(conf + 0.01 * (match_count - 2), 1.0)
        return conf

    def map(self, systems: list[dict]) -> dict:
        """
        Full ID mapping pipeline (Steps 1-4).

        Args:
            systems: List of system dicts with sample data

        Returns:
            Full mapping result
        """
        bridge_fields = self.find_bridge_fields(systems)
        if not bridge_fields:
            logger.warning("No bridge fields found across systems. Cannot perform ID mapping.")
            return {
                "mapping_table": [],
                "unmapped": [],
                "coverage": 0.0,
                "by_confidence": {"high": 0, "medium": 0, "low": 0},
            }

        return self.build_mapping(systems, bridge_fields)
