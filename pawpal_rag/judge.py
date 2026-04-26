"""LLM-as-judge quality eval for advisor suggestions.

Two layers:
1. Programmatic checks (no LLM) — citation grounding, schema sanity
2. LLM-as-judge — sensibility scoring with a stronger model (Sonnet 4.6)

Used by tests/test_rag_quality.py to verify advisor output quality. Not invoked
from the main app — purely a developer-time quality bar.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("pawpal_rag.judge")

_JUDGE_MODEL = "claude-sonnet-4-6"
_JUDGE_MAX_TOKENS = 1024


JUDGE_SYSTEM_PROMPT = """You are evaluating an AI-generated pet-care recommendation for accuracy
and groundedness. Another AI was given retrieved care guidance plus a pet's
profile (species, breed, age) and a task title, and asked to suggest sensible
defaults for duration, priority, and frequency.

Your job: judge whether the suggestion is reasonable, whether the citations are
plausibly grounded in the retrieved guidance, and whether the rationale supports
the chosen values. Be strict — a suggestion that contradicts the retrieved
guidance, ignores the pet's profile, or invents citation snippets that don't
appear in the corpus should score 1 or 2.

Always call the judge_verdict tool. Never respond with plain text."""


JUDGE_TOOL = {
    "name": "judge_verdict",
    "description": "Return a structured quality verdict for the advisor's suggestion.",
    "input_schema": {
        "type": "object",
        "properties": {
            "duration_appropriate": {
                "type": "boolean",
                "description": "Is the suggested duration reasonable for this pet+task?",
            },
            "priority_appropriate": {
                "type": "boolean",
                "description": "Is the priority level reasonable?",
            },
            "frequency_appropriate": {
                "type": "boolean",
                "description": "Is the frequency reasonable?",
            },
            "citations_grounded": {
                "type": "boolean",
                "description": "Do the citation snippets plausibly appear in the retrieved guidance?",
            },
            "rationale_consistent": {
                "type": "boolean",
                "description": "Does the rationale support the chosen values without contradicting them?",
            },
            "overall_score": {
                "type": "integer",
                "minimum": 1,
                "maximum": 5,
                "description": "1=very bad, 3=acceptable, 5=excellent",
            },
            "notes": {
                "type": "string",
                "description": "Brief reasons for any 'false' answers above.",
            },
        },
        "required": [
            "duration_appropriate",
            "priority_appropriate",
            "frequency_appropriate",
            "citations_grounded",
            "rationale_consistent",
            "overall_score",
            "notes",
        ],
        "additionalProperties": False,
    },
}


@dataclass
class JudgeVerdict:
    duration_appropriate: bool
    priority_appropriate: bool
    frequency_appropriate: bool
    citations_grounded: bool
    rationale_consistent: bool
    overall_score: int
    notes: str

    @property
    def all_appropriate(self) -> bool:
        return (
            self.duration_appropriate
            and self.priority_appropriate
            and self.frequency_appropriate
            and self.citations_grounded
            and self.rationale_consistent
        )


@dataclass
class GroundingReport:
    """Programmatic citation-grounding check (no LLM)."""

    total_citations: int
    grounded_citations: int
    ungrounded_snippets: list[str] = field(default_factory=list)

    @property
    def all_grounded(self) -> bool:
        return self.total_citations > 0 and self.grounded_citations == self.total_citations

    @property
    def grounding_rate(self) -> float:
        if self.total_citations == 0:
            return 0.0
        return self.grounded_citations / self.total_citations


def check_citation_grounding(
    suggestion, retrieved_chunks, min_snippet_overlap: int = 20
) -> GroundingReport:
    """Verify each citation snippet appears in the retrieved chunks.

    For each citation, check that at least the first `min_snippet_overlap`
    characters of the snippet appear verbatim in any retrieved chunk's text.
    This catches outright fabricated snippets without requiring full-string
    matches (LLMs often paraphrase or truncate).
    """
    corpus_text = " ".join(c.text for c in retrieved_chunks)
    grounded = 0
    ungrounded: list[str] = []

    for citation in suggestion.citations:
        snippet = (citation.get("snippet") or "").strip()
        if not snippet:
            ungrounded.append("(empty snippet)")
            continue
        probe = snippet[:min_snippet_overlap].strip()
        if probe and probe in corpus_text:
            grounded += 1
        else:
            ungrounded.append(snippet[:60])

    return GroundingReport(
        total_citations=len(suggestion.citations),
        grounded_citations=grounded,
        ungrounded_snippets=ungrounded,
    )


def _get_client():
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        logger.info("ANTHROPIC_API_KEY not set — judge unavailable")
        return None
    try:
        import anthropic
    except ImportError:
        logger.warning("anthropic package not installed")
        return None
    return anthropic.Anthropic(api_key=api_key)


def _validate_verdict(payload: dict) -> JudgeVerdict | None:
    try:
        score = int(payload["overall_score"])
        if not (1 <= score <= 5):
            logger.warning("judge returned out-of-range score=%s", score)
            return None
        return JudgeVerdict(
            duration_appropriate=bool(payload["duration_appropriate"]),
            priority_appropriate=bool(payload["priority_appropriate"]),
            frequency_appropriate=bool(payload["frequency_appropriate"]),
            citations_grounded=bool(payload["citations_grounded"]),
            rationale_consistent=bool(payload["rationale_consistent"]),
            overall_score=score,
            notes=str(payload.get("notes") or ""),
        )
    except (KeyError, TypeError, ValueError) as e:
        logger.warning("judge verdict failed schema validation: %s", e)
        return None


def judge_suggestion(pet, task_title, suggestion, retrieved_chunks) -> JudgeVerdict | None:
    """Ask Sonnet 4.6 to grade an advisor suggestion against the corpus.

    Returns None on any failure so callers can mark the case as
    inconclusive rather than crash.
    """
    client = _get_client()
    if client is None:
        return None

    chunk_block = "\n\n".join(
        f"[{i+1}] (source={c.metadata.get('source_name', '?')}) {c.text.strip()}"
        for i, c in enumerate(retrieved_chunks)
    ) or "(no chunks retrieved)"

    citations_block = "\n".join(
        f"  - {c.get('source_name', '?')}: \"{c.get('snippet', '')}\""
        for c in suggestion.citations
    ) or "(none)"

    user_message = (
        f"Pet: species={getattr(pet, 'species', '?')}, "
        f"breed={getattr(pet, 'breed', '') or 'unspecified'}, "
        f"age={getattr(pet, 'age', '?')}\n"
        f"Task title: {task_title!r}\n\n"
        f"Retrieved care guidance the advisor was given:\n{chunk_block}\n\n"
        f"Advisor's suggestion:\n"
        f"  duration_minutes: {suggestion.duration_minutes}\n"
        f"  priority: {suggestion.priority}\n"
        f"  frequency: {suggestion.frequency}\n"
        f"  rationale: {suggestion.rationale}\n"
        f"  citations:\n{citations_block}\n\n"
        f"Call judge_verdict with your assessment."
    )

    try:
        response = client.messages.create(
            model=_JUDGE_MODEL,
            max_tokens=_JUDGE_MAX_TOKENS,
            system=[
                {
                    "type": "text",
                    "text": JUDGE_SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            tools=[JUDGE_TOOL],
            tool_choice={"type": "tool", "name": "judge_verdict"},
            messages=[{"role": "user", "content": user_message}],
        )
    except Exception:
        logger.exception("judge API call failed")
        return None

    for block in response.content:
        if getattr(block, "type", None) == "tool_use" and block.name == "judge_verdict":
            verdict = _validate_verdict(block.input)
            if verdict is not None:
                logger.info(
                    "judge verdict: score=%s all_appropriate=%s notes=%r",
                    verdict.overall_score, verdict.all_appropriate, verdict.notes,
                )
            return verdict

    logger.warning("judge response had no judge_verdict tool_use block")
    return None
