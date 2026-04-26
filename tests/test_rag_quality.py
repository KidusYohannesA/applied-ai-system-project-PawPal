"""LLM-as-judge quality eval for the RAG advisor.

These tests are SLOW and COST MONEY (~$0.005 per case via Sonnet 4.6 + Haiku 4.5).
They are gated behind `@pytest.mark.eval` and excluded from default test runs.

Run only when you want to verify advisor quality:

    pytest tests/test_rag_quality.py -v -m eval
"""
import os
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pawpal_rag import suggest_task_defaults, judge_suggestion, check_citation_grounding
from pawpal_rag.advisor import _MODEL as ADVISOR_MODEL
from pawpal_rag.retriever import retrieve


# ── Golden dataset ──────────────────────────────────────────────────
#
# Each case has expected RANGES rather than exact values — LLMs vary
# across runs. The eval passes when the actual suggestion is plausibly
# within the range AND the LLM judge approves.

GOLDEN_CASES = [
    {
        "name": "adult_shiba_walk",
        "pet": {"species": "dog", "breed": "Shiba Inu", "age": 3},
        "task_title": "Morning walk",
        "expected_duration_range": (20, 60),
        "expected_frequencies": {"daily"},
        "expected_priorities": {"medium", "high"},
    },
    {
        "name": "adult_lab_feeding",
        "pet": {"species": "dog", "breed": "Labrador Retriever", "age": 5},
        "task_title": "Feeding",
        "expected_duration_range": (5, 20),
        "expected_frequencies": {"daily"},
        "expected_priorities": {"high"},
    },
    {
        "name": "maine_coon_brushing",
        "pet": {"species": "cat", "breed": "Maine Coon", "age": 4},
        "task_title": "Brushing",
        "expected_duration_range": (5, 30),
        "expected_frequencies": {"daily", "weekly"},
        "expected_priorities": {"medium"},
    },
    {
        "name": "monthly_heartworm_dog",
        "pet": {"species": "dog", "breed": "Beagle", "age": 4},
        "task_title": "Heartworm prevention",
        "expected_duration_range": (1, 10),
        "expected_frequencies": {"monthly"},
        "expected_priorities": {"high"},
    },
    {
        "name": "annual_vet_checkup",
        "pet": {"species": "dog", "breed": "Boxer", "age": 5},
        "task_title": "Vet checkup",
        "expected_duration_range": (30, 90),
        "expected_frequencies": {"once"},
        "expected_priorities": {"high"},
    },
    {
        "name": "indoor_cat_play",
        "pet": {"species": "cat", "breed": "Domestic Shorthair", "age": 2},
        "task_title": "Play session",
        "expected_duration_range": (5, 30),
        "expected_frequencies": {"daily"},
        "expected_priorities": {"medium", "high"},
    },
    {
        "name": "frenchie_walk",
        "pet": {"species": "dog", "breed": "French Bulldog", "age": 2},
        "task_title": "Walk",
        "expected_duration_range": (10, 30),
        "expected_frequencies": {"daily"},
        "expected_priorities": {"medium", "high"},
    },
    {
        "name": "litter_box_scoop",
        "pet": {"species": "cat", "breed": "Domestic Shorthair", "age": 3},
        "task_title": "Scoop litter box",
        "expected_duration_range": (1, 10),
        "expected_frequencies": {"daily"},
        "expected_priorities": {"high"},
    },
]


# ── Pre-flight: skip the whole module if no API key ─────────────────


def _api_key_set():
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


pytestmark = [
    pytest.mark.eval,
    pytest.mark.skipif(not _api_key_set(), reason="ANTHROPIC_API_KEY not set"),
]


# ── Helpers ─────────────────────────────────────────────────────────


def _build_pet(spec: dict):
    return SimpleNamespace(
        name="EvalPet",
        species=spec["species"],
        breed=spec["breed"],
        age=spec["age"],
    )


def _retrieve_for(pet, task_title):
    """Mirror the advisor's retrieval so the judge sees the same chunks."""
    query = f"{pet.species or ''} {pet.breed or ''} {task_title}".strip()
    species_filter = (
        {"species": {"$in": [pet.species, "any"]}} if pet.species else None
    )
    try:
        return retrieve(query, k=5, where=species_filter)
    except Exception:
        return []


# ── Per-case eval (parametrized) ────────────────────────────────────


@pytest.mark.parametrize("case", GOLDEN_CASES, ids=lambda c: c["name"])
def test_golden_case_quality(case):
    """End-to-end eval per golden case: range checks + grounding + LLM judge."""
    pet = _build_pet(case["pet"])
    title = case["task_title"]

    # 1. Run the real advisor (Haiku 4.5 + retrieval)
    suggestion = suggest_task_defaults(pet, title)
    assert suggestion is not None, (
        f"advisor returned None for {case['name']} — schema validation failed "
        f"or API errored"
    )

    # 2. Range / enum checks (fail loudly, no LLM needed)
    lo, hi = case["expected_duration_range"]
    assert lo <= suggestion.duration_minutes <= hi, (
        f"{case['name']}: duration_minutes={suggestion.duration_minutes} "
        f"outside expected [{lo}, {hi}]"
    )
    assert suggestion.frequency in case["expected_frequencies"], (
        f"{case['name']}: frequency={suggestion.frequency!r} not in "
        f"{case['expected_frequencies']}"
    )
    assert suggestion.priority in case["expected_priorities"], (
        f"{case['name']}: priority={suggestion.priority!r} not in "
        f"{case['expected_priorities']}"
    )

    # 3. Programmatic citation grounding (no LLM)
    chunks = _retrieve_for(pet, title)
    grounding = check_citation_grounding(suggestion, chunks)
    assert grounding.total_citations >= 1, f"{case['name']}: zero citations returned"
    assert grounding.grounding_rate >= 0.5, (
        f"{case['name']}: only {grounding.grounded_citations}/"
        f"{grounding.total_citations} citations are grounded in the corpus. "
        f"Ungrounded snippets: {grounding.ungrounded_snippets}"
    )

    # 4. LLM-as-judge (Sonnet 4.6)
    verdict = judge_suggestion(pet, title, suggestion, chunks)
    assert verdict is not None, f"{case['name']}: judge returned None"
    assert verdict.overall_score >= 3, (
        f"{case['name']}: judge gave low score {verdict.overall_score}/5. "
        f"Notes: {verdict.notes}"
    )
    assert verdict.citations_grounded, (
        f"{case['name']}: judge says citations not grounded. Notes: {verdict.notes}"
    )
    assert verdict.rationale_consistent, (
        f"{case['name']}: rationale doesn't support the values. Notes: {verdict.notes}"
    )


# ── Aggregate sanity check ──────────────────────────────────────────


def test_advisor_uses_haiku_4_5():
    """Cheap model is what we ship for production cost reasons."""
    assert ADVISOR_MODEL == "claude-haiku-4-5"
