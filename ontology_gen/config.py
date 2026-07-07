"""Global configuration for ontology auto-generation pipeline."""
import os
from dataclasses import dataclass, field
from typing import Optional

from dotenv import load_dotenv

load_dotenv()


@dataclass
class Config:
    """Central configuration. All thresholds and API settings live here."""

    # --- LLM ---
    llm_base_url: str = field(default_factory=lambda: os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"))
    llm_api_key: str = field(default_factory=lambda: os.getenv("OPENAI_API_KEY", ""))
    llm_model: str = field(default_factory=lambda: os.getenv("OPENAI_MODEL", "gpt-4o"))
    llm_temperature: float = 0.1
    llm_max_tokens: int = 4096

    # --- Embedding ---
    embedding_model: str = field(default_factory=lambda: os.getenv("EMBEDDING_MODEL", "paraphrase-multilingual-MiniLM-L12-v2"))

    # --- Concept merge thresholds (Algorithm 2.3) ---
    merge_threshold_exact: float = 0.98
    merge_threshold_edit: float = 0.85
    merge_threshold_semantic: float = 0.85
    merge_threshold_llm: float = 0.75  # sim in [0.75, 0.85) -> needs LLM judge

    # --- Quality scoring (Algorithm 1.1) ---
    quality_min_score: int = 5
    semantic_coverage_min: float = 0.6

    # --- Null rate filtering (Algorithm 1.5) ---
    null_rate_ignore: float = 0.5   # > 50% null -> ignore field
    null_rate_warning: float = 0.3  # 30-50% -> low confidence

    # --- Sampling ---
    sample_non_null: int = 1000
    sample_null: int = 100

    # --- Domain/range inference (Algorithm 5.2-A) ---
    domain_range_auto_threshold: float = 0.95
    domain_range_review_threshold: float = 0.80

    # --- Axiom risk classification ---
    axiom_auto_adopt_low: float = 0.80   # low-risk > 0.80 -> auto adopt
    axiom_auto_adopt_medium: float = 0.90  # medium-risk > 0.90 -> auto adopt

    # --- Taxonomy ---
    max_taxonomy_depth: int = 4

    # --- SWRL ---
    swrl_max_fix_iterations: int = 3

    # --- Stage 6/7 feature flags ---
    enable_stage6: bool = True
    enable_stage7: bool = True

    # --- Glossary (Category 3) ---
    glossary_min_frequency: int = 2

    # --- Trigger rules (Category 4) ---
    trigger_confidence_threshold: float = 0.7

    # --- Query patterns (Category 7) ---
    query_pattern_min_frequency: int = 2

    # --- Governance (Category 2.7) ---
    governance_auto_generate: bool = True

    # --- Paths ---
    data_dir: str = "examples"
    output_dir: str = "output"

    @property
    def llm_available(self) -> bool:
        """Whether LLM API is configured."""
        return bool(self.llm_api_key and self.llm_api_key != "sk-your-key-here")
