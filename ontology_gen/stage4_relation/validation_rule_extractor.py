"""Validation rule extractor (Category 2.5).

Extracts value domain and validation rules from DDL constraints and text.
"""
from __future__ import annotations

import logging
import re

from ..config import Config
from ..llm_client import LLMClient
from ..models import Property

logger = logging.getLogger("ontology_gen.validation_rule_extractor")


VALIDATION_RULE_PROMPT = """# 任务
你是一个数据质量专家。请从以下文本中提取数据验证规则。

# 已知属性列表
{properties}

# 文本
{text}

# 输出格式（严格 JSON）
{{"validations": [{{"property_name": "属性名", "regex": "正则表达式(如有)", "min_value": null, "max_value": null, "max_length": null, "format": "格式说明(如有)", "description": "规则描述"}}]}}
"""


class ValidationRuleExtractor:
    def __init__(self, config: Config, llm: LLMClient):
        self.config = config
        self.llm = llm

    def extract_from_ddl(
        self,
        parsed_tables: list[dict],
        properties: list[Property],
    ) -> list[Property]:
        if not parsed_tables:
            return properties

        # Build column lookup: (table_name, column_name) -> column_info
        col_info_map = {}
        for table in parsed_tables:
            tname = table.get("table_name", "").lower()
            for col in table.get("columns", []):
                col_info_map[(tname, col["name"].lower())] = col

        for prop in properties:
            ref_table = None
            if prop.source_ref and "table:" in prop.source_ref:
                parts = prop.source_ref.split("table:")
                if len(parts) > 1:
                    ref_table = parts[1].strip().lower()
            if not ref_table:
                continue

            col_name = prop.name.lower()
            col_info = col_info_map.get((ref_table, col_name))
            if not col_info:
                continue

            col_type = col_info.get("type", "").upper()
            self._extract_from_column_type(prop, col_type)

        assigned = sum(
            1
            for p in properties
            if p.max_length or p.min_value is not None or p.max_value is not None
        )
        logger.info(f"DDL validation rules: {assigned} properties enriched")
        return properties

    def extract_from_text(
        self,
        text: str,
        properties: list[Property],
    ) -> list[Property]:
        if not text:
            return properties

        self._rule_based_text_extract(text, properties)

        if self.config.llm_available and self.llm:
            self._llm_extract(text, properties)

        return properties

    def _extract_from_column_type(self, prop: Property, col_type: str) -> None:
        # VARCHAR(N) -> max_length
        varchar_match = re.match(r"VARCHAR\((\d+)\)", col_type)
        if varchar_match:
            prop.max_length = int(varchar_match.group(1))

        # CHAR(N) -> max_length
        char_match = re.match(r"CHAR\((\d+)\)", col_type)
        if char_match:
            prop.max_length = int(char_match.group(1))

        # DECIMAL(M,N) -> precision hints
        decimal_match = re.match(r"DECIMAL\((\d+),\s*(\d+)\)", col_type)
        if decimal_match:
            m = int(decimal_match.group(1))
            n = int(decimal_match.group(2))
            integer_digits = m - n
            prop.max_value = 10**integer_digits - 10**(-n)

        # TINYINT UNSIGNED -> 0-255
        if "TINYINT" in col_type:
            if "UNSIGNED" in col_type:
                prop.min_value = 0
                prop.max_value = 255
            else:
                prop.min_value = -128
                prop.max_value = 127

        # Date/datetime format patterns
        if "DATE" in col_type and "TIME" not in col_type:
            prop.format_pattern = "yyyy-MM-dd"
        elif "DATETIME" in col_type or "TIMESTAMP" in col_type:
            prop.format_pattern = "yyyy-MM-dd HH:mm:ss"

    def _rule_based_text_extract(self, text: str, properties: list[Property]) -> None:
        name_to_prop = {}
        for p in properties:
            name_to_prop[p.name] = p
            if p.name_cn:
                name_to_prop[p.name_cn] = p

        # Pattern: "X必须为N位数字" or "X不超过N个字符"
        digit_pattern = re.compile(r"([一-龥]+)必须[为是](\d+)位")
        for match in digit_pattern.finditer(text):
            pname = match.group(1)
            length = int(match.group(2))
            if pname in name_to_prop:
                prop = name_to_prop[pname]
                prop.max_length = length
                prop.validation_regex = r"^\d{" + str(length) + r"}$"

        # Pattern: "X不超过N个字符"
        len_pattern = re.compile(r"([一-龥]+)不超过(\d+)个字符")
        for match in len_pattern.finditer(text):
            pname = match.group(1)
            length = int(match.group(2))
            if pname in name_to_prop:
                name_to_prop[pname].max_length = length

        # Pattern: "X必须大于N" or "X必须>=N"
        min_pattern = re.compile(r"([一-龥]+)必须[大≥]于?[等=]?(\d+(?:\.\d+)?)")
        for match in min_pattern.finditer(text):
            pname = match.group(1)
            val = float(match.group(2))
            if pname in name_to_prop:
                name_to_prop[pname].min_value = val

    def _llm_extract(self, text: str, properties: list[Property]) -> None:
        prop_list = ", ".join(p.name for p in properties[:50])
        prompt = VALIDATION_RULE_PROMPT.format(
            properties=prop_list,
            text=text[:2000],
        )
        messages = [{"role": "system", "content": "You are a data quality expert. Respond in JSON only."}, {"role": "user", "content": prompt}]
        result = self.llm.chat_json(messages)
        if not result:
            return

        name_to_prop = {}
        for p in properties:
            name_to_prop[p.name] = p
            if p.name_cn:
                name_to_prop[p.name_cn] = p

        for item in result.get("validations", []):
            pname = item.get("property_name", "")
            if pname not in name_to_prop:
                continue
            prop = name_to_prop[pname]
            if item.get("regex") and not prop.validation_regex:
                prop.validation_regex = item["regex"]
            if item.get("min_value") is not None and prop.min_value is None:
                prop.min_value = float(item["min_value"])
            if item.get("max_value") is not None and prop.max_value is None:
                prop.max_value = float(item["max_value"])
            if item.get("max_length") is not None and prop.max_length is None:
                prop.max_length = int(item["max_length"])
            if item.get("format") and not prop.format_pattern:
                prop.format_pattern = item["format"]
