"""Operation extractor (Category 5.1/5.2/5.3).

Extracts atomic business operations from text and query logs.
"""
from __future__ import annotations

import logging
import re

from ..config import Config
from ..llm_client import LLMClient
from ..models import Concept, Relation, AtomicOperation
from .prompts import OPERATION_EXTRACTION_PROMPT

logger = logging.getLogger("ontology_gen.operation_extractor")


class OperationExtractor:
    def __init__(self, config: Config, llm: LLMClient):
        self.config = config
        self.llm = llm

    def extract(
        self,
        docs_text: str,
        concepts: list[Concept],
        relations: list[Relation],
    ) -> list[AtomicOperation]:
        if not docs_text:
            return []

        operations: list[AtomicOperation] = []

        # Rule-based: detect verb phrases
        operations.extend(self._rule_based_extract(docs_text, concepts))

        # LLM-enhanced
        if self.config.llm_available and self.llm:
            operations.extend(self._llm_extract(docs_text, concepts))

        # Deduplicate by name
        seen = set()
        deduped = []
        for op in operations:
            if op.name not in seen:
                seen.add(op.name)
                deduped.append(op)

        logger.info(f"Operations extracted: {len(deduped)}")
        return deduped

    def extract_from_query_log(
        self,
        queries: list[str],
        concepts: list[Concept],
    ) -> list[AtomicOperation]:
        if not queries:
            return []

        operations = []
        concept_name_map = {}
        for c in concepts:
            if c.name_en:
                concept_name_map[c.name_en.lower()] = c
            concept_name_map[c.name.lower()] = c

        crud_pattern = re.compile(
            r"^\s*(SELECT|INSERT|UPDATE|DELETE)\s+",
            re.IGNORECASE,
        )
        table_pattern = re.compile(
            r"(?:FROM|INTO|UPDATE|JOIN)\s+[`\"']?(\w+)[`\"']?",
            re.IGNORECASE,
        )

        crud_ops = {"SELECT": "查询", "INSERT": "创建", "UPDATE": "更新", "DELETE": "删除"}
        seen = set()

        for query in queries:
            crud_match = crud_pattern.match(query)
            if not crud_match:
                continue

            crud_type = crud_match.group(1).upper()
            tables = table_pattern.findall(query)

            for table in tables:
                table_lower = table.lower()
                if table_lower in concept_name_map:
                    concept = concept_name_map[table_lower]
                    op_name = f"{crud_ops[crud_type]}{concept.name}"
                    if op_name in seen:
                        continue
                    seen.add(op_name)

                    operations.append(AtomicOperation(
                        name=op_name,
                        description=f"{crud_ops[crud_type]}{concept.name}数据",
                        target_concept_id=concept.id,
                        source="query_log",
                    ))

        logger.info(f"Operations from query log: {len(operations)}")
        return operations

    def _rule_based_extract(self, text: str, concepts: list[Concept]) -> list[AtomicOperation]:
        operations = []
        concept_name_to_id = {c.name: c.id for c in concepts}

        # Pattern: "X可以Y" or "X能够Y" (actor can do action)
        action_pattern = re.compile(
            r"([一-龥]+)(?:可以|能够|可)([一-龥]{2,8}(?:[、，]|$))"
        )

        for match in action_pattern.finditer(text):
            actor = match.group(1)
            actions_str = match.group(2).rstrip("、，")
            actions = re.split(r"[、，]", actions_str)

            actor_id = concept_name_to_id.get(actor)
            for action in actions:
                action = action.strip()
                if len(action) >= 2:
                    operations.append(AtomicOperation(
                        name=action,
                        description=f"{actor}{action}",
                        actor_concept_id=actor_id,
                        source="text",
                    ))

        return operations

    def _llm_extract(self, text: str, concepts: list[Concept]) -> list[AtomicOperation]:
        concept_list = ", ".join(c.name for c in concepts[:30])
        prompt = OPERATION_EXTRACTION_PROMPT.format(
            concepts=concept_list,
            text=text[:2000],
        )
        messages = [{"role": "system", "content": "You are a business process analyst. Respond in JSON only."}, {"role": "user", "content": prompt}]
        result = self.llm.chat_json(messages)
        if not result:
            return []

        concept_name_to_id = {c.name: c.id for c in concepts}
        operations = []

        for item in result.get("operations", []):
            name = item.get("name", "")
            if not name:
                continue

            actor = item.get("actor", "")
            target = item.get("target", "")
            op = AtomicOperation(
                name=name,
                description=item.get("description", ""),
                actor_concept_id=concept_name_to_id.get(actor),
                target_concept_id=concept_name_to_id.get(target),
                inputs=item.get("inputs", []),
                outputs=item.get("outputs", []),
                preconditions=item.get("preconditions", []),
                postconditions=item.get("postconditions", []),
                source="llm_inferred",
            )
            operations.append(op)

        return operations
