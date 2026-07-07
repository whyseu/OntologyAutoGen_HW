"""Algorithm 3.3: Cycle detection in taxonomy graph (DFS).

Detects cycles in the is-a relation graph and optionally removes them
by deleting the lowest-confidence edge on each cycle.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from typing import Optional

logger = logging.getLogger("ontology_gen.cycle_detector")


class CycleDetector:
    """DFS-based cycle detection and resolution for taxonomy graphs."""

    def detect(self, edges: list[tuple[str, str]]) -> dict:
        """
        Detect if the taxonomy graph has cycles.

        Args:
            edges: List of (child_id, parent_id) tuples representing is-a relations

        Returns:
            {
                "has_cycle": bool,
                "cycles": list[list[str]],  # Each cycle as a node sequence
            }
        """
        # Build adjacency list (parent -> children)
        graph = defaultdict(list)
        for child, parent in edges:
            graph[parent].append(child)

        visited = set()
        rec_stack = set()
        cycles = []

        def dfs(node: str, path: list[str]) -> None:
            visited.add(node)
            rec_stack.add(node)
            path.append(node)

            for neighbor in graph.get(node, []):
                if neighbor not in visited:
                    dfs(neighbor, path)
                elif neighbor in rec_stack:
                    # Found a cycle
                    cycle_start = path.index(neighbor)
                    cycle = path[cycle_start:] + [neighbor]
                    cycles.append(cycle)

            path.pop()
            rec_stack.discard(node)

        all_nodes = set()
        for child, parent in edges:
            all_nodes.add(child)
            all_nodes.add(parent)

        for node in all_nodes:
            if node not in visited:
                dfs(node, [])

        has_cycle = len(cycles) > 0
        if has_cycle:
            logger.warning(f"Cycle detection: found {len(cycles)} cycle(s)")
        else:
            logger.info("Cycle detection: no cycles found")

        return {
            "has_cycle": has_cycle,
            "cycles": cycles,
        }

    def remove_cycles(
        self,
        edges: list[tuple[str, str]],
        confidences: dict[tuple[str, str], float] | None = None,
    ) -> list[tuple[str, str]]:
        """
        Remove cycles by deleting the lowest-confidence edge on each cycle.

        Args:
            edges: List of (child_id, parent_id) edges
            confidences: {(child, parent): confidence} mapping

        Returns:
            Edge list with cycles removed
        """
        confidences = confidences or {}
        remaining = list(edges)
        max_iterations = len(edges)  # Safety limit

        for _ in range(max_iterations):
            result = self.detect(remaining)
            if not result["has_cycle"]:
                break

            # Find the cycle and remove the lowest-confidence edge
            for cycle in result["cycles"]:
                # Find edges on this cycle
                cycle_edges = []
                for i in range(len(cycle) - 1):
                    edge = (cycle[i], cycle[i + 1])
                    if edge in remaining:
                        cycle_edges.append(edge)
                    # Also check reverse direction
                    edge_rev = (cycle[i + 1], cycle[i])
                    if edge_rev in remaining:
                        cycle_edges.append(edge_rev)

                if not cycle_edges:
                    continue

                # Remove the edge with lowest confidence
                if confidences:
                    weakest = min(cycle_edges, key=lambda e: confidences.get(e, 0.5))
                else:
                    weakest = cycle_edges[0]  # Just remove the first one

                remaining.remove(weakest)
                logger.info(f"Removed edge {weakest} to break cycle")

        return remaining

    def topological_sort(self, edges: list[tuple[str, str]]) -> list[str] | None:
        """
        Topological sort of the taxonomy graph.

        Returns:
            Node list in topological order (root first), or None if cycle exists.
        """
        result = self.detect(edges)
        if result["has_cycle"]:
            return None

        # Kahn's algorithm
        in_degree = defaultdict(int)
        graph = defaultdict(list)
        all_nodes = set()

        for child, parent in edges:
            graph[parent].append(child)
            in_degree[child] += 1
            all_nodes.add(child)
            all_nodes.add(parent)

        queue = [n for n in all_nodes if in_degree[n] == 0]
        sorted_nodes = []

        while queue:
            node = queue.pop(0)
            sorted_nodes.append(node)
            for neighbor in graph.get(node, []):
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        return sorted_nodes if len(sorted_nodes) == len(all_nodes) else None
