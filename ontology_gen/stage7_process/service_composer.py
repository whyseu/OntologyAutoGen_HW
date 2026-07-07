"""Service composer (Category 5.4/5.5).

Composes atomic operations into service chains and workflows.
"""
from __future__ import annotations

import logging
import re

from ..config import Config
from ..llm_client import LLMClient
from ..models import AtomicOperation, TriggerRule, ServiceComposition
from .prompts import SERVICE_COMPOSITION_PROMPT

logger = logging.getLogger("ontology_gen.service_composer")


class ServiceComposer:
    def __init__(self, config: Config, llm: LLMClient):
        self.config = config
        self.llm = llm

    def compose_simple(
        self,
        operations: list[AtomicOperation],
        text: str,
    ) -> list[ServiceComposition]:
        if not operations or not text:
            return []

        compositions: list[ServiceComposition] = []

        # Rule-based: detect sequential flow patterns
        compositions.extend(self._detect_sequential_flows(operations, text))

        # LLM-enhanced
        if self.config.llm_available and self.llm:
            compositions.extend(self._llm_compose(operations, text))

        # Deduplicate
        seen = set()
        deduped = []
        for c in compositions:
            if c.name not in seen:
                seen.add(c.name)
                deduped.append(c)

        logger.info(f"Simple compositions: {len(deduped)}")
        return deduped

    def compose_complex(
        self,
        operations: list[AtomicOperation],
        text: str,
        trigger_rules: list[TriggerRule],
    ) -> list[ServiceComposition]:
        if not operations:
            return []

        compositions: list[ServiceComposition] = []

        # Build exception handling compositions from trigger rules
        for trigger in trigger_rules:
            if trigger.event_type == "time_based" and "取消" in trigger.action_detail:
                handler_steps = [
                    {"operation": trigger.action_detail, "order": 1},
                ]
                comp = ServiceComposition(
                    name=f"异常处理_{trigger.name}",
                    description=trigger.description,
                    composition_type="exception_handling",
                    steps=[],
                    exception_handlers=[{
                        "trigger": trigger.condition_expression,
                        "action": trigger.action_detail,
                    }],
                    source="trigger_derived",
                )
                compositions.append(comp)

        logger.info(f"Complex compositions: {len(compositions)}")
        return compositions

    def _detect_sequential_flows(
        self,
        operations: list[AtomicOperation],
        text: str,
    ) -> list[ServiceComposition]:
        compositions = []
        op_name_set = {op.name for op in operations}

        # Pattern: "A -> B -> C" or "A → B → C"
        arrow_pattern = re.compile(r"([一-龥\w]+)\s*[->→]+\s*([一-龥\w]+(?:\s*[->→]+\s*[一-龥\w]+)*)")
        for match in arrow_pattern.finditer(text):
            full_match = match.group(0)
            step_names = re.split(r"\s*[->→]+\s*", full_match)
            step_names = [s.strip() for s in step_names if s.strip()]

            if len(step_names) >= 2:
                steps = [
                    {"operation": name, "order": i + 1}
                    for i, name in enumerate(step_names)
                ]
                compositions.append(ServiceComposition(
                    name=f"流程_{'_'.join(step_names[:3])}",
                    description=full_match,
                    composition_type="sequential",
                    steps=steps,
                    source="text",
                ))

        return compositions

    def _llm_compose(
        self,
        operations: list[AtomicOperation],
        text: str,
    ) -> list[ServiceComposition]:
        op_list = ", ".join(op.name for op in operations[:30])
        prompt = SERVICE_COMPOSITION_PROMPT.format(
            operations=op_list,
            text=text[:2000],
        )
        messages = [{"role": "system", "content": "You are a service orchestration expert. Respond in JSON only."}, {"role": "user", "content": prompt}]
        result = self.llm.chat_json(messages)
        if not result:
            return []

        compositions = []
        for item in result.get("compositions", []):
            name = item.get("name", "")
            if not name:
                continue

            comp_type = item.get("type", "sequential")
            valid_types = {"sequential", "parallel", "conditional", "loop", "exception_handling"}
            if comp_type not in valid_types:
                comp_type = "sequential"

            comp = ServiceComposition(
                name=name,
                description=item.get("description", ""),
                composition_type=comp_type,
                steps=item.get("steps", []),
                exception_handlers=item.get("exception_handlers", []),
                source="llm_inferred",
            )
            compositions.append(comp)

        return compositions
