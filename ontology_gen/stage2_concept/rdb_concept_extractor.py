"""Prompt 2.1: RDB path concept extraction.

Extracts candidate entity types and properties from DDL table/column names.
"""
from __future__ import annotations

import logging
from typing import Optional

from ..config import Config
from ..llm_client import LLMClient
from ..models import Concept, Property, SourceType
from ..utils import parse_ddl
from .prompts import RDB_CONCEPT_EXTRACTION_PROMPT

logger = logging.getLogger("ontology_gen.rdb_extractor")


class RDBConceptExtractor:
    """Extract concepts from RDB DDL (table names -> entity types, columns -> properties)."""

    def __init__(self, config: Config, llm_client: LLMClient):
        self.config = config
        self.llm = llm_client

    def extract_from_ddl(self, ddl_text: str) -> list[Concept]:
        """
        Extract concepts from DDL text.

        Uses both rule-based extraction and LLM enhancement.

        Args:
            ddl_text: Raw DDL text (CREATE TABLE statements)

        Returns:
            List of Concept objects
        """
        tables = parse_ddl(ddl_text)
        all_concepts = []

        for table in tables:
            concepts = self._extract_from_table(table)
            all_concepts.extend(concepts)

        logger.info(f"RDB concept extraction: {len(all_concepts)} concepts from {len(tables)} tables")
        return all_concepts

    def _extract_from_table(self, table: dict) -> list[Concept]:
        """Extract concepts from a single parsed table."""
        concepts = []
        table_name = table["table_name"]
        table_comment = table.get("comment", "")
        columns = table["columns"]
        foreign_keys = table.get("foreign_keys", [])

        # Rule-based: table name -> entity type
        # Skip system tables (tmp_, log, etc.)
        if not self._is_system_table(table_name):
            concept = Concept(
                name=self._table_name_to_concept(table_name, table_comment),
                name_en=table_name,
                description=table_comment,
                source=SourceType.RDB,
                source_ref=f"table:{table_name}",
                confidence=0.9,
            )
            # Add properties from columns
            for col in columns:
                if not col.get("is_primary_key"):
                    concept.properties.append(col["name"])
            concepts.append(concept)

        # Rule-based: FK referenced tables -> entity types
        for fk in foreign_keys:
            ref_table = fk["ref_table"]
            if not self._is_system_table(ref_table):
                ref_concept = Concept(
                    name=self._table_name_to_concept(ref_table, ""),
                    name_en=ref_table,
                    source=SourceType.RDB,
                    source_ref=f"fk:{table_name}.{fk['fk_column']}->{ref_table}",
                    confidence=0.7,
                )
                # Avoid duplicates
                if not any(c.name == ref_concept.name for c in concepts):
                    concepts.append(ref_concept)

        # LLM enhancement: if available, use LLM to refine extraction
        if self.config.llm_available and self.llm and concepts:
            llm_concepts = self._llm_extract(table)
            if llm_concepts:
                # Merge LLM results with rule-based results
                existing_names = {c.name for c in concepts}
                for lc in llm_concepts:
                    if lc.name not in existing_names:
                        concepts.append(lc)

        return concepts

    def _llm_extract(self, table: dict) -> list[Concept]:
        """Use LLM to extract concepts from a table (Prompt 2.1)."""
        table_name = table["table_name"]
        table_comment = table.get("comment", "")
        columns_str = "\n".join(
            f"  - {c['name']} {c['type']}" + (f" COMMENT '{c['comment']}'" if c.get("comment") else "")
            + (f" ENUM{c['enum_values']}" if c.get("enum_values") else "")
            for c in table["columns"]
        )

        prompt = RDB_CONCEPT_EXTRACTION_PROMPT.format(
            table_name=table_name,
            table_comment=table_comment,
            columns=columns_str,
        )

        messages = [
            {"role": "system", "content": "You are an ontology engineer. Respond in JSON only."},
            {"role": "user", "content": prompt},
        ]

        result = self.llm.chat_json(messages, temperature=0.1)

        concepts = []
        for et in result.get("entity_types", []):
            concepts.append(Concept(
                name=et.get("name", ""),
                source=SourceType.RDB,
                source_ref=et.get("source", ""),
                description=et.get("evidence", ""),
                confidence=0.8,
            ))

        return concepts

    @staticmethod
    def _table_name_to_concept(table_name: str, comment: str) -> str:
        """Convert table name to concept name (prefer Chinese comment)."""
        if comment:
            # Extract Chinese name from comment like "客户信息表"
            # Remove common suffixes
            name = comment.replace("信息表", "").replace("表", "").replace("记录", "").strip()
            if name:
                return name
        return table_name

    @staticmethod
    def _is_system_table(table_name: str) -> bool:
        """Check if a table name indicates a system/temp table."""
        import re
        return bool(re.match(r"^(tmp_|temp_|backup_|system_|log_|audit_|session_|cache_)", table_name, re.IGNORECASE))

    def extract_properties_from_ddl(self, ddl_text: str, concept_map: dict[str, str]) -> list[Property]:
        """
        Extract properties from DDL, mapped to concepts.

        Args:
            ddl_text: Raw DDL text
            concept_map: {table_name: concept_id} mapping

        Returns:
            List of Property objects
        """
        tables = parse_ddl(ddl_text)
        properties = []

        for table in tables:
            table_name = table["table_name"]
            concept_id = concept_map.get(table_name) or concept_map.get(self._table_name_to_concept(table_name, table.get("comment", "")))
            if not concept_id:
                continue

            for col in table["columns"]:
                if col.get("is_primary_key"):
                    continue

                # Skip FK columns (they become relations, not properties)
                fk_columns = {fk["fk_column"] for fk in table.get("foreign_keys", [])}
                if col["name"] in fk_columns:
                    continue

                prop = Property(
                    name=col["name"],
                    domain_concept_id=concept_id,
                    name_cn=col.get("comment", ""),
                    value_type=self._map_sql_type(col["type"]),
                    enum_values=col.get("enum_values", []),
                    source=SourceType.RDB,
                    source_ref=f"{table_name}.{col['name']}",
                    confidence=0.9,
                )
                properties.append(prop)

        logger.info(f"RDB property extraction: {len(properties)} properties")
        return properties

    @staticmethod
    def _map_sql_type(sql_type: str) -> str:
        """Map SQL type to ontology value type."""
        sql_type_lower = sql_type.lower()
        if "int" in sql_type_lower or "bigint" in sql_type_lower:
            return "int"
        if "decimal" in sql_type_lower or "float" in sql_type_lower or "double" in sql_type_lower:
            return "float"
        if "date" in sql_type_lower or "time" in sql_type_lower:
            return "date"
        if "enum" in sql_type_lower:
            return "enum"
        if "bool" in sql_type_lower:
            return "bool"
        return "string"
