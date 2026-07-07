"""Hearst Pattern matching for taxonomy construction.

Uses regex patterns to find is-a relations directly from text.
This is the most reliable (deterministic) method for taxonomy construction.
"""
from __future__ import annotations

import re
import logging
from typing import Optional

logger = logging.getLogger("ontology_gen.hearst")


class HearstPatternMatcher:
    """Match Hearst patterns in Chinese and English text to find is-a relations."""

    # Chinese patterns: (child, parent) pairs
    # Each pattern: (regex, child_group, parent_group)
    PATTERNS = [
        # "X是一种Y" / "X是一种Y" -> X is-a Y
        (re.compile(r"(.+?)是一(?:种|个|类)(.+?)"), 1, 2),
        # "X属于Y范畴" / "X属于Y" -> X is-a Y
        (re.compile(r"(.+?)属于(.+?)(?:范畴|类别|大类)"), 1, 2),
        # "X是Y的子类" -> X is-a Y
        (re.compile(r"(.+?)是(.+?)的子类"), 1, 2),
        # "X是Y的一种" -> X is-a Y
        (re.compile(r"(.+?)是(.+?)的一(?:种|个|类)"), 1, 2),
        # "Y包括X" / "Y包含X" -> X is-a Y
        (re.compile(r"(.+?)包括(.+?)"), 2, 1),
        # "Y分为X1、X2、X3" -> Xi is-a Y
        (re.compile(r"(.+?)分为(.+?)"), 2, 1),
    ]

    # English patterns
    EN_PATTERNS = [
        # "X is a Y" / "X is an Y"
        (re.compile(r"(\w[\w\s]+?)\s+is\s+(?:a|an)\s+(\w[\w\s]+?)", re.IGNORECASE), 1, 2),
        # "X is a kind of Y"
        (re.compile(r"(\w[\w\s]+?)\s+is\s+a\s+kind\s+of\s+(\w[\w\s]+?)", re.IGNORECASE), 1, 2),
        # "X such as Y" -> Y is-a X
        (re.compile(r"(\w[\w\s]+?)\s+such\s+as\s+(\w[\w\s]+?)", re.IGNORECASE), 2, 1),
        # "Y including X" -> X is-a Y
        (re.compile(r"(\w[\w\s]+?)\s+including\s+(\w[\w\s]+?)", re.IGNORECASE), 2, 1),
    ]

    def match(self, text: str) -> list[tuple[str, str, float]]:
        """
        Find all is-a relations in text using Hearst patterns.

        Args:
            text: Input text

        Returns:
            List of (child, parent, confidence) tuples
        """
        results = []

        # Match Chinese patterns
        for pattern, child_group, parent_group in self.PATTERNS:
            for match in pattern.finditer(text):
                child = match.group(child_group).strip().rstrip("，。、；")
                parent = match.group(parent_group).strip().rstrip("，。、；")

                # Filter out matches that are too long (likely not concept names)
                if len(child) > 20 or len(parent) > 20:
                    continue
                if len(child) < 2 or len(parent) < 2:
                    continue

                results.append((child, parent, 0.95))  # High confidence for pattern match

        # Match English patterns
        for pattern, child_group, parent_group in self.EN_PATTERNS:
            for match in pattern.finditer(text):
                child = match.group(child_group).strip()
                parent = match.group(parent_group).strip()

                if len(child) > 30 or len(parent) > 30:
                    continue
                if len(child) < 2 or len(parent) < 2:
                    continue

                results.append((child, parent, 0.90))

        # Deduplicate
        seen = set()
        unique = []
        for child, parent, conf in results:
            key = (child, parent)
            if key not in seen:
                seen.add(key)
                unique.append((child, parent, conf))

        logger.info(f"Hearst pattern matching: found {len(unique)} is-a relations")
        return unique

    def match_from_chunks(self, chunks: list[str]) -> list[tuple[str, str, float]]:
        """Match patterns across multiple text chunks."""
        all_results = []
        for chunk in chunks:
            all_results.extend(self.match(chunk))

        # Deduplicate across chunks, keeping highest confidence
        best = {}
        for child, parent, conf in all_results:
            key = (child, parent)
            if key not in best or conf > best[key]:
                best[key] = conf

        return [(c, p, conf) for (c, p), conf in best.items()]
