"""Symbolic reasoner: deterministic, explainable inference over the ontology.

This is the "with-ontology" reasoning engine that does NOT call an LLM. It
demonstrates how a structured ontology enables sound, traceable conclusions
that a bare LLM may get wrong or hallucinate.

Reasoning capabilities implemented:

  1. Subclass reasoning — transitive closure of subClassOf.
     e.g. iPhone ⊑ 智能手机 ⊑ 电子产品 ⊑ 商品  →  iPhone IS_A 商品
  2. Relation inheritance — a subclass inherits its super-class' relations.
     e.g. VIP客户 ⊑ 客户, 客户 hasOrder 订单  →  VIP客户 hasOrder 订单
  3. Property inheritance — same idea for properties.
  4. Domain/range constraint checks — verifies that a relation only applies
     between its declared (or sub-) domain/range concepts; flags violations.
  5. Derived-property derivation — resolves derivation_formula dependencies
     and computes the property chain (e.g. total_amount = SUM(price*stock)).
  6. ECA trigger firing — given an event + state, find matching trigger rules
     and produce the resulting action (deterministic if-then).
  7. Membership classification — given a concept + a feature, decide which
     subclass it belongs to using subclass axioms + derived rules
     (e.g. annual_spend > 100000 → VIP客户).
  8. Multi-hop path queries — find relation paths between two concepts,
     which a bare LLM often cannot enumerate completely.

Every conclusion returns an InferenceResult with a `proof_chain` — a list of
human-readable steps citing the exact axiom/relation/trigger used — so the
reasoning is fully auditable (the opposite of a black-box LLM).
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Optional

from .ontology_loader import OntologyIndex

logger = logging.getLogger("ontology_gen.reasoning.symbolic")


@dataclass
class ProofStep:
    """A single step in a reasoning proof chain."""
    rule: str          # e.g. "subClassOf", "relation_inheritance", "trigger"
    premise: str       # human-readable premise
    conclusion: str    # human-readable conclusion
    evidence_id: str = ""   # axiom id / relation id / trigger id

    def to_dict(self) -> dict:
        return {
            "rule": self.rule,
            "premise": self.premise,
            "conclusion": self.conclusion,
            "evidence_id": self.evidence_id,
        }


@dataclass
class InferenceResult:
    """The outcome of one reasoning query."""
    query: str
    answer: str
    confidence: float = 1.0
    proof_chain: list[ProofStep] = field(default_factory=list)
    supporting_facts: list[str] = field(default_factory=list)
    method: str = "symbolic"  # symbolic / inheritance / trigger / derivation
    found: bool = True

    def to_dict(self) -> dict:
        return {
            "query": self.query,
            "answer": self.answer,
            "confidence": self.confidence,
            "method": self.method,
            "found": self.found,
            "proof_chain": [s.to_dict() for s in self.proof_chain],
            "supporting_facts": self.supporting_facts,
        }


class SymbolicReasoner:
    """Deterministic reasoner over an OntologyIndex."""

    def __init__(self, index: OntologyIndex):
        self.idx = index

    # ================================================================
    # 1. Subclass reasoning
    # ================================================================
    def is_a(self, child_ref: str, parent_ref: str) -> InferenceResult:
        """Is `child_ref` a subclass of `parent_ref`?

        Resolves names/aliases/ids, then walks the transitive closure.
        """
        child_id = self.idx.resolve_concept_id(child_ref)
        parent_id = self.idx.resolve_concept_id(parent_ref)
        query = f"{child_ref} 是 {parent_ref} 的子类吗？"
        if not child_id or not parent_id:
            return InferenceResult(query, "无法解析概念引用", confidence=0.0,
                                   found=False)
        chain: list[ProofStep] = []
        if child_id == parent_id:
            chain.append(ProofStep("reflexive_subclass",
                                   f"{self._name(child_id)} == {self._name(parent_id)}",
                                   f"{self._name(child_id)} 是自身的子类（自反性）"))
            return InferenceResult(query, "是（自反）", 1.0, chain,
                                   method="subClassOf")
        ancestors = self.idx.get_ancestors(child_id)
        path = self._build_subclass_path(child_id, parent_id)
        if parent_id in ancestors:
            for i, step_id in enumerate(path):
                if i == 0:
                    premise = self._name(child_id)
                else:
                    premise = f"{self._name(path[i-1])} ⊑ {self._name(step_id)}"
                # find the axiom that established this edge
                ax = self._find_subclass_axiom(path[i-1] if i > 0 else child_id,
                                               step_id if i > 0 else None)
                # The path stores edges; reconstruct premise/conclusion
            # Simpler: emit one step per edge in the path
            chain.clear()
            prev = child_id
            for nxt in path:
                ax = self._find_subclass_axiom(prev, nxt)
                chain.append(ProofStep(
                    "subClassOf",
                    f"{self._name(prev)} ⊑ {self._name(nxt)}",
                    f"由公理 subClassOf 推出：{self._name(prev)} 是 {self._name(nxt)} 的子类",
                    evidence_id=ax.get("id", "") if ax else "",
                ))
                prev = nxt
            chain.append(ProofStep(
                "transitive_closure",
                "传递闭包：A⊑B ∧ B⊑C ⟹ A⊑C",
                f"结论：{self._name(child_id)} 是 {self._name(parent_id)} 的子类",
            ))
            return InferenceResult(query, "是", 1.0, chain, method="subClassOf")
        return InferenceResult(query, "否", 0.95, chain, method="subClassOf",
                               found=False)

    def _build_subclass_path(self, child_id: str, parent_id: str
                             ) -> list[str]:
        """Find a concrete path of direct parent edges child->...->parent."""
        # BFS over direct parents
        from collections import deque
        queue = deque([(child_id, [])])
        visited = {child_id}
        while queue:
            node, path = queue.popleft()
            for p in self.idx.subclass_parents.get(node, []):
                if p == parent_id:
                    return path + [p]
                if p not in visited:
                    visited.add(p)
                    queue.append((p, path + [p]))
        return []

    def _find_subclass_axiom(self, child_id: str, parent_id: Optional[str]
                             ) -> Optional[dict]:
        for a in self.idx.axioms_by_type.get("subClassOf", []):
            if (self.idx.resolve_concept_id(a.get("subject")) == child_id
                    and self.idx.resolve_concept_id(a.get("obj")) == parent_id):
                return a
        return None

    # ================================================================
    # 2. Relation inheritance — what relations does a concept have?
    # ================================================================
    def relations_of(self, concept_ref: str) -> InferenceResult:
        """List all relations of a concept, including inherited ones."""
        cid = self.idx.resolve_concept_id(concept_ref)
        query = f"{concept_ref} 有哪些关系？"
        if not cid:
            return InferenceResult(query, "概念未找到", confidence=0.0,
                                   found=False)
        chain: list[ProofStep] = []
        # Direct relations
        direct = self.idx.relations_by_domain.get(cid, [])
        for rid in direct:
            r = self.idx.relation_by_id[rid]
            chain.append(ProofStep(
                "direct_relation",
                f"关系 {r.get('name')} 直接定义在 {self._name(cid)} 上",
                f"{self._name(cid)} --[{r.get('name')}]--> {self._name(r.get('range_concept_id'))}",
                evidence_id=rid,
            ))
        # Inherited relations from ancestors
        ancestors = self.idx.get_ancestors(cid)
        for anc in ancestors:
            for rid in self.idx.relations_by_domain.get(anc, []):
                if rid in direct:
                    continue
                r = self.idx.relation_by_id[rid]
                chain.append(ProofStep(
                    "relation_inheritance",
                    f"{self._name(cid)} ⊑ {self._name(anc)}（子类继承父类关系）",
                    f"{self._name(cid)} 通过继承获得关系：{r.get('name')} → {self._name(r.get('range_concept_id'))}",
                    evidence_id=rid,
                ))
        rels = self.idx.get_relations_of(cid, include_inherited=True)
        answer_lines = [
            f"{self._name(r.get('domain_concept_id'))} --[{r.get('name')}]--> "
            f"{self._name(r.get('range_concept_id'))}"
            for r in rels
        ]
        answer = "\n".join(answer_lines) if answer_lines else "无关系"
        return InferenceResult(query, answer, 1.0, chain,
                               method="inheritance")

    # ================================================================
    # 3. Multi-hop path query between two concepts
    # ================================================================
    def find_paths(self, src_ref: str, dst_ref: str, max_hops: int = 4
                   ) -> InferenceResult:
        """Find all relation paths from src to dst within max_hops.

        This enumerates reachable concepts through the relation graph
        (including inherited relations) — something LLMs frequently miss.
        """
        src_id = self.idx.resolve_concept_id(src_ref)
        dst_id = self.idx.resolve_concept_id(dst_ref)
        query = f"从 {src_ref} 到 {dst_ref} 的关系路径？"
        if not src_id or not dst_id:
            return InferenceResult(query, "概念未找到", confidence=0.0,
                                   found=False)
        from collections import deque
        results: list[list[tuple[str, str]]] = []  # list of [(rel_name, target)]
        queue = deque([(src_id, [])])
        visited_paths: set = set()
        while queue:
            node, path = queue.popleft()
            if len(path) >= max_hops:
                continue
            rels = self.idx.get_relations_of(node, include_inherited=True)
            for r in rels:
                target = r.get("range_concept_id")
                if not target:
                    continue
                new_path = path + [(r.get("name"), target)]
                key = (node, target, r.get("name"))
                if key in visited_paths:
                    continue
                visited_paths.add(key)
                if target == dst_id:
                    results.append(new_path)
                else:
                    queue.append((target, new_path))
        chain: list[ProofStep] = []
        for i, p in enumerate(results[:5]):  # show up to 5 in proof
            path_str = " → ".join(
                f"[{rn}]→{self._name(t)}" for rn, t in p
            )
            chain.append(ProofStep(
                "path_search",
                f"路径{i+1}：{self._name(src_id)} {path_str}",
                f"到达 {self._name(dst_id)}",
            ))
        if results:
            lines = []
            for p in results:
                path_str = " → ".join(
                    f"--[{rn}]--> {self._name(t)}" for rn, t in p
                )
                lines.append(f"{self._name(src_id)} {path_str}")
            answer = "\n".join(lines)
            return InferenceResult(query, answer, 1.0, chain,
                                   method="path_search")
        return InferenceResult(query, "未找到路径", 0.5, chain,
                               method="path_search", found=False)

    # ================================================================
    # 4. Domain/range constraint check
    # ================================================================
    def check_relation_validity(self, relation_ref: str, domain_ref: str,
                                range_ref: str) -> InferenceResult:
        """Check whether (domain_ref, relation_ref, range_ref) is consistent
        with the ontology's domain/range axioms (allowing subclassing)."""
        rid = self.idx.resolve_relation_id(relation_ref)
        dom_id = self.idx.resolve_concept_id(domain_ref)
        rng_id = self.idx.resolve_concept_id(range_ref)
        query = (f"关系 {relation_ref}({domain_ref}, {range_ref}) "
                 f"是否符合本体约束？")
        if not rid:
            return InferenceResult(query, "关系未找到", 0.0, found=False)
        r = self.idx.relation_by_id[rid]
        declared_dom = r.get("domain_concept_id")
        declared_rng = r.get("range_concept_id")
        chain: list[ProofStep] = []
        # Find domain axiom
        dom_axiom = None
        rng_axiom = None
        for a in self.idx.axioms_by_type.get("domain", []):
            if self.idx.resolve_relation_id(a.get("subject")) == rid:
                dom_axiom = a
                break
        for a in self.idx.axioms_by_type.get("range", []):
            if self.idx.resolve_relation_id(a.get("subject")) == rid:
                rng_axiom = a
                break
        # Check domain
        dom_ok = True
        if declared_dom:
            dom_ok = self.idx.is_subclass_of(dom_id, declared_dom)
            chain.append(ProofStep(
                "domain_check",
                f"声明的 domain = {self._name(declared_dom)}，"
                f"实际 domain = {self._name(dom_id)}",
                f"domain {'满足' if dom_ok else '不满足'}（子类兼容）",
                evidence_id=dom_axiom.get("id", "") if dom_axiom else rid,
            ))
        # Check range
        rng_ok = True
        if declared_rng:
            rng_ok = self.idx.is_subclass_of(rng_id, declared_rng)
            chain.append(ProofStep(
                "range_check",
                f"声明的 range = {self._name(declared_rng)}，"
                f"实际 range = {self._name(rng_id)}",
                f"range {'满足' if rng_ok else '不满足'}（子类兼容）",
                evidence_id=rng_axiom.get("id", "") if rng_axiom else rid,
            ))
        ok = dom_ok and rng_ok
        return InferenceResult(
            query,
            "符合" if ok else "不符合（违反 domain/range 约束）",
            1.0 if ok else 0.3,
            chain, method="constraint_check", found=ok,
        )

    # ================================================================
    # 5. Derived property derivation
    # ================================================================
    def explain_derived_property(self, concept_ref: str,
                                 prop_name_ref: str) -> InferenceResult:
        """Explain how a derived property is computed, tracing its sources."""
        cid = self.idx.resolve_concept_id(concept_ref)
        query = f"{concept_ref} 的派生属性 {prop_name_ref} 是如何计算的？"
        if not cid:
            return InferenceResult(query, "概念未找到", 0.0, found=False)
        # find the property
        target = None
        for p in self.idx.get_properties_of(cid, include_inherited=True):
            if (p.get("name", "").lower() == prop_name_ref.lower()
                    or (p.get("name_cn") or "").lower() == prop_name_ref.lower()):
                target = p
                break
        if not target:
            return InferenceResult(query, "属性未找到", 0.0, found=False)
        if not target.get("is_derived"):
            return InferenceResult(query, "该属性非派生属性", 0.5,
                                   found=False)
        chain: list[ProofStep] = []
        chain.append(ProofStep(
            "derivation_definition",
            f"派生类型 = {target.get('derivation_type')}",
            f"计算公式 = {target.get('derivation_formula')}",
            evidence_id=target.get("id", ""),
        ))
        # trace source properties
        src_names = []
        for src_pid in target.get("derivation_sources", []):
            sp = self.idx.property_by_id.get(src_pid)
            if sp:
                src_names.append(sp.get("name"))
                chain.append(ProofStep(
                    "derivation_source",
                    f"依赖源属性 {sp.get('name')} "
                    f"({self._name(sp.get('domain_concept_id'))})",
                    f"该属性的值参与计算",
                    evidence_id=src_pid,
                ))
        answer = (f"{target.get('name')} = {target.get('derivation_formula')}\n"
                  f"类型：{target.get('derivation_type')}\n"
                  f"依赖源：{', '.join(src_names) if src_names else '无'}")
        return InferenceResult(query, answer, 1.0, chain,
                               method="derivation")

    # ================================================================
    # 6. ECA trigger firing
    # ================================================================
    def fire_triggers(self, event_description: str,
                      state_description: str = "") -> InferenceResult:
        """Match trigger rules against an event + state.

        Trigger rules are ECA (Event-Condition-Action). We do keyword matching
        on the event/detail/condition fields — deterministic, no LLM.
        """
        query = f"事件「{event_description}」触发哪些规则？"
        chain: list[ProofStep] = []
        matched: list[dict] = []
        text = (event_description + " " + state_description).lower()
        for tr in self.idx.raw_triggers:
            score = 0
            # match event detail
            detail = (tr.get("event_detail") or "").lower()
            cond = (tr.get("condition_expression") or "").lower()
            action = (tr.get("action_detail") or "").lower()
            nl = (tr.get("nl_source") or tr.get("description") or "").lower()
            # tokenize Chinese by characters, match substrings
            for field_text in [detail, cond, nl]:
                if not field_text:
                    continue
                # check overlap of significant tokens (>=2 chars)
                for i in range(len(field_text) - 1):
                    bigram = field_text[i:i+2]
                    if bigram in text:
                        score += 1
                        break
            if score > 0 or self._keyword_match(text, tr):
                matched.append(tr)
                chain.append(ProofStep(
                    "trigger_match",
                    f"触发器「{tr.get('name')}」条件匹配 "
                    f"(nl: {tr.get('nl_source') or tr.get('description')})",
                    f"动作：{tr.get('action_type')} - {tr.get('action_detail')}",
                    evidence_id=tr.get("id", ""),
                ))
        if matched:
            lines = []
            for tr in matched:
                lines.append(
                    f"• {tr.get('name')}：{tr.get('nl_source') or tr.get('description')}\n"
                    f"  → 动作：{tr.get('action_type')} - {tr.get('action_detail')}"
                )
            return InferenceResult(query, "\n".join(lines), 1.0, chain,
                                   method="trigger")
        return InferenceResult(query, "无匹配触发器", 0.5, chain,
                               method="trigger", found=False)

    def _keyword_match(self, text: str, trigger: dict) -> bool:
        """Fallback: if any 3-char substring of nl_source appears in text."""
        nl = (trigger.get("nl_source") or trigger.get("description") or "").lower()
        if len(nl) < 3:
            return False
        for i in range(len(nl) - 2):
            if nl[i:i+3] in text:
                return True
        return False

    # ================================================================
    # 7. Membership classification (e.g. is a customer VIP?)
    # ================================================================
    def classify_instance(self, concept_ref: str,
                          features: dict) -> InferenceResult:
        """Classify an instance into a subclass based on features.

        Uses derived-property rules found in the ontology. Example:
          customer_type is_derived with formula:
            IF(annual_spend > 100000, 'VIP', ...)
          → given annual_spend=120000, conclude VIP客户.
        """
        cid = self.idx.resolve_concept_id(concept_ref)
        query = f"根据特征 {features} 判定 {concept_ref} 的子类"
        if not cid:
            return InferenceResult(query, "概念未找到", 0.0, found=False)
        chain: list[ProofStep] = []
        chain.append(ProofStep(
            "instance_anchor",
            f"实例属于概念 {self._name(cid)}",
            f"候选子类：{[self._name(d) for d in self.idx.get_descendants(cid)]}",
        ))
        # Look for derived properties with conditional formulas referencing
        # features present in `features`.
        conclusions = []
        for p in self.idx.get_properties_of(cid, include_inherited=True):
            if not p.get("is_derived"):
                continue
            formula = (p.get("derivation_formula") or "")
            dtype = p.get("derivation_type")
            chain.append(ProofStep(
                "derived_rule_candidate",
                f"派生属性 {p.get('name')} 类型={dtype} 公式={formula}",
                f"检查公式中的条件是否被特征满足",
                evidence_id=p.get("id", ""),
            ))
            result = self._evaluate_conditional_formula(formula, features, p)
            if result:
                conclusions.append(result)
                chain.append(ProofStep(
                    "conditional_evaluation",
                    f"公式 {formula} 在特征 {features} 下求值",
                    f"结果：{result}",
                    evidence_id=p.get("id", ""),
                ))
                # If result mentions a subclass name, verify it IS a subclass
                for desc_id in self.idx.get_descendants(cid):
                    desc_name = self._name(desc_id)
                    if desc_name in str(result) or str(result) in desc_name:
                        chain.append(ProofStep(
                            "subclass_confirmation",
                            f"{desc_name} ⊑ {self._name(cid)}（确认为合法子类）",
                            f"分类结论：实例属于 {desc_name}",
                            evidence_id="",
                        ))
        answer = "；".join(conclusions) if conclusions else "无法判定（无匹配派生规则）"
        return InferenceResult(
            query, answer,
            1.0 if conclusions else 0.3,
            chain, method="classification",
            found=bool(conclusions),
        )

    def _evaluate_conditional_formula(self, formula: str, features: dict,
                                      prop: dict) -> str:
        """Best-effort evaluation of a conditional derivation formula.

        Handles patterns like:
          IF(annual_spend > 100000, 'VIP', IF(customer_name IS NOT NULL, '个人客户', '企业客户'))
          IF(condition, 'A', 'B')
        """
        if not formula or "IF(" not in formula.upper():
            return ""
        # Extract top-level IF(cond, then, else)
        m = re.match(r"\s*IF\((.*),\s*'([^']*)'\s*,\s*(.*)\)\s*",
                     formula, re.IGNORECASE | re.DOTALL)
        if not m:
            return ""
        cond, then_val, else_part = m.group(1), m.group(2), m.group(3)
        if self._eval_condition(cond, features):
            return f"{prop.get('name')}={then_val}"
        # else_part may itself be an IF(...)
        if else_part.strip().upper().startswith("IF("):
            inner = self._evaluate_conditional_formula(else_part.strip(),
                                                       features, prop)
            return inner
        # else is a literal
        m2 = re.match(r"\s*'([^']*)'\s*", else_part)
        if m2:
            return f"{prop.get('name')}={m2.group(1)}"
        return ""

    def _eval_condition(self, cond: str, features: dict) -> bool:
        """Evaluate a simple comparison condition against feature dict."""
        # Pattern: field OP value
        m = re.match(r"\s*(\w+)\s*(>|<|>=|<=|==|!=)\s*([0-9.]+)\s*$", cond)
        if m:
            field, op, val = m.group(1), m.group(2), float(m.group(3))
            actual = features.get(field)
            if actual is None:
                return False
            try:
                actual = float(actual)
            except (TypeError, ValueError):
                return False
            return {
                ">": actual > val, "<": actual < val,
                ">=": actual >= val, "<=": actual <= val,
                "==": actual == val, "!=": actual != val,
            }[op]
        # Pattern: field IS NOT NULL
        if "IS NOT NULL" in cond.upper():
            field = cond.split()[0]
            return features.get(field) is not None
        if "IS NULL" in cond.upper():
            field = cond.split()[0]
            return features.get(field) is None
        return False

    # ================================================================
    # 8. Concept lookup by name/alias
    # ================================================================
    def describe_concept(self, concept_ref: str) -> InferenceResult:
        """Full description of a concept: layer, source, properties,
        relations, ancestors, descendants."""
        cid = self.idx.resolve_concept_id(concept_ref)
        query = f"描述概念 {concept_ref}"
        if not cid:
            return InferenceResult(query, "概念未找到", 0.0, found=False)
        c = self.idx.concept_ref(cid)
        chain: list[ProofStep] = []
        chain.append(ProofStep("concept_lookup",
                               f"解析引用 {concept_ref} → id {cid}",
                               f"名称={c.get('name')} 层={c.get('layer')} "
                               f"来源={c.get('source')}"))
        ancestors = self.idx.get_ancestors(cid)
        descendants = self.idx.get_descendants(cid)
        if ancestors:
            chain.append(ProofStep("ancestor_closure",
                                   f"subClassOf 传递闭包",
                                   f"祖先：{[self._name(a) for a in ancestors]}"))
        if descendants:
            chain.append(ProofStep("descendant_closure",
                                   f"subClassOf 传递闭包",
                                   f"后代：{[self._name(d) for d in descendants]}"))
        props = self.idx.get_properties_of(cid, include_inherited=True)
        rels = self.idx.get_relations_of(cid, include_inherited=True)
        lines = [
            f"名称：{c.get('name')}（{c.get('name_en') or ''}）",
            f"别名：{', '.join(c.get('aliases') or []) or '无'}",
            f"描述：{c.get('description') or '无'}",
            f"层次：{c.get('layer')}　来源：{c.get('source')}",
            f"祖先：{', '.join(self._name(a) for a in ancestors) or '无'}",
            f"后代：{', '.join(self._name(d) for d in descendants) or '无'}",
            f"属性（含继承）：{', '.join(p.get('name') for p in props) or '无'}",
            f"关系（含继承）：{', '.join(r.get('name') for r in rels) or '无'}",
        ]
        return InferenceResult(query, "\n".join(lines), 1.0, chain,
                               method="lookup")

    # ================================================================
    # Helpers
    # ================================================================
    def _name(self, concept_id: Optional[str]) -> str:
        if not concept_id:
            return "?"
        return self.idx.concept_name(concept_id)
