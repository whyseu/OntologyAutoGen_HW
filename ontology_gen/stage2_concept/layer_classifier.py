"""Concept layer classifier (Category 2.1).

Classifies concepts into data/logic/application layers based on
source type and business context.
"""
from __future__ import annotations

import logging
from typing import Optional

from ..config import Config
from ..llm_client import LLMClient
from ..models import Concept, ConceptLayer

logger = logging.getLogger("ontology_gen.layer_classifier")


LAYER_CLASSIFICATION_PROMPT = """# 任务
你是一个本体工程师。请将以下概念分类到三个层次：
- data（数据层）：直接对应数据库表/存储实体的概念
- logic（逻辑层）：代表业务逻辑、状态机、计算规则的概念
- application（应用层）：面向用户操作、界面交互的概念

# 概念列表
{concepts}

# 输出格式（严格 JSON）
{{"classifications": [{{"name": "概念名", "layer": "data|logic|application", "reason": "分类理由"}}]}}
"""


class LayerClassifier:
    def __init__(self, config: Config, llm: LLMClient):
        self.config = config
        self.llm = llm

    def classify(
        self,
        concepts: list[Concept],
        parsed_tables: list[dict],
        docs_text: str,
    ) -> list[Concept]:
        # Rule-based classification
        table_names = {t.get("table_name", "").lower() for t in parsed_tables}
        for c in concepts:
            c.layer = self._rule_based_classify(c, table_names, docs_text)

        # LLM refinement
        if self.config.llm_available and self.llm and concepts:
            self._llm_refine(concepts)

        layer_counts = {}
        for c in concepts:
            lv = c.layer.value
            layer_counts[lv] = layer_counts.get(lv, 0) + 1
        logger.info(f"Layer classification: {layer_counts}")

        return concepts

    def _rule_based_classify(
        self,
        concept: Concept,
        table_names: set[str],
        docs_text: str,
    ) -> ConceptLayer:
        name_lower = concept.name.lower()
        name_en_lower = (concept.name_en or "").lower()

        # Concepts from RDB with direct table mapping -> DATA
        if concept.source.value == "rdb":
            if name_en_lower in table_names or name_lower in table_names:
                return ConceptLayer.DATA

        # Keywords indicating logic layer
        logic_keywords = ["状态", "流程", "规则", "策略", "计算", "校验", "审核",
                          "status", "workflow", "rule", "policy", "validation"]
        for kw in logic_keywords:
            if kw in name_lower or kw in name_en_lower:
                return ConceptLayer.LOGIC

        # Keywords indicating application layer
        app_keywords = ["页面", "界面", "按钮", "表单", "通知", "提醒", "导航",
                        "page", "form", "button", "notification", "ui", "view"]
        for kw in app_keywords:
            if kw in name_lower or kw in name_en_lower:
                return ConceptLayer.APPLICATION

        # Text-sourced concepts default to LOGIC (business concepts from docs)
        if concept.source.value == "text":
            return ConceptLayer.LOGIC

        return ConceptLayer.DATA

    def _llm_refine(self, concepts: list[Concept]) -> None:
        concept_list = ", ".join(c.name for c in concepts[:50])
        prompt = LAYER_CLASSIFICATION_PROMPT.format(concepts=concept_list)

        messages = [
            {"role": "system", "content": "You are an ontology engineer. Respond in JSON only."},
            {"role": "user", "content": prompt},
        ]
        result = self.llm.chat_json(messages)

        if not result or "classifications" not in result:
            return

        name_to_concept = {c.name: c for c in concepts}
        layer_map = {"data": ConceptLayer.DATA, "logic": ConceptLayer.LOGIC, "application": ConceptLayer.APPLICATION}

        for item in result.get("classifications", []):
            name = item.get("name", "")
            layer_str = item.get("layer", "")
            if name in name_to_concept and layer_str in layer_map:
                name_to_concept[name].layer = layer_map[layer_str]
