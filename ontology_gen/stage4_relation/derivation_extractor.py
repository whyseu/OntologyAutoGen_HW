"""Derivation extractor (Category 2.2).

Extracts computed/derived attribute formulas from text and SQL query patterns.
"""
from __future__ import annotations

import logging
import re

from ..config import Config
from ..llm_client import LLMClient
from ..models import Concept, Property

logger = logging.getLogger("ontology_gen.derivation_extractor")


DERIVATION_EXTRACTION_PROMPT = """# 任务
你是一个数据分析师。请从以下文本中识别派生属性（计算得出的属性）的计算规则。

# 已知属性列表
{properties}

# 文本
{text}

# 输出格式（严格 JSON）
{{"derived_properties": [{{"property_name": "属性名", "formula": "计算公式", "type": "formula|aggregation|lookup|conditional", "source_properties": ["源属性1", "源属性2"]}}]}}
"""


class DerivationExtractor:
    def __init__(self, config: Config, llm: LLMClient):
        self.config = config
        self.llm = llm

    def extract_from_text(
        self,
        text: str,
        properties: list[Property],
        concepts: list[Concept],
    ) -> list[Property]:
        if not text:
            return properties

        # Rule-based: detect formula patterns like "A = B + C" or "A = B - C"
        self._rule_based_extract(text, properties)

        # LLM-enhanced
        if self.config.llm_available and self.llm:
            self._llm_extract(text, properties)

        derived_count = sum(1 for p in properties if p.is_derived)
        logger.info(f"Derivation extraction: {derived_count} derived properties found")
        return properties

    def extract_from_query_log(
        self,
        queries: list[str],
        properties: list[Property],
    ) -> list[Property]:
        if not queries:
            return properties

        prop_name_map = {}
        for p in properties:
            prop_name_map[p.name.lower()] = p
            if p.name_cn:
                prop_name_map[p.name_cn.lower()] = p

        agg_pattern = re.compile(
            r"(SUM|COUNT|AVG|MAX|MIN)\s*\(\s*[`\"']?(\w+)[`\"']?\s*\)",
            re.IGNORECASE,
        )

        for query in queries:
            for match in agg_pattern.finditer(query):
                func = match.group(1).upper()
                col_name = match.group(2).lower()
                if col_name in prop_name_map:
                    prop = prop_name_map[col_name]
                    if not prop.is_derived:
                        prop.is_derived = True
                        prop.derivation_type = "aggregation"
                        prop.derivation_formula = f"{func}({prop.name})"

        return properties

    def _rule_based_extract(self, text: str, properties: list[Property]) -> None:
        prop_names = {p.name for p in properties}
        if properties and properties[0].name_cn:
            prop_names.update(p.name_cn for p in properties if p.name_cn)

        # Pattern: "X = Y + Z - W" or "X = Y × Z"
        formula_pattern = re.compile(
            r"([一-龥\w]+)\s*[=＝]\s*([一-龥\w]+(?:\s*[+\-×÷*/]\s*[一-龥\w]+)*)"
        )

        name_to_prop = {}
        for p in properties:
            name_to_prop[p.name] = p
            if p.name_cn:
                name_to_prop[p.name_cn] = p

        for match in formula_pattern.finditer(text):
            target_name = match.group(1).strip()
            formula = match.group(2).strip()

            if target_name in name_to_prop:
                prop = name_to_prop[target_name]
                # Check that formula references known properties
                sources = [n for n in name_to_prop if n in formula and n != target_name]
                if sources:
                    prop.is_derived = True
                    prop.derivation_formula = formula
                    prop.derivation_type = "formula"
                    prop.derivation_sources = [
                        name_to_prop[s].id for s in sources if s in name_to_prop
                    ]

    def _llm_extract(self, text: str, properties: list[Property]) -> None:
        prop_list = ", ".join(p.name for p in properties[:50])
        prompt = DERIVATION_EXTRACTION_PROMPT.format(
            properties=prop_list,
            text=text[:2000],
        )
        messages = [{"role": "system", "content": "You are a data analyst. Respond in JSON only."}, {"role": "user", "content": prompt}]
        result = self.llm.chat_json(messages)
        if not result:
            return

        name_to_prop = {}
        for p in properties:
            name_to_prop[p.name] = p
            if p.name_cn:
                name_to_prop[p.name_cn] = p

        for item in result.get("derived_properties", []):
            pname = item.get("property_name", "")
            if pname in name_to_prop:
                prop = name_to_prop[pname]
                if not prop.is_derived:
                    prop.is_derived = True
                    prop.derivation_formula = item.get("formula", "")
                    prop.derivation_type = item.get("type", "formula")
                    source_names = item.get("source_properties", [])
                    prop.derivation_sources = [
                        name_to_prop[s].id
                        for s in source_names
                        if s in name_to_prop
                    ]
