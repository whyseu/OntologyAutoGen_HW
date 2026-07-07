#!/usr/bin/env python3
"""Full pipeline runner: execute the complete ontology auto-generation pipeline.

Usage:
    python scripts/run_full_pipeline.py [--data-dir examples] [--output-dir output]
                                        [--config examples/config/ecommerce.yaml]
                                        [--rules "rule1" "rule2"]

Examples:
    # Run with default e-commerce example data
    python scripts/run_full_pipeline.py

    # Run with custom data and config
    python scripts/run_full_pipeline.py \\
        --data-dir my_data \\
        --output-dir my_output \\
        --config my_config.yaml

    # Run with business rules for NL2SWRL
    python scripts/run_full_pipeline.py \\
        --rules "如果客户的累计消费金额超过10000元，则该客户为VIP客户" \\
                "如果订单状态为已支付且物流状态为已发货，则订单状态为已完成"
"""
from __future__ import annotations

import argparse
import sys
import os

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from ontology_gen.config import Config
from ontology_gen.pipeline import OntologyPipeline


def main():
    parser = argparse.ArgumentParser(
        description="Run the full ontology auto-generation pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--data-dir", default="examples",
        help="Directory containing DDL, docs, queries (default: examples)",
    )
    parser.add_argument(
        "--output-dir", default="output",
        help="Directory for output files (default: output)",
    )
    parser.add_argument(
        "--config", default=None,
        help="Path to YAML domain config file",
    )
    parser.add_argument(
        "--rules", nargs="*", default=None,
        help="Business rules (natural language) for NL2SWRL conversion",
    )
    parser.add_argument(
        "--no-stage6", action="store_true",
        help="Disable Stage 6 (Semantic Enrichment)",
    )
    parser.add_argument(
        "--no-stage7", action="store_true",
        help="Disable Stage 7 (Process & Permission)",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Enable verbose (DEBUG) logging",
    )

    args = parser.parse_args()

    # Configure logging
    import logging
    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    # Resolve paths relative to project root
    data_dir = os.path.join(project_root, args.data_dir) if not os.path.isabs(args.data_dir) else args.data_dir
    output_dir = os.path.join(project_root, args.output_dir) if not os.path.isabs(args.output_dir) else args.output_dir
    config_file = os.path.join(project_root, args.config) if args.config and not os.path.isabs(args.config) else args.config

    # Run pipeline
    config = Config()
    if args.no_stage6:
        config.enable_stage6 = False
    if args.no_stage7:
        config.enable_stage7 = False

    print()
    print("=" * 60)
    print("  Ontology Auto-Generation Pipeline")
    print("=" * 60)
    print(f"  LLM API:  {'configured' if config.llm_available else 'NOT configured (degraded mode)'}")
    if config.llm_available:
        print(f"  Model:    {config.llm_model}")
        print(f"  Base URL: {config.llm_base_url}")
    print(f"  Data:     {data_dir}")
    print(f"  Output:   {output_dir}")
    if config_file:
        print(f"  Config:   {config_file}")
    if args.rules:
        print(f"  Rules:    {len(args.rules)} business rules")
    print(f"  Stage 6:  {'enabled' if config.enable_stage6 else 'disabled'}")
    print(f"  Stage 7:  {'enabled' if config.enable_stage7 else 'disabled'}")
    print("=" * 60)
    print()

    pipeline = OntologyPipeline(config)
    ontology = pipeline.run(
        data_dir=data_dir,
        output_dir=output_dir,
        config_file=config_file,
        business_rules=args.rules,
    )

    # Print summary
    print()
    print("=" * 60)
    print("  Pipeline Result Summary")
    print("=" * 60)
    print(f"  Domain:        {ontology.domain}")
    print(f"  Entity types:  {len(ontology.entity_types)}")
    print(f"  Properties:    {len(ontology.properties)}")
    print(f"  Relations:     {len(ontology.relations)}")
    print(f"  Axioms:        {len(ontology.axioms)}")
    print(f"  Rules:         {len(ontology.rules)}")
    print(f"  Glossary:      {len(ontology.glossary)}")
    print(f"  Triggers:      {len(ontology.trigger_rules)}")
    print(f"  Operations:    {len(ontology.operations)}")
    print(f"  Permissions:   {len(ontology.permission_rules)}")
    print(f"  Query Patterns:{len(ontology.query_patterns)}")
    print(f"  Taxonomy:      {len(ontology.taxonomy.nodes)} nodes, {len(ontology.taxonomy.root_ids)} roots")

    errors = ontology.validate()
    print(f"  Validation:    {'PASS' if not errors else f'{len(errors)} errors'}")

    consistency = ontology.metadata.get("consistency_report", {})
    print(f"  Consistency:   {'PASS' if consistency.get('is_consistent', True) else 'FAIL'}")
    if consistency.get("violations"):
        print(f"    Violations:  {len(consistency['violations'])}")
    if consistency.get("warnings"):
        print(f"    Warnings:    {len(consistency['warnings'])}")

    print()
    print(f"  Output files:")
    print(f"    {output_dir}/ontology.json")
    print(f"    {output_dir}/consistency_report.json")
    for stage in ["stage1", "stage2", "stage3", "stage4", "stage5", "stage6", "stage7"]:
        print(f"    {output_dir}/{stage}_report.json")
    print("=" * 60)


if __name__ == "__main__":
    main()
