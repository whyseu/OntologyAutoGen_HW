"""End-to-end pipeline orchestrator.

Wires together all 5 stages of ontology auto-generation:
  Stage 1: Data preparation (quality scoring, DDL parsing, doc parsing)
  Stage 2: Concept extraction (RDB + text + merge + granularity)
  Stage 3: Taxonomy construction (Hearst + LLM + cycle removal)
  Stage 4: Relation/property construction (extraction + FK filter + M:N reify + normalize)
  Stage 5: Axiom/rule layer (domain/range + axioms + NL2SWRL + consistency check)
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

import yaml

from .config import Config
from .llm_client import LLMClient
from .models import Ontology, Concept, Property, Relation, Axiom, Rule, Taxonomy
from .utils import parse_ddl, load_json, save_json, logger

# Stage 1
from .stage1_data_prep.quality_scorer import QualityScorer
from .stage1_data_prep.doc_parser import DocumentParser
from .stage1_data_prep.query_pattern_analyzer import QueryPatternAnalyzer

# Stage 2
from .stage2_concept.rdb_concept_extractor import RDBConceptExtractor
from .stage2_concept.text_concept_extractor import TextConceptExtractor
from .stage2_concept.concept_merger import ConceptMerger
from .stage2_concept.granularity_decider import GranularityDecider
from .stage2_concept.layer_classifier import LayerClassifier
from .stage2_concept.identity_spec_extractor import IdentitySpecExtractor

# Stage 3
from .stage3_taxonomy.hearst_pattern import HearstPatternMatcher
from .stage3_taxonomy.taxonomy_inducer import TaxonomyInducer
from .stage3_taxonomy.relation_type_classifier import RelationTypeClassifier

# Stage 4
from .stage4_relation.relation_extractor import RelationExtractor
from .stage4_relation.m2m_reifier import M2MReifier
from .stage4_relation.relation_normalizer import RelationNormalizer
from .stage4_relation.derivation_extractor import DerivationExtractor
from .stage4_relation.validation_rule_extractor import ValidationRuleExtractor

# Stage 5
from .stage5_axiom.domain_range_inferrer import DomainRangeInferrer
from .stage5_axiom.axiom_generator import AxiomGenerator
from .stage5_axiom.axiom_risk_classifier import AxiomRiskClassifier
from .stage5_axiom.nl2swrl import NL2SWRL
from .stage5_axiom.consistency_checker import ConsistencyChecker

# Stage 6
from .stage6_semantic.glossary_builder import GlossaryBuilder
from .stage6_semantic.external_mapping_extractor import ExternalMappingExtractor
from .stage6_semantic.annotation_extractor import AnnotationExtractor
from .stage6_semantic.trigger_rule_extractor import TriggerRuleExtractor
from .stage6_semantic.governance_rule_generator import GovernanceRuleGenerator

# Stage 7
from .stage7_process.operation_extractor import OperationExtractor
from .stage7_process.service_composer import ServiceComposer
from .stage7_process.permission_extractor import PermissionExtractor

# Output
from .output.ontology_builder import OntologyBuilder
from .output.visualizer import StageVisualizer


class OntologyPipeline:
    """Full pipeline: data -> ontology JSON."""

    def __init__(self, config: Config | None = None):
        self.config = config or Config()
        self.llm = LLMClient(self.config)
        self.stage_results: dict[str, any] = {}

    def run(
        self,
        data_dir: str = "examples",
        output_dir: str = "output",
        config_file: str | None = None,
        business_rules: list[str] | None = None,
    ) -> Ontology:
        """
        Run the full ontology auto-generation pipeline.

        Args:
            data_dir: Directory containing DDL, docs, queries
            output_dir: Directory for output files
            config_file: Path to YAML config file (business terms, synonyms, etc.)
            business_rules: List of natural language business rules for NL2SWRL

        Returns:
            The final Ontology object
        """
        logger.info("=" * 60)
        logger.info("Ontology Auto-Generation Pipeline START")
        logger.info(f"  data_dir={data_dir}")
        logger.info(f"  output_dir={output_dir}")
        logger.info(f"  LLM available: {self.config.llm_available}")
        logger.info("=" * 60)

        # Load domain config
        domain_config = self._load_config(config_file)
        domain = domain_config.get("domain", "unknown")

        # Initialize builder
        builder = OntologyBuilder(domain=domain)

        # Initialize Visualizer
        visualizer = StageVisualizer(output_dir)

        # ============================================================
        # Stage 1: Data Preparation
        # ============================================================
        stage1_data = self._run_stage1(data_dir, domain_config)
        self.stage_results["stage1"] = stage1_data
        visualizer.visualize_stage1(stage1_data)

        # ============================================================
        # Stage 2: Concept Extraction
        # ============================================================
        stage2_data = self._run_stage2(stage1_data, domain_config, domain)
        self.stage_results["stage2"] = stage2_data
        builder.set_concepts(stage2_data["concepts"])
        visualizer.visualize_stage2(stage2_data)

        # ============================================================
        # Stage 3: Taxonomy Construction
        # ============================================================
        stage3_data = self._run_stage3(stage2_data, stage1_data, domain_config)
        self.stage_results["stage3"] = stage3_data
        builder.set_taxonomy(stage3_data["taxonomy"])
        visualizer.visualize_stage3(stage3_data)

        # ============================================================
        # Stage 4: Relation/Property Construction
        # ============================================================
        stage4_data = self._run_stage4(stage1_data, stage2_data, domain_config)
        self.stage_results["stage4"] = stage4_data
        builder.set_properties(stage4_data["properties"])
        builder.set_relations(stage4_data["relations"])
        visualizer.visualize_stage4(stage2_data, stage4_data)
        # Add reified intermediate concepts
        if stage4_data.get("new_concepts"):
            builder.add_concepts(stage4_data["new_concepts"])

        # ============================================================
        # Stage 5: Axiom/Rule Layer
        # ============================================================
        stage5_data = self._run_stage5(
            stage2_data, stage3_data, stage4_data, domain_config, business_rules
        )
        self.stage_results["stage5"] = stage5_data
        builder.set_axioms(stage5_data["axioms"])
        builder.set_rules(stage5_data["rules"])

        # ============================================================
        # Stage 6: Semantic Enrichment (Categories 2.6, 2.7, 3, 4)
        # ============================================================
        if self.config.enable_stage6:
            stage6_data = self._run_stage6(
                stage1_data, stage2_data, stage4_data, stage5_data, domain_config
            )
            self.stage_results["stage6"] = stage6_data
            builder.set_glossary(stage6_data["glossary"])
            builder.set_external_mappings(stage6_data["external_mappings"])
            builder.set_semantic_annotations(stage6_data["annotations"])
            builder.set_trigger_rules(stage6_data["trigger_rules"])
            builder.set_governance_rules(stage6_data["governance_rules"])

        # ============================================================
        # Stage 7: Process & Permission (Categories 5, 6, 7)
        # ============================================================
        if self.config.enable_stage7:
            stage7_data = self._run_stage7(
                stage1_data, stage2_data, stage4_data, domain_config,
                stage6_data.get("trigger_rules", []) if self.config.enable_stage6 else [],
            )
            self.stage_results["stage7"] = stage7_data
            builder.set_operations(stage7_data["operations"])
            builder.set_service_compositions(stage7_data["compositions"])
            builder.set_permission_subjects(stage7_data["permission_subjects"])
            builder.set_permission_rules(stage7_data["permission_rules"])
            builder.set_query_patterns(stage7_data["query_patterns"])

        # ============================================================
        # Build & Export
        # ============================================================
        ontology = builder.build()

        # Consistency check
        checker = ConsistencyChecker()
        consistency_report = checker.check(ontology)
        ontology.metadata["consistency_report"] = consistency_report

        # Save outputs
        os.makedirs(output_dir, exist_ok=True)
        ontology.to_json(os.path.join(output_dir, "ontology.json"))

        # Save stage reports
        self._save_stage_reports(output_dir)

        # Save consistency report
        save_json(consistency_report, os.path.join(output_dir, "consistency_report.json"))

        logger.info("=" * 60)
        logger.info("Pipeline COMPLETE")
        logger.info(f"  Entity types: {len(ontology.entity_types)}")
        logger.info(f"  Properties:   {len(ontology.properties)}")
        logger.info(f"  Relations:    {len(ontology.relations)}")
        logger.info(f"  Axioms:       {len(ontology.axioms)}")
        logger.info(f"  Rules:        {len(ontology.rules)}")
        logger.info(f"  Glossary:     {len(ontology.glossary)}")
        logger.info(f"  Triggers:     {len(ontology.trigger_rules)}")
        logger.info(f"  Operations:   {len(ontology.operations)}")
        logger.info(f"  Permissions:  {len(ontology.permission_rules)}")
        logger.info(f"  QueryPatterns:{len(ontology.query_patterns)}")
        logger.info(f"  Consistent:   {consistency_report['is_consistent']}")
        logger.info(f"  Output:       {output_dir}/ontology.json")
        logger.info("=" * 60)

        return ontology

    # ============================================================
    # Stage 1: Data Preparation
    # ============================================================

    def _run_stage1(self, data_dir: str, domain_config: dict) -> dict:
        """Stage 1: Load and prepare data sources."""
        logger.info("-" * 40)
        logger.info("Stage 1: Data Preparation")
        logger.info("-" * 40)

        data_path = Path(data_dir)
        result = {
            "ddl_text": "",
            "parsed_tables": [],
            "quality_scores": [],
            "docs_text": "",
            "query_log": [],
            "business_terms": domain_config.get("business_terms", []),
            "system_table_tags": domain_config.get("system_table_tags", {}),
        }

        # Load DDL
        ddl_path = data_path / "ddl"
        if ddl_path.exists():
            ddl_files = list(ddl_path.glob("*.sql"))
            if ddl_files:
                ddl_text = ddl_files[0].read_text(encoding="utf-8")
                result["ddl_text"] = ddl_text
                result["parsed_tables"] = parse_ddl(ddl_text)
                logger.info(f"  DDL loaded: {len(result['parsed_tables'])} tables from {ddl_files[0].name}")

        # Quality scoring
        if result["parsed_tables"]:
            scorer = QualityScorer(self.config)
            result["quality_scores"] = scorer.score_all_tables(result["parsed_tables"])
            passed = [s for s in result["quality_scores"] if s["should_process"]]
            logger.info(f"  Quality scoring: {len(passed)}/{len(result['quality_scores'])} tables passed")

        # Load documents
        docs_path = data_path / "docs"
        if docs_path.exists():
            parser = DocumentParser(self.config)
            doc_texts = []
            for doc_file in docs_path.iterdir():
                if doc_file.suffix in (".txt", ".md", ".html", ".pdf"):
                    parsed = parser.parse(str(doc_file))
                    if parsed and parsed.get("text"):
                        doc_texts.append(parsed["text"])
            result["docs_text"] = "\n\n".join(doc_texts)
            logger.info(f"  Documents loaded: {len(doc_texts)} files, {len(result['docs_text'])} chars")

        # Load query log
        queries_path = data_path / "queries"
        if queries_path.exists():
            query_files = list(queries_path.glob("*.jsonl"))
            if query_files:
                queries = []
                for qf in query_files:
                    for line in qf.read_text(encoding="utf-8").strip().split("\n"):
                        if line:
                            try:
                                import json
                                q_data = json.loads(line)
                                queries.append(q_data.get("sql", q_data.get("query", line)))
                            except json.JSONDecodeError:
                                queries.append(line)
                result["query_log"] = queries
                logger.info(f"  Query log loaded: {len(queries)} queries")

        return result

    # ============================================================
    # Stage 2: Concept Extraction
    # ============================================================

    def _run_stage2(self, stage1: dict, domain_config: dict, domain: str) -> dict:
        """Stage 2: Extract and merge concepts from RDB and text."""
        logger.info("-" * 40)
        logger.info("Stage 2: Concept Extraction")
        logger.info("-" * 40)

        all_concepts: list[Concept] = []

        # 2A: RDB concept extraction
        if stage1["ddl_text"]:
            rdb_extractor = RDBConceptExtractor(self.config, self.llm)
            rdb_concepts = rdb_extractor.extract_from_ddl(stage1["ddl_text"])

            # Filter by quality scores
            quality_map = {s["table_name"]: s["should_process"] for s in stage1["quality_scores"]}
            filtered = []
            for c in rdb_concepts:
                # Keep concepts from tables that passed quality check
                if c.source_ref and "table:" in c.source_ref:
                    table_name = c.source_ref.split("table:")[1]
                    if quality_map.get(table_name, True):
                        filtered.append(c)
                else:
                    filtered.append(c)

            all_concepts.extend(filtered)
            logger.info(f"  RDB extraction: {len(filtered)} concepts (from {len(rdb_concepts)} raw)")

        # 2B: Text concept extraction
        if stage1["docs_text"]:
            text_extractor = TextConceptExtractor(self.config, self.llm)
            text_concepts = text_extractor.extract(stage1["docs_text"])
            all_concepts.extend(text_concepts)
            logger.info(f"  Text extraction: {len(text_concepts)} concepts")

        logger.info(f"  Total before merge: {len(all_concepts)} concepts")

        # 2C: Four-step concept merge
        merger = ConceptMerger(self.config, self.llm)
        merged_concepts = merger.merge(all_concepts, domain=domain)
        logger.info(f"  After merge: {len(merged_concepts)} concepts")

        # 2D: Granularity decision
        decider = GranularityDecider(self.config)
        # Build taxonomy hints from config
        taxonomy_hints = {}
        for syn in domain_config.get("concept_synonyms", []):
            for alias in syn.get("aliases", []):
                taxonomy_hints[alias] = syn.get("standard", "")

        final_concepts = decider.decide(
            merged_concepts,
            taxonomy=taxonomy_hints,
            query_patterns=stage1["query_log"],
        )
        logger.info(f"  After granularity: {len(final_concepts)} concepts")

        # 2E: Layer classification (Category 2.1)
        layer_classifier = LayerClassifier(self.config, self.llm)
        layer_classifier.classify(final_concepts, stage1.get("parsed_tables", []), stage1.get("docs_text", ""))
        layer_counts = {}
        for c in final_concepts:
            layer_counts[c.layer.value] = layer_counts.get(c.layer.value, 0) + 1
        logger.info(f"  Layer classification: {layer_counts}")

        # 2F: Identity spec extraction (Category 2.4)
        id_extractor = IdentitySpecExtractor()
        id_extractor.extract(final_concepts, stage1.get("parsed_tables", []))
        id_count = sum(1 for c in final_concepts if c.identity_spec)
        logger.info(f"  Identity specs: {id_count}/{len(final_concepts)} concepts")

        return {
            "concepts": final_concepts,
            "merge_alias_map": merger.alias_map,
            "concept_count_before_merge": len(all_concepts),
        }

    # ============================================================
    # Stage 3: Taxonomy Construction
    # ============================================================

    def _run_stage3(self, stage2: dict, stage1: dict, domain_config: dict) -> dict:
        """Stage 3: Build concept hierarchy (taxonomy)."""
        logger.info("-" * 40)
        logger.info("Stage 3: Taxonomy Construction")
        logger.info("-" * 40)

        concepts = stage2["concepts"]

        # 3A: Hearst pattern matching (deterministic, from text)
        hearst_matcher = HearstPatternMatcher()
        hearst_relations = []
        if stage1["docs_text"]:
            hearst_relations = hearst_matcher.match(stage1["docs_text"])
            logger.info(f"  Hearst patterns: {len(hearst_relations)} is-a relations")

        # 3B: LLM taxonomy induction + instance-based hierarchy
        inducer = TaxonomyInducer(self.config, self.llm)
        taxonomy = inducer.induce(concepts)

        # 3C: Add Hearst pattern results to taxonomy
        if hearst_relations:
            name_to_id = {}
            for c in concepts:
                name_to_id[c.name] = c.id
                for alias in c.aliases:
                    name_to_id[alias] = c.id

            added = 0
            for child_name, parent_name, conf in hearst_relations:
                child_id = name_to_id.get(child_name)
                parent_id = name_to_id.get(parent_name)
                if child_id and parent_id and child_id != parent_id:
                    if child_id in taxonomy.nodes and parent_id in taxonomy.nodes:
                        node = taxonomy.nodes[child_id]
                        if node.parent_id is None:  # Only set if not already assigned
                            node.parent_id = parent_id
                            node.confidence = conf
                            node.reason = "Hearst pattern match"
                            parent_node = taxonomy.nodes[parent_id]
                            if child_id not in parent_node.children_ids:
                                parent_node.children_ids.append(child_id)
                            if child_id in taxonomy.root_ids:
                                taxonomy.root_ids.remove(child_id)
                            added += 1
            if added:
                logger.info(f"  Added {added} Hearst-based hierarchy edges")

        logger.info(f"  Taxonomy: {len(taxonomy.nodes)} nodes, {len(taxonomy.root_ids)} roots")

        return {"taxonomy": taxonomy}

    # ============================================================
    # Stage 4: Relation/Property Construction
    # ============================================================

    def _run_stage4(self, stage1: dict, stage2: dict, domain_config: dict) -> dict:
        """Stage 4: Extract properties and relations."""
        logger.info("-" * 40)
        logger.info("Stage 4: Relation/Property Construction")
        logger.info("-" * 40)

        concepts = stage2["concepts"]
        ddl_text = stage1["ddl_text"]

        # Build concept map: {table_name: concept_id}
        concept_map = {}
        for c in concepts:
            if c.name_en:
                concept_map[c.name_en] = c.id
            concept_map[c.name] = c.id

        all_properties: list[Property] = []
        all_relations: list[Relation] = []

        # 4A: Extract properties from DDL
        if ddl_text:
            rdb_extractor = RDBConceptExtractor(self.config, self.llm)
            rdb_properties = rdb_extractor.extract_properties_from_ddl(ddl_text, concept_map)
            all_properties.extend(rdb_properties)
            logger.info(f"  DDL properties: {len(rdb_properties)}")

        # 4B: Extract relations from DDL (with FK filtering)
        if ddl_text:
            rel_extractor = RelationExtractor(self.config, self.llm)
            ddl_result = rel_extractor.extract_from_ddl(
                ddl_text,
                concept_map,
                table_tags=stage1.get("system_table_tags", {}),
                query_log=stage1.get("query_log", []),
                business_terms=stage1.get("business_terms", []),
            )
            all_relations.extend(ddl_result["relations"])
            all_properties.extend(ddl_result.get("properties", []))
            logger.info(f"  DDL relations: {len(ddl_result['relations'])}")

        # 4C: Extract relations from text (LLM)
        if stage1["docs_text"] and self.config.llm_available:
            rel_extractor = RelationExtractor(self.config, self.llm)
            text_result = rel_extractor.extract_from_text(stage1["docs_text"], concepts)
            all_relations.extend(text_result["relations"])
            all_properties.extend(text_result.get("properties", []))
            logger.info(f"  Text relations: {len(text_result['relations'])}")

        # 4D: M:N reification
        m2m_reifier = M2MReifier()
        reified_relations, new_concepts = m2m_reifier.reify_all(all_relations, concepts)
        all_relations = reified_relations
        if new_concepts:
            logger.info(f"  Reified: {len(new_concepts)} intermediate concepts created")

        # 4E: Relation normalization (using config synonyms)
        relation_synonyms = domain_config.get("relation_synonyms", [])
        normalizer = RelationNormalizer(synonym_table=relation_synonyms)
        normalized_relations = normalizer.normalize(all_relations)
        all_relations = normalized_relations
        logger.info(f"  After normalization: {len(all_relations)} relations")

        # 4F: Derivation extraction (Category 2.2)
        deriv_extractor = DerivationExtractor(self.config, self.llm)
        deriv_extractor.extract_from_text(stage1["docs_text"], all_properties, concepts)
        if hasattr(deriv_extractor, "extract_from_sql"):
            deriv_extractor.extract_from_sql(stage1.get("query_log", []), all_properties)
        derived_count = sum(1 for p in all_properties if p.is_derived)
        logger.info(f"  Derivation: {derived_count} derived properties")

        # 4G: Validation rule extraction (Category 2.5)
        val_extractor = ValidationRuleExtractor(self.config, self.llm)
        val_extractor.extract_from_ddl(stage1.get("parsed_tables", []), all_properties)
        val_extractor.extract_from_text(stage1["docs_text"], all_properties)
        val_count = sum(1 for p in all_properties if p.validation_regex or p.max_length or p.min_value is not None or p.max_value is not None)
        logger.info(f"  Validation rules: {val_count} properties with constraints")

        logger.info(f"  Total: {len(all_properties)} properties, {len(all_relations)} relations")

        return {
            "properties": all_properties,
            "relations": all_relations,
            "new_concepts": new_concepts,
        }

    # ============================================================
    # Stage 5: Axiom/Rule Layer
    # ============================================================

    def _run_stage5(
        self,
        stage2: dict,
        stage3: dict,
        stage4: dict,
        domain_config: dict,
        business_rules: list[str] | None,
    ) -> dict:
        """Stage 5: Generate axioms and rules."""
        logger.info("-" * 40)
        logger.info("Stage 5: Axiom/Rule Layer")
        logger.info("-" * 40)

        concepts = stage2["concepts"]
        relations = stage4["relations"]
        taxonomy = stage3["taxonomy"]
        all_axioms: list[Axiom] = []
        all_rules: list[Rule] = []

        # 5A: Taxonomy -> subClassOf axioms (deterministic)
        axiom_generator = AxiomGenerator(self.config, self.llm)
        taxonomy_nodes_dict = {
            node.concept_id: node for node in taxonomy.nodes.values()
        }
        subclass_axioms = axiom_generator.generate_from_taxonomy(taxonomy_nodes_dict)
        all_axioms.extend(subclass_axioms)
        logger.info(f"  Taxonomy -> axioms: {len(subclass_axioms)} subClassOf")

        # 5B: LLM-driven axiom generation
        domain_description = domain_config.get("domain", "")
        if self.config.llm_available:
            llm_axioms = axiom_generator.generate(domain_description, concepts, relations)
            all_axioms.extend(llm_axioms)
            logger.info(f"  LLM axioms: {len(llm_axioms)}")

        # 5C: Axiom risk classification
        classifier = AxiomRiskClassifier(self.config)
        classification = classifier.classify_batch(all_axioms)
        # Only keep auto-adopted + needs_review (reject < 0.7 confidence)
        all_axioms = classification["auto_adopted"] + classification["needs_review"]
        logger.info(f"  Axiom classification: {len(classification['auto_adopted'])} auto, "
                     f"{len(classification['needs_review'])} review, "
                     f"{len(classification['rejected'])} rejected")

        # 5D: NL2SWRL (if business rules provided)
        if business_rules:
            # Build a partial Ontology for NL2SWRL binding
            from .models import Ontology
            partial_ontology = Ontology(
                domain=domain_config.get("domain", "unknown"),
                entity_types=concepts,
                properties=stage4["properties"],
                relations=relations,
            )
            nl2swrl = NL2SWRL(self.config, self.llm)
            for i, nl_rule in enumerate(business_rules):
                logger.info(f"  NL2SWRL rule {i+1}/{len(business_rules)}: {nl_rule[:60]}...")
                rule = nl2swrl.convert(nl_rule, partial_ontology)
                if rule and rule.name != "failed":
                    all_rules.append(rule)
                    logger.info(f"    -> Rule '{rule.name}' (validated={rule.validated})")
                else:
                    logger.warning(f"    -> Rule generation failed")

        logger.info(f"  Total: {len(all_axioms)} axioms, {len(all_rules)} rules")

        return {
            "axioms": all_axioms,
            "rules": all_rules,
            "axiom_classification": classification,
        }

    # ============================================================
    # Stage 6: Semantic Enrichment
    # ============================================================

    def _run_stage6(
        self,
        stage1: dict,
        stage2: dict,
        stage4: dict,
        stage5: dict,
        domain_config: dict,
    ) -> dict:
        """Stage 6: Glossary, annotations, triggers, governance."""
        logger.info("-" * 40)
        logger.info("Stage 6: Semantic Enrichment")
        logger.info("-" * 40)

        concepts = stage2["concepts"]
        properties = stage4["properties"]
        relations = stage4["relations"]
        docs_text = stage1["docs_text"]

        # 6A: Build glossary (Category 3.1/3.2)
        glossary_builder = GlossaryBuilder(self.config, self.llm)
        glossary = glossary_builder.build(concepts, domain_config, docs_text)
        logger.info(f"  Glossary: {len(glossary)} terms")

        # 6B: External mappings (Category 3.3)
        mapping_extractor = ExternalMappingExtractor(self.config, self.llm)
        external_mappings = mapping_extractor.extract_from_config(domain_config, glossary)
        if docs_text:
            external_mappings.extend(mapping_extractor.extract_from_text(docs_text, glossary))
        logger.info(f"  External mappings: {len(external_mappings)}")

        # 6C: Semantic annotations (Category 2.6)
        annotation_extractor = AnnotationExtractor(self.config, self.llm)
        annotations = annotation_extractor.extract(
            docs_text, concepts, properties,
            parsed_tables=stage1.get("parsed_tables"),
        )
        logger.info(f"  Annotations: {len(annotations)}")

        # 6D: Trigger rules (Category 4.1)
        trigger_extractor = TriggerRuleExtractor(self.config, self.llm)
        trigger_rules = trigger_extractor.extract_from_text(docs_text, concepts)
        # Convert applicable SWRL rules to triggers
        swrl_rules = stage5.get("rules", [])
        if swrl_rules:
            trigger_rules.extend(trigger_extractor.convert_from_rules(swrl_rules))
        logger.info(f"  Trigger rules: {len(trigger_rules)}")

        # 6E: Governance rules (Category 2.7)
        governance_rules = []
        if self.config.governance_auto_generate:
            gov_generator = GovernanceRuleGenerator(self.config)
            governance_rules = gov_generator.generate(
                concepts, properties, relations, domain_config
            )
        logger.info(f"  Governance rules: {len(governance_rules)}")

        return {
            "glossary": glossary,
            "external_mappings": external_mappings,
            "annotations": annotations,
            "trigger_rules": trigger_rules,
            "governance_rules": governance_rules,
        }

    # ============================================================
    # Stage 7: Process & Permission
    # ============================================================

    def _run_stage7(
        self,
        stage1: dict,
        stage2: dict,
        stage4: dict,
        domain_config: dict,
        trigger_rules: list,
    ) -> dict:
        """Stage 7: Operations, compositions, permissions, query patterns."""
        logger.info("-" * 40)
        logger.info("Stage 7: Process & Permission")
        logger.info("-" * 40)

        concepts = stage2["concepts"]
        properties = stage4["properties"]
        relations = stage4["relations"]
        docs_text = stage1["docs_text"]
        query_log = stage1.get("query_log", [])

        # 7A: Atomic operations (Category 5.1-5.3)
        op_extractor = OperationExtractor(self.config, self.llm)
        operations = op_extractor.extract(docs_text, concepts, relations)
        if query_log:
            operations.extend(op_extractor.extract_from_query_log(query_log, concepts))
        logger.info(f"  Operations: {len(operations)}")

        # 7B: Service composition (Category 5.4-5.5)
        composer = ServiceComposer(self.config, self.llm)
        compositions = composer.compose_simple(operations, docs_text)
        compositions.extend(composer.compose_complex(operations, docs_text, trigger_rules))
        logger.info(f"  Compositions: {len(compositions)}")

        # 7C: Permission extraction (Category 6)
        perm_extractor = PermissionExtractor(self.config, self.llm)
        permission_subjects = perm_extractor.extract_subjects(docs_text, concepts, domain_config)
        permission_rules = perm_extractor.extract_rules(docs_text, permission_subjects, concepts)
        logger.info(f"  Permissions: {len(permission_subjects)} subjects, {len(permission_rules)} rules")

        # 7D: Query pattern analysis (Category 7)
        query_patterns = []
        if query_log:
            analyzer = QueryPatternAnalyzer(self.config)
            query_patterns = analyzer.analyze(query_log, concepts, properties)
        logger.info(f"  Query patterns: {len(query_patterns)}")

        return {
            "operations": operations,
            "compositions": compositions,
            "permission_subjects": permission_subjects,
            "permission_rules": permission_rules,
            "query_patterns": query_patterns,
        }

    # ============================================================
    # Helpers
    # ============================================================

    def _load_config(self, config_file: str | None) -> dict:
        """Load YAML domain config."""
        if not config_file:
            return {}
        path = Path(config_file)
        if not path.exists():
            logger.warning(f"Config file not found: {config_file}")
            return {}
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}

    def _save_stage_reports(self, output_dir: str) -> None:
        """Save per-stage summary reports."""
        for stage_name, data in self.stage_results.items():
            # Convert non-serializable objects to summaries
            summary = self._make_serializable(data)
            save_json(summary, os.path.join(output_dir, f"{stage_name}_report.json"))

    @staticmethod
    def _make_serializable(data: dict) -> dict:
        """Convert pipeline data to JSON-serializable summary."""
        summary = {}
        for key, value in data.items():
            if isinstance(value, (str, int, float, bool, list, dict)):
                # Try to serialize; if it fails, convert to string
                try:
                    import json
                    json.dumps(value, ensure_ascii=False)
                    summary[key] = value
                except (TypeError, ValueError):
                    summary[key] = str(value)
            elif value is None:
                summary[key] = None
            else:
                summary[key] = str(value)
        return summary
