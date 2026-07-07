"""Utility functions: JSON I/O, text chunking, logging."""
import json
import re
import logging
from pathlib import Path
from typing import Any

# --- Logging ---

logger = logging.getLogger("ontology_gen")
if not logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    logger.addHandler(_handler)
    logger.setLevel(logging.INFO)


# --- JSON I/O ---

def save_json(data: Any, path: str) -> None:
    """Save data as JSON file."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    logger.info(f"Saved JSON: {path}")


def load_json(path: str) -> Any:
    """Load JSON file."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# --- Text chunking (for text concept extraction) ---

def chunk_by_sections(text: str) -> list[str]:
    """Chunk by markdown headings (#, ##, ###)."""
    sections = re.split(r"\n(?=#{1,6}\s)", text)
    return [s.strip() for s in sections if s.strip()]


def chunk_by_paragraphs(text: str) -> list[str]:
    """Chunk by double newlines."""
    return [p.strip() for p in text.split("\n\n") if p.strip()]


def chunk_by_fixed_window(text: str, window: int = 800, overlap: int = 200) -> list[str]:
    """Chunk by fixed character window with overlap."""
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + window, len(text))
        chunks.append(text[start:end])
        if end >= len(text):
            break
        start = end - overlap
    return chunks


def chunk_text(text: str, strategy: str = "auto",
               window: int = 800, overlap: int = 200) -> list[str]:
    """
    Chunk text using the best available strategy.
    Priority: sections > paragraphs > fixed window.
    """
    if strategy == "sections" or (strategy == "auto" and re.search(r"^#{1,6}\s", text, re.MULTILINE)):
        chunks = chunk_by_sections(text)
        if len(chunks) > 1:
            return chunks
    if strategy == "paragraphs" or strategy == "auto":
        chunks = chunk_by_paragraphs(text)
        if len(chunks) > 1:
            return chunks
    return chunk_by_fixed_window(text, window, overlap)


# --- DDL parsing ---

def parse_ddl(ddl_text: str) -> list[dict]:
    """
    Parse CREATE TABLE statements from DDL text.
    Returns list of {table_name, comment, columns, foreign_keys}.
    """
    tables = []

    # Step 1: Split DDL into individual CREATE TABLE statements
    # Each statement ends with ';' at the top level
    statements = _split_ddl_statements(ddl_text)

    for stmt in statements:
        stmt = stmt.strip()
        if not re.search(r"CREATE\s+TABLE", stmt, re.IGNORECASE):
            continue

        # Extract table name
        name_match = re.search(
            r"CREATE\s+TABLE\s+(?:`?(\w+)`?)", stmt, re.IGNORECASE
        )
        if not name_match:
            continue
        table_name = name_match.group(1)

        # Extract body (between first '(' and the matching last ')')
        # Find the first '(' after the table name
        paren_start = stmt.index("(", name_match.end())
        # Find the matching closing ')' by tracking depth
        depth = 0
        paren_end = -1
        for i in range(paren_start, len(stmt)):
            if stmt[i] == "(":
                depth += 1
            elif stmt[i] == ")":
                depth -= 1
                if depth == 0:
                    paren_end = i
                    break
        if paren_end == -1:
            continue

        body = stmt[paren_start + 1:paren_end]
        rest_after_body = stmt[paren_end + 1:].strip()

        # Extract table comment from the rest
        table_comment = ""
        comment_match = re.search(r"COMMENT\s*['\"](.*?)['\"]", rest_after_body, re.IGNORECASE)
        if comment_match:
            table_comment = comment_match.group(1)

        # Parse body into columns and foreign keys
        columns = []
        foreign_keys = []
        parts = _split_ddl_body(body)

        for part in parts:
            part = part.strip()
            if not part:
                continue

            # FOREIGN KEY
            fk_match = re.match(
                r"FOREIGN\s+KEY\s*\(\s*`?(\w+)`?\s*\)\s*REFERENCES\s+`?(\w+)`?\s*\(\s*`?(\w+)`?\s*\)",
                part, re.IGNORECASE
            )
            if fk_match:
                foreign_keys.append({
                    "fk_column": fk_match.group(1),
                    "ref_table": fk_match.group(2),
                    "ref_column": fk_match.group(3),
                })
                continue

            # PRIMARY KEY (standalone)
            if re.match(r"PRIMARY\s+KEY", part, re.IGNORECASE):
                continue

            # Column definition
            col_match = re.match(
                r"`?(\w+)`?\s+(\w+\s*(?:\([^)]*\))?)\s*(.*)",
                part, re.IGNORECASE
            )
            if col_match:
                col_name = col_match.group(1)
                col_type = col_match.group(2).strip()
                rest = col_match.group(3) or ""

                # Extract COMMENT
                comment_match = re.search(r"COMMENT\s*['\"](.*?)['\"]", rest, re.IGNORECASE)
                col_comment = comment_match.group(1) if comment_match else ""

                # Check for ENUM
                enum_match = re.search(r"ENUM\s*\((.*?)\)", col_type, re.IGNORECASE)
                enum_values = []
                if enum_match:
                    enum_values = [v.strip().strip("'\"") for v in enum_match.group(1).split(",")]

                columns.append({
                    "name": col_name,
                    "type": col_type,
                    "comment": col_comment,
                    "enum_values": enum_values,
                    "is_primary_key": bool(re.search(r"PRIMARY\s+KEY", rest, re.IGNORECASE)),
                })

        tables.append({
            "table_name": table_name,
            "comment": table_comment,
            "columns": columns,
            "foreign_keys": foreign_keys,
        })

    return tables


def _split_ddl_statements(ddl_text: str) -> list[str]:
    """Split DDL text into individual statements by semicolons at depth 0."""
    statements = []
    depth = 0
    in_quote = False
    quote_char = ""
    current = []

    for char in ddl_text:
        if not in_quote:
            if char in ("'", '"'):
                in_quote = True
                quote_char = char
            elif char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
            elif char == ";" and depth == 0:
                statements.append("".join(current))
                current = []
                continue
        else:
            if char == quote_char:
                in_quote = False
        current.append(char)

    if current:
        statements.append("".join(current))

    return statements


def _split_ddl_body(body: str) -> list[str]:
    """Split DDL body by commas, respecting parentheses depth."""
    parts = []
    depth = 0
    current = []
    for char in body:
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        if char == "," and depth == 0:
            parts.append("".join(current))
            current = []
        else:
            current.append(char)
    if current:
        parts.append("".join(current))
    return parts
