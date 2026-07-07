"""Algorithm 5.2-A: Data-driven domain/range inference.

Infers the domain and range of properties using statistical majority voting
from instance data.
"""
from __future__ import annotations

import logging
from collections import Counter
from typing import Optional

from ..config import Config
from ..models import Axiom, AxiomType, RiskLevel

logger = logging.getLogger("ontology_gen.domain_range_inferrer")


class DomainRangeInferrer:
    """Statistical domain/range inference using majority voting."""

    def __init__(self, config: Config):
        self.config = config

    def infer_domain(
        self,
        triples: list[tuple[str, str, any]],
        property_name: str,
        class_lookup: dict[str, str] | None = None,
    ) -> dict:
        """
        Infer the domain of a property from instance data.

        For each triple (s, P, o), look up the class of s.
        Majority vote determines the domain.

        Confidence levels:
        - > 95%: auto-adopt
        - 80-95%: needs human review
        - < 80%: don't generate domain axiom

        Args:
            triples: List of (subject_id, predicate, object) tuples
            property_name: Name of the property to infer domain for
            class_lookup: {instance_id: class_name} mapping

        Returns:
            {
                "domain": str | None,     # Inferred domain class
                "confidence": float,       # 0-1
                "status": "auto" | "review" | "skip",
                "distribution": dict,      # {class_name: count}
            }
        """
        class_lookup = class_lookup or {}
        counts = Counter()

        for s, p, o in triples:
            if p != property_name:
                continue
            cls = class_lookup.get(s, "unknown")
            counts[cls] += 1

        total = sum(counts.values())
        if total == 0:
            return {"domain": None, "confidence": 0, "status": "skip", "distribution": {}}

        top_class, top_count = counts.most_common(1)[0]
        confidence = top_count / total

        if confidence >= self.config.domain_range_auto_threshold:
            status = "auto"
        elif confidence >= self.config.domain_range_review_threshold:
            status = "review"
        else:
            status = "skip"

        return {
            "domain": top_class if status != "skip" else None,
            "confidence": confidence,
            "status": status,
            "distribution": dict(counts),
        }

    def infer_range(
        self,
        triples: list[tuple[str, str, any]],
        property_name: str,
        type_lookup: dict[str, str] | None = None,
    ) -> dict:
        """
        Infer the range of a property from instance data.

        For object properties: look up the class of the object.
        For data properties: infer the data type from values.

        Args:
            triples: List of (subject_id, predicate, object) tuples
            property_name: Name of the property
            type_lookup: {instance_id: class_name} or {value: type_name}

        Returns:
            Same format as infer_domain
        """
        type_lookup = type_lookup or {}
        counts = Counter()

        for s, p, o in triples:
            if p != property_name:
                continue
            # Try to look up the type
            obj_type = type_lookup.get(str(o))
            if obj_type:
                counts[obj_type] += 1
            else:
                # Infer type from value
                counts[self._infer_type(o)] += 1

        total = sum(counts.values())
        if total == 0:
            return {"range": None, "confidence": 0, "status": "skip", "distribution": {}}

        top_type, top_count = counts.most_common(1)[0]
        confidence = top_count / total

        if confidence >= self.config.domain_range_auto_threshold:
            status = "auto"
        elif confidence >= self.config.domain_range_review_threshold:
            status = "review"
        else:
            status = "skip"

        return {
            "range": top_type if status != "skip" else None,
            "confidence": confidence,
            "status": status,
            "distribution": dict(counts),
        }

    def infer_all(
        self,
        triples: list[tuple[str, str, any]],
        properties: list[str],
        class_lookup: dict[str, str] | None = None,
        type_lookup: dict[str, str] | None = None,
    ) -> list[Axiom]:
        """
        Infer domain and range for all properties.

        Returns:
            List of Axiom objects (only auto-adopted ones)
        """
        axioms = []
        class_lookup = class_lookup or {}
        type_lookup = type_lookup or {}

        for prop in properties:
            # Infer domain
            domain_result = self.infer_domain(triples, prop, class_lookup)
            if domain_result["status"] == "auto" and domain_result["domain"]:
                axiom = Axiom(
                    axiom_type=AxiomType.DOMAIN,
                    subject=prop,
                    obj=domain_result["domain"],
                    confidence=domain_result["confidence"],
                    risk_level=RiskLevel.LOW,
                    source="data_driven",
                    rationale=f"Statistical: {domain_result['confidence']:.1%} of instances have domain '{domain_result['domain']}'",
                    validated=True,
                )
                axioms.append(axiom)

            # Infer range
            range_result = self.infer_range(triples, prop, type_lookup)
            if range_result["status"] == "auto" and range_result["range"]:
                axiom = Axiom(
                    axiom_type=AxiomType.RANGE,
                    subject=prop,
                    obj=range_result["range"],
                    confidence=range_result["confidence"],
                    risk_level=RiskLevel.LOW,
                    source="data_driven",
                    rationale=f"Statistical: {range_result['confidence']:.1%} of values have type '{range_result['range']}'",
                    validated=True,
                )
                axioms.append(axiom)

        logger.info(f"Domain/range inference: {len(axioms)} axioms from {len(properties)} properties")
        return axioms

    @staticmethod
    def _infer_type(value: any) -> str:
        """Infer data type from a value."""
        if isinstance(value, bool):
            return "bool"
        if isinstance(value, int):
            return "int"
        if isinstance(value, float):
            return "float"
        if isinstance(value, str):
            # Try to detect date
            import re
            if re.match(r"\d{4}-\d{2}-\d{2}", value):
                return "date"
            return "string"
        return "unknown"
