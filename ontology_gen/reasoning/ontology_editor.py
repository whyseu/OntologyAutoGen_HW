"""Ontology CRUD editor: create / read / update / delete over a loaded ontology.

The :class:`OntologyEditor` wraps an :class:`OntologyIndex` and lets you mutate
the in-memory ontology — adding, updating, removing concepts / properties /
relations / axioms — while keeping the subclass graph and all secondary indexes
consistent. Every mutation is recorded in an append-only change log so the
session is auditable.

This module is the foundation for "interactive ontology" scenarios:
  - case 1 (CRUD) demonstrates the four operations directly;
  - case 2 (multi-agent) lets several agents share one editor so their edits
    are visible to each other immediately;
  - case 3 (multi-step) uses CRUD + reasoning together.

Design notes
------------
* Mutations operate on the *raw* lists inside ``OntologyIndex`` (``raw_concepts``,
  ``raw_relations``, ...) and then call :func:`_build_indexes` +
  :func:`_build_subclass_graph` to refresh all derived structures.
* IDs for new elements are generated as ``concept_<8hex>`` etc., mirroring the
  pipeline's own id scheme.
* Deletion is *safe*: removing a concept also prunes dangling references in
  relations (domain/range), properties (domain), and axioms (subject/obj).
"""
from __future__ import annotations

import logging
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from .ontology_loader import (
    OntologyIndex, _build_indexes, _build_subclass_graph,
)

logger = logging.getLogger("ontology_gen.reasoning.editor")


# ============================================================
# Change log
# ============================================================

@dataclass
class ChangeRecord:
    """A single auditable mutation of the ontology."""
    op: str               # "create" | "update" | "delete"
    target: str           # "concept" | "property" | "relation" | "axiom"
    ref: str              # id or name of the affected element
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    detail: dict = field(default_factory=dict)

    def __str__(self) -> str:
        return f"[{self.timestamp}] {self.op} {self.target} {self.ref}"

    def to_dict(self) -> dict:
        return {
            "op": self.op, "target": self.target, "ref": self.ref,
            "timestamp": self.timestamp, "detail": self.detail,
        }


# ============================================================
# Editor
# ============================================================

class OntologyEditor:
    """Read/write controller over an :class:`OntologyIndex`.

    Usage::

        idx = load_ontology("output/ontology.json")
        editor = OntologyEditor(idx)

        # create
        cid = editor.add_concept(name="海外仓", layer="data")
        # read
        print(editor.get_concept(cid))
        # update
        editor.update_concept(cid, aliases=["跨境仓"])
        # delete
        editor.delete_concept(cid)

        # persist
        editor.save("output/ontology_edited.json")
    """

    def __init__(self, index: OntologyIndex):
        self.idx = index
        self.changelog: list[ChangeRecord] = []

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _new_id(prefix: str) -> str:
        return f"{prefix}_{secrets.token_hex(4)}"

    def _rebuild(self) -> None:
        """Re-derive all indexes and the subclass graph from raw lists."""
        # Clear ALL secondary indexes so deletions are reflected.
        for attr in (
            "concept_by_id", "concept_id_by_name", "concept_id_by_alias",
            "concept_id_by_name_orig", "concept_id_by_alias_orig",
            "concepts_by_layer", "concepts_by_source",
            "property_by_id", "properties_by_domain",
            "relation_by_id", "relations_by_domain", "relations_by_range",
            "relation_id_by_name",
            "axioms_by_type",
            "subclass_parents", "subclass_children",
            "ancestors_cache", "descendants_cache",
        ):
            getattr(self.idx, attr).clear()
        _build_indexes(self.idx)
        _build_subclass_graph(self.idx)

    def _log(self, op: str, target: str, ref: str, **detail: Any) -> None:
        rec = ChangeRecord(op=op, target=target, ref=ref, detail=detail)
        self.changelog.append(rec)
        logger.info("CRUD %s %s %s", op, target, ref)

    # ================================================================
    # CONCEPT CRUD
    # ================================================================
    def add_concept(self, name: str, *, name_en: str = "",
                    aliases: Optional[list[str]] = None, layer: str = "data",
                    source: str = "manual", confidence: float = 1.0,
                    description: str = "",
                    is_entity_type: bool = True,
                    identity_spec: str = "") -> str:
        """Create a concept; return its new id."""
        cid = self._new_id("concept")
        concept = {
            "id": cid,
            "name": name,
            "name_en": name_en,
            "aliases": aliases or [],
            "layer": layer,
            "source": source,
            "confidence": confidence,
            "description": description,
            "is_entity_type": is_entity_type,
            "identity_spec": identity_spec,
        }
        self.idx.raw_concepts.append(concept)
        self._rebuild()
        self._log("create", "concept", cid, name=name)
        return cid

    def get_concept(self, ref: str) -> Optional[dict]:
        """Read a concept by id, name, or alias."""
        cid = self.idx.resolve_concept_id(ref)
        return self.idx.concept_ref(cid) if cid else None

    def update_concept(self, ref: str, **fields) -> bool:
        """Update concept fields. Any of name/name_en/aliases/layer/..."""
        cid = self.idx.resolve_concept_id(ref)
        if not cid:
            return False
        c = self.idx.concept_ref(cid)
        changed = []
        for k, v in fields.items():
            if v is not None and c.get(k) != v:
                c[k] = v
                changed.append(k)
        if changed:
            self._rebuild()
            self._log("update", "concept", cid, fields=changed)
        return bool(changed)

    def delete_concept(self, ref: str) -> bool:
        """Delete a concept and prune all dangling references."""
        cid = self.idx.resolve_concept_id(ref)
        if not cid:
            return False
        name = self.idx.concept_name(cid)
        # remove the concept
        self.idx.raw_concepts = [c for c in self.idx.raw_concepts
                                 if c.get("id") != cid]
        # prune relations referencing it in domain/range
        before_r = len(self.idx.raw_relations)
        self.idx.raw_relations = [
            r for r in self.idx.raw_relations
            if r.get("domain_concept_id") != cid
            and r.get("range_concept_id") != cid
        ]
        pruned_r = before_r - len(self.idx.raw_relations)
        # prune properties whose domain is this concept
        before_p = len(self.idx.raw_properties)
        self.idx.raw_properties = [
            p for p in self.idx.raw_properties
            if p.get("domain_concept_id") != cid
        ]
        pruned_p = before_p - len(self.idx.raw_properties)
        # prune axioms referencing it (by id or name)
        self.idx.raw_axioms = [
            a for a in self.idx.raw_axioms
            if a.get("subject") != cid and a.get("subject") != name
            and a.get("obj") != cid and a.get("obj") != name
        ]
        self._rebuild()
        self._log("delete", "concept", cid, name=name,
                  pruned_relations=pruned_r, pruned_properties=pruned_p)
        return True

    # ================================================================
    # RELATION CRUD
    # ================================================================
    def add_relation(self, name: str, domain_ref: str, range_ref: str, *,
                     name_cn: str = "", relation_type: str = "object",
                     inverse: str = "", description: str = "") -> str:
        """Create a relation between two concepts; return its id."""
        did = self.idx.resolve_concept_id(domain_ref)
        rid = self.idx.resolve_concept_id(range_ref)
        if not did or not rid:
            raise ValueError(f"Cannot resolve domain '{domain_ref}' or range '{range_ref}'")
        rel_id = self._new_id("relation")
        rel = {
            "id": rel_id,
            "name": name,
            "name_cn": name_cn,
            "domain_concept_id": did,
            "range_concept_id": rid,
            "type": relation_type,
            "inverse": inverse,
            "description": description,
            "source": "manual",
            "confidence": 1.0,
        }
        self.idx.raw_relations.append(rel)
        self._rebuild()
        self._log("create", "relation", rel_id, name=name,
                  domain=did, range=rid)
        return rel_id

    def get_relation(self, ref: str) -> Optional[dict]:
        rid = self.idx.resolve_relation_id(ref)
        return self.idx.relation_by_id.get(rid) if rid else None

    def update_relation(self, ref: str, **fields) -> bool:
        rid = self.idx.resolve_relation_id(ref)
        if not rid:
            return False
        r = self.idx.relation_by_id[rid]
        changed = []
        for k, v in fields.items():
            if v is not None and r.get(k) != v:
                r[k] = v
                changed.append(k)
        if changed:
            self._rebuild()
            self._log("update", "relation", rid, fields=changed)
        return bool(changed)

    def delete_relation(self, ref: str) -> bool:
        rid = self.idx.resolve_relation_id(ref)
        if not rid:
            return False
        name = self.idx.relation_by_id[rid].get("name", rid)
        self.idx.raw_relations = [r for r in self.idx.raw_relations
                                  if r.get("id") != rid]
        self._rebuild()
        self._log("delete", "relation", rid, name=name)
        return True

    # ================================================================
    # PROPERTY CRUD
    # ================================================================
    def add_property(self, name: str, domain_ref: str, *,
                     name_cn: str = "", data_type: str = "string",
                     is_derived: bool = False, derivation_formula: str = "",
                     validation_rules: Optional[list[dict]] = None,
                     enum_values: Optional[list[str]] = None) -> str:
        did = self.idx.resolve_concept_id(domain_ref)
        if not did:
            raise ValueError(f"Cannot resolve domain concept '{domain_ref}'")
        pid = self._new_id("property")
        prop = {
            "id": pid,
            "name": name,
            "name_cn": name_cn,
            "domain_concept_id": did,
            "data_type": data_type,
            "is_derived": is_derived,
            "derivation_formula": derivation_formula,
            "validation_rules": validation_rules or [],
            "enum_values": enum_values or [],
            "source": "manual",
            "confidence": 1.0,
        }
        self.idx.raw_properties.append(prop)
        self._rebuild()
        self._log("create", "property", pid, name=name, domain=did)
        return pid

    def get_property(self, ref: str) -> Optional[dict]:
        """Read a property by id or name."""
        # by id
        for p in self.idx.raw_properties:
            if p.get("id") == ref:
                return p
        # by name
        low = ref.strip().lower()
        for p in self.idx.raw_properties:
            if (p.get("name") or "").strip().lower() == low:
                return p
        return None

    def delete_property(self, ref: str) -> bool:
        p = self.get_property(ref)
        if not p:
            return False
        pid = p["id"]
        self.idx.raw_properties = [pp for pp in self.idx.raw_properties
                                   if pp.get("id") != pid]
        self._rebuild()
        self._log("delete", "property", pid, name=p.get("name"))
        return True

    # ================================================================
    # AXIOM CRUD (subClassOf / domain / range / inverseOf ...)
    # ================================================================
    def add_subclass_axiom(self, child_ref: str, parent_ref: str) -> str:
        """Assert child ⊑ parent."""
        cid = self.idx.resolve_concept_id(child_ref)
        pid = self.idx.resolve_concept_id(parent_ref)
        if not cid or not pid:
            raise ValueError("Cannot resolve child/parent concept")
        ax_id = self._new_id("axiom")
        ax = {
            "id": ax_id,
            "axiom_type": "subClassOf",
            "subject": cid,
            "obj": pid,
            "subject_name": self.idx.concept_name(cid),
            "obj_name": self.idx.concept_name(pid),
            "confidence": 1.0,
            "risk": "low",
            "source": "manual",
        }
        self.idx.raw_axioms.append(ax)
        self._rebuild()
        self._log("create", "axiom", ax_id,
                  type="subClassOf", subject=cid, obj=pid)
        return ax_id

    def delete_axiom(self, axiom_id: str) -> bool:
        before = len(self.idx.raw_axioms)
        self.idx.raw_axioms = [a for a in self.idx.raw_axioms
                               if a.get("id") != axiom_id]
        if len(self.idx.raw_axioms) == before:
            return False
        self._rebuild()
        self._log("delete", "axiom", axiom_id)
        return True

    # ================================================================
    # bulk read helpers
    # ================================================================
    def list_concepts(self) -> list[dict]:
        return list(self.idx.raw_concepts)

    def list_relations(self) -> list[dict]:
        return list(self.idx.raw_relations)

    def list_properties(self) -> list[dict]:
        return list(self.idx.raw_properties)

    def list_axioms(self) -> list[dict]:
        return list(self.idx.raw_axioms)

    # ------------------------------------------------------------------
    # persistence
    # ------------------------------------------------------------------
    def to_dict(self) -> dict:
        """Serialise the current (possibly mutated) ontology to a dict."""
        idx = self.idx
        return {
            "version": "1.0",
            "domain": idx.domain,
            "entity_types": idx.raw_concepts,
            "properties": idx.raw_properties,
            "relations": idx.raw_relations,
            "axioms": idx.raw_axioms,
            "rules": idx.raw_rules,
            "trigger_rules": idx.raw_triggers,
            "operations": idx.raw_operations,
            "service_compositions": idx.raw_service_compositions,
            "permission_rules": idx.raw_permissions,
            "glossary": idx.raw_glossary,
            "external_mappings": idx.raw_external_mappings,
            "taxonomy": idx.raw_taxonomy,
            "metadata": idx.metadata,
        }

    def save(self, path: str) -> None:
        """Write the mutated ontology to a JSON file."""
        import json
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)
        logger.info("Saved edited ontology to %s", path)

    # ------------------------------------------------------------------
    # change-log summary
    # ------------------------------------------------------------------
    def changelog_summary(self) -> dict:
        from collections import Counter
        ops = Counter((r.op, r.target) for r in self.changelog)
        return {
            "total_changes": len(self.changelog),
            "by_op_target": {f"{op}_{tgt}": n for (op, tgt), n in ops.items()},
            "records": [str(r) for r in self.changelog],
        }
