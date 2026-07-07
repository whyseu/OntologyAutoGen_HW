#!/usr/bin/env python3
"""Single-stage runner: execute one stage of the pipeline independently.

Useful for debugging and incremental development.

Usage:
    python scripts/run_stage.py <stage> [options]

Stages:
    stage1  - Data preparation (quality scoring, DDL parsing)
    stage2  - Concept extraction (RDB + text + merge)
    stage3  - Taxonomy construction (Hearst + LLM + cycles)
    stage4  - Relation/property construction (FK filter + M:N + normalize)
    stage5  - Axiom/rule layer (domain/range + axioms + NL2SWRL)
    all     - Run all stages (equivalent to run_full_pipeline.py)

Examples:
    # Run only stage 1
    python scripts/run_stage.py stage1 --data-dir examples

    # Run stage 2 with verbose output
    python scripts/run_stage.py stage2 --data-dir examples -v
"""
from __future__ import annotations

import argparse
import json
import sys
import os

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from ontology_gen.config import Config
from ontology_gen.pipeline import OntologyPipeline


def main():
    parser = argparse.ArgumentParser(
        description="Run a single stage of the ontology pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "stage",
        choices=["stage1", "stage2", "stage3", "stage4", "stage5", "all"],
        help="Which stage to run",
    )
    parser.add_argument("--data-dir", default="examples", help="Data directory")
    parser.add_argument("--output-dir", default="output", help="Output directory")
    parser.add_argument("--config", default=None, help="YAML config file path")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose logging")

    args = parser.parse_args()

    import logging
    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    data_dir = os.path.join(project_root, args.data_dir) if not os.path.isabs(args.data_dir) else args.data_dir
    output_dir = os.path.join(project_root, args.output_dir) if not os.path.isabs(args.output_dir) else args.output_dir
    config_file = os.path.join(project_root, args.config) if args.config and not os.path.isabs(args.config) else args.config

    config = Config()
    pipeline = OntologyPipeline(config)

    if args.stage == "all":
        ontology = pipeline.run(
            data_dir=data_dir, output_dir=output_dir, config_file=config_file,
        )
        print(f"\nDone. Entity types: {len(ontology.entity_types)}, "
              f"Relations: {len(ontology.relations)}")
        return

    # Load domain config
    domain_config = pipeline._load_config(config_file)

    # Run stages up to the requested one (dependencies)
    print(f"\nRunning {args.stage}...")

    if args.stage == "stage1":
        result = pipeline._run_stage1(data_dir, domain_config)
        _print_stage1_summary(result)

    elif args.stage == "stage2":
        stage1 = pipeline._run_stage1(data_dir, domain_config)
        result = pipeline._run_stage2(stage1, domain_config, domain_config.get("domain", "unknown"))
        _print_stage2_summary(result)

    elif args.stage == "stage3":
        stage1 = pipeline._run_stage1(data_dir, domain_config)
        stage2 = pipeline._run_stage2(stage1, domain_config, domain_config.get("domain", "unknown"))
        result = pipeline._run_stage3(stage2, stage1, domain_config)
        _print_stage3_summary(result)

    elif args.stage == "stage4":
        stage1 = pipeline._run_stage1(data_dir, domain_config)
        stage2 = pipeline._run_stage2(stage1, domain_config, domain_config.get("domain", "unknown"))
        stage3 = pipeline._run_stage3(stage2, stage1, domain_config)
        result = pipeline._run_stage4(stage1, stage2, domain_config)
        _print_stage4_summary(result)

    elif args.stage == "stage5":
        stage1 = pipeline._run_stage1(data_dir, domain_config)
        stage2 = pipeline._run_stage2(stage1, domain_config, domain_config.get("domain", "unknown"))
        stage3 = pipeline._run_stage3(stage2, stage1, domain_config)
        stage4 = pipeline._run_stage4(stage1, stage2, domain_config)
        result = pipeline._run_stage5(stage2, stage3, stage4, domain_config, None)
        _print_stage5_summary(result)

    # Save the stage result
    os.makedirs(output_dir, exist_ok=True)
    summary = pipeline._make_serializable(result)
    save_path = os.path.join(output_dir, f"{args.stage}_report.json")
    from ontology_gen.utils import save_json
    save_json(summary, save_path)
    print(f"\nReport saved: {save_path}")


def _print_stage1_summary(result: dict):
    print("\n" + "=" * 50)
    print("  Stage 1: Data Preparation Summary")
    print("=" * 50)
    print(f"  Tables parsed:      {len(result.get('parsed_tables', []))}")
    print(f"  Quality scores:     {len(result.get('quality_scores', []))}")
    passed = sum(1 for s in result.get('quality_scores', []) if s.get('should_process'))
    print(f"  Tables passed:      {passed}")
    print(f"  Docs text length:   {len(result.get('docs_text', ''))} chars")
    print(f"  Query log entries:  {len(result.get('query_log', []))}")
    print(f"  Business terms:     {len(result.get('business_terms', []))}")
    print("=" * 50)


def _print_stage2_summary(result: dict):
    print("\n" + "=" * 50)
    print("  Stage 2: Concept Extraction Summary")
    print("=" * 50)
    print(f"  Concepts (before merge): {result.get('concept_count_before_merge', 0)}")
    print(f"  Concepts (after merge):  {len(result.get('concepts', []))}")
    print(f"  Alias mappings:          {len(result.get('merge_alias_map', {}))}")
    print("=" * 50)


def _print_stage3_summary(result: dict):
    tax = result.get("taxonomy")
    if tax:
        print("\n" + "=" * 50)
        print("  Stage 3: Taxonomy Construction Summary")
        print("=" * 50)
        print(f"  Taxonomy nodes:  {len(tax.nodes)}")
        print(f"  Root concepts:   {len(tax.root_ids)}")
        print(f"  Has cycle:       {tax.has_cycle()}")
        print("=" * 50)


def _print_stage4_summary(result: dict):
    print("\n" + "=" * 50)
    print("  Stage 4: Relation/Property Summary")
    print("=" * 50)
    print(f"  Properties:             {len(result.get('properties', []))}")
    print(f"  Relations:              {len(result.get('relations', []))}")
    print(f"  Reified concepts:       {len(result.get('new_concepts', []))}")
    print("=" * 50)


def _print_stage5_summary(result: dict):
    print("\n" + "=" * 50)
    print("  Stage 5: Axiom/Rule Summary")
    print("=" * 50)
    print(f"  Axioms:    {len(result.get('axioms', []))}")
    print(f"  Rules:     {len(result.get('rules', []))}")
    cls = result.get("axiom_classification", {})
    if cls:
        print(f"  Auto-adopted: {len(cls.get('auto_adopted', []))}")
        print(f"  Needs review: {len(cls.get('needs_review', []))}")
        print(f"  Rejected:     {len(cls.get('rejected', []))}")
    print("=" * 50)


if __name__ == "__main__":
    main()
