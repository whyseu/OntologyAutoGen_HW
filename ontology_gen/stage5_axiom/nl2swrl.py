"""NL2SWRL: Natural language to SWRL rule pipeline (4 steps).

Step 1: Input preprocessing — decompose NL rule into conditions + conclusion
Step 2: Ontology binding — map NL terms to ontology elements
Step 3: LLM generate — generate SWRL rule in JSON atom format
Step 4: Syntax validation + error fix — pure Python validation, max 3 iterations
"""
from __future__ import annotations

import logging
from typing import Optional

from ..config import Config
from ..llm_client import LLMClient
from ..models import Rule, RuleAtom, Concept, Property, Ontology
from .prompts import SWRL_STEP1_PROMPT, SWRL_STEP2_PROMPT, SWRL_STEP3_PROMPT, SWRL_STEP4_PROMPT

logger = logging.getLogger("ontology_gen.nl2swrl")


class NL2SWRL:
    """4-step NL to SWRL rule conversion pipeline."""

    def __init__(self, config: Config, llm_client: LLMClient):
        self.config = config
        self.llm = llm_client

    def convert(self, nl_rule: str, ontology: Ontology) -> Rule:
        """
        Convert a natural language rule to a SWRL rule.

        Args:
            nl_rule: Natural language rule text
            ontology: Ontology with confirmed concepts and properties

        Returns:
            Rule object (may be partially filled if LLM unavailable)
        """
        # Step 1: Preprocessing
        parsed = self._preprocess(nl_rule)
        if not parsed:
            return Rule(name="failed", description=nl_rule, nl_source=nl_rule)

        # Step 2: Ontology binding
        bound = self._bind_to_ontology(parsed, ontology)
        if not bound:
            return Rule(name="failed", description=nl_rule, nl_source=nl_rule)

        # Step 3: Generate SWRL
        rule = self._generate_swrl(bound, ontology, nl_rule)
        if not rule:
            return Rule(name="failed", description=nl_rule, nl_source=nl_rule)

        # Step 4: Validate and fix
        rule = self._validate_and_fix(rule, ontology)

        return rule

    def _preprocess(self, nl_rule: str) -> dict | None:
        """Step 1: Decompose NL rule into conditions and conclusion."""
        if not self.config.llm_available:
            return self._rule_based_preprocess(nl_rule)

        prompt = SWRL_STEP1_PROMPT.format(nl_rule=nl_rule)
        messages = [
            {"role": "system", "content": "You are a rule parser. Respond in JSON only."},
            {"role": "user", "content": prompt},
        ]
        return self.llm.chat_json(messages, temperature=0.1)

    @staticmethod
    def _rule_based_preprocess(nl_rule: str) -> dict:
        """Fallback: rule-based preprocessing when LLM is unavailable."""
        import re

        conditions = []
        conclusion = {}

        # Split by "则" or "那么" (then)
        parts = re.split(r"则|那么|就", nl_rule, maxsplit=1)
        if len(parts) == 2:
            cond_text = parts[0].strip()
            concl_text = parts[1].strip()

            # Remove "如果" (if) from condition
            cond_text = re.sub(r"^如果|^若|^当", "", cond_text).strip()

            # Split conditions by "且" or "并" or "and"
            cond_parts = re.split(r"且|并|and|AND", cond_text)
            for cp in cond_parts:
                cp = cp.strip()
                if cp:
                    cond_type = "comparison" if any(op in cp for op in [">", "<", "=", ">=", "<="]) else "class_membership"
                    conditions.append({"text": cp, "type": cond_type})

            conclusion = {"text": concl_text, "type": "class_assertion"}
        else:
            # No clear if-then structure
            conditions.append({"text": nl_rule, "type": "relation"})
            conclusion = {"text": nl_rule, "type": "property_assertion"}

        return {"conditions": conditions, "conclusion": conclusion}

    def _bind_to_ontology(self, parsed: dict, ontology: Ontology) -> dict | None:
        """Step 2: Bind NL terms to ontology elements."""
        concept_names = [c.name for c in ontology.entity_types]
        property_names = [p.name for p in ontology.properties]

        # Extract all terms from conditions and conclusion
        all_terms = set()
        for cond in parsed.get("conditions", []):
            all_terms.add(cond.get("text", ""))
        all_terms.add(parsed.get("conclusion", {}).get("text", ""))

        if not self.config.llm_available:
            return self._rule_based_bind(parsed, concept_names, property_names)

        prompt = SWRL_STEP2_PROMPT.format(
            concepts=concept_names,
            properties=property_names,
            terms=list(all_terms),
        )
        messages = [
            {"role": "system", "content": "You are an ontology binder. Respond in JSON only."},
            {"role": "user", "content": prompt},
        ]
        bindings = self.llm.chat_json(messages, temperature=0.1)

        return {**parsed, "bindings": bindings}

    @staticmethod
    def _rule_based_bind(parsed: dict, concepts: list[str], properties: list[str]) -> dict:
        """Fallback: rule-based binding using string matching."""
        bindings = []
        unbound = []

        for cond in parsed.get("conditions", []):
            text = cond.get("text", "")
            # Check if any concept name appears in the text
            for concept in concepts:
                if concept in text:
                    bindings.append({
                        "nl_term": text,
                        "ontology_term": concept,
                        "confidence": 0.8,
                        "method": "exact_match",
                    })
                    break
            else:
                unbound.append(text)

        return {**parsed, "bindings": {"bindings": bindings, "unbound": unbound}}

    def _generate_swrl(self, bound: dict, ontology: Ontology, nl_rule: str) -> Rule | None:
        """Step 3: Generate SWRL rule using LLM."""
        if not self.config.llm_available:
            return self._rule_based_generate(bound, ontology, nl_rule)

        concepts = [c.name for c in ontology.entity_types]
        properties = [p.name for p in ontology.properties]

        prompt = SWRL_STEP3_PROMPT.format(
            conditions=bound.get("conditions", []),
            conclusion=bound.get("conclusion", {}),
            concepts=concepts,
            properties=properties,
        )
        messages = [
            {"role": "system", "content": "You are a SWRL rule generator. Respond in JSON only."},
            {"role": "user", "content": prompt},
        ]
        result = self.llm.chat_json(messages, temperature=0.1)

        if not result:
            return None

        # Build Rule object
        body_atoms = [
            RuleAtom(atom_type=a.get("atom_type", ""), predicate=a.get("predicate", ""),
                     variables=a.get("variables", []))
            for a in result.get("body", [])
        ]
        head_atoms = [
            RuleAtom(atom_type=a.get("atom_type", ""), predicate=a.get("predicate", ""),
                     variables=a.get("variables", []))
            for a in result.get("head", [])
        ]

        return Rule(
            name=result.get("rule_name", "unnamed_rule"),
            description=result.get("description", nl_rule),
            body=body_atoms,
            head=head_atoms,
            confidence=0.8,
            nl_source=nl_rule,
        )

    @staticmethod
    def _rule_based_generate(bound: dict, ontology: Ontology, nl_rule: str) -> Rule:
        """Fallback: create a basic rule structure from parsed data."""
        body_atoms = []
        head_atoms = []

        bindings = bound.get("bindings", {}).get("bindings", [])

        for cond in bound.get("conditions", []):
            text = cond.get("text", "")
            # Find binding
            binding = next((b for b in bindings if b.get("nl_term") == text), None)
            if binding:
                term = binding.get("ontology_term", "")
                if cond.get("type") == "comparison":
                    body_atoms.append(RuleAtom(atom_type="builtin_atom", predicate="greaterThan", variables=["?x", "?y"]))
                else:
                    body_atoms.append(RuleAtom(atom_type="class_atom", predicate=term, variables=["?x"]))

        conclusion = bound.get("conclusion", {})
        concl_binding = next((b for b in bindings if b.get("nl_term") == conclusion.get("text", "")), None)
        if concl_binding:
            head_atoms.append(RuleAtom(atom_type="class_atom", predicate=concl_binding.get("ontology_term", ""), variables=["?x"]))

        return Rule(
            name="generated_rule",
            description=nl_rule,
            body=body_atoms,
            head=head_atoms,
            confidence=0.5,
            nl_source=nl_rule,
        )

    def _validate_and_fix(self, rule: Rule, ontology: Ontology) -> Rule:
        """Step 4: Validate rule and attempt to fix errors (max 3 iterations)."""
        for iteration in range(self.config.swrl_max_fix_iterations):
            errors = self._validate(rule, ontology)
            if not errors:
                rule.validated = True
                logger.info(f"SWRL rule '{rule.name}' validated successfully")
                return rule

            logger.info(f"SWRL validation iteration {iteration+1}: {len(errors)} errors")

            if not self.config.llm_available:
                # Can't fix without LLM
                break

            # Try to fix with LLM
            rule = self._llm_fix(rule, errors, ontology)

        # Final validation
        errors = self._validate(rule, ontology)
        rule.validated = len(errors) == 0
        if errors:
            logger.warning(f"SWRL rule '{rule.name}' has {len(errors)} unresolved errors: {errors}")

        return rule

    @staticmethod
    def _validate(rule: Rule, ontology: Ontology) -> list[str]:
        """Pure Python SWRL validation (no owlready2 dependency)."""
        errors = []

        # Check 1: Variable binding completeness
        # All variables in head must appear in body
        body_vars = set()
        for atom in rule.body:
            body_vars.update(v for v in atom.variables if v.startswith("?"))

        head_vars = set()
        for atom in rule.head:
            head_vars.update(v for v in atom.variables if v.startswith("?"))

        unbound = head_vars - body_vars
        if unbound:
            errors.append(f"Head variables not bound in body: {unbound}")

        # Check 2: All body variables must be bound by some atom
        # (a variable appearing in a builtin atom must also appear in a class/property atom)
        class_prop_vars = set()
        builtin_vars = set()
        for atom in rule.body:
            if atom.atom_type in ("class_atom", "property_atom"):
                class_prop_vars.update(atom.variables)
            elif atom.atom_type == "builtin_atom":
                builtin_vars.update(atom.variables)

        unbound_builtin = builtin_vars - class_prop_vars
        if unbound_builtin:
            errors.append(f"Builtin variables not bound by class/property atoms: {unbound_builtin}")

        # Check 3: Ontology element existence
        valid_concepts = {c.name for c in ontology.entity_types}
        valid_properties = {p.name for p in ontology.properties}

        for atom in rule.body + rule.head:
            if atom.atom_type == "class_atom":
                if atom.predicate and atom.predicate not in valid_concepts:
                    # Allow common built-in predicates
                    if atom.predicate not in ("Thing", "Nothing"):
                        errors.append(f"Unknown concept in rule: '{atom.predicate}'")
            elif atom.atom_type == "property_atom":
                if atom.predicate and atom.predicate not in valid_properties:
                    errors.append(f"Unknown property in rule: '{atom.predicate}'")

        # Check 4: Non-empty body and head
        if not rule.body:
            errors.append("Rule body is empty")
        if not rule.head:
            errors.append("Rule head is empty")

        return errors

    def _llm_fix(self, rule: Rule, errors: list[str], ontology: Ontology) -> Rule:
        """Use LLM to fix SWRL rule errors."""
        import json
        from dataclasses import asdict

        rule_json = json.dumps(asdict(rule), ensure_ascii=False, indent=2)
        concepts = [c.name for c in ontology.entity_types]
        properties = [p.name for p in ontology.properties]

        prompt = SWRL_STEP4_PROMPT.format(
            rule_json=rule_json,
            errors="\n".join(f"- {e}" for e in errors),
            concepts=concepts,
            properties=properties,
        )
        messages = [
            {"role": "system", "content": "You are a SWRL rule fixer. Respond in JSON only."},
            {"role": "user", "content": prompt},
        ]
        result = self.llm.chat_json(messages, temperature=0.1)

        if result:
            body_atoms = [
                RuleAtom(atom_type=a.get("atom_type", ""), predicate=a.get("predicate", ""),
                         variables=a.get("variables", []))
                for a in result.get("body", [])
            ]
            head_atoms = [
                RuleAtom(atom_type=a.get("atom_type", ""), predicate=a.get("predicate", ""),
                         variables=a.get("variables", []))
                for a in result.get("head", [])
            ]
            rule.body = body_atoms
            rule.head = head_atoms

        return rule
