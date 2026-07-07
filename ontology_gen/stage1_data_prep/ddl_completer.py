"""Algorithm 1.2: DDL semantic completion.

Uses LLM to infer business meaning for tables/columns missing comments,
then applies 3-layer validation (LLM inference -> cross-validation -> manual review).
"""
from __future__ import annotations

import re
from typing import Optional

from ..config import Config
from ..llm_client import LLMClient
from ..utils import logger


# Prompt template for DDL completion
DDL_COMPLETION_PROMPT = """# 任务
你是一位数据库架构师和领域专家。
给定一张数据库表的 CREATE TABLE 语句（可能缺少注释），
请：
1. 推断每张表的业务含义（这张表是干什么的）
2. 推断每个字段的业务含义（这个字段存的是什么）
3. 输出完整的 CREATE TABLE 语句，包含所有注释

# 推断规则
- 优先根据字段名、表名推断
- 如果字段名完全无意义（如 col1, tmp），根据字段类型和枚举值推断
- 不要凭空捏造含义——如果确实无法推断，注释写 "unknown"

# 输入
{ddl}
-- 实例数据（前3行）：
{sample_data}

# 输出格式（严格 JSON）
{{
  "table_name": "表名",
  "table_comment": "推断的表业务含义",
  "columns": [
    {{
      "name": "字段名",
      "type": "字段类型",
      "comment": "推断的字段业务含义",
      "confidence": "high|medium|low"
    }}
  ]
}}"""


class DDLCompleter:
    """LLM-powered DDL semantic completion with 3-layer validation."""

    def __init__(self, config: Config, llm_client: LLMClient):
        self.config = config
        self.llm = llm_client

    def complete(
        self,
        table_name: str,
        raw_ddl: str,
        sample_rows: list[dict] | None = None,
        data_dictionary: dict | None = None,
    ) -> dict:
        """
        Complete DDL with semantic comments.

        Layer 1: LLM inference — generate comments via LLM
        Layer 2: Cross-validation — compare with data dictionary if available
        Layer 3: Manual review marking — output confidence for each field

        Args:
            table_name: Name of the table
            raw_ddl: Original CREATE TABLE statement
            sample_rows: Sample data rows (first 3)
            data_dictionary: Optional {field_name: description} for cross-validation

        Returns:
            {
                "table_name": str,
                "completed_ddl": str,           # DDL with comments
                "field_annotations": list[dict], # [{field, llm_inferred, confirmed, confidence}]
                "overall_confidence": float,
                "cross_validated": bool,
            }
        """
        sample_str = self._format_sample_rows(sample_rows or [])

        # Layer 1: LLM inference
        llm_result = self._llm_infer(raw_ddl, sample_str)

        if not llm_result:
            # Degraded mode: return original DDL without completion
            logger.warning(f"LLM not available, skipping DDL completion for '{table_name}'")
            return {
                "table_name": table_name,
                "completed_ddl": raw_ddl,
                "field_annotations": [],
                "overall_confidence": 0.0,
                "cross_validated": False,
            }

        # Layer 2: Cross-validation with data dictionary
        cross_validated = False
        if data_dictionary:
            llm_result = self._cross_validate(llm_result, data_dictionary)
            cross_validated = True

        # Layer 3: Build field annotations with confidence
        field_annotations = self._build_annotations(llm_result)

        # Generate completed DDL
        completed_ddl = self._generate_completed_ddl(table_name, llm_result)

        # Overall confidence
        confidences = [f.get("confidence_num", 0.5) for f in field_annotations]
        overall_conf = sum(confidences) / len(confidences) if confidences else 0.0

        logger.info(f"DDL completion for '{table_name}': overall confidence={overall_conf:.2f}")

        return {
            "table_name": table_name,
            "completed_ddl": completed_ddl,
            "field_annotations": field_annotations,
            "overall_confidence": overall_conf,
            "cross_validated": cross_validated,
        }

    def _llm_infer(self, ddl: str, sample_str: str) -> dict | None:
        """Layer 1: Use LLM to infer table/column meanings."""
        prompt = DDL_COMPLETION_PROMPT.format(ddl=ddl, sample_data=sample_str)
        messages = [
            {"role": "system", "content": "You are a database architect and domain expert. Always respond in JSON."},
            {"role": "user", "content": prompt},
        ]
        result = self.llm.chat_json(messages, temperature=0.1)
        if not result:
            return None
        return result

    def _cross_validate(self, llm_result: dict, data_dict: dict) -> dict:
        """Layer 2: Cross-validate LLM inferences against data dictionary."""
        for col in llm_result.get("columns", []):
            col_name = col.get("name", "")
            llm_inferred = col.get("comment", "")

            # Check if data dictionary has this field
            dict_desc = data_dict.get(col_name) or data_dict.get(col_name.lower())

            if dict_desc:
                # Compare LLM inference with data dictionary
                if self._text_similarity(llm_inferred, dict_desc) > 0.7:
                    col["confidence"] = "high"
                    col["confirmed"] = dict_desc  # Use dictionary version
                else:
                    col["confidence"] = "low"
                    col["confirmed"] = None  # Needs manual review
                    col["dict_value"] = dict_desc

        return llm_result

    @staticmethod
    def _text_similarity(a: str, b: str) -> float:
        """Simple text similarity based on character overlap."""
        if not a or not b:
            return 0.0
        set_a = set(a)
        set_b = set(b)
        intersection = set_a & set_b
        union = set_a | set_b
        return len(intersection) / len(union) if union else 0.0

    @staticmethod
    def _build_annotations(llm_result: dict) -> list[dict]:
        """Layer 3: Build field annotation records with confidence levels."""
        annotations = []
        confidence_map = {"high": 0.9, "medium": 0.6, "low": 0.3}

        for col in llm_result.get("columns", []):
            confidence_str = col.get("confidence", "medium")
            annotations.append({
                "field": col.get("name", ""),
                "llm_inferred": col.get("comment", ""),
                "confirmed": col.get("confirmed", col.get("comment", "")),
                "confidence": confidence_str,
                "confidence_num": confidence_map.get(confidence_str, 0.5),
            })

        return annotations

    @staticmethod
    def _generate_completed_ddl(table_name: str, llm_result: dict) -> str:
        """Generate a completed CREATE TABLE statement with comments."""
        table_comment = llm_result.get("table_comment", "")
        columns = llm_result.get("columns", [])

        lines = [f"CREATE TABLE {table_name} ("]
        for i, col in enumerate(columns):
            name = col.get("name", "")
            col_type = col.get("type", "VARCHAR(255)")
            comment = col.get("comment", "")
            line = f"    {name} {col_type}"
            if comment:
                line += f" COMMENT '{comment}'"
            if i < len(columns) - 1:
                line += ","
            lines.append(line)
        lines.append(")")

        if table_comment:
            lines.append(f"COMMENT '{table_comment}';")
        else:
            lines[-1] += ";"

        return "\n".join(lines)

    @staticmethod
    def _format_sample_rows(rows: list[dict]) -> str:
        """Format sample rows for LLM prompt."""
        if not rows:
            return "(no sample data available)"
        lines = []
        for i, row in enumerate(rows[:3]):
            lines.append(f"Row {i+1}: {row}")
        return "\n".join(lines)
