"""Trigger rule extractor (Category 4.1).

Extracts Event-Condition-Action trigger rules from text.
"""
from __future__ import annotations

import logging
import re

from ..config import Config
from ..llm_client import LLMClient
from ..models import Concept, Rule, TriggerRule
from .prompts import TRIGGER_RULE_EXTRACTION_PROMPT

logger = logging.getLogger("ontology_gen.trigger_rule_extractor")


class TriggerRuleExtractor:
    def __init__(self, config: Config, llm: LLMClient):
        self.config = config
        self.llm = llm

    def extract_from_text(
        self,
        text: str,
        concepts: list[Concept],
    ) -> list[TriggerRule]:
        if not text:
            return []

        rules: list[TriggerRule] = []

        # Rule-based extraction
        rules.extend(self._rule_based_extract(text, concepts))

        # LLM-enhanced extraction
        if self.config.llm_available and self.llm:
            rules.extend(self._llm_extract(text, concepts))

        # Deduplicate by name
        seen = set()
        deduped = []
        for r in rules:
            if r.name not in seen:
                seen.add(r.name)
                deduped.append(r)

        logger.info(f"Trigger rules: {len(deduped)} extracted")
        return deduped

    def convert_from_rules(self, swrl_rules: list[Rule]) -> list[TriggerRule]:
        triggers = []
        for rule in swrl_rules:
            has_temporal = any(
                atom.predicate in ("swrlb:greaterThan", "swrlb:lessThan")
                and any("time" in v.lower() or "date" in v.lower() for v in atom.variables)
                for atom in rule.body
            )
            if has_temporal:
                trigger = TriggerRule(
                    name=f"trigger_from_{rule.name}",
                    description=rule.description,
                    event_type="time_based",
                    event_source=rule.body[0].predicate if rule.body else "",
                    event_detail=rule.nl_source or rule.description,
                    condition_expression=" AND ".join(
                        f"{a.predicate}({', '.join(a.variables)})"
                        for a in rule.body
                    ),
                    action_type="update_field",
                    action_detail=" AND ".join(
                        f"{a.predicate}({', '.join(a.variables)})"
                        for a in rule.head
                    ),
                    source="swrl_conversion",
                    nl_source=rule.nl_source,
                    confidence=rule.confidence,
                )
                triggers.append(trigger)

        if triggers:
            logger.info(f"Converted {len(triggers)} SWRL rules to trigger rules")
        return triggers

    def _rule_based_extract(self, text: str, concepts: list[Concept]) -> list[TriggerRule]:
        rules = []
        concept_names = {c.name for c in concepts}

        # Pattern: "如果...未...则自动..." (timeout triggers)
        timeout_pattern = re.compile(
            r"如果[^，。]*?在(\d+[小时天分钟]+)内未([一-龥\w]+)[，,].*?[将则]自动([一-龥\w]+)"
        )
        for match in timeout_pattern.finditer(text):
            time_window = match.group(1)
            condition = match.group(2)
            action = match.group(3)
            rules.append(TriggerRule(
                name=f"超时{action}",
                description=match.group(0),
                event_type="time_based",
                event_source="",
                event_detail=f"超过{time_window}",
                condition_expression=f"未{condition}",
                action_type="update_field",
                action_detail=action,
                nl_source=match.group(0),
            ))

        # Pattern: "...后..." + "系统自动..." (post-action triggers)
        post_action_pattern = re.compile(
            r"([一-龥\w]+)(?:成功|完成)后[，,]\s*系统[会将]?(?:自动)?([一-龥\w]+)"
        )
        for match in post_action_pattern.finditer(text):
            event = match.group(1)
            action = match.group(2)
            rules.append(TriggerRule(
                name=f"{event}后{action}",
                description=match.group(0),
                event_type="status_transition",
                event_source="",
                event_detail=f"{event}完成",
                condition_expression=f"{event}成功",
                action_type="invoke_service",
                action_detail=action,
                nl_source=match.group(0),
            ))

        return rules

    def _llm_extract(self, text: str, concepts: list[Concept]) -> list[TriggerRule]:
        concept_list = ", ".join(c.name for c in concepts[:30])
        prompt = TRIGGER_RULE_EXTRACTION_PROMPT.format(
            concepts=concept_list,
            text=text[:2000],
        )
        messages = [{"role": "system", "content": "You are a business rule analyst. Respond in JSON only."}, {"role": "user", "content": prompt}]
        result = self.llm.chat_json(messages)
        if not result:
            return []

        rules = []
        for item in result.get("trigger_rules", []):
            rule = TriggerRule(
                name=item.get("name", ""),
                description=item.get("description", ""),
                event_type=item.get("event_type", "data_change"),
                event_source=item.get("event_source", ""),
                event_detail=item.get("event_detail", ""),
                condition_expression=item.get("condition", ""),
                action_type=item.get("action_type", ""),
                action_detail=item.get("action_detail", ""),
                source="llm_inferred",
            )
            if rule.name and rule.event_type:
                rules.append(rule)

        return rules
