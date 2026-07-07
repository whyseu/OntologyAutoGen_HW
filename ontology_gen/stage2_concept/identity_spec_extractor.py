"""Identity specification extractor (Category 2.4).

Extracts unique identity rules from DDL primary keys and unique constraints.
"""
from __future__ import annotations

import logging

from ..models import Concept

logger = logging.getLogger("ontology_gen.identity_spec_extractor")


class IdentitySpecExtractor:
    def extract(
        self,
        concepts: list[Concept],
        parsed_tables: list[dict],
    ) -> list[Concept]:
        # Build table_name -> primary key mapping
        table_pk_map = {}
        for table in parsed_tables:
            tname = table.get("table_name", "")
            pk_cols = table.get("primary_key", [])
            if not pk_cols:
                # Fallback: find columns marked as primary_key
                pk_cols = [
                    col["name"]
                    for col in table.get("columns", [])
                    if col.get("primary_key")
                ]
            if pk_cols:
                table_pk_map[tname.lower()] = pk_cols

        assigned = 0
        for concept in concepts:
            if concept.identity_spec:
                continue

            # Try to match concept to a table
            ref_table = None
            if concept.source_ref and "table:" in concept.source_ref:
                ref_table = concept.source_ref.split("table:")[1].strip().lower()
            elif concept.name_en:
                ref_table = concept.name_en.lower()

            if ref_table and ref_table in table_pk_map:
                pk_cols = table_pk_map[ref_table]
                if len(pk_cols) == 1:
                    concept.identity_spec = pk_cols[0]
                else:
                    concept.identity_spec = " + ".join(pk_cols)
                assigned += 1

        logger.info(f"Identity spec: assigned {assigned}/{len(concepts)} concepts")
        return concepts
