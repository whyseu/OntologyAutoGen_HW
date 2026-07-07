"""Algorithm 1.5: Null rate filtering and sampling strategy.

Filters out high-null-rate fields and provides stratified sampling
for large tables.
"""
from __future__ import annotations

import random
from typing import Optional

from ..config import Config
from ..utils import logger


class NullFilter:
    """Filter fields by null rate and sample data from large tables."""

    def __init__(self, config: Config):
        self.config = config

    def filter_columns(self, null_rates: dict[str, float]) -> dict:
        """
        Filter columns based on null rates.

        Rules:
        - null_rate > 50%: ignore this column (don't use for ontology)
        - null_rate 30-50%: mark as low confidence
        - null_rate < 30%: normal

        Returns:
            {
                "ignored": [col_names],          # null_rate > 50%
                "low_confidence": [col_names],   # 30% < null_rate <= 50%
                "normal": [col_names],           # null_rate <= 30%
                "report": {col_name: {null_rate, status}}
            }
        """
        ignored = []
        low_confidence = []
        normal = []
        report = {}

        for col, rate in null_rates.items():
            if rate > self.config.null_rate_ignore:
                ignored.append(col)
                status = "ignored"
            elif rate > self.config.null_rate_warning:
                low_confidence.append(col)
                status = "low_confidence"
            else:
                normal.append(col)
                status = "normal"

            report[col] = {"null_rate": rate, "status": status}

        logger.info(
            f"Null filter: {len(ignored)} ignored, "
            f"{len(low_confidence)} low confidence, "
            f"{len(normal)} normal"
        )

        return {
            "ignored": ignored,
            "low_confidence": low_confidence,
            "normal": normal,
            "report": report,
        }

    def sample_data(
        self,
        rows: list[dict],
        non_null_count: int = 0,
    ) -> dict:
        """
        Stratified sampling for large tables.

        Strategy:
        - If table has > sample_non_null rows: sample sample_non_null non-null rows
          + sample_null null rows (for diagnosis)
        - Otherwise: return all rows

        Args:
            rows: Full row data (list of dicts)
            non_null_count: Number of rows with non-null values (for estimation)

        Returns:
            {
                "sampled_data": list[dict],
                "total_rows": int,
                "sampled_count": int,
                "is_sampled": bool,
            }
        """
        total = len(rows)
        if total <= self.config.sample_non_null:
            return {
                "sampled_data": rows,
                "total_rows": total,
                "sampled_count": total,
                "is_sampled": False,
            }

        # Stratified sampling: prefer rows with more non-null values
        def non_null_count_in_row(row: dict) -> int:
            return sum(1 for v in row.values() if v is not None and v != "")

        # Sort by non-null count (descending), take top N
        sorted_rows = sorted(rows, key=non_null_count_in_row, reverse=True)
        sampled = sorted_rows[: self.config.sample_non_null]

        # Also sample some null-heavy rows for diagnosis
        null_heavy = [r for r in rows if non_null_count_in_row(r) < len(r) * 0.3]
        if null_heavy:
            sampled.extend(random.sample(null_heavy, min(self.config.sample_null, len(null_heavy))))

        logger.info(f"Sampled {len(sampled)} rows from {total} total (stratified)")

        return {
            "sampled_data": sampled,
            "total_rows": total,
            "sampled_count": len(sampled),
            "is_sampled": True,
        }

    def detect_skew(self, rows: list[dict], column: str, threshold: float = 0.95) -> dict:
        """
        Detect if a column's value distribution is extremely skewed.

        If 95%+ of values are the same (e.g., "N/A"), that value is likely
        meaningless and should be weighted down.

        Returns:
            {
                "is_skewed": bool,
                "dominant_value": any,
                "dominant_ratio": float,
                "suggestion": str,
            }
        """
        values = [r.get(column) for r in rows if r.get(column) is not None]
        if not values:
            return {"is_skewed": False, "dominant_value": None, "dominant_ratio": 0, "suggestion": ""}

        from collections import Counter
        counter = Counter(values)
        dominant_value, dominant_count = counter.most_common(1)[0]
        ratio = dominant_count / len(values)

        is_skewed = ratio >= threshold
        suggestion = ""
        if is_skewed:
            suggestion = (
                f"Column '{column}' is {ratio:.1%} '{dominant_value}'. "
                f"This value is likely meaningless — weight down in concept extraction."
            )

        return {
            "is_skewed": is_skewed,
            "dominant_value": dominant_value,
            "dominant_ratio": ratio,
            "suggestion": suggestion,
        }

    def filter_and_sample(
        self,
        rows: list[dict],
        null_rates: dict[str, float],
    ) -> dict:
        """
        Combined filtering + sampling.

        Returns:
            {
                "filtered_columns": dict,   # from filter_columns
                "sampled_data": list[dict], # from sample_data
                "skew_report": dict,        # from detect_skew for each column
                "null_report": dict,
            }
        """
        filtered = self.filter_columns(null_rates)
        sampled = self.sample_data(rows)

        # Detect skew for non-ignored columns
        skew_report = {}
        for col in filtered["normal"] + filtered["low_confidence"]:
            skew_report[col] = self.detect_skew(rows, col)

        return {
            "filtered_columns": filtered,
            "sampled_data": sampled["sampled_data"],
            "total_rows": sampled["total_rows"],
            "is_sampled": sampled["is_sampled"],
            "skew_report": skew_report,
            "null_report": filtered["report"],
        }
