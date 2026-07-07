"""Tests for Algorithm 5.2-A: Data-driven domain/range inference."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ontology_gen.config import Config
from ontology_gen.stage5_axiom.domain_range_inferrer import DomainRangeInferrer


class TestDomainRangeInferrer:
    """Test statistical domain/range inference."""

    def setup_method(self):
        self.config = Config()
        self.inferrer = DomainRangeInferrer(self.config)

    def test_high_confidence_domain(self):
        """>95% consistency should auto-adopt."""
        triples = [
            ("c1", "hasAge", 25),
            ("c2", "hasAge", 30),
            ("c3", "hasAge", 35),
            ("c4", "hasAge", 40),
            ("c5", "hasAge", 28),
        ]
        class_lookup = {f"c{i}": "Customer" for i in range(1, 6)}

        result = self.inferrer.infer_domain(triples, "hasAge", class_lookup)
        assert result["domain"] == "Customer"
        assert result["confidence"] == 1.0
        assert result["status"] == "auto"

    def test_medium_confidence_domain(self):
        """80-95% should need review."""
        triples = [
            ("c1", "hasAge", 25),
            ("c2", "hasAge", 30),
            ("c3", "hasAge", 35),
            ("c4", "hasAge", 40),
            ("d1", "hasAge", 28),  # different class
        ]
        class_lookup = {
            "c1": "Customer", "c2": "Customer", "c3": "Customer",
            "c4": "Customer", "d1": "Doctor",
        }

        result = self.inferrer.infer_domain(triples, "hasAge", class_lookup)
        assert result["confidence"] == 0.8  # 4/5
        assert result["status"] == "review"

    def test_low_confidence_domain(self):
        """<80% should skip."""
        triples = [
            ("c1", "hasAge", 25),
            ("c2", "hasAge", 30),
            ("d1", "hasAge", 35),
            ("d2", "hasAge", 40),
            ("d3", "hasAge", 28),
        ]
        class_lookup = {
            "c1": "Customer", "c2": "Customer",
            "d1": "Doctor", "d2": "Doctor", "d3": "Doctor",
        }

        result = self.inferrer.infer_domain(triples, "hasAge", class_lookup)
        assert result["confidence"] == 0.6  # 3/5 for Doctor
        assert result["status"] == "skip"
        assert result["domain"] is None

    def test_range_inference(self):
        """Test range type inference from values."""
        triples = [
            ("c1", "hasAge", 25),
            ("c2", "hasAge", 30),
            ("c3", "hasAge", 35),
        ]
        result = self.inferrer.infer_range(triples, "hasAge")
        assert result["range"] == "int"
        assert result["confidence"] == 1.0
        assert result["status"] == "auto"

    def test_no_triples(self):
        """No triples should return skip."""
        result = self.inferrer.infer_domain([], "hasAge", {})
        assert result["status"] == "skip"
        assert result["domain"] is None

    def test_infer_all(self):
        """Test batch inference for multiple properties."""
        triples = [
            ("c1", "hasAge", 25),
            ("c2", "hasAge", 30),
            ("c1", "hasName", "Alice"),
            ("c2", "hasName", "Bob"),
        ]
        class_lookup = {"c1": "Customer", "c2": "Customer"}

        axioms = self.inferrer.infer_all(
            triples, ["hasAge", "hasName"], class_lookup
        )

        # Should generate domain axioms for both properties
        domain_axioms = [a for a in axioms if a.axiom_type.value == "domain"]
        assert len(domain_axioms) >= 1

    def test_type_inference(self):
        """Test type inference from different value types."""
        assert self.inferrer._infer_type(42) == "int"
        assert self.inferrer._infer_type(3.14) == "float"
        assert self.inferrer._infer_type("hello") == "string"
        assert self.inferrer._infer_type("2024-01-01") == "date"
        assert self.inferrer._infer_type(True) == "bool"
