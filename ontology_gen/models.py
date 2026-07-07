"""Core data types for the ontology auto-generation pipeline.

All types use dataclass + asdict() for JSON serialization.
"""
from __future__ import annotations

import json
import uuid
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional


# ============================================================
# Enums
# ============================================================

class SourceType(str, Enum):
    RDB = "rdb"
    TEXT = "text"
    DIALOGUE = "dialogue"


class ConfidenceLevel(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class RiskLevel(str, Enum):
    LOW = "low"        # domain/range
    MEDIUM = "medium"  # subClassOf, inverseOf
    HIGH = "high"      # disjointWith, equivalentClass, TransitiveProperty


class RelationType(str, Enum):
    IS_A = "is-a"
    PART_OF = "part-of"
    ATTRIBUTE_OF = "attribute-of"
    RELATED_TO = "related-to"
    BUSINESS = "business"  # non-hierarchical business relation


class AxiomType(str, Enum):
    SUBCLASS_OF = "subClassOf"
    EQUIVALENT_CLASS = "equivalentClass"
    DISJOINT_WITH = "disjointWith"
    DOMAIN = "domain"
    RANGE = "range"
    INVERSE_OF = "inverseOf"
    TRANSITIVE_PROPERTY = "TransitiveProperty"


class ConceptLayer(str, Enum):
    DATA = "data"
    LOGIC = "logic"
    APPLICATION = "application"


class DerivationType(str, Enum):
    FORMULA = "formula"
    AGGREGATION = "aggregation"
    LOOKUP = "lookup"
    CONDITIONAL = "conditional"


class TriggerEventType(str, Enum):
    DATA_CHANGE = "data_change"
    TIME_BASED = "time_based"
    STATUS_TRANSITION = "status_transition"
    EXTERNAL_EVENT = "external_event"


class PermissionAction(str, Enum):
    READ = "read"
    WRITE = "write"
    DELETE = "delete"
    EXECUTE = "execute"
    APPROVE = "approve"


class ServiceCompositionType(str, Enum):
    SEQUENTIAL = "sequential"
    PARALLEL = "parallel"
    CONDITIONAL = "conditional"
    LOOP = "loop"
    EXCEPTION_HANDLING = "exception_handling"


class QueryPatternType(str, Enum):
    ENTITY_LOOKUP = "entity_lookup"
    FILTERED_QUERY = "filtered_query"
    JOIN_QUERY = "join_query"
    AGGREGATION = "aggregation"
    CROSS_SOURCE = "cross_source"
    TEMPLATE = "template"
    DATA_GAP = "data_gap"


# ============================================================
# Concept
# ============================================================

def _gen_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


@dataclass
class Concept:
    """A candidate concept extracted from data sources."""
    name: str
    id: str = field(default_factory=lambda: _gen_id("concept"))
    name_en: Optional[str] = None
    aliases: list[str] = field(default_factory=list)
    description: Optional[str] = None
    source: SourceType = SourceType.RDB
    source_ref: Optional[str] = None  # table name / doc name / line number
    confidence: float = 1.0
    properties: list[str] = field(default_factory=list)  # property IDs
    is_entity_type: bool = True  # True = entity type, False = value type
    instance_count: int = 0  # for granularity decision (Algorithm 2.4)
    layer: ConceptLayer = ConceptLayer.DATA
    identity_spec: Optional[str] = None

    def merge_from(self, other: Concept) -> None:
        """Merge another concept into this one (as alias)."""
        if other.name != self.name:
            self.aliases.append(other.name)
        self.aliases.extend(other.aliases)
        self.aliases = list(set(self.aliases))  # deduplicate
        if other.description and not self.description:
            self.description = other.description
        if other.name_en and not self.name_en:
            self.name_en = other.name_en
        self.confidence = max(self.confidence, other.confidence)
        self.properties = list(set(self.properties + other.properties))


# ============================================================
# Property
# ============================================================

@dataclass
class Property:
    """A property with a literal value (not a relation to another entity)."""
    name: str
    domain_concept_id: str
    id: str = field(default_factory=lambda: _gen_id("prop"))
    name_cn: Optional[str] = None
    value_type: str = "string"  # int/float/date/string/bool/enum
    enum_values: list[str] = field(default_factory=list)
    description: Optional[str] = None
    source: SourceType = SourceType.RDB
    source_ref: Optional[str] = None
    confidence: float = 1.0
    nullable: bool = True
    null_rate: float = 0.0
    validation_regex: Optional[str] = None
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    max_length: Optional[int] = None
    format_pattern: Optional[str] = None
    is_derived: bool = False
    derivation_formula: Optional[str] = None
    derivation_type: Optional[str] = None
    derivation_sources: list[str] = field(default_factory=list)
    usage_scope: list[str] = field(default_factory=list)


# ============================================================
# Relation
# ============================================================

@dataclass
class Relation:
    """A relation between two entity types."""
    name: str
    domain_concept_id: str
    range_concept_id: str
    id: str = field(default_factory=lambda: _gen_id("rel"))
    name_cn: Optional[str] = None
    relation_type: RelationType = RelationType.BUSINESS
    inverse_relation_id: Optional[str] = None
    aliases: list[str] = field(default_factory=list)
    description: Optional[str] = None
    source: SourceType = SourceType.RDB
    source_ref: Optional[str] = None  # FK info, text span, etc.
    confidence: float = 1.0
    cardinality: str = "1:N"  # 1:1, 1:N, N:M
    is_reified: bool = False
    reified_concept_id: Optional[str] = None  # intermediate concept if reified


# ============================================================
# Taxonomy
# ============================================================

@dataclass
class TaxonomyNode:
    """A node in the concept hierarchy."""
    concept_id: str
    parent_id: Optional[str] = None
    children_ids: list[str] = field(default_factory=list)
    depth: int = 0
    confidence: float = 1.0
    reason: Optional[str] = None  # why this parent-child relation


@dataclass
class Taxonomy:
    """The full concept hierarchy (is-a tree/forest)."""
    nodes: dict[str, TaxonomyNode] = field(default_factory=dict)
    root_ids: list[str] = field(default_factory=list)

    def add_node(self, node: TaxonomyNode) -> None:
        self.nodes[node.concept_id] = node
        if node.parent_id is None and node.concept_id not in self.root_ids:
            self.root_ids.append(node.concept_id)
        # Update parent's children list
        if node.parent_id and node.parent_id in self.nodes:
            parent = self.nodes[node.parent_id]
            if node.concept_id not in parent.children_ids:
                parent.children_ids.append(node.concept_id)

    def get_ancestors(self, concept_id: str) -> list[str]:
        """Get all ancestors of a concept (root first)."""
        ancestors = []
        node = self.nodes.get(concept_id)
        while node and node.parent_id:
            ancestors.append(node.parent_id)
            node = self.nodes.get(node.parent_id)
        return ancestors

    def get_descendants(self, concept_id: str) -> list[str]:
        """Get all descendants of a concept."""
        descendants = []
        node = self.nodes.get(concept_id)
        if not node:
            return descendants
        for child_id in node.children_ids:
            descendants.append(child_id)
            descendants.extend(self.get_descendants(child_id))
        return descendants

    def has_cycle(self) -> bool:
        """Detect if the taxonomy graph has a cycle (DFS)."""
        visited = set()
        rec_stack = set()

        def dfs(node_id: str) -> bool:
            visited.add(node_id)
            rec_stack.add(node_id)
            node = self.nodes.get(node_id)
            if node:
                for child_id in node.children_ids:
                    if child_id not in visited:
                        if dfs(child_id):
                            return True
                    elif child_id in rec_stack:
                        return True
            rec_stack.discard(node_id)
            return False

        return any(dfs(nid) for nid in self.nodes if nid not in visited)

    def topological_sort(self) -> Optional[list[str]]:
        """Return topological order (root first), or None if cycle exists."""
        if self.has_cycle():
            return None
        in_degree = {nid: 0 for nid in self.nodes}
        for node in self.nodes.values():
            for child_id in node.children_ids:
                if child_id in in_degree:
                    in_degree[child_id] += 1
        queue = [nid for nid, deg in in_degree.items() if deg == 0]
        result = []
        while queue:
            nid = queue.pop(0)
            result.append(nid)
            node = self.nodes.get(nid)
            if node:
                for child_id in node.children_ids:
                    if child_id in in_degree:
                        in_degree[child_id] -= 1
                        if in_degree[child_id] == 0:
                            queue.append(child_id)
        return result if len(result) == len(self.nodes) else None


# ============================================================
# Axiom
# ============================================================

@dataclass
class Axiom:
    """An OWL axiom constraint."""
    axiom_type: AxiomType
    subject: str  # concept ID or relation ID
    obj: str      # concept ID or data type
    id: str = field(default_factory=lambda: _gen_id("axiom"))
    confidence: float = 1.0
    risk_level: RiskLevel = RiskLevel.LOW
    source: str = "data_driven"  # data_driven / llm_driven / manual
    rationale: Optional[str] = None
    validated: bool = False


# ============================================================
# Rule (SWRL)
# ============================================================

@dataclass
class RuleAtom:
    """A single atom in a SWRL rule body or head."""
    atom_type: str  # class_atom / property_atom / builtin_atom / same_as_atom
    predicate: str  # e.g. "Customer", "hasAge", "swrlb:greaterThan"
    variables: list[str] = field(default_factory=list)  # e.g. ["?x", "?y"]


@dataclass
class Rule:
    """A business rule in SWRL-like JSON format."""
    name: str
    description: str
    body: list[RuleAtom] = field(default_factory=list)   # antecedent (conditions)
    head: list[RuleAtom] = field(default_factory=list)   # consequent (conclusion)
    id: str = field(default_factory=lambda: _gen_id("rule"))
    confidence: float = 1.0
    validated: bool = False
    nl_source: Optional[str] = None  # original natural language rule


# ============================================================
# Semantic Annotation (Category 2.6)
# ============================================================

@dataclass
class SemanticAnnotation:
    target_id: str
    target_type: str  # "concept" | "property" | "relation"
    annotation_key: str
    annotation_value: str
    id: str = field(default_factory=lambda: _gen_id("annot"))
    author: Optional[str] = None
    created_at: Optional[str] = None


# ============================================================
# Governance Rule (Category 2.7)
# ============================================================

@dataclass
class GovernanceRule:
    name: str
    description: str
    rule_type: str  # "naming_convention" | "cardinality_constraint" | "completeness_check" | "consistency_axiom"
    target_scope: str
    check_expression: str
    severity: str = "warning"  # "error" | "warning" | "info"
    id: str = field(default_factory=lambda: _gen_id("gov"))
    enabled: bool = True
    auto_fix: bool = False


# ============================================================
# Glossary Term (Category 3.1/3.2)
# ============================================================

@dataclass
class GlossaryTerm:
    standard_term: str
    aliases: list[str] = field(default_factory=list)
    definition: str = ""
    category: str = ""
    id: str = field(default_factory=lambda: _gen_id("term"))
    domain: str = ""
    owner: Optional[str] = None
    status: str = "active"  # active | deprecated | draft


# ============================================================
# External Mapping (Category 3.3)
# ============================================================

@dataclass
class ExternalMapping:
    internal_term_id: str
    external_system: str
    external_term: str
    external_code: Optional[str] = None
    mapping_type: str = "equivalent"  # equivalent | broader | narrower | related
    id: str = field(default_factory=lambda: _gen_id("extmap"))
    confidence: float = 1.0
    bidirectional: bool = True


# ============================================================
# Trigger Rule (Category 4.1)
# ============================================================

@dataclass
class TriggerRule:
    name: str
    description: str
    event_type: str  # "data_change" | "time_based" | "status_transition" | "external_event"
    event_source: str
    event_detail: str
    condition_expression: str
    condition_concepts: list[str] = field(default_factory=list)
    action_type: str = ""
    action_detail: str = ""
    action_target: str = ""
    id: str = field(default_factory=lambda: _gen_id("trigger"))
    priority: int = 0
    enabled: bool = True
    confidence: float = 1.0
    source: str = "text"
    nl_source: Optional[str] = None


# ============================================================
# Atomic Operation (Category 5.1/5.2/5.3)
# ============================================================

@dataclass
class AtomicOperation:
    name: str
    description: str
    parent_operation_id: Optional[str] = None
    inputs: list[dict] = field(default_factory=list)
    outputs: list[dict] = field(default_factory=list)
    preconditions: list[str] = field(default_factory=list)
    postconditions: list[str] = field(default_factory=list)
    id: str = field(default_factory=lambda: _gen_id("op"))
    actor_concept_id: Optional[str] = None
    target_concept_id: Optional[str] = None
    confidence: float = 1.0
    source: str = "text"


# ============================================================
# Service Composition (Category 5.4/5.5)
# ============================================================

@dataclass
class ServiceComposition:
    name: str
    description: str
    composition_type: str  # "sequential" | "parallel" | "conditional" | "loop" | "exception_handling"
    steps: list[dict] = field(default_factory=list)
    exception_handlers: list[dict] = field(default_factory=list)
    timeout_seconds: Optional[int] = None
    retry_policy: Optional[dict] = None
    id: str = field(default_factory=lambda: _gen_id("svc"))
    involved_concepts: list[str] = field(default_factory=list)
    confidence: float = 1.0
    source: str = "text"


# ============================================================
# Permission Subject (Category 6.2)
# ============================================================

@dataclass
class PermissionSubject:
    name: str
    subject_type: str  # "role" | "user_group" | "individual" | "system"
    id: str = field(default_factory=lambda: _gen_id("psubj"))
    parent_subject_id: Optional[str] = None
    description: Optional[str] = None


# ============================================================
# Permission Rule (Category 6.1/6.3/6.4)
# ============================================================

@dataclass
class PermissionRule:
    name: str
    description: str
    subject_id: str
    object_concept_id: str
    object_scope: str = "all"
    actions: list[str] = field(default_factory=list)
    effect: str = "allow"  # "allow" | "deny"
    condition: Optional[str] = None
    id: str = field(default_factory=lambda: _gen_id("perm"))
    priority: int = 0
    confidence: float = 1.0
    source: str = "text"


# ============================================================
# Query Pattern (Category 7.1-7.7)
# ============================================================

@dataclass
class QueryPattern:
    name: str
    description: str
    pattern_type: str  # "entity_lookup"|"filtered_query"|"join_query"|"aggregation"|"cross_source"|"template"|"data_gap"|"update"|"delete"
    target_concepts: list[str] = field(default_factory=list)
    filter_conditions: list[str] = field(default_factory=list)
    join_paths: list[str] = field(default_factory=list)
    aggregation_functions: list[str] = field(default_factory=list)
    suggested_indexes: list[str] = field(default_factory=list)
    cache_strategy: Optional[str] = None
    data_gap_fields: list[str] = field(default_factory=list)
    compensation_strategy: Optional[str] = None
    sql_template: Optional[str] = None
    parameters: list[dict] = field(default_factory=list)
    id: str = field(default_factory=lambda: _gen_id("qpat"))
    frequency: int = 0
    confidence: float = 1.0
    source: str = "query_log"


# ============================================================
# Ontology (final output container)
# ============================================================

@dataclass
class Ontology:
    """The complete ontology output — 7+1 semantic specification."""
    version: str = "2.0"
    domain: str = "unknown"
    entity_types: list[Concept] = field(default_factory=list)
    properties: list[Property] = field(default_factory=list)
    relations: list[Relation] = field(default_factory=list)
    taxonomy: Taxonomy = field(default_factory=Taxonomy)
    axioms: list[Axiom] = field(default_factory=list)
    rules: list[Rule] = field(default_factory=list)
    semantic_annotations: list[SemanticAnnotation] = field(default_factory=list)
    governance_rules: list[GovernanceRule] = field(default_factory=list)
    glossary: list[GlossaryTerm] = field(default_factory=list)
    external_mappings: list[ExternalMapping] = field(default_factory=list)
    trigger_rules: list[TriggerRule] = field(default_factory=list)
    operations: list[AtomicOperation] = field(default_factory=list)
    service_compositions: list[ServiceComposition] = field(default_factory=list)
    permission_subjects: list[PermissionSubject] = field(default_factory=list)
    permission_rules: list[PermissionRule] = field(default_factory=list)
    query_patterns: list[QueryPattern] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Serialize to dict (JSON-ready)."""
        return {
            "version": self.version,
            "domain": self.domain,
            "entity_types": [asdict(c) for c in self.entity_types],
            "properties": [asdict(p) for p in self.properties],
            "relations": [asdict(r) for r in self.relations],
            "taxonomy": {
                "nodes": {k: asdict(v) for k, v in self.taxonomy.nodes.items()},
                "root_ids": self.taxonomy.root_ids,
            },
            "axioms": [asdict(a) for a in self.axioms],
            "rules": [asdict(r) for r in self.rules],
            "semantic_annotations": [asdict(a) for a in self.semantic_annotations],
            "governance_rules": [asdict(g) for g in self.governance_rules],
            "glossary": [asdict(g) for g in self.glossary],
            "external_mappings": [asdict(m) for m in self.external_mappings],
            "trigger_rules": [asdict(t) for t in self.trigger_rules],
            "operations": [asdict(o) for o in self.operations],
            "service_compositions": [asdict(s) for s in self.service_compositions],
            "permission_subjects": [asdict(s) for s in self.permission_subjects],
            "permission_rules": [asdict(p) for p in self.permission_rules],
            "query_patterns": [asdict(q) for q in self.query_patterns],
            "metadata": self.metadata,
        }

    def to_json(self, path: str) -> None:
        """Serialize to JSON file."""
        from .utils import save_json
        save_json(self.to_dict(), path)

    def validate(self) -> list[str]:
        """Return list of validation error messages (empty = valid)."""
        errors = []
        concept_ids = {c.id for c in self.entity_types}
        prop_ids = {p.id for p in self.properties}
        rel_ids = {r.id for r in self.relations}

        # Check property domain references
        for prop in self.properties:
            if prop.domain_concept_id not in concept_ids:
                errors.append(f"Property '{prop.name}' references unknown concept: {prop.domain_concept_id}")

        # Check relation domain/range references
        for rel in self.relations:
            if rel.domain_concept_id not in concept_ids:
                errors.append(f"Relation '{rel.name}' domain references unknown concept: {rel.domain_concept_id}")
            if rel.range_concept_id not in concept_ids:
                errors.append(f"Relation '{rel.name}' range references unknown concept: {rel.range_concept_id}")

        # Check taxonomy node references
        for node in self.taxonomy.nodes.values():
            if node.parent_id and node.parent_id not in concept_ids:
                errors.append(f"Taxonomy node '{node.concept_id}' has unknown parent: {node.parent_id}")

        # Check taxonomy for cycles
        if self.taxonomy.has_cycle():
            errors.append("Taxonomy has a cycle")

        # Check trigger rule references
        for tr in self.trigger_rules:
            for cid in tr.condition_concepts:
                if cid not in concept_ids:
                    errors.append(f"TriggerRule '{tr.name}' references unknown concept: {cid}")

        # Check operation references
        for op in self.operations:
            if op.actor_concept_id and op.actor_concept_id not in concept_ids:
                errors.append(f"Operation '{op.name}' actor references unknown concept: {op.actor_concept_id}")
            if op.target_concept_id and op.target_concept_id not in concept_ids:
                errors.append(f"Operation '{op.name}' target references unknown concept: {op.target_concept_id}")

        # Check permission rule references
        psubj_ids = {s.id for s in self.permission_subjects}
        for pr in self.permission_rules:
            if pr.subject_id not in psubj_ids:
                errors.append(f"PermissionRule '{pr.name}' references unknown subject: {pr.subject_id}")
            if pr.object_concept_id not in concept_ids:
                errors.append(f"PermissionRule '{pr.name}' references unknown concept: {pr.object_concept_id}")

        # Check query pattern references
        for qp in self.query_patterns:
            for cid in qp.target_concepts:
                if cid not in concept_ids:
                    errors.append(f"QueryPattern '{qp.name}' references unknown concept: {cid}")

        return errors
