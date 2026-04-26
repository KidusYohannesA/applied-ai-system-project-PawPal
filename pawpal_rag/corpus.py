from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Chunk:
    text: str
    metadata: dict = field(default_factory=dict)
    score: float = 0.0


_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)
_H2_SPLIT_RE = re.compile(r"^## ", re.MULTILINE)
_MAX_CHUNK_CHARS = 800
_FALLBACK_WINDOW = 500
_FALLBACK_OVERLAP = 50


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    """Extract YAML-style frontmatter (key: value lines only)."""
    match = _FRONTMATTER_RE.match(text)
    if not match:
        return {}, text
    raw = match.group(1)
    body = text[match.end():]
    meta: dict = {}
    for line in raw.splitlines():
        if ":" not in line:
            continue
        k, _, v = line.partition(":")
        meta[k.strip()] = v.strip()
    return meta, body


def _window(text: str, size: int, overlap: int) -> list[str]:
    """Sliding window for sections that exceed the max chunk size."""
    if len(text) <= size:
        return [text]
    out = []
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        out.append(text[start:end])
        if end == len(text):
            break
        start = end - overlap
    return out


def chunk_markdown(text: str, source_file: str = "") -> list[Chunk]:
    """Split a single markdown document into chunks.

    Splits on `##` headings (one chunk per section). Sections longer than
    _MAX_CHUNK_CHARS are further split with a sliding window.
    """
    meta, body = _parse_frontmatter(text)
    base_meta = {**meta, "source_file": source_file}

    parts = _H2_SPLIT_RE.split(body)
    chunks: list[Chunk] = []
    # The first part (before any ##) is preamble — skip if blank.
    for i, part in enumerate(parts):
        section = part.strip()
        if not section:
            continue
        if i == 0 and not section.startswith("#"):
            heading = "(preamble)"
            section_text = section
        else:
            heading_line, _, rest = section.partition("\n")
            heading = heading_line.strip()
            section_text = f"## {section}".strip()

        for piece in _window(section_text, _MAX_CHUNK_CHARS, _FALLBACK_OVERLAP) if len(section_text) > _MAX_CHUNK_CHARS else [section_text]:
            chunks.append(Chunk(text=piece, metadata={**base_meta, "heading": heading}))
    return chunks


def load_corpus(root: Path) -> list[Chunk]:
    """Load and chunk every markdown file under root."""
    chunks: list[Chunk] = []
    for path in sorted(Path(root).rglob("*.md")):
        text = path.read_text(encoding="utf-8")
        rel = str(path.relative_to(root))
        chunks.extend(chunk_markdown(text, source_file=rel))
    return chunks
