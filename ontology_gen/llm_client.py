"""OpenAI-compatible LLM client with embedding fallback."""
from __future__ import annotations

import json
import os
import re
import logging
from typing import Optional

import numpy as np

from .config import Config

logger = logging.getLogger("ontology_gen.llm")


class LLMClient:
    """Unified LLM client: chat completions + text embeddings.

    - chat() / chat_json(): OpenAI-compatible API
    - embed(): sentence-transformers local model (with TF-IDF fallback)
    - Degrades gracefully when API key is not configured.
    """

    def __init__(self, config: Config):
        self.config = config
        self._client = None
        self._embedder = None
        self._embedder_backend = None  # "st" | "tfidf" | "hash"

        if config.llm_available:
            try:
                from openai import OpenAI
                self._client = OpenAI(
                    base_url=config.llm_base_url,
                    api_key=config.llm_api_key,
                    timeout=float(os.getenv("LLM_TIMEOUT", "30")),
                    max_retries=int(os.getenv("LLM_MAX_RETRIES", "1")),
                )
                logger.info(f"LLM client initialized: {config.llm_base_url} / {config.llm_model}")
            except Exception as e:
                logger.warning(f"Failed to init OpenAI client: {e}")
        else:
            logger.warning("LLM API key not configured. LLM calls will return empty results (degraded mode).")

    # ============================================================
    # Chat completions
    # ============================================================

    def chat(self, messages: list[dict], **kwargs) -> str:
        """Call chat completion, return text."""
        if not self._client:
            return ""
        try:
            resp = self._client.chat.completions.create(
                model=kwargs.get("model", self.config.llm_model),
                messages=messages,
                temperature=kwargs.get("temperature", self.config.llm_temperature),
                max_tokens=kwargs.get("max_tokens", self.config.llm_max_tokens),
            )
            return resp.choices[0].message.content or ""
        except Exception as e:
            logger.error(f"LLM chat failed: {e}")
            return ""

    def chat_json(self, messages: list[dict], **kwargs) -> dict:
        """Call chat completion, parse JSON from response."""
        text = self.chat(messages, **kwargs)
        if not text:
            return {}
        return self._parse_json(text)

    @staticmethod
    def _parse_json(text: str) -> dict:
        """Extract JSON from text that may be wrapped in markdown code fences."""
        # Try direct parse first
        text = text.strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Try extracting from ```json ... ``` fences
        fence_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
        if fence_match:
            try:
                return json.loads(fence_match.group(1).strip())
            except json.JSONDecodeError:
                pass

        # Try finding the first { ... } block
        brace_match = re.search(r"\{.*\}", text, re.DOTALL)
        if brace_match:
            try:
                return json.loads(brace_match.group(0))
            except json.JSONDecodeError:
                pass

        logger.warning(f"Failed to parse JSON from LLM response: {text[:200]}...")
        return {}

    # ============================================================
    # Embeddings
    # ============================================================

    def embed(self, texts: list[str]) -> np.ndarray:
        """
        Get embedding vectors for a list of texts.
        Priority: sentence-transformers -> TF-IDF -> hash vectors.
        Returns: (N, D) numpy array.
        """
        if not texts:
            return np.array([])

        if self._embedder is None:
            self._init_embedder()

        if self._embedder_backend == "st":
            return self._embedder.encode(texts, convert_to_numpy=True)
        elif self._embedder_backend == "tfidf":
            return self._embedder.transform(texts).toarray()
        else:  # hash fallback
            return np.array([self._hash_embed(t) for t in texts])

    def embed_one(self, text: str) -> np.ndarray:
        """Get embedding for a single text."""
        return self.embed([text])[0]

    def _init_embedder(self):
        """Initialize embedding model with fallback chain."""
        # Try sentence-transformers
        try:
            from sentence_transformers import SentenceTransformer
            self._embedder = SentenceTransformer(self.config.embedding_model)
            self._embedder_backend = "st"
            logger.info(f"Embedding model loaded: {self.config.embedding_model}")
            return
        except Exception as e:
            logger.warning(f"sentence-transformers failed ({e}), trying TF-IDF fallback...")

        # Fallback: TF-IDF
        try:
            from sklearn.feature_extraction.text import TfidfVectorizer
            self._embedder = TfidfVectorizer(
                analyzer="char_wb",
                ngram_range=(1, 3),
                max_features=384,
            )
            # Need to fit on some dummy data to initialize vocabulary
            self._embedder.fit(["placeholder text for initialization"])
            self._embedder_backend = "tfidf"
            logger.info("Embedding fallback: TF-IDF (char-level)")
            return
        except ImportError:
            logger.warning("scikit-learn not available, using hash vectors")

        # Last resort: hash vectors
        self._embedder_backend = "hash"
        logger.info("Embedding fallback: hash vectors")

    @staticmethod
    def _hash_embed(text: str, dim: int = 384) -> np.ndarray:
        """Simple character-level hash embedding (deterministic but crude)."""
        vec = np.zeros(dim, dtype=np.float32)
        for i in range(len(text)):
            vec[hash(text[i:i+3]) % dim] += 1.0
        # Also hash bigrams
        for i in range(len(text) - 1):
            vec[hash(text[i:i+2]) % dim] += 0.5
        norm = np.linalg.norm(vec)
        return vec / norm if norm > 0 else vec

    # ============================================================
    # Cosine similarity helper
    # ============================================================

    @staticmethod
    def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
        """Compute cosine similarity between two vectors."""
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return float(np.dot(a, b) / (norm_a * norm_b))
