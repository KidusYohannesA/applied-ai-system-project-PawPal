from __future__ import annotations

from .corpus import Chunk
from .store import query


def retrieve(query_text: str, k: int = 5, where: dict | None = None) -> list[Chunk]:
    """Retrieve top-k chunks for the query, optionally filtered by metadata.

    `where` follows ChromaDB's filter syntax, e.g. {"species": "dog"}. To allow
    species-tagged docs plus species-agnostic docs, pass {"species": {"$in": [...]}}.
    """
    return query(query_text, k=k, where=where)
