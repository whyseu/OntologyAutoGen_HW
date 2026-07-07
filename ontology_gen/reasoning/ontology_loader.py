"""Ontology loader & indexer.

Loads output/ontology.json into a richly-indexed in-memory structure so that
the symbolic reasoner and context builder can do fast lookups:

  - concepts by id / by name / by alias / by layer / by source
  - subclass graph (built from subClassOf axioms) with ancestor / descendant
    queries (transitive closure), plus the original taxonomy tree
  - relations by name / by domain concept / by range concept
  - properties by id / by domain concept / derived properties
  - axioms grouped by type (subClassOf / domain / range / inverseOf / ...)
  - trigger rules, operations, permissions, glossary, external mappings

The loader is intentionally tolerant: concept IDs that appear in axioms but
refer to a concept *name* (some LLM-generated axioms use names instead of ids)
are resolved via a name->id lookup table, so the reasoner never crashes on
mixed references.
"""
from __future__ import annotations

import json
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger("ontology_gen.reasoning.loader")


@dataclass
class OntologyIndex:
    """An indexed, read-optimized view of a generated ontology."""

    # Raw dicts (kept for context building)
    raw_concepts: list[dict] = field(default_factory=list)
    raw_properties: list[dict] = field(default_factory=list)
    raw_relations: list[dict] = field(default_factory=list)
    raw_axioms: list[dict] = field(default_factory=list)
    raw_rules: list[dict] = field(default_factory=list)
    raw_triggers: list[dict] = field(default_factory=list)
    raw_operations: list[dict] = field(default_factory=list)
    raw_service_compositions: list[dict] = field(default_factory=list)
    raw_permissions: list[dict] = field(default_factory=list)
    raw_glossary: list[dict] = field(default_factory=list)
    raw_external_mappings: list[dict] = field(default_factory=list)
    raw_taxonomy: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)
    domain: str = "unknown"

    # Indexes
    concept_by_id: dict[str, dict] = field(default_factory=dict)
    concept_id_by_name: dict[str, str] = field(default_factory=dict)  # lowercase
    concept_id_by_alias: dict[str, str] = field(default_factory=dict)  # lowercase
    concept_id_by_name_orig: dict[str, str] = field(default_factory=dict)  # original case
    concept_id_by_alias_orig: dict[str, str] = field(default_factory=dict)  # original case
    concepts_by_layer: dict[str, list[str]] = field(default_factory=dict)
    concepts_by_source: dict[str, list[str]] = field(default_factory=dict)

    property_by_id: dict[str, dict] = field(default_factory=dict)
    properties_by_domain: dict[str, list[str]] = field(default_factory=dict)  # prop ids

    relation_by_id: dict[str, dict] = field(default_factory=dict)
    relations_by_domain: dict[str, list[str]] = field(default_factory=dict)  # rel ids
    relations_by_range: dict[str, list[str]] = field(default_factory=dict)
    relation_id_by_name: dict[str, str] = field(default_factory=dict)  # lowercase

    axioms_by_type: dict[str, list[dict]] = field(default_factory=dict)
    subclass_parents: dict[str, list[str]] = field(default_factory=dict)  # id -> parent ids
    subclass_children: dict[str, list[str]] = field(default_factory=dict)  # id -> child ids
    ancestors_cache: dict[str, list[str]] = field(default_factory=dict)
    descendants_cache: dict[str, list[str]] = field(default_factory=dict)

    # ------------------------------------------------------------------
    # Name / id resolution
    # ------------------------------------------------------------------
    def resolve_concept_id(self, ref: str) -> Optional[str]:
        """Resolve a string that may be a concept id OR a concept name/alias.

        Many LLM-generated axioms store the *name* (e.g. '客户') in subject/obj
        rather than the id. This unifies both cases so the reasoner is robust.
        """
        if not ref:
            return None
        if ref in self.concept_by_id:
            return ref
        low = ref.strip().lower()
        if low in self.concept_id_by_name:
            return self.concept_id_by_name[low]
        if low in self.concept_id_by_alias:
            return self.concept_id_by_alias[low]
        return None

    def concept_name(self, concept_id: str) -> str:
        c = self.concept_by_id.get(concept_id)
        return c["name"] if c else concept_id

    def concept_ref(self, concept_id: str) -> Optional[dict]:
        return self.concept_by_id.get(concept_id)

    def resolve_relation_id(self, ref: str) -> Optional[str]:
        if not ref:
            return None
        if ref in self.relation_by_id:
            return ref
        low = ref.strip().lower()
        return self.relation_id_by_name.get(low)

    # ------------------------------------------------------------------
    # Subclass graph queries (transitive closure, memoized)
    # ------------------------------------------------------------------
    def get_ancestors(self, concept_id: str) -> list[str]:
        """All super-concepts (transitive closure), root first.

        Uses subClassOf axioms as the source of truth (these are also the
        taxonomy edges, but axioms may contain LLM-added extra edges).
        """
        if concept_id in self.ancestors_cache:
            return self.ancestors_cache[concept_id]
        seen: list[str] = []
        seen_set: set[str] = set()
        stack = list(self.subclass_parents.get(concept_id, []))
        while stack:
            parent = stack.pop(0)
            if parent in seen_set:
                continue
            seen_set.add(parent)
            seen.append(parent)
            stack.extend(self.subclass_parents.get(parent, []))
        self.ancestors_cache[concept_id] = seen
        return seen

    def get_descendants(self, concept_id: str) -> list[str]:
        """All sub-concepts (transitive closure)."""
        if concept_id in self.descendants_cache:
            return self.descendants_cache[concept_id]
        seen: list[str] = []
        seen_set: set[str] = set()
        stack = list(self.subclass_children.get(concept_id, []))
        while stack:
            child = stack.pop(0)
            if child in seen_set:
                continue
            seen_set.add(child)
            seen.append(child)
            stack.extend(self.subclass_children.get(child, []))
        self.descendants_cache[concept_id] = seen
        return seen

    def is_subclass_of(self, child_id: str, parent_id: str) -> bool:
        """True if child_id is a (transitive) subclass of parent_id."""
        if child_id == parent_id:
            return True
        return parent_id in self.get_ancestors(child_id)

    def get_relations_of(self, concept_id: str, include_inherited: bool = True
                         ) -> list[dict]:
        """All relations whose domain is concept_id or an ancestor of it.

        With include_inherited=True (default), a subclass inherits its
        super-class' relations — this is the core 'relation inheritance'
        reasoning that makes the ontology useful.
        """
        domain_ids = [concept_id]
        if include_inherited:
            domain_ids.extend(self.get_ancestors(concept_id))
        out: list[dict] = []
        for did in domain_ids:
            for rid in self.relations_by_domain.get(did, []):
                out.append(self.relation_by_id[rid])
        return out

    def get_properties_of(self, concept_id: str, include_inherited: bool = True
                          ) -> list[dict]:
        """All properties of concept_id (optionally inherited)."""
        domain_ids = [concept_id]
        if include_inherited:
            domain_ids.extend(self.get_ancestors(concept_id))
        out: list[dict] = []
        for did in domain_ids:
            for pid in self.properties_by_domain.get(did, []):
                out.append(self.property_by_id[pid])
        return out

    def get_derived_properties(self) -> list[dict]:
        return [p for p in self.raw_properties if p.get("is_derived")]

    def get_triggers_for_concept(self, concept_id: str) -> list[dict]:
        out = []
        for tr in self.raw_triggers:
            concepts = tr.get("condition_concepts", []) or []
            if concept_id in concepts:
                out.append(tr)
        return out

    def all_concept_ids(self) -> list[str]:
        return list(self.concept_by_id.keys())


def load_ontology(path: str | Path) -> OntologyIndex:
    """Load an ontology.json file into an OntologyIndex."""
    path = Path(path)
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    idx = OntologyIndex()
    idx.raw_concepts = data.get("entity_types", [])
    idx.raw_properties = data.get("properties", [])
    idx.raw_relations = data.get("relations", [])
    idx.raw_axioms = data.get("axioms", [])
    idx.raw_rules = data.get("rules", [])
    idx.raw_triggers = data.get("trigger_rules", [])
    idx.raw_operations = data.get("operations", [])
    idx.raw_service_compositions = data.get("service_compositions", [])
    idx.raw_permissions = data.get("permission_rules", [])
    idx.raw_glossary = data.get("glossary", [])
    idx.raw_external_mappings = data.get("external_mappings", [])
    idx.raw_taxonomy = data.get("taxonomy", {})
    idx.metadata = data.get("metadata", {})
    idx.domain = data.get("domain", "unknown")

    _build_indexes(idx)
    _build_subclass_graph(idx)
    return idx


def _build_indexes(idx: OntologyIndex) -> None:
    # Concepts
    for c in idx.raw_concepts:
        cid = c.get("id")
        if not cid:
            continue
        idx.concept_by_id[cid] = c
        name = (c.get("name") or "").strip()
        if name:
            idx.concept_id_by_name[name.lower()] = cid
            idx.concept_id_by_name_orig[name] = cid
        for alias in (c.get("aliases") or []):
            a = alias.strip()
            if a:
                idx.concept_id_by_alias[a.lower()] = cid
                idx.concept_id_by_alias_orig[a] = cid
        layer = c.get("layer") or "data"
        idx.concepts_by_layer.setdefault(layer, []).append(cid)
        src = c.get("source") or "unknown"
        idx.concepts_by_source.setdefault(src, []).append(cid)

    # Properties
    for p in idx.raw_properties:
        pid = p.get("id")
        if not pid:
            continue
        idx.property_by_id[pid] = p
        did = p.get("domain_concept_id")
        if did:
            idx.properties_by_domain.setdefault(did, []).append(pid)

    # Relations
    for r in idx.raw_relations:
        rid = r.get("id")
        if not rid:
            continue
        idx.relation_by_id[rid] = r
        name = (r.get("name") or "").strip()
        if name:
            idx.relation_id_by_name[name.lower()] = rid
        did = r.get("domain_concept_id")
        if did:
            idx.relations_by_domain.setdefault(did, []).append(rid)
        rid_r = r.get("range_concept_id")
        if rid_r:
            idx.relations_by_range.setdefault(rid_r, []).append(r.get("id"))

    # Axioms grouped by type
    for a in idx.raw_axioms:
        atype = a.get("axiom_type") or "unknown"
        idx.axioms_by_type.setdefault(atype, []).append(a)

    logger.info(
        "OntologyIndex built: %d concepts, %d properties, %d relations, "
        "%d axioms (%d subClassOf), %d triggers, %d derived props",
        len(idx.concept_by_id), len(idx.property_by_id),
        len(idx.relation_by_id), len(idx.raw_axioms),
        len(idx.axioms_by_type.get("subClassOf", [])),
        len(idx.raw_triggers),
        len([p for p in idx.raw_properties if p.get("is_derived")]),
    )


def _build_subclass_graph(idx: OntologyIndex) -> None:
    """Build subclass parent/child adjacency from subClassOf axioms.

    Handles the mixed id/name references in LLM-generated axioms by resolving
    through OntologyIndex.resolve_concept_id.
    """
    for a in idx.axioms_by_type.get("subClassOf", []):
        subj_ref = a.get("subject")
        obj_ref = a.get("obj")
        subj_id = idx.resolve_concept_id(subj_ref)
        obj_id = idx.resolve_concept_id(obj_ref)
        if subj_id and obj_id:
            idx.subclass_parents.setdefault(subj_id, []).append(obj_id)
            idx.subclass_children.setdefault(obj_id, []).append(subj_id)
        else:
            logger.debug(
                "subClassOf edge unresolved: subject=%r obj=%r "
                "(subj_id=%r obj_id=%r)", subj_ref, obj_ref, subj_id, obj_id
            )
    # Dedupe
    for k, v in list(idx.subclass_parents.items()):
        idx.subclass_parents[k] = list(dict.fromkeys(v))
    for k, v in list(idx.subclass_children.items()):
        idx.subclass_children[k] = list(dict.fromkeys(v))
