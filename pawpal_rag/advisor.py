from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

from .prompts import SUGGEST_TOOL, SYSTEM_PROMPT, build_user_message
from .retriever import retrieve

load_dotenv()

logger = logging.getLogger("pawpal_rag.advisor")

_MODEL = "claude-haiku-4-5"
_MAX_TOKENS = 1024
_VALID_PRIORITIES = {"low", "medium", "high"}
_VALID_FREQUENCIES = {"once", "daily", "weekly", "monthly"}


@dataclass
class SuggestedDefaults:
    duration_minutes: int
    priority: str
    frequency: str
    rationale: str
    citations: list = field(default_factory=list)


def _validate(payload: dict) -> SuggestedDefaults | None:
    try:
        duration = int(payload["duration_minutes"])
        priority = str(payload["priority"]).lower()
        frequency = str(payload["frequency"]).lower()
        rationale = str(payload["rationale"])
        citations = list(payload.get("citations") or [])
    except (KeyError, TypeError, ValueError) as e:
        logger.warning("schema validation failed: missing/invalid field (%s)", e)
        return None

    if not (1 <= duration <= 240):
        logger.warning("schema validation failed: duration_minutes=%s out of range", duration)
        return None
    if priority not in _VALID_PRIORITIES:
        logger.warning("schema validation failed: priority=%r not in %s", priority, _VALID_PRIORITIES)
        return None
    if frequency not in _VALID_FREQUENCIES:
        logger.warning("schema validation failed: frequency=%r not in %s", frequency, _VALID_FREQUENCIES)
        return None
    if not citations:
        logger.warning("schema validation failed: no citations returned")
        return None

    return SuggestedDefaults(
        duration_minutes=duration,
        priority=priority,
        frequency=frequency,
        rationale=rationale,
        citations=citations,
    )


def _get_client():
    """Lazy import + construct so the package loads even without anthropic installed."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        logger.info("ANTHROPIC_API_KEY not set — AI suggestions disabled")
        return None
    try:
        import anthropic
    except ImportError:
        logger.warning("anthropic package not installed — pip install -r requirements.txt")
        return None
    return anthropic.Anthropic(api_key=api_key)


def suggest_task_defaults(pet, task_title: str) -> SuggestedDefaults | None:
    """Suggest duration/priority/frequency for a task on this pet, grounded in the corpus.

    Returns None on any failure (missing API key, network error, schema mismatch),
    so callers can fall back to existing defaults without crashing.
    """
    client = _get_client()
    if client is None:
        return None

    species = getattr(pet, "species", None)
    breed = getattr(pet, "breed", "") or ""
    query = f"{species or ''} {breed} {task_title}".strip()
    species_filter = (
        {"species": {"$in": [species, "any"]}} if species else None
    )

    logger.info(
        "suggest_task_defaults: pet=(species=%s, breed=%r, age=%s) title=%r",
        species, breed, getattr(pet, "age", None), task_title,
    )

    try:
        chunks = retrieve(query, k=5, where=species_filter)
        logger.info("retrieved %d chunks for query=%r", len(chunks), query)
    except Exception:
        logger.exception("retrieval failed; proceeding with empty context")
        chunks = []

    user_message = build_user_message(pet, task_title, chunks)

    try:
        response = client.messages.create(
            model=_MODEL,
            max_tokens=_MAX_TOKENS,
            system=[
                {
                    "type": "text",
                    "text": SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            tools=[SUGGEST_TOOL],
            tool_choice={"type": "tool", "name": "suggest_defaults"},
            messages=[{"role": "user", "content": user_message}],
        )
    except Exception:
        logger.exception("Anthropic API call failed")
        return None

    usage = getattr(response, "usage", None)
    if usage is not None:
        logger.info(
            "anthropic usage: input=%s cache_read=%s cache_creation=%s output=%s",
            getattr(usage, "input_tokens", None),
            getattr(usage, "cache_read_input_tokens", None),
            getattr(usage, "cache_creation_input_tokens", None),
            getattr(usage, "output_tokens", None),
        )

    for block in response.content:
        if getattr(block, "type", None) == "tool_use" and block.name == "suggest_defaults":
            result = _validate(block.input)
            if result is not None:
                logger.info(
                    "suggestion: duration=%s priority=%s frequency=%s",
                    result.duration_minutes, result.priority, result.frequency,
                )
            return result

    logger.warning("response contained no suggest_defaults tool_use block")
    return None
