"""Reasoning module: symbolic inference + LLM context building.

This package consumes an already-generated ontology (output/ontology.json)
and provides:
  - OntologyIndex: an in-memory, indexed view of the ontology with name/id
    resolution, subclass graph, relation/property indexes.
  - SymbolicReasoner: deterministic, explainable inference over the ontology
    (transitive subclass reasoning, relation inheritance, domain/range checks,
    ECA trigger firing, derived-property derivation, with proof chains).
  - OntologyContextBuilder: serializes the ontology into a compact, LLM-readable
    text block so that "with-ontology" vs "without-ontology" LLM reasoning can
    be compared.
"""
from .ontology_loader import OntologyIndex, load_ontology
from .symbolic_reasoner import SymbolicReasoner, InferenceResult
from .context_builder import OntologyContextBuilder

__all__ = [
    "OntologyIndex",
    "load_ontology",
    "SymbolicReasoner",
    "InferenceResult",
    "OntologyContextBuilder",
]
