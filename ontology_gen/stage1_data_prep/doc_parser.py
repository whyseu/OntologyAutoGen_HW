"""Algorithm 1.4: Document parsing.

Parses PDF, TXT, MD files into structured text for concept extraction.
Uses pdfplumber (already installed) for PDF, direct read for text files.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from ..config import Config
from ..utils import logger, chunk_text


class DocumentParser:
    """Parse documents into structured text for downstream processing."""

    def __init__(self, config: Config):
        self.config = config

    def parse(self, file_path: str) -> dict:
        """
        Parse a document file.

        Args:
            file_path: Path to .pdf, .txt, .md, or .html file

        Returns:
            {
                "text": str,              # Full text content
                "tables": list[list],     # Extracted tables (list of rows)
                "sections": list[dict],   # Section structure [{title, content}]
                "quality_check": dict,    # Quality check results
                "source": str,            # File path
            }
        """
        path = Path(file_path)
        if not path.exists():
            logger.warning(f"File not found: {file_path}")
            return {"text": "", "tables": [], "sections": [], "quality_check": {}, "source": file_path}

        suffix = path.suffix.lower()

        if suffix == ".pdf":
            return self._parse_pdf(file_path)
        elif suffix in (".txt", ".md"):
            return self._parse_text(file_path)
        elif suffix == ".html":
            return self._parse_html(file_path)
        else:
            logger.warning(f"Unsupported file type: {suffix}")
            return {"text": "", "tables": [], "sections": [], "quality_check": {}, "source": file_path}

    def _parse_text(self, file_path: str) -> dict:
        """Parse plain text or markdown file."""
        with open(file_path, "r", encoding="utf-8") as f:
            text = f.read()

        sections = self._extract_sections(text)
        has_structure = len(sections) > 1

        return {
            "text": text,
            "tables": [],
            "sections": sections,
            "quality_check": self._quality_check(text, has_structure, []),
            "source": file_path,
        }

    def _parse_pdf(self, file_path: str) -> dict:
        """Parse PDF using pdfplumber (already installed)."""
        try:
            import pdfplumber
        except ImportError:
            logger.error("pdfplumber not installed. Falling back to PyPDF2.")
            return self._parse_pdf_fallback(file_path)

        text_parts = []
        tables = []

        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text() or ""
                text_parts.append(page_text)

                # Extract tables
                page_tables = page.extract_tables()
                if page_tables:
                    tables.extend(page_tables)

        text = "\n\n".join(text_parts)
        sections = self._extract_sections(text)
        has_structure = len(sections) > 1

        return {
            "text": text,
            "tables": tables,
            "sections": sections,
            "quality_check": self._quality_check(text, has_structure, tables),
            "source": file_path,
        }

    def _parse_pdf_fallback(self, file_path: str) -> dict:
        """Fallback PDF parsing using PyPDF2."""
        try:
            from PyPDF2 import PdfReader
            reader = PdfReader(file_path)
            text = "\n\n".join(page.extract_text() or "" for page in reader.pages)
        except Exception as e:
            logger.error(f"PDF parsing failed: {e}")
            text = ""

        return {
            "text": text,
            "tables": [],
            "sections": self._extract_sections(text),
            "quality_check": self._quality_check(text, False, []),
            "source": file_path,
        }

    def _parse_html(self, file_path: str) -> dict:
        """Parse HTML file, extracting text content."""
        try:
            from lxml import html as lxml_html
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
            tree = lxml_html.fromstring(content)
            text = tree.text_content().strip()
        except Exception as e:
            logger.error(f"HTML parsing failed: {e}")
            text = ""

        return {
            "text": text,
            "tables": [],
            "sections": self._extract_sections(text),
            "quality_check": self._quality_check(text, False, []),
            "source": file_path,
        }

    @staticmethod
    def _extract_sections(text: str) -> list[dict]:
        """Extract section structure from markdown/text."""
        sections = []
        # Match markdown headings
        heading_pattern = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)

        matches = list(heading_pattern.finditer(text))
        if not matches:
            return [{"title": "", "content": text}]

        for i, match in enumerate(matches):
            level = len(match.group(1))
            title = match.group(2).strip()
            start = match.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            content = text[start:end].strip()
            sections.append({"title": title, "level": level, "content": content})

        return sections

    @staticmethod
    def _quality_check(text: str, has_structure: bool, tables: list) -> dict:
        """Run quality checks on parsed document."""
        checks = {}

        # Check 1: Text length
        checks["text_length"] = len(text)
        checks["has_sufficient_content"] = len(text) > 100

        # Check 2: Structure
        checks["has_structure"] = has_structure

        # Check 3: Tables preserved
        checks["table_count"] = len(tables)

        # Check 4: No obvious garbled text (high ratio of non-printable chars)
        if text:
            printable_ratio = sum(1 for c in text if c.isprintable() or c.isspace()) / len(text)
            checks["printable_ratio"] = printable_ratio
            checks["is_clean"] = printable_ratio > 0.95
        else:
            checks["printable_ratio"] = 0
            checks["is_clean"] = False

        return checks

    def get_chunks(self, file_path: str, strategy: str = "auto") -> list[str]:
        """Parse document and return text chunks for concept extraction."""
        parsed = self.parse(file_path)
        return chunk_text(parsed["text"], strategy=strategy)
