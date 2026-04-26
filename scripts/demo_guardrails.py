"""Demonstrates PawPal++ guardrails and reliability mechanisms.

Shows what happens when the AI returns bad data — the schema gate
rejects it and the system falls back safely. No API key needed;
all examples use simulated payloads to exercise the real _validate()
and check_citation_grounding() functions.

Run:
    python scripts/demo_guardrails.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import logging

# Suppress internal logger warnings so demo output stays clean.
# The real app logs these for debugging; here we show the behavior directly.
logging.getLogger("pawpal_rag.advisor").setLevel(logging.CRITICAL)
logging.getLogger("pawpal_rag.judge").setLevel(logging.CRITICAL)

from pawpal_rag.advisor import _validate
from pawpal_rag.judge import check_citation_grounding, GroundingReport
from pawpal_rag.corpus import Chunk

SEPARATOR = "─" * 60
PASS = "✅"
REJECT = "🚫"


# ── Schema gate demos ───────────────────────────────────────────────

SCHEMA_CASES = [
    {
        "label": "Valid payload (baseline)",
        "payload": {
            "duration_minutes": 30,
            "priority": "high",
            "frequency": "daily",
            "rationale": "Adult dogs need 30+ min walks daily.",
            "citations": [{"source_name": "AKC", "snippet": "30-60 minutes daily"}],
        },
        "should_pass": True,
    },
    {
        "label": "Invalid priority — 'URGENT' not in {low, medium, high}",
        "payload": {
            "duration_minutes": 30,
            "priority": "URGENT",
            "frequency": "daily",
            "rationale": "Very important task.",
            "citations": [{"source_name": "AKC", "snippet": "..."}],
        },
        "should_pass": False,
    },
    {
        "label": "Out-of-range duration — 9999 minutes (max is 240)",
        "payload": {
            "duration_minutes": 9999,
            "priority": "high",
            "frequency": "daily",
            "rationale": "Very long walk.",
            "citations": [{"source_name": "AKC", "snippet": "..."}],
        },
        "should_pass": False,
    },
    {
        "label": "Zero duration — below minimum of 1",
        "payload": {
            "duration_minutes": 0,
            "priority": "medium",
            "frequency": "weekly",
            "rationale": "Instant task.",
            "citations": [{"source_name": "Source", "snippet": "..."}],
        },
        "should_pass": False,
    },
    {
        "label": "Missing citations — empty list",
        "payload": {
            "duration_minutes": 15,
            "priority": "high",
            "frequency": "daily",
            "rationale": "No evidence provided.",
            "citations": [],
        },
        "should_pass": False,
    },
    {
        "label": "Invalid frequency — 'biweekly' not in {once, daily, weekly, monthly}",
        "payload": {
            "duration_minutes": 20,
            "priority": "medium",
            "frequency": "biweekly",
            "rationale": "Every two weeks.",
            "citations": [{"source_name": "Vet guide", "snippet": "..."}],
        },
        "should_pass": False,
    },
    {
        "label": "Missing required field — no 'rationale' key",
        "payload": {
            "duration_minutes": 30,
            "priority": "high",
            "frequency": "daily",
            "citations": [{"source_name": "AKC", "snippet": "..."}],
        },
        "should_pass": False,
    },
]


# ── Citation grounding demos ────────────────────────────────────────

CORPUS_CHUNKS = [
    Chunk(
        text="Active medium-energy breeds (Labrador Retriever, Golden Retriever, "
             "Shiba Inu, Beagle, Boxer) need 45-60 minutes of daily exercise. "
             "Two 30-minute walks (morning + evening) is a reliable default.",
        metadata={"source_name": "AKC exercise guide", "species": "dog"},
    ),
    Chunk(
        text="Short-haired cats benefit from brushing 1-2 times per week to "
             "reduce shed and hairballs. Each session takes 5-10 minutes.",
        metadata={"source_name": "AAFP grooming guide", "species": "cat"},
    ),
]


class FakeSuggestion:
    """Mimics SuggestedDefaults for grounding demos."""
    def __init__(self, citations):
        self.duration_minutes = 30
        self.priority = "high"
        self.frequency = "daily"
        self.rationale = "..."
        self.citations = citations


GROUNDING_CASES = [
    {
        "label": "Grounded citation — snippet matches corpus verbatim",
        "citations": [
            {"source_name": "AKC exercise guide",
             "snippet": "Active medium-energy breeds (Labrador Retriever, Golden Retriever"},
        ],
        "expect_grounded": True,
    },
    {
        "label": "Fabricated citation — snippet not in any corpus chunk",
        "citations": [
            {"source_name": "Made-up Source",
             "snippet": "Dogs should swim for 2 hours every day in a heated pool"},
        ],
        "expect_grounded": False,
    },
    {
        "label": "Mixed — one grounded, one fabricated",
        "citations": [
            {"source_name": "AAFP grooming guide",
             "snippet": "Short-haired cats benefit from brushing 1-2 times per week"},
            {"source_name": "Unknown",
             "snippet": "Cats require daily ice baths for optimal health"},
        ],
        "expect_grounded": False,  # not ALL grounded
    },
    {
        "label": "Empty snippet — treated as ungrounded",
        "citations": [
            {"source_name": "Some Source", "snippet": ""},
        ],
        "expect_grounded": False,
    },
]


def run_schema_gate_demo():
    print()
    print("🛡️  GUARDRAIL 1: Schema Gate (_validate)")
    print("=" * 60)
    print()
    print("  The schema gate inspects every AI response before it reaches")
    print("  the UI. Bad values are rejected and the system returns None,")
    print("  keeping the app safe with manual defaults.")
    print()

    passed = 0
    rejected = 0

    for case in SCHEMA_CASES:
        result = _validate(case["payload"])
        accepted = result is not None
        icon = PASS if accepted else REJECT
        status = "ACCEPTED" if accepted else "REJECTED → None"

        print(f"  {icon} {case['label']}")
        print(f"     → {status}")

        if accepted:
            print(f"     Result: duration={result.duration_minutes}, "
                  f"priority={result.priority}, frequency={result.frequency}")
            passed += 1
        else:
            rejected += 1

        # Verify our expectation
        assert accepted == case["should_pass"], (
            f"Unexpected result for {case['label']}: "
            f"expected {'pass' if case['should_pass'] else 'reject'}"
        )
        print()

    print(f"  Summary: {passed} accepted, {rejected} rejected")
    print(f"  The {rejected} rejections prevented bad AI data from reaching")
    print(f"  the scheduler — the app stays functional with safe defaults.")
    print()


def run_grounding_demo():
    print()
    print("🔍  GUARDRAIL 2: Citation Grounding Check")
    print("=" * 60)
    print()
    print("  Verifies that citation snippets actually appear in the")
    print("  retrieved corpus chunks. Catches fabricated references")
    print("  without needing an LLM.")
    print()

    for case in GROUNDING_CASES:
        suggestion = FakeSuggestion(case["citations"])
        report = check_citation_grounding(suggestion, CORPUS_CHUNKS)

        all_ok = report.all_grounded
        icon = PASS if all_ok else REJECT
        rate = f"{report.grounding_rate:.0%}"

        print(f"  {icon} {case['label']}")
        print(f"     Grounding rate: {report.grounded_citations}/"
              f"{report.total_citations} ({rate})")

        if report.ungrounded_snippets:
            for s in report.ungrounded_snippets:
                print(f"     ⚠  Ungrounded: \"{s}\"")

        assert all_ok == case["expect_grounded"]
        print()

    print("  The grounding check runs at dev-time (in test_rag_quality.py)")
    print("  to ensure the advisor doesn't invent citation snippets.")
    print()


def run_error_handling_demo():
    print()
    print("🔌  GUARDRAIL 3: Graceful Error Handling")
    print("=" * 60)
    print()
    print("  The advisor never crashes the app. Every failure path")
    print("  returns None so the UI can show a warning and keep working.")
    print()

    from types import SimpleNamespace
    from unittest.mock import MagicMock, patch
    from pawpal_rag import advisor

    pet = SimpleNamespace(species="dog", breed="Lab", age=3, name="Test")

    # Case 1: No API key
    print(f"  {PASS} No API key set")
    with patch.object(advisor, "_get_client", return_value=None):
        result = advisor.suggest_task_defaults(pet, "Walk")
    print(f"     → Result: {result}")
    print(f"     App continues with manual defaults.")
    assert result is None
    print()

    # Case 2: API throws exception
    print(f"  {PASS} API call raises RuntimeError('network timeout')")
    fake_client = MagicMock()
    fake_client.messages.create.side_effect = RuntimeError("network timeout")
    with patch.object(advisor, "_get_client", return_value=fake_client), \
         patch.object(advisor, "retrieve", return_value=[]):
        result = advisor.suggest_task_defaults(pet, "Walk")
    print(f"     → Result: {result}")
    print(f"     Exception caught and logged. App continues.")
    assert result is None
    print()

    # Case 3: API returns unexpected response (no tool_use block)
    print(f"  {PASS} API returns text instead of tool_use block")
    fake_client = MagicMock()
    text_block = SimpleNamespace(type="text", text="I can't help with that.")
    fake_client.messages.create.return_value = SimpleNamespace(
        content=[text_block], usage=None
    )
    with patch.object(advisor, "_get_client", return_value=fake_client), \
         patch.object(advisor, "retrieve", return_value=[]):
        result = advisor.suggest_task_defaults(pet, "Walk")
    print(f"     → Result: {result}")
    print(f"     Missing tool_use block handled. App continues.")
    assert result is None
    print()

    print("  All 3 failure scenarios returned None without crashing.")
    print("  The Streamlit UI shows a warning and keeps the form usable.")
    print()


def main():
    print()
    print("🐾 PawPal++ Guardrails & Reliability Demo")
    print("━" * 60)
    print()
    print("This script demonstrates three layers of reliability")
    print("mechanisms that protect the app from bad AI output.")
    print("No API key required — all examples use simulated data.")

    run_schema_gate_demo()
    print(SEPARATOR)
    run_grounding_demo()
    print(SEPARATOR)
    run_error_handling_demo()

    print(SEPARATOR)
    print()
    print("✅ All guardrails demonstrated successfully.")
    print()
    print("For the fourth layer (LLM-as-judge eval with Sonnet 4.6),")
    print("run: pytest tests/test_rag_quality.py -v -m eval")
    print("(requires ANTHROPIC_API_KEY)")
    print()


if __name__ == "__main__":
    main()
