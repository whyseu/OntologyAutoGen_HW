"""Axiom risk classification (low/medium/high).

Classifies axioms by risk level and determines whether they can be auto-adopted
or need human review.
"""
from __future__ import annotations

import logging
from typing import Optional

from ..config import Config
from ..models import Axiom, AxiomType, RiskLevel

logger = logging.getLogger("ontology_gen.risk_classifier")


class AxiomRiskClassifier:
    """Classify axioms by risk level and adoption policy."""

    # Risk level mapping by axiom type
    RISK_MAP = {
        AxiomType.DOMAIN: RiskLevel.LOW,
        AxiomType.RANGE: RiskLevel.LOW,
        AxiomType.SUBCLASS_OF: RiskLevel.MEDIUM,
        AxiomType.INVERSE_OF: RiskLevel.MEDIUM,
        AxiomType.DISJOINT_WITH: RiskLevel.HIGH,
        AxiomType.EQUIVALENT_CLASS: RiskLevel.HIGH,
        AxiomType.TRANSITIVE_PROPERTY: RiskLevel.HIGH,
    }

    def __init__(self, config: Config):
        self.config = config

    def classify(self, axiom: Axiom) -> RiskLevel:
        """Classify an axiom's risk level based on its type."""
        risk = self.RISK_MAP.get(axiom.axiom_type, RiskLevel.MEDIUM)
        axiom.risk_level = risk
        return risk

    def should_auto_adopt(self, axiom: Axiom) -> bool:
        """
        Determine if an axiom should be auto-adopted.

        - Low risk (domain/range): confidence > 0.80 -> auto-adopt
        - Medium risk (subClassOf, inverseOf): confidence > 0.90 -> auto-adopt
        - High risk (disjointWith, equivalentClass, TransitiveProperty): never auto-adopt
        """
        self.classify(axiom)

        if axiom.risk_level == RiskLevel.LOW:
            return axiom.confidence >= self.config.axiom_auto_adopt_low
        elif axiom.risk_level == RiskLevel.MEDIUM:
            return axiom.confidence >= self.config.axiom_auto_adopt_medium
        else:  # HIGH
            return False

    def classify_batch(self, axioms: list[Axiom]) -> dict:
        """
        Classify a batch of axioms.

        Returns:
            {
                "auto_adopted": [Axiom],
                "needs_review": [Axiom],
                "rejected": [Axiom],  # confidence < 0.7
                "summary": {"low": N, "medium": N, "high": N}
            }
        """
        auto_adopted = []
        needs_review = []
        rejected = []
        summary = {"low": 0, "medium": 0, "high": 0}

        for axiom in axioms:
            self.classify(axiom)
            summary[axiom.risk_level.value] += 1

            if axiom.confidence < 0.7:
                rejected.append(axiom)
            elif self.should_auto_adopt(axiom):
                axiom.validated = True
                auto_adopted.append(axiom)
            else:
                needs_review.append(axiom)

        logger.info(
            f"Axiom classification: {len(auto_adopted)} auto-adopted, "
            f"{len(needs_review)} needs review, {len(rejected)} rejected. "
            f"Risk: low={summary['low']}, medium={summary['medium']}, high={summary['high']}"
        )

        return {
            "auto_adopted": auto_adopted,
            "needs_review": needs_review,
            "rejected": rejected,
            "summary": summary,
        }
