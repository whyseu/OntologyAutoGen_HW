"""Multi-step reasoning pipeline: chain CRUD + reasoning into one workflow.

This module composes the editor, reasoner and agent framework into a single
*multi-step* scenario that demonstrates how the ontology evolves and reasons
end-to-end.  The canonical example is "new business line launch": a company
adds a new product category, wires it into the taxonomy, creates relations,
then reasons across the expanded graph.

Each step is a pure function ``step_*(editor, reasoner) -> dict`` returning a
result dict that gets collected into a final report.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable

from .ontology_editor import OntologyEditor
from .symbolic_reasoner import SymbolicReasoner, InferenceResult

logger = logging.getLogger("ontology_gen.reasoning.multistep")


@dataclass
class StepResult:
    name: str
    description: str
    ok: bool
    output: dict = field(default_factory=dict)
    detail: str = ""


# ============================================================
# Individual steps
# ============================================================

def step_add_concepts(editor: OntologyEditor, reasoner: SymbolicReasoner,
                      cfg: dict) -> StepResult:
    """Step 1: add new concepts for the new business line."""
    added = []
    for spec in cfg.get("concepts", []):
        cid = editor.add_concept(**spec)
        added.append({"id": cid, "name": spec["name"]})
    return StepResult("step_add_concepts",
                      f"新增 {len(added)} 个概念", True,
                      {"added": added})


def step_build_taxonomy(editor: OntologyEditor, reasoner: SymbolicReasoner,
                        cfg: dict) -> StepResult:
    """Step 2: wire new concepts into the taxonomy via subClassOf axioms."""
    edges = cfg.get("subclass_edges", [])
    ax_ids = []
    for child, parent in edges:
        ax_ids.append(editor.add_subclass_axiom(child, parent))
    return StepResult("step_build_taxonomy",
                      f"建立 {len(ax_ids)} 条 subClassOf 边", True,
                      {"axioms": ax_ids, "edges": edges})


def step_add_relations(editor: OntologyEditor, reasoner: SymbolicReasoner,
                        cfg: dict) -> StepResult:
    """Step 3: create relations between concepts."""
    rel_ids = []
    for spec in cfg.get("relations", []):
        # Normalize config keys to the editor's signature.
        spec = dict(spec)
        if "domain" in spec and "domain_ref" not in spec:
            spec["domain_ref"] = spec.pop("domain")
        if "range_" in spec and "range_ref" not in spec:
            spec["range_ref"] = spec.pop("range_")
        rid = editor.add_relation(**spec)
        rel_ids.append(rid)
    return StepResult("step_add_relations",
                      f"新增 {len(rel_ids)} 个关系", True,
                      {"relations": rel_ids})


def step_verify_inheritance(editor: OntologyEditor,
                            reasoner: SymbolicReasoner,
                            cfg: dict) -> StepResult:
    """Step 4: verify that new subclasses inherit ancestor relations."""
    checks = cfg.get("inheritance_checks", [])
    results = []
    all_ok = True
    for entry in checks:
        # Support both 2-tuple [concept, rel] (expect True) and
        # 3-tuple [concept, rel, expected].
        concept_ref, expected_rel = entry[0], entry[1]
        expected = entry[2] if len(entry) > 2 else True
        cid = editor.idx.resolve_concept_id(concept_ref)
        if not cid:
            results.append({"concept": concept_ref, "ok": False,
                            "reason": "concept not found"})
            all_ok = False
            continue
        rels = editor.idx.get_relations_of(cid, include_inherited=True)
        names = {r.get("name") for r in rels}
        has_rel = expected_rel in names
        ok = (has_rel == expected)
        results.append({"concept": concept_ref,
                        "expected_relation": expected_rel,
                        "expected": expected,
                        "inherited": has_rel,
                        "ok": ok,
                        "all_relations": sorted(names)})
        if not ok:
            all_ok = False
    return StepResult("step_verify_inheritance",
                      "验证关系继承", all_ok, {"checks": results})


def step_multi_hop_reasoning(editor: OntologyEditor,
                             reasoner: SymbolicReasoner,
                             cfg: dict) -> StepResult:
    """Step 5: run multi-hop path reasoning on the expanded graph."""
    queries = cfg.get("path_queries", [])
    results = []
    for src, dst in queries:
        res: InferenceResult = reasoner.find_paths(src, dst, max_hops=5)
        results.append({
            "src": src, "dst": dst,
            "found": res.found,
            "answer": res.answer[:200],
            "proof_steps": len(res.proof_chain),
        })
    return StepResult("step_multi_hop_reasoning",
                      f"执行 {len(queries)} 个多跳路径查询", True,
                      {"queries": results})


def step_subclass_closure(editor: OntologyEditor,
                          reasoner: SymbolicReasoner,
                          cfg: dict) -> StepResult:
    """Step 6: verify transitive subclass closure over the new taxonomy."""
    checks = cfg.get("closure_checks", [])
    results = []
    all_ok = True
    for entry in checks:
        child, parent = entry[0], entry[1]
        expected = entry[2] if len(entry) > 2 else True
        res = reasoner.is_a(child, parent)
        ok = (res.found == expected)
        results.append({"child": child, "parent": parent,
                        "expected": expected,
                        "answer": res.answer, "found": res.found,
                        "ok": ok,
                        "proof_steps": len(res.proof_chain)})
        if not ok:
            all_ok = False
    return StepResult("step_subclass_closure",
                      "验证传递闭包", all_ok, {"checks": results})


def step_trigger_firing(editor: OntologyEditor,
                        reasoner: SymbolicReasoner,
                        cfg: dict) -> StepResult:
    """Step 7: fire ECA triggers relevant to the new concepts."""
    queries = cfg.get("trigger_queries", [])
    results = []
    for q in queries:
        res = reasoner.fire_triggers(q)
        results.append({"query": q, "answer": res.answer[:200],
                        "fired": res.found})
    return StepResult("step_trigger_firing",
                      f"触发 {len(queries)} 个 ECA 查询", True,
                      {"queries": results})


# ============================================================
# Pipeline runner
# ============================================================

@dataclass
class PipelineReport:
    steps: list[StepResult] = field(default_factory=list)

    @property
    def all_ok(self) -> bool:
        return all(s.ok for s in self.steps)

    def summary(self) -> dict:
        return {
            "total_steps": len(self.steps),
            "passed": sum(1 for s in self.steps if s.ok),
            "failed": sum(1 for s in self.steps if not s.ok),
            "all_ok": self.all_ok,
            "steps": [{"name": s.name, "description": s.description,
                       "ok": s.ok} for s in self.steps],
        }

    def to_dict(self) -> dict:
        return {"summary": self.summary(),
                "steps": [{"name": s.name, "description": s.description,
                           "ok": s.ok, "output": s.output, "detail": s.detail}
                          for s in self.steps]}


STEPS: list[Callable[..., StepResult]] = [
    step_add_concepts,
    step_build_taxonomy,
    step_add_relations,
    step_verify_inheritance,
    step_multi_hop_reasoning,
    step_subclass_closure,
    step_trigger_firing,
]


def run_multistep_pipeline(editor: OntologyEditor, config: dict) -> PipelineReport:
    """Run the full multi-step pipeline driven by ``config``.

    ``config`` is a dict with keys matching each step's expectations:
      - concepts: list[dict]          (add_concept kwargs)
      - subclass_edges: list[[child, parent]]
      - relations: list[dict]         (add_relation kwargs, with range_ key)
      - inheritance_checks: list[[concept, expected_relation]]
      - path_queries: list[[src, dst]]
      - closure_checks: list[[child, parent]]
      - trigger_queries: list[str]
    """
    reasoner = SymbolicReasoner(editor.idx)
    report = PipelineReport()
    for fn in STEPS:
        try:
            res = fn(editor, reasoner, config)
            report.steps.append(res)
            logger.info("[%s] %s -> ok=%s", res.name, res.description, res.ok)
        except Exception as e:
            logger.exception("Step %s failed", fn.__name__)
            report.steps.append(StepResult(fn.__name__, str(e), False, {}))
    return report
