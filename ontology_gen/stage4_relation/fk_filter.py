"""Algorithm 4.3: Foreign key business semantic filtering (3-layer rules).

Determines whether a database foreign key represents a business relation
or just a technical association (e.g., log table referencing user table).
"""
from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger("ontology_gen.fk_filter")


class ForeignKeyFilter:
    """3-layer FK business semantic filtering."""

    # System table name patterns (Rule 1 whitelist)
    SYSTEM_TABLE_PATTERNS = {"log", "audit", "session", "cache", "tmp", "backup", "temp"}

    def __init__(self, table_tags: dict[str, str] | None = None):
        """
        Args:
            table_tags: {table_name: "system" | "business"} explicit tags
        """
        self.table_tags = table_tags or {}

    def filter(
        self,
        fk_info: dict,
        table_tags: dict[str, str] | None = None,
        query_log: list[str] | None = None,
        business_terms: list[str] | None = None,
    ) -> dict:
        """
        Apply 3-layer filtering rules to a foreign key.

        Rule 1: System table filter — if source table is a system table, reject
        Rule 2: Business query validation — check if FK pattern appears in business SQL
        Rule 3: Business term check — check if table names contain business terms

        Args:
            fk_info: {"fk_table": str, "fk_column": str, "ref_table": str, "ref_column": str}
            table_tags: {table_name: "system"|"business"} (overrides init tags)
            query_log: List of business query SQL strings
            business_terms: List of business domain terms

        Returns:
            {
                "is_business_relation": bool,
                "reason": str,
                "status": "accepted" | "rejected" | "needs_review",
                "rules_passed": list[str],
            }
        """
        table_tags = {**self.table_tags, **(table_tags or {})}
        query_log = query_log or []
        business_terms = business_terms or []

        fk_table = fk_info.get("fk_table", "")
        ref_table = fk_info.get("ref_table", "")
        rules_passed = []

        # Rule 1: System table filter
        if self._is_system_table(fk_table, table_tags):
            return {
                "is_business_relation": False,
                "reason": f"Source table '{fk_table}' is a system table, not a business table",
                "status": "rejected",
                "rules_passed": [],
            }
        rules_passed.append("rule1_system_filter")

        # Rule 2: Business query validation
        fk_pattern = f"{fk_table}.{fk_info.get('fk_column', '')}"
        used_in_query = any(fk_pattern in q or fk_info.get("fk_column", "") in q for q in query_log)

        if not used_in_query:
            # Not found in business queries — mark for review
            logger.info(f"FK '{fk_pattern}' not found in business queries — needs review")
        else:
            rules_passed.append("rule2_query_validation")

        # Rule 3: Business term check
        tables_involved = f"{fk_table} {ref_table}"
        has_business_term = any(term in tables_involved for term in business_terms)

        if not has_business_term and not used_in_query:
            return {
                "is_business_relation": False,
                "reason": "Tables don't contain business terms and FK not in business queries",
                "status": "rejected",
                "rules_passed": rules_passed,
            }
        rules_passed.append("rule3_business_term")

        # Determine final status
        if used_in_query and has_business_term:
            status = "accepted"
            reason = "Passed all 3 rules: not system table, found in business queries, contains business terms"
        elif has_business_term:
            status = "accepted"
            reason = "Contains business terms (Rule 3 passed), but not found in business queries (Rule 2 needs review)"
        else:
            status = "needs_review"
            reason = "Found in business queries but no business terms — needs manual confirmation"

        return {
            "is_business_relation": status == "accepted",
            "reason": reason,
            "status": status,
            "rules_passed": rules_passed,
        }

    def _is_system_table(self, table_name: str, table_tags: dict[str, str]) -> bool:
        """Check if a table is a system table (Rule 1)."""
        # Check explicit tags first
        if table_tags.get(table_name) == "system":
            return True

        # Check name patterns
        name_lower = table_name.lower()
        for pattern in self.SYSTEM_TABLE_PATTERNS:
            if pattern in name_lower:
                return True

        return False

    def filter_all(
        self,
        fk_list: list[dict],
        table_tags: dict[str, str] | None = None,
        query_log: list[str] | None = None,
        business_terms: list[str] | None = None,
    ) -> list[dict]:
        """
        Filter a list of foreign keys.

        Returns:
            List of {fk_info, result} dicts
        """
        results = []
        for fk_info in fk_list:
            result = self.filter(fk_info, table_tags, query_log, business_terms)
            results.append({"fk_info": fk_info, "result": result})

        accepted = sum(1 for r in results if r["result"]["status"] == "accepted")
        rejected = sum(1 for r in results if r["result"]["status"] == "rejected")
        review = sum(1 for r in results if r["result"]["status"] == "needs_review")

        logger.info(f"FK filtering: {accepted} accepted, {rejected} rejected, {review} needs review")

        return results
