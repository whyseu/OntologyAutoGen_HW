"""Algorithm 1.1: Data quality scoring.

Evaluates each data source on a 0-10 scale across 5 dimensions.
Tables scoring below the threshold (< 5) must undergo data remediation first.
"""
from __future__ import annotations

import re
from typing import Optional

from ..config import Config
from ..utils import logger

# Patterns that indicate meaningless table/column names
_MEANINGLESS_TABLE_PATTERNS = re.compile(
    r"^(tmp_|temp_|backup_|bak_|t\d|test_|copy_)", re.IGNORECASE
)
_MEANINGLESS_COL_PATTERNS = re.compile(
    r"^(c\d|col\d|field\d|tmp_|f\d)", re.IGNORECASE
)


class QualityScorer:
    """Score data sources on a 0-10 quality scale."""

    def __init__(self, config: Config):
        self.config = config

    def score_rdb_table(
        self,
        table_name: str,
        columns: list[dict],
        ddl_comments: dict[str, str] | None = None,
        null_rates: dict[str, float] | None = None,
        has_foreign_keys: bool = False,
    ) -> int:
        """
        Score an RDB table on 5 dimensions (max 10 points):

        1. Table name has semantic meaning (not tmp_/t1/backup_): +3
        2. Column names have semantic meaning: +2
        3. DDL has comments: +2
        4. Null rate < 30%: +2
        5. Has foreign key definitions: +1

        Args:
            table_name: Name of the table
            columns: List of {name, type, comment, ...}
            ddl_comments: {column_name: comment} or {table_name: comment}
            null_rates: {column_name: null_rate_0_to_1}
            has_foreign_keys: Whether the table has FK definitions

        Returns:
            Integer score 0-10
        """
        ddl_comments = ddl_comments or {}
        null_rates = null_rates or {}

        score = 0

        # Rule 1: Table name has semantic meaning (+3)
        if not _MEANINGLESS_TABLE_PATTERNS.match(table_name):
            score += 3

        # Rule 2: Column names have semantic meaning (+2)
        if columns:
            meaningful_cols = sum(
                1 for c in columns
                if not _MEANINGLESS_COL_PATTERNS.match(c.get("name", ""))
            )
            ratio = meaningful_cols / len(columns)
            if ratio >= 0.8:
                score += 2
            elif ratio >= 0.5:
                score += 1

        # Rule 3: DDL has comments (+2)
        table_comment = ddl_comments.get(table_name, "")
        col_comments = [
            ddl_comments.get(c["name"], c.get("comment", ""))
            for c in columns
        ]
        commented_count = sum(1 for c in col_comments if c and c.strip())
        if table_comment and commented_count >= len(columns) * 0.6:
            score += 2
        elif commented_count >= len(columns) * 0.3:
            score += 1

        # Rule 4: Null rate < 30% (+2)
        if null_rates:
            avg_null = sum(null_rates.values()) / len(null_rates) if null_rates else 1.0
            if avg_null < self.config.null_rate_warning:
                score += 2
            elif avg_null < self.config.null_rate_ignore:
                score += 1
        else:
            # No null rate data available — assume moderate
            score += 1

        # Rule 5: Has foreign keys (+1)
        if has_foreign_keys:
            score += 1

        return min(score, 10)

    def score_document(self, text_length: int, has_structure: bool) -> int:
        """
        Score a parsed document (simplified).

        Args:
            text_length: Length of parsed text
            has_structure: Whether the document has heading/section structure

        Returns:
            Integer score 0-10
        """
        score = 0
        if text_length > 500:
            score += 4
        elif text_length > 100:
            score += 2
        if has_structure:
            score += 3
        if text_length > 2000:
            score += 2  # substantial content
        if text_length > 5000:
            score += 1  # rich content
        return min(score, 10)

    def should_process(self, score: int) -> bool:
        """Whether a data source with this score should enter the pipeline."""
        return score >= self.config.quality_min_score

    def score_all_tables(self, tables: list[dict]) -> list[dict]:
        """
        Score all tables from parsed DDL.

        Args:
            tables: List of parsed table dicts from utils.parse_ddl()

        Returns:
            List of {table_name, score, should_process, reason}
        """
        results = []
        for table in tables:
            table_name = table["table_name"]
            columns = table["columns"]
            has_fk = len(table.get("foreign_keys", [])) > 0

            # Build comments dict
            comments = {table_name: table.get("comment", "")}
            for col in columns:
                comments[col["name"]] = col.get("comment", "")

            score = self.score_rdb_table(
                table_name=table_name,
                columns=columns,
                ddl_comments=comments,
                has_foreign_keys=has_fk,
            )

            result = {
                "table_name": table_name,
                "score": score,
                "should_process": self.should_process(score),
                "has_fk": has_fk,
                "column_count": len(columns),
                "reason": "" if self.should_process(score) else f"Score {score} < {self.config.quality_min_score}, needs data remediation",
            }
            results.append(result)
            logger.info(f"Quality score for '{table_name}': {score}/10 ({'PASS' if result['should_process'] else 'FAIL'})")

        return results
