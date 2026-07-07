"""Ontology context builder: serialize the ontology into LLM-readable text.

This produces a compact, structured text block that can be prepended to an LLM
prompt, turning "no ontology" LLM calls into "with ontology" LLM calls.

The text is organized so the LLM can cite specific sections:
  - Domain summary
  - Concept catalog (name, aliases, layer, description)
  - Taxonomy (is-a hierarchy)
  - Relations (domain --[rel]--> range)
  - Properties (with validation rules + derived formulas)
  - Axioms (subClassOf / domain / range / inverseOf)
  - Trigger rules (ECA)
  - Derived rules (conditional classification)
  - Business operations / service compositions
  - Permission model

Two output modes:
  - full:        the entire ontology (large, ~thousands of tokens)
  - relevant(query): only the slice relevant to a natural-language query,
    computed by keyword overlap with concept/relation/property names.
"""
from __future__ import annotations

import logging
from typing import Optional

from .ontology_loader import OntologyIndex

logger = logging.getLogger("ontology_gen.reasoning.context")


class OntologyContextBuilder:
    """Build LLM-readable context strings from an OntologyIndex."""

    def __init__(self, index: OntologyIndex):
        self.idx = index

    # ================================================================
    # Full context
    # ================================================================
    def build_full_context(self, max_concepts: int = 0) -> str:
        """Build the complete ontology context text.

        Args:
            max_concepts: if >0, limit concept catalog to that many (for
              token budgeting). 0 = all.
        """
        sections: list[str] = []
        sections.append(self._section_domain_summary())
        sections.append(self._section_concept_catalog(max_concepts))
        sections.append(self._section_taxonomy())
        sections.append(self._section_relations())
        sections.append(self._section_properties())
        sections.append(self._section_axioms())
        sections.append(self._section_triggers())
        sections.append(self._section_derived_rules())
        sections.append(self._section_operations())
        sections.append(self._section_permissions())
        return "\n\n".join(sections)

    # ================================================================
    # Query-relevant slice
    # ================================================================
    def build_relevant_context(self, query: str,
                               max_concepts: int = 40) -> str:
        """Build a context slice relevant to a natural-language query.

        Strategy: tokenize the query, find concepts/relations/properties
        whose names or aliases overlap with query tokens, then include
        their ancestors, descendants, direct relations, and properties.
        """
        relevant_ids = self._find_relevant_concepts(query)
        if not relevant_ids:
            # fall back to a small summary
            return self._section_domain_summary() + "\n\n" + \
                   self._section_concept_catalog(15)

        # expand: ancestors + descendants of each relevant concept
        expanded = set(relevant_ids)
        for cid in list(relevant_ids):
            for a in self.idx.get_ancestors(cid):
                expanded.add(a)
            for d in self.idx.get_descendants(cid)[:5]:
                expanded.add(d)
        # cap
        expanded_list = list(expanded)[:max_concepts]

        sections: list[str] = []
        sections.append(self._section_domain_summary())
        sections.append(self._section_concept_catalog_subset(expanded_list))
        sections.append(self._section_taxonomy_subset(expanded_list))
        sections.append(self._section_relations_subset(expanded_list))
        sections.append(self._section_properties_subset(expanded_list))
        sections.append(self._section_axioms_subset(expanded_list))
        sections.append(self._section_triggers())
        sections.append(self._section_derived_rules())
        return "\n\n".join(sections)

    # ================================================================
    # Section builders
    # ================================================================
    def _section_domain_summary(self) -> str:
        stats = self.idx.metadata.get("stats", {})
        lines = [
            "【领域本体概览】",
            f"领域：{self.idx.domain}",
            f"概念数：{len(self.idx.concept_by_id)}",
            f"属性数：{len(self.idx.property_by_id)}",
            f"关系数：{len(self.idx.relation_by_id)}",
            f"公理数：{len(self.idx.raw_axioms)}",
            f"触发规则数：{len(self.idx.raw_triggers)}",
            f"派生属性数：{len([p for p in self.idx.raw_properties if p.get('is_derived')])}",
        ]
        return "\n".join(lines)

    def _section_concept_catalog(self, max_concepts: int = 0) -> str:
        ids = list(self.idx.concept_by_id.keys())
        if max_concepts > 0:
            ids = ids[:max_concepts]
        return self._section_concept_catalog_subset(ids)

    def _section_concept_catalog_subset(self, ids: list[str]) -> str:
        lines = ["【概念目录】"]
        for cid in ids:
            c = self.idx.concept_ref(cid)
            if not c:
                continue
            aliases = ", ".join(c.get("aliases") or []) or "无"
            desc = c.get("description") or "无"
            lines.append(
                f"- {c.get('name')}({c.get('id')}) "
                f"[层:{c.get('layer')} 来源:{c.get('source')}] "
                f"别名:{aliases} 描述:{desc}"
            )
        return "\n".join(lines)

    def _section_taxonomy(self) -> str:
        return self._section_taxonomy_subset(list(self.idx.concept_by_id.keys()))

    def _section_taxonomy_subset(self, ids: list[str]) -> str:
        lines = ["【概念层次 (is-a)】"]
        id_set = set(ids)
        for a in self.idx.axioms_by_type.get("subClassOf", []):
            subj = self.idx.resolve_concept_id(a.get("subject"))
            obj = self.idx.resolve_concept_id(a.get("obj"))
            if not subj or not obj:
                continue
            if subj in id_set or obj in id_set:
                lines.append(
                    f"- {self.idx.concept_name(subj)} ⊑ {self.idx.concept_name(obj)}"
                )
        return "\n".join(lines) if len(lines) > 1 else "【概念层次】无"

    def _section_relations(self) -> str:
        return self._section_relations_subset(list(self.idx.concept_by_id.keys()))

    def _section_relations_subset(self, ids: list[str]) -> str:
        lines = ["【关系】"]
        id_set = set(ids)
        for r in self.idx.raw_relations:
            dom = r.get("domain_concept_id")
            rng = r.get("range_concept_id")
            if dom in id_set or rng in id_set:
                lines.append(
                    f"- {self.idx.concept_name(dom)} --[{r.get('name')}"
                    f"({r.get('cardinality')})]--> {self.idx.concept_name(rng)}"
                    + (f"  说明:{r.get('description')}" if r.get('description') else "")
                )
        return "\n".join(lines) if len(lines) > 1 else "【关系】无"

    def _section_properties(self) -> str:
        return self._section_properties_subset(list(self.idx.concept_by_id.keys()))

    def _section_properties_subset(self, ids: list[str]) -> str:
        lines = ["【属性】"]
        id_set = set(ids)
        for p in self.idx.raw_properties:
            if p.get("domain_concept_id") in id_set:
                parts = [f"- {self.idx.concept_name(p.get('domain_concept_id'))}.{p.get('name')}"
                         f"({p.get('value_type')})"]
                if p.get("is_derived"):
                    parts.append(f" 派生[{p.get('derivation_type')}]: {p.get('derivation_formula')}")
                if p.get("validation_regex"):
                    parts.append(f" 正则:{p.get('validation_regex')}")
                if p.get("enum_values"):
                    parts.append(f" 枚举:{p.get('enum_values')}")
                if p.get("min_value") is not None:
                    parts.append(f" 范围:[{p.get('min_value')},{p.get('max_value')}]")
                if p.get("max_length"):
                    parts.append(f" 最大长度:{p.get('max_length')}")
                lines.append("".join(parts))
        return "\n".join(lines) if len(lines) > 1 else "【属性】无"

    def _section_axioms(self) -> str:
        return self._section_axioms_subset(list(self.idx.concept_by_id.keys()))

    def _section_axioms_subset(self, ids: list[str]) -> str:
        lines = ["【公理约束】"]
        id_set = set(ids)
        for atype, axioms in self.idx.axioms_by_type.items():
            for a in axioms:
                subj = a.get("subject")
                obj = a.get("obj")
                # resolve to ids for filtering
                subj_id = self.idx.resolve_concept_id(subj) or subj
                obj_id = self.idx.resolve_concept_id(obj) or obj
                if atype == "subClassOf":
                    if subj_id in id_set or obj_id in id_set:
                        lines.append(f"- subClassOf({subj}, {obj})  置信:{a.get('confidence')}")
                elif atype == "domain":
                    lines.append(f"- domain({subj}) = {obj}  置信:{a.get('confidence')}")
                elif atype == "range":
                    lines.append(f"- range({subj}) = {obj}  置信:{a.get('confidence')}")
                elif atype == "inverseOf":
                    lines.append(f"- inverseOf({subj}, {obj})")
        return "\n".join(lines) if len(lines) > 1 else "【公理约束】无"

    def _section_triggers(self) -> str:
        lines = ["【触发规则 (ECA)】"]
        for tr in self.idx.raw_triggers:
            lines.append(
                f"- {tr.get('name')} [类型:{tr.get('event_type')}]\n"
                f"  事件:{tr.get('event_detail')} 条件:{tr.get('condition_expression')}\n"
                f"  动作:{tr.get('action_type')} - {tr.get('action_detail')}\n"
                f"  原文:{tr.get('nl_source') or tr.get('description')}"
            )
        return "\n".join(lines) if len(lines) > 1 else "【触发规则】无"

    def _section_derived_rules(self) -> str:
        lines = ["【派生规则 (分类/计算)】"]
        for p in self.idx.raw_properties:
            if not p.get("is_derived"):
                continue
            lines.append(
                f"- {self.idx.concept_name(p.get('domain_concept_id'))}.{p.get('name')}\n"
                f"  类型:{p.get('derivation_type')} 公式:{p.get('derivation_formula')}\n"
                f"  依赖:{p.get('derivation_sources')}"
            )
        return "\n".join(lines) if len(lines) > 1 else "【派生规则】无"

    def _section_operations(self) -> str:
        lines = ["【业务操作】"]
        for op in self.idx.raw_operations[:15]:
            lines.append(f"- {op.get('name')}: {op.get('description')}")
        return "\n".join(lines) if len(lines) > 1 else "【业务操作】无"

    def _section_permissions(self) -> str:
        lines = ["【权限模型】"]
        for ps in self.idx.raw_permissions[:10]:
            lines.append(f"- {ps.get('name')}: {ps.get('description') or ''}")
        # Also include permission subjects if stored
        for ps in self.idx.metadata.get("permission_subjects", [])[:10]:
            lines.append(f"- 角色:{ps}")
        return "\n".join(lines) if len(lines) > 1 else "【权限模型】无"

    # ================================================================
    # Relevance scoring
    # ================================================================
    def _find_relevant_concepts(self, query: str) -> list[str]:
        """Find concept IDs whose name/alias/description overlaps the query."""
        query_lower = query.lower()
        scored: list[tuple[int, str]] = []
        for cid, c in self.idx.concept_by_id.items():
            score = 0
            name = (c.get("name") or "").lower()
            if name and len(name) >= 2 and name in query_lower:
                score += 5
            for alias in (c.get("aliases") or []):
                a = alias.lower()
                if a and len(a) >= 2 and a in query_lower:
                    score += 3
            desc = (c.get("description") or "").lower()
            if desc:
                # character overlap
                for i in range(len(desc) - 1):
                    if desc[i:i+2] in query_lower:
                        score += 1
                        break
            if score > 0:
                scored.append((score, cid))
        scored.sort(reverse=True)
        return [cid for _, cid in scored[:20]]
