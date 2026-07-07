"""Tests for Algorithm 3.3: Cycle detection (DFS)."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ontology_gen.stage3_taxonomy.cycle_detector import CycleDetector


class TestCycleDetector:
    """Test DFS-based cycle detection and removal."""

    def setup_method(self):
        self.detector = CycleDetector()

    def test_no_cycle(self):
        """A simple tree should have no cycles."""
        edges = [
            ("B", "A"),  # B is-a A
            ("C", "A"),  # C is-a A
            ("D", "B"),  # D is-a B
        ]
        result = self.detector.detect(edges)
        assert result["has_cycle"] is False
        assert len(result["cycles"]) == 0

    def test_simple_cycle(self):
        """A -> B -> A should be detected as a cycle."""
        edges = [
            ("B", "A"),  # B is-a A
            ("A", "B"),  # A is-a B (creates cycle)
        ]
        result = self.detector.detect(edges)
        assert result["has_cycle"] is True
        assert len(result["cycles"]) >= 1

    def test_complex_cycle(self):
        """A -> B -> C -> A should be detected."""
        edges = [
            ("B", "A"),  # B is-a A
            ("C", "B"),  # C is-a B
            ("A", "C"),  # A is-a C (creates cycle A->C->B->A)
        ]
        result = self.detector.detect(edges)
        assert result["has_cycle"] is True

    def test_remove_cycles(self):
        """remove_cycles should break all cycles."""
        edges = [
            ("B", "A"),  # B is-a A (valid)
            ("C", "B"),  # C is-a B (valid)
            ("A", "C"),  # A is-a C (creates cycle)
        ]
        confidences = {
            ("B", "A"): 0.9,
            ("C", "B"): 0.8,
            ("A", "C"): 0.5,  # Lowest confidence — should be removed
        }
        clean_edges = self.detector.remove_cycles(edges, confidences)
        assert ("A", "C") not in clean_edges, "Lowest confidence edge should be removed"
        assert ("B", "A") in clean_edges
        assert ("C", "B") in clean_edges

    def test_remove_cycles_no_confidence(self):
        """remove_cycles should work even without confidence scores."""
        edges = [
            ("B", "A"),
            ("A", "B"),
        ]
        clean_edges = self.detector.remove_cycles(edges)
        # Should have at most 1 edge remaining
        assert len(clean_edges) <= 1

    def test_topological_sort_no_cycle(self):
        """Topological sort should work for acyclic graphs."""
        edges = [
            ("B", "A"),
            ("C", "A"),
            ("D", "B"),
        ]
        sorted_nodes = self.detector.topological_sort(edges)
        assert sorted_nodes is not None
        assert "A" in sorted_nodes
        # A should come before B and C (since B and C depend on A)
        assert sorted_nodes.index("A") < sorted_nodes.index("B")
        assert sorted_nodes.index("A") < sorted_nodes.index("C")
        # B should come before D
        assert sorted_nodes.index("B") < sorted_nodes.index("D")

    def test_topological_sort_with_cycle(self):
        """Topological sort should return None for cyclic graphs."""
        edges = [
            ("B", "A"),
            ("A", "B"),
        ]
        result = self.detector.topological_sort(edges)
        assert result is None

    def test_empty_edges(self):
        """Empty edge list should have no cycles."""
        result = self.detector.detect([])
        assert result["has_cycle"] is False

    def test_single_edge(self):
        """Single edge should have no cycle."""
        result = self.detector.detect([("B", "A")])
        assert result["has_cycle"] is False

    def test_self_loop(self):
        """Self-loop (A -> A) should be detected as a cycle."""
        result = self.detector.detect([("A", "A")])
        assert result["has_cycle"] is True
