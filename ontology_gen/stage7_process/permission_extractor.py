"""Permission extractor (Category 6).

Extracts permission subjects and permission rules from text.
"""
from __future__ import annotations

import logging
import re

from ..config import Config
from ..llm_client import LLMClient
from ..models import Concept, PermissionSubject, PermissionRule
from .prompts import PERMISSION_EXTRACTION_PROMPT

logger = logging.getLogger("ontology_gen.permission_extractor")


class PermissionExtractor:
    def __init__(self, config: Config, llm: LLMClient):
        self.config = config
        self.llm = llm

    def extract_subjects(
        self,
        docs_text: str,
        concepts: list[Concept],
        domain_config: dict | None = None,
    ) -> list[PermissionSubject]:
        subjects: list[PermissionSubject] = []

        # From config
        if domain_config:
            for item in domain_config.get("permission_subjects", []):
                subj = PermissionSubject(
                    name=item.get("name", ""),
                    subject_type=item.get("type", "role"),
                    description=item.get("description"),
                )
                # Handle parent
                parent_name = item.get("parent")
                if parent_name:
                    for s in subjects:
                        if s.name == parent_name:
                            subj.parent_subject_id = s.id
                            break
                subjects.append(subj)

        # Rule-based from text
        if docs_text:
            subjects.extend(self._rule_based_subjects(docs_text, subjects))

        # Deduplicate
        seen = set()
        deduped = []
        for s in subjects:
            if s.name not in seen:
                seen.add(s.name)
                deduped.append(s)

        logger.info(f"Permission subjects: {len(deduped)}")
        return deduped

    def extract_rules(
        self,
        docs_text: str,
        subjects: list[PermissionSubject],
        concepts: list[Concept],
    ) -> list[PermissionRule]:
        if not docs_text:
            return []

        rules: list[PermissionRule] = []

        # Rule-based
        rules.extend(self._rule_based_rules(docs_text, subjects, concepts))

        # LLM-enhanced
        if self.config.llm_available and self.llm:
            rules.extend(self._llm_extract(docs_text, subjects, concepts))

        # Deduplicate
        seen = set()
        deduped = []
        for r in rules:
            if r.name not in seen:
                seen.add(r.name)
                deduped.append(r)

        logger.info(f"Permission rules: {len(deduped)}")
        return deduped

    def _rule_based_subjects(
        self,
        text: str,
        existing: list[PermissionSubject],
    ) -> list[PermissionSubject]:
        subjects = []
        existing_names = {s.name for s in existing}

        # Patterns like "VIP客户", "管理员", "系统管理员"
        role_patterns = [
            re.compile(r"([\w]*管理[员人][\w]*)"),
            re.compile(r"([\w]*客户[\w]*)"),
            re.compile(r"(VIP[\w]*)"),
        ]

        for pattern in role_patterns:
            for match in pattern.finditer(text):
                name = match.group(1).strip()
                if name and len(name) <= 10 and name not in existing_names:
                    subjects.append(PermissionSubject(
                        name=name,
                        subject_type="role",
                    ))
                    existing_names.add(name)

        return subjects

    def _rule_based_rules(
        self,
        text: str,
        subjects: list[PermissionSubject],
        concepts: list[Concept],
    ) -> list[PermissionRule]:
        rules = []
        subj_name_to_id = {s.name: s.id for s in subjects}
        concept_name_to_id = {c.name: c.id for c in concepts}

        # Pattern: "X只能/不能/可以Y"
        perm_patterns = [
            (re.compile(r"([一-龥\w]+)不[能可]以?([一-龥]+)"), "deny"),
            (re.compile(r"([一-龥\w]+)可以([一-龥]+)"), "allow"),
            (re.compile(r"([一-龥\w]+)有权([一-龥]+)"), "allow"),
        ]

        for pattern, effect in perm_patterns:
            for match in pattern.finditer(text):
                subject_name = match.group(1).strip()
                action_desc = match.group(2).strip()

                subj_id = subj_name_to_id.get(subject_name)
                if not subj_id:
                    continue

                # Try to find the object concept
                obj_id = ""
                for cname, cid in concept_name_to_id.items():
                    if cname in action_desc:
                        obj_id = cid
                        break

                if not obj_id:
                    obj_id = "unknown"

                actions = []
                if any(kw in action_desc for kw in ["查看", "查询", "浏览", "查"]):
                    actions.append("read")
                if any(kw in action_desc for kw in ["修改", "更新", "编辑", "改"]):
                    actions.append("write")
                if any(kw in action_desc for kw in ["删除", "移除"]):
                    actions.append("delete")
                if not actions:
                    actions.append("execute")

                rules.append(PermissionRule(
                    name=f"{subject_name}_{effect}_{action_desc[:10]}",
                    description=match.group(0),
                    subject_id=subj_id,
                    object_concept_id=obj_id,
                    actions=actions,
                    effect=effect,
                    source="text",
                ))

        return rules

    def _llm_extract(
        self,
        text: str,
        subjects: list[PermissionSubject],
        concepts: list[Concept],
    ) -> list[PermissionRule]:
        concept_list = ", ".join(c.name for c in concepts[:30])
        prompt = PERMISSION_EXTRACTION_PROMPT.format(
            concepts=concept_list,
            text=text[:2000],
        )
        messages = [{"role": "system", "content": "You are a permission management expert. Respond in JSON only."}, {"role": "user", "content": prompt}]
        result = self.llm.chat_json(messages)
        if not result:
            return []

        subj_name_to_id = {s.name: s.id for s in subjects}
        concept_name_to_id = {c.name: c.id for c in concepts}
        rules = []

        for item in result.get("rules", []):
            subj_name = item.get("subject", "")
            obj_name = item.get("object", "")
            subj_id = subj_name_to_id.get(subj_name, "")
            obj_id = concept_name_to_id.get(obj_name, "")
            if not subj_id or not obj_id:
                continue

            rule = PermissionRule(
                name=item.get("name", ""),
                description=item.get("description", ""),
                subject_id=subj_id,
                object_concept_id=obj_id,
                object_scope=item.get("scope", "all"),
                actions=item.get("actions", []),
                effect=item.get("effect", "allow"),
                condition=item.get("condition"),
                source="llm_inferred",
            )
            if rule.name:
                rules.append(rule)

        return rules
