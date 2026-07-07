"""Ontology Auto-Generation Pipeline.

A modular Python implementation of automated ontology construction
from heterogeneous data sources (RDB, text, dialogue).

Usage:
    from ontology_gen.pipeline import OntologyPipeline
    from ontology_gen.config import Config

    pipeline = OntologyPipeline(Config())
    ontology = pipeline.run(data_dir="examples", output_dir="output")
"""
__version__ = "2.0.0"
